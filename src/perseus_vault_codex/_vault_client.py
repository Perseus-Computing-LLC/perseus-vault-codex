"""Dependency-free JSON-RPC 2.0 stdio client for a local ``perseus-vault`` binary.

This is a trimmed, vendored copy of the official ``perseus-vault-client``
transport (https://github.com/Perseus-Computing-LLC/perseus-vault, MIT). It is
vendored — not pip-depended — so ``perseus-vault-codex`` installs with **zero
runtime dependencies** and a judge cloning the repo needs nothing but Python and
the ``perseus-vault`` binary on PATH.

The transport is the tricky, already-hardened part and is kept intact:

- **Reentrant lock.** ``initialize`` runs inside ``_request`` which itself needs
  the lock, so a non-reentrant lock would deadlock during the handshake.
- **Spawn under the lock.** Prevents a concurrent-startup race that would leak
  multiple child processes.
- **Deadline-bounded reads with teardown.** A plain ``readline()`` blocks forever
  if the child accepts stdin but never emits a newline. Reads happen on a daemon
  thread against a deadline; on timeout the child is terminated so a later call
  never races a still-blocked reader on a reused stdout.
- **Auto-respawn.** If the child has died, the next call starts a fresh one.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional

__all__ = ["VaultClient", "VaultError", "VaultTimeoutError"]

# MCP protocol version advertised in the handshake to the vault subprocess.
_PROTOCOL_VERSION = "2024-11-05"


class VaultError(RuntimeError):
    """A Perseus Vault MCP call returned an error or the transport failed."""


class VaultTimeoutError(VaultError, TimeoutError):
    """The vault process did not respond within the configured timeout."""


class VaultClient:
    """Client for a local ``perseus-vault serve`` MCP stdio server."""

    def __init__(
        self,
        binary: str,
        db_path: str,
        *,
        encryption_key: Optional[str] = None,
        llm_endpoint: Optional[str] = None,
        llm_api_key: Optional[str] = None,
        llm_model: Optional[str] = None,
        timeout: float = 45.0,
        env: Optional[Dict[str, str]] = None,
        tool_prefix: str = "perseus_vault",
    ):
        self._binary = binary
        self._db_path = db_path
        self._encryption_key = encryption_key
        self._llm_endpoint = llm_endpoint
        self._llm_api_key = llm_api_key
        self._llm_model = llm_model
        self._timeout = float(timeout)
        self._env = {**os.environ, **(env or {})}
        self._prefix = tool_prefix

        # Reentrant: _request recurses into _start -> _request during handshake.
        self._lock = threading.RLock()
        self._id = 0
        self._proc: Optional[subprocess.Popen] = None

    # -- lifecycle ----------------------------------------------------------

    def __enter__(self) -> "VaultClient":
        self._ensure_started()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def __del__(self):  # best-effort
        try:
            self.close()
        except Exception:
            pass

    def _ensure_started(self) -> None:
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                self._start()

    def _start(self) -> None:
        cmd = [self._binary, "serve", "--db", self._db_path]
        if self._encryption_key:
            cmd += ["--encryption-key", self._encryption_key]
        if self._llm_endpoint:
            cmd += ["--llm-endpoint", self._llm_endpoint]
        if self._llm_api_key:
            cmd += ["--llm-api-key", self._llm_api_key]
        if self._llm_model:
            cmd += ["--llm-model", self._llm_model]
        try:
            self._proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
                env=self._env,
            )
        except FileNotFoundError as exc:
            raise VaultError(
                f"Could not launch perseus-vault binary {self._binary!r}. "
                "Install the single static binary (no deps) from "
                "https://github.com/Perseus-Computing-LLC/perseus-vault and put "
                "it on PATH, or set PERSEUS_VAULT_BIN=/path/to/perseus-vault."
            ) from exc
        # Handshake.
        self._request(
            "initialize",
            {
                "protocolVersion": _PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "perseus-vault-codex", "version": "0.1.0"},
            },
        )
        self._notify("notifications/initialized", {})

    def _teardown(self) -> None:
        proc, self._proc = self._proc, None
        if proc and proc.poll() is None:
            try:
                if proc.stdin:
                    proc.stdin.close()
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    def close(self) -> None:
        with self._lock:
            self._teardown()

    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    # -- transport ----------------------------------------------------------

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def _readline_with_timeout(self, timeout: float) -> Optional[str]:
        assert self._proc and self._proc.stdout
        result: List[Optional[str]] = [None]

        def _read() -> None:
            try:
                result[0] = self._proc.stdout.readline()
            except Exception:
                result[0] = None

        t = threading.Thread(target=_read, daemon=True)
        t.start()
        t.join(timeout)
        if t.is_alive():
            return None
        return result[0]

    def _request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                self._start()
            rid = self._next_id()
            msg = {"jsonrpc": "2.0", "id": rid, "method": method, "params": params}
            assert self._proc and self._proc.stdin
            self._proc.stdin.write(json.dumps(msg) + "\n")
            self._proc.stdin.flush()
            deadline = time.time() + self._timeout
            while True:
                remaining = deadline - time.time()
                if remaining <= 0:
                    self._teardown()
                    raise VaultTimeoutError(
                        f"perseus-vault did not respond to {method} in {self._timeout}s"
                    )
                line = self._readline_with_timeout(remaining)
                if line is None:
                    self._teardown()
                    raise VaultTimeoutError(
                        f"perseus-vault did not respond to {method} in {self._timeout}s"
                    )
                if line == "":
                    # A live process can close stdout before it exits.  Do not
                    # retain that unusable process: the next call must be able
                    # to start a fresh vault instead of seeing EOF forever.
                    self._teardown()
                    raise VaultError("perseus-vault closed stdout unexpectedly")
                line = line.strip()
                if not line:
                    continue
                try:
                    resp = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if resp.get("id") == rid:
                    if resp.get("error"):
                        raise VaultError(f"perseus-vault error: {resp['error']}")
                    return resp.get("result", {})

    def _notify(self, method: str, params: Dict[str, Any]) -> None:
        with self._lock:
            assert self._proc and self._proc.stdin
            self._proc.stdin.write(
                json.dumps({"jsonrpc": "2.0", "method": method, "params": params}) + "\n"
            )
            self._proc.stdin.flush()

    # -- generic tool call --------------------------------------------------

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        """Invoke an MCP tool and return its unwrapped payload.

        Prefers ``structuredContent``; falls back to JSON-decoding the first
        text block; finally returns the raw string.
        """
        result = self._request("tools/call", {"name": name, "arguments": arguments})
        structured = result.get("structuredContent")
        if isinstance(structured, dict):
            return structured
        content = result.get("content", [])
        if not content:
            return result
        text = content[0].get("text", "") if isinstance(content[0], dict) else ""
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return text

    def list_tools(self) -> List[str]:
        result = self._request("tools/list", {})
        return [t["name"] for t in result.get("tools", [])]

    def tool(self, short: str) -> str:
        return f"{self._prefix}_{short}"
