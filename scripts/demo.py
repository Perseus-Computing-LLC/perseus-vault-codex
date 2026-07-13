#!/usr/bin/env python3
"""Perseus Vault Codex — end-to-end demo.

Simulates two separate Codex sessions to prove memory persists across them:

  Session 1  — the agent learns three project facts and remembers them.
  (vault process is fully torn down — nothing is held in RAM)
  Session 2  — a brand-new agent recalls those facts, then reflects on them.

Run it:
    PERSEUS_VAULT_BIN=/path/to/perseus-vault python scripts/demo.py

Set OPENAI_API_KEY as well to see `reflect` synthesize an answer with GPT-5.6;
without it, reflect returns the assembled memory context instead.
"""

from __future__ import annotations

import os
import sys
import tempfile

# Windows consoles default to cp1252; force UTF-8 so example text renders.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from perseus_vault_codex._vault_client import VaultClient
from perseus_vault_codex.config import load_config
from perseus_vault_codex.tools import Tools

RULE = "-" * 64


def banner(title: str) -> None:
    print(f"\n{RULE}\n  {title}\n{RULE}")


def session(cfg):
    """Open a fresh vault client (a new 'Codex session') bound to the same DB."""
    client = VaultClient(
        binary=cfg.binary,
        db_path=cfg.db_path,
        encryption_key=cfg.encryption_key,
        llm_endpoint=cfg.llm_endpoint,
        llm_api_key=cfg.llm_api_key,
        llm_model=cfg.llm_model,
    )
    return client, Tools(client, cfg)


def main() -> None:
    db = os.path.join(tempfile.mkdtemp(prefix="perseus-codex-demo-"), "memory.db")
    cfg = load_config(db_path=db, encrypt=True)

    print(f"Vault binary : {cfg.binary}")
    print(f"Database     : {cfg.db_path}")
    print(f"Encrypted    : {cfg.encrypted}  (AES-256-GCM at rest)")
    print(f"Reflect LLM  : {cfg.llm_model if cfg.reflect_enabled else 'not configured'}")

    # ---- Session 1: the agent learns and remembers ----------------------
    banner("SESSION 1  |  Codex learns your project")
    client, t = session(cfg)
    facts = [
        ("convention", "style", "This project formats with `ruff format` and lints with `ruff check`. Never commit unformatted code."),
        ("decision", "db", "We chose SQLite + FTS5 over Postgres for the local dev store — zero infra, single file."),
        ("gotcha", "windows-paths", "On Windows, always use pathlib; os.path.join with mixed separators breaks the test fixtures."),
    ]
    for cat, key, text in facts:
        res = t.remember({"text": text, "category": cat, "key": key})
        print(f"  remember  [{res['action']:>7}]  {cat}/{key}")
    print(f"\n  Stored {len(facts)} memories. Closing the session (vault process ends).")
    client.close()

    # ---- Session 2: a NEW agent recalls -----------------------------------
    banner("SESSION 2  |  A brand-new Codex session recalls everything")
    client, t = session(cfg)

    for q in ["how do we format code", "why sqlite", "windows path bug"]:
        hits = t.recall({"query": q, "limit": 1})
        top = hits["memories"][0]["text"] if hits["memories"] else "(nothing)"
        print(f"  recall  {q!r}\n     -> {top}\n")

    banner("REFLECT  |  Synthesize an insight from memory")
    reflection = t.reflect(
        {"query": "Summarize what you know about formatting, sqlite, and windows here"}
    )
    print(f"  mode: {reflection['mode']}")
    print(f"  {reflection['answer']}")
    if reflection.get("context"):
        print("\n  Grounding memories:")
        print("  " + reflection["context"].replace("\n", "\n  "))

    banner("STATUS")
    st = t.status({})
    print(f"  total memories   : {st['total_memories']}")
    print(f"  by category      : {st['by_category']}")
    print(f"  encrypted at rest: {st['encrypted_at_rest']}")
    print(f"  engine           : {st['engine']}")
    client.close()

    print("\n✅  Memory survived a full session teardown. Codex never forgets.\n")


if __name__ == "__main__":
    main()
