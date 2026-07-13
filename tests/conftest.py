"""Shared test fixtures: a fake vault client so unit tests need no binary."""

from __future__ import annotations

import json
from typing import Any, Dict, List

import pytest

from perseus_vault_codex.config import VaultConfig


class FakeVaultClient:
    """In-memory stand-in for VaultClient that mimics the vault tool contract.

    It records every call and stores memories in a dict keyed by
    (category, key), so tool translation can be asserted end-to-end without
    spawning the real binary.
    """

    def __init__(self, *, llm_answer: str | None = None):
        self.calls: List[Dict[str, Any]] = []
        self.store: Dict[tuple, Dict[str, Any]] = {}
        self.llm_answer = llm_answer

    def tool(self, short: str) -> str:
        return f"perseus_vault_{short}"

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        self.calls.append({"name": name, "arguments": arguments})
        short = name.replace("perseus_vault_", "")
        if short == "remember":
            key = (arguments["category"], arguments["key"])
            action = "updated" if key in self.store else "created"
            self.store[key] = json.loads(arguments["body_json"])
            return {"action": action, "category": key[0], "key": key[1], "id": "mem-abc"}
        if short == "recall":
            q = (arguments.get("query") or "").lower()
            items = []
            for (cat, key), body in self.store.items():
                if arguments.get("category") and arguments["category"] != cat:
                    continue
                text = body.get("content", "")
                if not q or any(w in text.lower() for w in q.split()):
                    items.append(
                        {"key": key, "category": cat, "body_json": json.dumps(body), "score": 0.9}
                    )
            return {"items": items[: arguments.get("limit", 5)]}
        if short == "forget":
            key = (arguments["category"], arguments["key"])
            archived = 1 if key in self.store else 0
            self.store.pop(key, None)
            return {"archived": archived}
        if short == "ask":
            if self.llm_answer is None:
                raise RuntimeError("no llm configured")
            return {"answer": self.llm_answer}
        if short == "stats":
            by_cat: Dict[str, int] = {}
            for (cat, _key) in self.store:
                by_cat[cat] = by_cat.get(cat, 0) + 1
            return {"total_entities": len(self.store), "by_category": by_cat}
        raise RuntimeError(f"unexpected tool {name}")

    def close(self) -> None:
        pass


@pytest.fixture
def fake_vault():
    return FakeVaultClient()


@pytest.fixture
def fake_config(tmp_path):
    return VaultConfig(
        binary="perseus-vault",
        db_path=str(tmp_path / "memory.db"),
        encryption_key=str(tmp_path / "vault.key"),
        llm_endpoint=None,
        llm_api_key=None,
        llm_model=None,
    )


@pytest.fixture
def fake_config_with_llm(tmp_path):
    return VaultConfig(
        binary="perseus-vault",
        db_path=str(tmp_path / "memory.db"),
        encryption_key=str(tmp_path / "vault.key"),
        llm_endpoint="https://api.openai.com/v1/chat/completions",
        llm_api_key="sk-test",
        llm_model="gpt-5.6",
    )
