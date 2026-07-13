"""The curated Codex tool surface.

Perseus Vault exposes 55+ low-level memory tools. A coding agent does not need
55 tools — it needs five verbs it can reason about: *remember, recall, forget,
reflect, status*. This module defines those five as MCP tools (JSON Schemas +
handlers) and translates each into the appropriate underlying vault call via
:class:`~perseus_vault_codex._vault_client.VaultClient`.

Every handler returns a plain ``dict`` — the server wraps it into the MCP
content/structuredContent envelope. Handlers never raise for expected empty
results (e.g. a recall with no hits); they raise :class:`VaultError` only on a
real transport/vault failure, which the server maps to a JSON-RPC error.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Callable, Dict, List

from ._vault_client import VaultClient, VaultError

# Default category for memories saved without an explicit one. Keeping Codex
# memories in their own namespace keeps recall focused and forget predictable.
DEFAULT_CATEGORY = "codex-memory"


# --------------------------------------------------------------------------- #
# Tool schemas (advertised to Codex via tools/list)                            #
# --------------------------------------------------------------------------- #

TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "name": "perseus_remember",
        "description": (
            "Save a fact, decision, convention, or piece of context to persistent "
            "encrypted memory so it survives across Codex sessions. Call this "
            "whenever you learn something durable about the project: build "
            "commands, code style, architectural decisions, gotchas, or the user's "
            "preferences. Idempotent per (category, key)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The fact or context to remember, in plain language.",
                },
                "category": {
                    "type": "string",
                    "description": (
                        "Optional grouping, e.g. 'convention', 'decision', "
                        "'gotcha'. Defaults to 'codex-memory'."
                    ),
                },
                "key": {
                    "type": "string",
                    "description": (
                        "Optional stable identifier. Re-using a key updates that "
                        "memory instead of creating a duplicate. Auto-generated "
                        "if omitted."
                    ),
                },
                "importance": {
                    "type": "number",
                    "description": "Optional salience 0.0–1.0 (higher ranks sooner in recall).",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional tags for later filtering.",
                },
            },
            "required": ["text"],
        },
    },
    {
        "name": "perseus_recall",
        "description": (
            "Retrieve relevant memories from past Codex sessions. Call this at the "
            "start of a task, or whenever you need project context you might have "
            "learned before, e.g. 'how do we run tests here', 'what did we decide "
            "about auth'. Uses FTS5 keyword + hybrid ranking; returns the most "
            "relevant memories with a score."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What you want to remember about (natural language).",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max memories to return (default 5).",
                },
                "category": {
                    "type": "string",
                    "description": "Optional: restrict recall to one category.",
                },
                "mode": {
                    "type": "string",
                    "enum": ["hybrid", "fts5", "semantic"],
                    "description": "Ranking mode (default 'hybrid').",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "perseus_forget",
        "description": (
            "Remove a stale or incorrect memory. Soft-deletes by (category, key) — "
            "the memory is hidden from recall but recoverable. Use the key shown "
            "in a prior perseus_recall / perseus_remember result."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "The memory's key."},
                "category": {
                    "type": "string",
                    "description": "The memory's category (default 'codex-memory').",
                },
                "reason": {
                    "type": "string",
                    "description": "Optional note on why it's being removed.",
                },
            },
            "required": ["key"],
        },
    },
    {
        "name": "perseus_reflect",
        "description": (
            "Synthesize an insight from stored memories. Given a question, Perseus "
            "Vault recalls the most relevant memories and asks the configured LLM "
            "(your OpenAI/GPT-5.6 key by default) to produce a grounded answer "
            "citing them. If no LLM is configured, returns the assembled memory "
            "context so you can reason over it yourself."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The question to reflect on, e.g. 'what are this project's conventions?'",
                },
                "top_k": {
                    "type": "integer",
                    "description": "How many memories to ground the answer in (default 8).",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "perseus_status",
        "description": (
            "Report the health of the memory store: how many memories are stored, "
            "whether encryption at rest is active, the database location, and "
            "whether reflect (LLM synthesis) is available. Zero-argument."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
]


# --------------------------------------------------------------------------- #
# Handlers                                                                      #
# --------------------------------------------------------------------------- #


class Tools:
    """Binds the curated tool handlers to a live vault client + config."""

    def __init__(self, client: VaultClient, config) -> None:
        self._v = client
        self._cfg = config

    # -- perseus_remember ---------------------------------------------------

    def remember(self, args: Dict[str, Any]) -> Dict[str, Any]:
        text = (args.get("text") or "").strip()
        if not text:
            raise VaultError("perseus_remember requires non-empty 'text'.")
        category = args.get("category") or DEFAULT_CATEGORY
        key = args.get("key") or f"mem-{uuid.uuid4().hex[:12]}"
        body: Dict[str, Any] = {"content": text}
        tags = args.get("tags")
        if tags:
            body["metadata"] = {"tags": tags}

        call_args: Dict[str, Any] = {
            "category": category,
            "key": key,
            "body_json": json.dumps(body),
        }
        if isinstance(args.get("importance"), (int, float)):
            call_args["importance"] = float(args["importance"])
        if tags:
            call_args["tags"] = tags

        res = self._v.call_tool(self._v.tool("remember"), call_args)
        action = res.get("action") if isinstance(res, dict) else None
        return {
            "status": "ok",
            "action": action or "saved",
            "key": key,
            "category": category,
            "message": f"Remembered under {category}/{key}.",
        }

    # -- perseus_recall -----------------------------------------------------

    def recall(self, args: Dict[str, Any]) -> Dict[str, Any]:
        query = args.get("query", "")
        limit = int(args.get("limit") or 5)
        call_args: Dict[str, Any] = {
            "query": query,
            "limit": limit,
            "mode": args.get("mode") or "hybrid",
        }
        if args.get("category"):
            call_args["category"] = args["category"]

        res = self._v.call_tool(self._v.tool("recall"), call_args)
        memories = _normalize_items(res)
        return {
            "status": "ok",
            "count": len(memories),
            "memories": memories,
            "message": (
                f"Recalled {len(memories)} memories for {query!r}."
                if memories
                else f"No memories found for {query!r} yet."
            ),
        }

    # -- perseus_forget -----------------------------------------------------

    def forget(self, args: Dict[str, Any]) -> Dict[str, Any]:
        key = args.get("key")
        if not key:
            raise VaultError("perseus_forget requires 'key'.")
        category = args.get("category") or DEFAULT_CATEGORY
        call_args: Dict[str, Any] = {"category": category, "key": key}
        if args.get("reason"):
            call_args["reason"] = args["reason"]
        res = self._v.call_tool(self._v.tool("forget"), call_args)
        archived = bool(isinstance(res, dict) and res.get("archived", 0))
        return {
            "status": "ok" if archived else "not_found",
            "archived": archived,
            "key": key,
            "category": category,
            "message": (
                f"Forgot {category}/{key}."
                if archived
                else f"No active memory at {category}/{key} to forget."
            ),
        }

    # -- perseus_reflect ----------------------------------------------------

    def reflect(self, args: Dict[str, Any]) -> Dict[str, Any]:
        query = (args.get("query") or "").strip()
        if not query:
            raise VaultError("perseus_reflect requires 'query'.")
        top_k = int(args.get("top_k") or 8)

        # Always gather the grounding memories so the answer is inspectable and
        # the tool is useful even without an LLM configured.
        recall_res = self._v.call_tool(
            self._v.tool("recall"), {"query": query, "limit": top_k, "mode": "hybrid"}
        )
        sources = _normalize_items(recall_res)

        if self._cfg.reflect_enabled:
            try:
                ask = self._v.call_tool(
                    self._v.tool("ask"), {"query": query, "top_k": top_k}
                )
                answer = _extract_answer(ask)
                if answer and not _looks_like_error(answer):
                    return {
                        "status": "ok",
                        "mode": "llm-synthesis",
                        "answer": answer,
                        "sources": sources,
                    }
            except VaultError:
                # Fall through to context-only mode on any LLM/transport hiccup.
                pass

        # No LLM (or it failed): hand back the assembled context to reason over.
        context = "\n".join(f"- {m['text']}" for m in sources) or "(no memories yet)"
        return {
            "status": "ok",
            "mode": "context-only",
            "answer": (
                "No LLM endpoint configured for synthesis. Assembled the "
                f"{len(sources)} most relevant memories below for you to reason "
                "over. Set OPENAI_API_KEY (or PERSEUS_VAULT_LLM_ENDPOINT) to have "
                "Perseus Vault synthesize an answer with GPT-5.6."
            ),
            "context": context,
            "sources": sources,
        }

    # -- perseus_status -----------------------------------------------------

    def status(self, args: Dict[str, Any]) -> Dict[str, Any]:
        stats = self._v.call_tool(self._v.tool("stats"), {})
        total = stats.get("total_entities") if isinstance(stats, dict) else None
        by_category = stats.get("by_category", {}) if isinstance(stats, dict) else {}
        return {
            "status": "ok",
            "total_memories": total,
            "by_category": by_category,
            "encrypted_at_rest": self._cfg.encrypted,
            "reflect_enabled": self._cfg.reflect_enabled,
            "reflect_model": self._cfg.llm_model if self._cfg.reflect_enabled else None,
            "database": self._cfg.db_path,
            "engine": "perseus-vault (SQLite + FTS5, local-first, no telemetry)",
        }

    # -- dispatch -----------------------------------------------------------

    def handler_for(self, name: str) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
        table: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
            "perseus_remember": self.remember,
            "perseus_recall": self.recall,
            "perseus_forget": self.forget,
            "perseus_reflect": self.reflect,
            "perseus_status": self.status,
        }
        if name not in table:
            raise VaultError(f"Unknown tool: {name}")
        return table[name]


# --------------------------------------------------------------------------- #
# Helpers                                                                       #
# --------------------------------------------------------------------------- #


def _normalize_items(res: Any) -> List[Dict[str, Any]]:
    """Flatten the vault's recall envelope into ``{text, key, category, score}``."""
    items = res.get("items", []) if isinstance(res, dict) else []
    out: List[Dict[str, Any]] = []
    for it in items:
        body = it.get("body_json") or it.get("body") or {}
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except json.JSONDecodeError:
                body = {"content": body}
        text = ""
        if isinstance(body, dict):
            text = body.get("content", "")
        # The server also surfaces expanded content/summary at the top level.
        text = text or it.get("content") or it.get("summary") or ""
        score = it.get("score")
        if score is None:
            score = it.get("confidence")
        out.append(
            {
                "key": it.get("key") or it.get("id"),
                "category": it.get("category"),
                "text": text,
                "score": round(float(score), 4) if isinstance(score, (int, float)) else None,
            }
        )
    return out


def _extract_answer(ask: Any) -> str:
    """Pull the answer string out of the vault's ``ask`` (RAG) response.

    Returns "" for error envelopes (``isError``) so the caller falls back to
    context-only mode instead of surfacing a vault error as an "answer".
    """
    if isinstance(ask, str):
        return ask.strip()
    if isinstance(ask, dict):
        if ask.get("isError"):
            return ""
        for field in ("answer", "response", "text", "result"):
            val = ask.get(field)
            if isinstance(val, str) and val.strip():
                return val.strip()
        # MCP text envelope: {"content": [{"type": "text", "text": "..."}]}
        content = ask.get("content")
        if isinstance(content, list) and content and isinstance(content[0], dict):
            txt = content[0].get("text")
            if isinstance(txt, str) and txt.strip():
                return txt.strip()
    return ""


def _looks_like_error(answer: str) -> bool:
    """Heuristic: does the vault's ``ask`` payload look like a failure message
    rather than a real synthesis? Guards against RAG/LLM errors that come back
    as an ordinary text block (e.g. 'Ask failed: LLM API call failed ...')."""
    low = answer.lower()
    return low.startswith("ask failed") or "llm api call failed" in low
