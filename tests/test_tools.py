"""Unit tests for the five curated tools' translation to vault calls."""

from __future__ import annotations

from perseus_vault_codex.tools import DEFAULT_CATEGORY, Tools


def _tools(client, cfg):
    return Tools(client, cfg)


def test_remember_defaults_category_and_generates_key(fake_vault, fake_config):
    t = _tools(fake_vault, fake_config)
    res = t.remember({"text": "Run pytest with -q"})
    assert res["status"] == "ok"
    assert res["category"] == DEFAULT_CATEGORY
    assert res["action"] == "created"
    # The underlying vault call carried a JSON body with the content.
    call = fake_vault.calls[-1]
    assert call["name"] == "perseus_vault_remember"
    assert "Run pytest" in call["arguments"]["body_json"]


def test_remember_is_idempotent_on_same_key(fake_vault, fake_config):
    t = _tools(fake_vault, fake_config)
    t.remember({"text": "v1", "key": "k1", "category": "convention"})
    res = t.remember({"text": "v2", "key": "k1", "category": "convention"})
    assert res["action"] == "updated"


def test_remember_rejects_empty_text(fake_vault, fake_config):
    t = _tools(fake_vault, fake_config)
    import pytest

    from perseus_vault_codex._vault_client import VaultError

    with pytest.raises(VaultError):
        t.remember({"text": "   "})


def test_recall_returns_normalized_memories(fake_vault, fake_config):
    t = _tools(fake_vault, fake_config)
    t.remember({"text": "We use SQLite with FTS5", "key": "db"})
    res = t.recall({"query": "sqlite"})
    assert res["count"] == 1
    mem = res["memories"][0]
    assert mem["text"] == "We use SQLite with FTS5"
    assert mem["key"] == "db"
    assert isinstance(mem["score"], float)


def test_recall_empty_is_friendly(fake_vault, fake_config):
    t = _tools(fake_vault, fake_config)
    res = t.recall({"query": "nothing here"})
    assert res["count"] == 0
    assert "No memories" in res["message"]


def test_forget_archives_and_reports(fake_vault, fake_config):
    t = _tools(fake_vault, fake_config)
    t.remember({"text": "stale fact", "key": "old", "category": "gotcha"})
    res = t.forget({"key": "old", "category": "gotcha"})
    assert res["archived"] is True
    # Forgetting again reports not_found rather than erroring.
    res2 = t.forget({"key": "old", "category": "gotcha"})
    assert res2["archived"] is False
    assert res2["status"] == "not_found"


def test_reflect_context_only_without_llm(fake_vault, fake_config):
    t = _tools(fake_vault, fake_config)
    t.remember({"text": "Always format with black", "key": "fmt"})
    res = t.reflect({"query": "format"})
    assert res["mode"] == "context-only"
    assert "black" in res["context"]
    assert res["sources"]


def test_reflect_uses_llm_when_configured(fake_config_with_llm):
    from tests.conftest import FakeVaultClient

    client = FakeVaultClient(llm_answer="This project formats with black and tests with pytest.")
    t = _tools(client, fake_config_with_llm)
    t.remember({"text": "Project conventions: black + pytest", "key": "conv"})
    res = t.reflect({"query": "conventions"})
    assert res["mode"] == "llm-synthesis"
    assert "black" in res["answer"]
    assert res["sources"]


def test_reflect_falls_back_when_llm_returns_error(fake_config_with_llm):
    """A vault 'ask' that comes back as an error envelope must not be surfaced
    as a real answer — reflect degrades to context-only instead."""
    from tests.conftest import FakeVaultClient

    class ErroringClient(FakeVaultClient):
        def call_tool(self, name, arguments):
            if name.endswith("_ask"):
                return {
                    "content": [{"type": "text", "text": "Ask failed: LLM API call failed: status 400"}],
                    "isError": True,
                }
            return super().call_tool(name, arguments)

    client = ErroringClient()
    t = _tools(client, fake_config_with_llm)
    t.remember({"text": "conventions: black", "key": "c"})
    res = t.reflect({"query": "conventions"})
    assert res["mode"] == "context-only"
    assert "Ask failed" not in res["answer"]


def test_status_reports_encryption_and_reflect(fake_vault, fake_config):
    t = _tools(fake_vault, fake_config)
    t.remember({"text": "a", "key": "1"})
    res = t.status({})
    assert res["encrypted_at_rest"] is True
    assert res["reflect_enabled"] is False
    assert res["total_memories"] == 1
