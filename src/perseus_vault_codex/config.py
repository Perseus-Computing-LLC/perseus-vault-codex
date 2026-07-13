"""Zero-config auto-init for the Perseus Vault Codex integration.

On first run this module resolves (and, where needed, *creates*) everything the
vault subprocess requires — with encryption **on by default**:

* the ``perseus-vault`` binary (env override, then PATH),
* a per-user data directory under ``~/.perseus-vault/codex/``,
* an AES-256-GCM key file (generated via ``perseus-vault keygen`` if absent),
* an optional LLM endpoint for the ``reflect`` tool, wired from OpenAI-style env.

Nothing here talks to the network. The only side effects are creating a local
directory and, once, a local key file — both under the user's home.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Where the Codex integration keeps its own vault, isolated from any other
# Perseus Vault database the user may run.
DEFAULT_HOME = Path.home() / ".perseus-vault" / "codex"
DEFAULT_DB = DEFAULT_HOME / "memory.db"
DEFAULT_KEY = DEFAULT_HOME / "vault.key"


def _log(msg: str) -> None:
    # NEVER write to stdout: stdout is the MCP JSON-RPC channel to Codex.
    print(f"[perseus-vault-codex] {msg}", file=sys.stderr, flush=True)


def find_binary(explicit: Optional[str] = None) -> str:
    """Resolve the ``perseus-vault`` executable.

    Order: explicit arg → ``PERSEUS_VAULT_BIN`` → ``perseus-vault(.exe)`` on PATH.
    Returns the string to spawn; does not verify it runs (the client surfaces a
    clear install message if the spawn fails).
    """
    if explicit:
        return explicit
    env = os.getenv("PERSEUS_VAULT_BIN")
    if env:
        return env
    for name in ("perseus-vault", "perseus-vault.exe"):
        found = shutil.which(name)
        if found:
            return found
    # Last resort: let the OS resolve it and let the client raise a helpful error.
    return "perseus-vault"


@dataclass
class VaultConfig:
    binary: str
    db_path: str
    encryption_key: Optional[str]
    llm_endpoint: Optional[str]
    llm_api_key: Optional[str]
    llm_model: Optional[str]

    @property
    def encrypted(self) -> bool:
        return bool(self.encryption_key)

    @property
    def reflect_enabled(self) -> bool:
        return bool(self.llm_endpoint)


def ensure_key(key_path: Path, binary: str) -> Optional[str]:
    """Ensure an AES-256-GCM key file exists at ``key_path``; create it if not.

    Returns the path as a string, or ``None`` if key generation failed (in which
    case the vault runs unencrypted and the caller should surface that).
    """
    if key_path.exists() and key_path.stat().st_size > 0:
        return str(key_path)
    key_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [binary, "keygen", "--key-file", str(key_path)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        _log("WARNING: could not generate an encryption key; vault will run "
             "UNENCRYPTED. Install the perseus-vault binary to enable "
             "encryption at rest.")
        return None
    if key_path.exists() and key_path.stat().st_size > 0:
        # Best-effort: tighten permissions on POSIX. (No-op on Windows.)
        try:
            os.chmod(key_path, 0o600)
        except OSError:
            pass
        _log(f"generated AES-256-GCM key at {key_path}")
        return str(key_path)
    return None


def _resolve_llm() -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Wire the ``reflect`` LLM from env, defaulting to OpenAI when a key exists.

    Precedence:
      * explicit ``PERSEUS_VAULT_LLM_ENDPOINT`` (+ ``_API_KEY`` / ``_MODEL``)
      * else, if ``OPENAI_API_KEY`` is set, point at OpenAI's chat completions
        endpoint with GPT-5.6 — the same model powering the Codex agent.
    Returns ``(endpoint, api_key, model)``; any may be ``None``.
    """
    endpoint = os.getenv("PERSEUS_VAULT_LLM_ENDPOINT")
    api_key = os.getenv("PERSEUS_VAULT_LLM_API_KEY")
    model = os.getenv("PERSEUS_VAULT_LLM_MODEL")

    if endpoint:
        return endpoint, api_key, model

    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        return (
            f"{base}/chat/completions",
            openai_key,
            model or os.getenv("OPENAI_MODEL", "gpt-5.6"),
        )
    return None, None, None


def load_config(
    *,
    binary: Optional[str] = None,
    db_path: Optional[str] = None,
    encryption_key: Optional[str] = None,
    encrypt: bool = True,
) -> VaultConfig:
    """Resolve a fully-initialized :class:`VaultConfig`, creating the data dir
    and encryption key on first run.

    Env overrides: ``PERSEUS_VAULT_BIN``, ``PERSEUS_VAULT_CODEX_DB``,
    ``PERSEUS_VAULT_CODEX_KEY``, ``PERSEUS_VAULT_CODEX_ENCRYPT`` (``0`` disables).
    """
    bin_path = find_binary(binary)

    db = db_path or os.getenv("PERSEUS_VAULT_CODEX_DB") or str(DEFAULT_DB)
    Path(db).expanduser().parent.mkdir(parents=True, exist_ok=True)

    if os.getenv("PERSEUS_VAULT_CODEX_ENCRYPT", "1") == "0":
        encrypt = False

    key: Optional[str] = None
    if encrypt:
        key_path = Path(
            encryption_key
            or os.getenv("PERSEUS_VAULT_CODEX_KEY")
            or str(DEFAULT_KEY)
        ).expanduser()
        key = ensure_key(key_path, bin_path)

    endpoint, api_key, model = _resolve_llm()

    return VaultConfig(
        binary=bin_path,
        db_path=str(Path(db).expanduser()),
        encryption_key=key,
        llm_endpoint=endpoint,
        llm_api_key=api_key,
        llm_model=model,
    )
