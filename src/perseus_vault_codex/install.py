"""One-command Codex setup: ``perseus-vault-codex-setup``.

Writes (or non-destructively merges) an ``[mcp_servers.perseus-vault]`` stanza
into the Codex config at ``~/.codex/config.toml`` so Codex launches this memory
server automatically. Existing config is preserved; a timestamped backup is
written before any change.

We render TOML by hand (the stdlib ``tomllib`` reads but cannot write) and keep
the stanza self-contained so the merge is a simple, auditable append.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from pathlib import Path

from .config import find_binary

CODEX_CONFIG = Path.home() / ".codex" / "config.toml"
STANZA_HEADER = "[mcp_servers.perseus-vault]"


def render_stanza(command: str, vault_bin: str | None) -> str:
    lines = [
        "",
        "# Added by perseus-vault-codex-setup — persistent encrypted memory for Codex.",
        STANZA_HEADER,
        f'command = "{command}"',
        "args = []",
    ]
    if vault_bin and vault_bin not in ("perseus-vault", "perseus-vault.exe"):
        # Pin the vault binary path if it isn't already on PATH.
        lines += [
            "",
            "[mcp_servers.perseus-vault.env]",
            f'PERSEUS_VAULT_BIN = "{_toml_escape(vault_bin)}"',
        ]
    lines.append("")
    return "\n".join(lines)


def _toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def install(
    config_path: Path = CODEX_CONFIG,
    *,
    command: str = "perseus-vault-codex",
    dry_run: bool = False,
) -> str:
    """Merge the stanza into ``config_path``. Returns a human-readable summary."""
    vault_bin = find_binary()
    stanza = render_stanza(command, vault_bin)

    existing = ""
    if config_path.exists():
        existing = config_path.read_text(encoding="utf-8")
        if STANZA_HEADER in existing:
            return (
                f"Already configured: {config_path} already contains "
                f"{STANZA_HEADER}. Nothing changed."
            )

    new_content = (existing.rstrip() + "\n" if existing.strip() else "") + stanza

    if dry_run:
        return (
            f"[dry-run] Would write to {config_path}:\n"
            f"{'-' * 60}\n{stanza}{'-' * 60}"
        )

    config_path.parent.mkdir(parents=True, exist_ok=True)
    if existing:
        backup = config_path.with_suffix(
            config_path.suffix + f".bak-{time.strftime('%Y%m%d-%H%M%S')}"
        )
        shutil.copy2(config_path, backup)
        backup_note = f" (backup: {backup})"
    else:
        backup_note = ""

    config_path.write_text(new_content, encoding="utf-8")
    return (
        f"Configured Codex MCP server 'perseus-vault' in {config_path}{backup_note}.\n"
        "Restart Codex (or start a new session) and the memory tools will be "
        "available: perseus_remember, perseus_recall, perseus_forget, "
        "perseus_reflect, perseus_status."
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="perseus-vault-codex-setup",
        description="Register Perseus Vault as a Codex MCP memory server.",
    )
    parser.add_argument(
        "--config",
        default=str(CODEX_CONFIG),
        help=f"Path to Codex config.toml (default: {CODEX_CONFIG}).",
    )
    parser.add_argument(
        "--command",
        default="perseus-vault-codex",
        help="Command Codex should run to launch the server.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be written without modifying any file.",
    )
    ns = parser.parse_args()
    summary = install(
        Path(ns.config).expanduser(), command=ns.command, dry_run=ns.dry_run
    )
    print(summary)
    if "Could not" in summary:
        sys.exit(1)


if __name__ == "__main__":
    main()
