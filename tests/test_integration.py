"""End-to-end integration test against the real ``perseus-vault`` binary.

Skipped unless a binary is discoverable (``PERSEUS_VAULT_BIN`` or on PATH). This
is the test that proves the wrapper actually drives the vault — spawning the
subprocess, storing an encrypted memory, and recalling it across a fresh client,
exactly as a new Codex session would.
"""

from __future__ import annotations

import shutil

import pytest

from perseus_vault_codex._vault_client import VaultClient
from perseus_vault_codex.config import find_binary, load_config
from perseus_vault_codex.tools import Tools


def _binary_available() -> bool:
    b = find_binary()
    return shutil.which(b) is not None or b not in ("perseus-vault", "perseus-vault.exe")


pytestmark = pytest.mark.skipif(
    not _binary_available(),
    reason="perseus-vault binary not found (set PERSEUS_VAULT_BIN to run integration test)",
)


def test_remember_recall_persist_across_sessions(tmp_path):
    cfg = load_config(db_path=str(tmp_path / "it.db"), encrypt=True)

    # Session 1: remember two project facts, then close the vault entirely.
    with VaultClient(
        binary=cfg.binary, db_path=cfg.db_path, encryption_key=cfg.encryption_key
    ) as v1:
        t1 = Tools(v1, cfg)
        t1.remember({"text": "This project runs tests with 'pytest -q'", "key": "tests",
                     "category": "convention"})
        t1.remember({"text": "Auth uses short-lived JWTs, refresh in Redis", "key": "auth",
                     "category": "decision"})

    # Session 2: a brand-new client/process — recall must survive.
    with VaultClient(
        binary=cfg.binary, db_path=cfg.db_path, encryption_key=cfg.encryption_key
    ) as v2:
        t2 = Tools(v2, cfg)
        hits = t2.recall({"query": "how do we run tests"})
        texts = " ".join(m["text"] for m in hits["memories"])
        assert "pytest" in texts

        status = t2.status({})
        assert status["encrypted_at_rest"] is True
        assert status["total_memories"] >= 2

        # Forget one and confirm it's gone.
        t2.forget({"key": "auth", "category": "decision"})
        again = t2.recall({"query": "JWT auth", "category": "decision"})
        assert again["count"] == 0


def test_encrypted_db_is_not_plaintext(tmp_path):
    """The on-disk database must not contain memory text in the clear."""
    cfg = load_config(db_path=str(tmp_path / "enc.db"), encrypt=True)
    if not cfg.encrypted:
        pytest.skip("key generation unavailable")
    secret = "SUPERSECRETCONVENTIONTOKEN12345"
    with VaultClient(
        binary=cfg.binary, db_path=cfg.db_path, encryption_key=cfg.encryption_key
    ) as v:
        Tools(v, cfg).remember({"text": secret, "key": "s", "category": "secret"})
    raw = (tmp_path / "enc.db").read_bytes()
    assert secret.encode() not in raw
