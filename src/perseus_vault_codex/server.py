"""The Perseus Vault Codex MCP server.

A dependency-free MCP stdio server that Codex connects to. It speaks JSON-RPC
2.0 over newline-delimited stdin/stdout (the MCP stdio transport) and forwards
the five curated memory tools to a ``perseus-vault serve`` subprocess.

    Codex agent  ── MCP stdio ──▶  this server  ── MCP stdio ──▶  perseus-vault
       (GPT-5.6)                   (5 curated tools)              (55+ tools, encrypted)

Design notes
------------
* **stdout is sacred.** Only JSON-RPC responses go to stdout; all logging goes to
  stderr. A stray print to stdout corrupts the protocol.
* **Lazy vault start.** The vault subprocess is spawned on the first tool call,
  not at import, so ``tools/list`` (which Codex calls during startup) is instant
  and never blocks on a missing binary.
* **Errors are JSON-RPC errors,** never crashes: a failing tool returns an error
  object so the Codex session stays alive.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, Optional

from . import __version__
from ._vault_client import VaultClient, VaultError
from .config import VaultConfig, load_config
from .tools import TOOL_SCHEMAS, Tools

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "perseus-vault-codex"

# JSON-RPC error codes (subset of the spec we use).
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INTERNAL_ERROR = -32603


def _log(msg: str) -> None:
    print(f"[{SERVER_NAME}] {msg}", file=sys.stderr, flush=True)


class CodexMemoryServer:
    """Owns the stdio loop, the vault subprocess, and the tool dispatch."""

    def __init__(self, config: Optional[VaultConfig] = None) -> None:
        self._cfg = config or load_config()
        self._client: Optional[VaultClient] = None
        self._tools: Optional[Tools] = None

    # -- lazy vault wiring --------------------------------------------------

    def _ensure_vault(self) -> Tools:
        if self._tools is None:
            self._client = VaultClient(
                binary=self._cfg.binary,
                db_path=self._cfg.db_path,
                encryption_key=self._cfg.encryption_key,
                llm_endpoint=self._cfg.llm_endpoint,
                llm_api_key=self._cfg.llm_api_key,
                llm_model=self._cfg.llm_model,
            )
            self._tools = Tools(self._client, self._cfg)
            _log(
                f"vault ready — db={self._cfg.db_path} "
                f"encrypted={self._cfg.encrypted} reflect={self._cfg.reflect_enabled}"
            )
        return self._tools

    def close(self) -> None:
        if self._client is not None:
            self._client.close()

    # -- request handling ---------------------------------------------------

    def handle(self, req: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle one JSON-RPC request. Returns a response dict, or ``None`` for
        notifications (which take no reply)."""
        method = req.get("method")
        rid = req.get("id")
        params = req.get("params") or {}

        # Notifications have no id and expect no response.
        is_notification = "id" not in req

        try:
            if method == "initialize":
                return _ok(rid, self._initialize())
            if method == "notifications/initialized":
                return None
            if method == "ping":
                return _ok(rid, {})
            if method == "tools/list":
                return _ok(rid, {"tools": TOOL_SCHEMAS})
            if method == "tools/call":
                return _ok(rid, self._call_tool(params))
            if is_notification:
                return None
            return _err(rid, METHOD_NOT_FOUND, f"Method not found: {method}")
        except VaultError as exc:
            _log(f"vault error on {method}: {exc}")
            return _err(rid, INTERNAL_ERROR, str(exc))
        except Exception as exc:  # never let one bad call kill the session
            _log(f"unexpected error on {method}: {exc!r}")
            return _err(rid, INTERNAL_ERROR, f"{type(exc).__name__}: {exc}")

    def _initialize(self) -> Dict[str, Any]:
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": __version__},
            "instructions": (
                "Persistent encrypted memory for this Codex agent. Recall project "
                "context at the start of a task; remember durable facts, decisions, "
                "and conventions as you learn them; reflect to synthesize insights."
            ),
        }

    def _call_tool(self, params: Dict[str, Any]) -> Dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        tools = self._ensure_vault()
        handler = tools.handler_for(name)
        result = handler(arguments)
        text = json.dumps(result, indent=2, ensure_ascii=False)
        # Return both the human/agent-readable text block and structured content.
        return {
            "content": [{"type": "text", "text": text}],
            "structuredContent": result,
            "isError": False,
        }

    # -- main loop ----------------------------------------------------------

    def serve(self, stdin=None, stdout=None) -> None:
        stdin = stdin or sys.stdin
        stdout = stdout or sys.stdout
        _log(f"v{__version__} started — waiting for Codex on stdio")
        try:
            for line in stdin:
                line = line.strip()
                if not line:
                    continue
                try:
                    req = json.loads(line)
                except json.JSONDecodeError:
                    _write(stdout, _err(None, PARSE_ERROR, "Invalid JSON"))
                    continue
                if not isinstance(req, dict):
                    _write(stdout, _err(None, INVALID_REQUEST, "Request must be an object"))
                    continue
                resp = self.handle(req)
                if resp is not None:
                    _write(stdout, resp)
        finally:
            self.close()


# --------------------------------------------------------------------------- #
# JSON-RPC helpers                                                              #
# --------------------------------------------------------------------------- #


def _ok(rid: Any, result: Dict[str, Any]) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def _err(rid: Any, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


def _write(stdout, obj: Dict[str, Any]) -> None:
    stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    stdout.flush()


def main() -> None:
    """Console entry point (``perseus-vault-codex``)."""
    CodexMemoryServer().serve()


if __name__ == "__main__":
    main()
