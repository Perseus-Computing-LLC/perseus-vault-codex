"""Tests for the Codex config installer (non-destructive merge)."""

from __future__ import annotations

from pathlib import Path

from perseus_vault_codex.install import STANZA_HEADER, install, render_stanza


def test_render_stanza_contains_command():
    stanza = render_stanza("perseus-vault-codex", None)
    assert STANZA_HEADER in stanza
    assert 'command = "perseus-vault-codex"' in stanza


def test_render_stanza_pins_binary_when_not_on_path():
    stanza = render_stanza("perseus-vault-codex", "/opt/perseus/perseus-vault")
    assert "PERSEUS_VAULT_BIN" in stanza
    assert "/opt/perseus/perseus-vault" in stanza


def test_install_creates_config_when_absent(tmp_path):
    cfg = tmp_path / ".codex" / "config.toml"
    summary = install(cfg)
    assert cfg.exists()
    assert STANZA_HEADER in cfg.read_text(encoding="utf-8")
    assert "Configured Codex" in summary


def test_install_preserves_existing_config_and_backs_up(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text('[foo]\nbar = "baz"\n', encoding="utf-8")
    summary = install(cfg)
    text = cfg.read_text(encoding="utf-8")
    assert '[foo]' in text  # preserved
    assert STANZA_HEADER in text  # appended
    assert "backup" in summary
    # A timestamped backup was written next to it.
    backups = list(tmp_path.glob("config.toml.bak-*"))
    assert len(backups) == 1


def test_install_is_idempotent(tmp_path):
    cfg = tmp_path / "config.toml"
    install(cfg)
    summary = install(cfg)
    assert "Already configured" in summary
    # Only one stanza header present.
    assert cfg.read_text(encoding="utf-8").count(STANZA_HEADER) == 1


def test_dry_run_writes_nothing(tmp_path):
    cfg = tmp_path / "config.toml"
    summary = install(cfg, dry_run=True)
    assert not cfg.exists()
    assert "[dry-run]" in summary
