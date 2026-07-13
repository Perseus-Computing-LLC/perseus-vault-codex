# Architecture

## The two-hop MCP design

Perseus Vault Codex sits between the Codex agent and the Perseus Vault binary as
a thin, curated MCP server:

```
┌───────────────────┐   MCP stdio    ┌────────────────────────┐   MCP stdio    ┌────────────────────┐
│   Codex agent     │  (JSON-RPC)    │  perseus-vault-codex   │  (JSON-RPC)    │   perseus-vault    │
│   (GPT-5.6)       │◀──────────────▶│  MCP server            │◀──────────────▶│   binary (serve)   │
│                   │   5 tools      │  (this package)        │  55+ tools     │   SQLite + FTS5    │
└───────────────────┘                └────────────────────────┘                │   AES-256-GCM      │
                                                                                 └─────────┬──────────┘
                                                                                           │
                                                                                 ┌─────────▼──────────┐
                                                                                 │ ~/.perseus-vault/  │
                                                                                 │  codex/memory.db   │
                                                                                 │  (encrypted at rest)│
                                                                                 └────────────────────┘
```

**Why two hops?** Perseus Vault exposes 55+ low-level memory tools (bitemporal
queries, graph traversal, consolidation, decay, communities…). A coding agent
does not want to reason about 55 tools. This package collapses that surface into
five verbs an agent understands — *remember, recall, forget, reflect, status* —
and translates each into the right underlying vault call. The Vault binary does
the hard part: encrypted storage, FTS5 keyword + hybrid ranking, and RAG.

## Components

| File | Responsibility |
|------|----------------|
| `server.py` | The Codex-facing MCP stdio server: JSON-RPC loop, `initialize` / `tools/list` / `tools/call`, error mapping. Lazily spawns the vault on first tool call. |
| `tools.py` | The five curated tool schemas + handlers. Translates each verb into a Perseus Vault call and normalizes the result. |
| `_vault_client.py` | Vendored, hardened JSON-RPC stdio client for the vault subprocess (reentrant-lock handshake, deadline-bounded reads, auto-respawn). |
| `config.py` | Zero-config auto-init: binary discovery, per-user data dir, AES-256-GCM key generation, LLM wiring for `reflect`. |
| `install.py` | `perseus-vault-codex-setup` — non-destructive merge of the MCP stanza into `~/.codex/config.toml`. |

## Tool mapping

| Codex tool | Perseus Vault call | Notes |
|------------|--------------------|-------|
| `perseus_remember` | `perseus_vault_remember` | Wraps text in a JSON body; idempotent per (category, key). |
| `perseus_recall` | `perseus_vault_recall` | FTS5 keyword + hybrid ranking; normalizes hits to `{key, category, text, score}`. |
| `perseus_forget` | `perseus_vault_forget` | Soft-delete (recoverable). |
| `perseus_reflect` | `perseus_vault_recall` + `perseus_vault_ask` | Gathers grounding memories, then RAG-synthesizes with the user's LLM; degrades to context-only if no LLM. |
| `perseus_status` | `perseus_vault_stats` | Plus local facts: encryption state, DB path, reflect availability. |

## Reliability decisions

- **stdout is the protocol.** All logging goes to stderr. A single stray stdout
  write would corrupt the JSON-RPC stream.
- **Lazy vault start.** `tools/list` (which Codex calls at startup) never blocks
  on spawning the binary; the vault starts on the first real tool call.
- **Errors never crash the session.** A failing tool becomes a JSON-RPC error
  object, so the Codex session stays alive.
- **Encryption on by default.** A key is generated on first run; the on-disk DB
  never contains plaintext memory (verified by an integration test).
