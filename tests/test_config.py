"""Tests for zero-config auto-init resolution logic."""

from __future__ import annotations

import perseus_vault_codex.config as config


def test_find_binary_prefers_explicit():
    assert config.find_binary("/custom/perseus-vault") == "/custom/perseus-vault"


def test_find_binary_reads_env(monkeypatch):
    monkeypatch.setenv("PERSEUS_VAULT_BIN", "/env/perseus-vault")
    assert config.find_binary() == "/env/perseus-vault"


def test_resolve_llm_prefers_explicit_endpoint(monkeypatch):
    monkeypatch.setenv("PERSEUS_VAULT_LLM_ENDPOINT", "http://localhost:11434/api/chat")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    endpoint, _key, _model = config._resolve_llm()
    assert endpoint == "http://localhost:11434/api/chat"


def test_resolve_llm_defaults_to_openai_when_key_present(monkeypatch):
    monkeypatch.delenv("PERSEUS_VAULT_LLM_ENDPOINT", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-abc")
    endpoint, key, model = config._resolve_llm()
    assert endpoint == "https://api.openai.com/v1/chat/completions"
    assert key == "sk-abc"
    assert model == "gpt-5.6"


def test_resolve_llm_none_when_nothing_configured(monkeypatch):
    monkeypatch.delenv("PERSEUS_VAULT_LLM_ENDPOINT", raising=False)
    monkeypatch.delenv("PERSEUS_VAULT_LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert config._resolve_llm() == (None, None, None)


def test_load_config_disables_encryption_when_env_set(monkeypatch, tmp_path):
    monkeypatch.setenv("PERSEUS_VAULT_CODEX_ENCRYPT", "0")
    monkeypatch.setenv("PERSEUS_VAULT_CODEX_DB", str(tmp_path / "m.db"))
    monkeypatch.setenv("PERSEUS_VAULT_BIN", "perseus-vault")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("PERSEUS_VAULT_LLM_ENDPOINT", raising=False)
    cfg = config.load_config()
    assert cfg.encrypted is False
    assert cfg.db_path.endswith("m.db")
