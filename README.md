# Perseus Vault Codex

**Persistent, encrypted, local-first memory for OpenAI Codex agents.**

> Codex never forgets. Perseus Vault gives your Codex agent persistent encrypted
> memory — so it remembers your project conventions, past decisions, and
> debugging context across every session.

[![CI](https://github.com/Perseus-Computing-LLC/perseus-vault-codex/actions/workflows/ci.yml/badge.svg)](https://github.com/Perseus-Computing-LLC/perseus-vault-codex/actions/workflows/ci.yml)
&nbsp;License: MIT &nbsp;·&nbsp; Built for **OpenAI Build Week** — Developer Tools track

---

## The problem

Every Codex session starts from zero. The agent re-learns your build commands,
re-discovers your conventions, and re-derives the same architectural context you
explained yesterday. Memory is the missing primitive for coding agents.

Existing memory stores don't fit a developer's machine: **mem0** is
cloud-dependent, **cognee** is Python-only with no encryption at rest, **Letta**
manages memory but doesn't encrypt local storage, **Chroma** is a vector DB, not
structured agent memory. None are single-binary, zero-infra, and encrypted.

## The answer

`perseus-vault-codex` is a tiny MCP server that wraps [**Perseus Vault**](https://github.com/Perseus-Computing-LLC/perseus-vault)
— a single 12 MB binary, fully local, **AES-256-GCM encrypted at rest**, with
FTS5 keyword + hybrid recall and **no API keys, no cloud, no telemetry**. Install
it and any Codex session gains five memory tools:

| Tool | What it does |
|------|--------------|
| `perseus_remember` | Save a fact, decision, convention, or gotcha across sessions. |
| `perseus_recall` | Retrieve relevant past context (FTS5 + hybrid ranking). |
| `perseus_forget` | Remove a stale or wrong memory. |
| `perseus_reflect` | Synthesize an insight from stored memories (RAG via your OpenAI/GPT-5.6 key). |
| `perseus_status` | Store health: memory count, encryption state, DB location. |

## Install

```bash
# 1. Install the wrapper (zero Python dependencies)
pip install perseus-vault-codex            # from PyPI, or from source (below)

# 2. Install the Perseus Vault binary (single static binary, no deps) and put it on PATH
#    https://github.com/Perseus-Computing-LLC/perseus-vault/releases

# 3. Register it with Codex (non-destructive; backs up your config)
perseus-vault-codex-setup
```

**Install from source (works today, before the PyPI release):**

```bash
git clone https://github.com/Perseus-Computing-LLC/perseus-vault-codex
cd perseus-vault-codex
pip install -e .
perseus-vault-codex-setup
```

That's it. On first run the server auto-creates an encrypted vault at
`~/.perseus-vault/codex/memory.db` — **no config required**.

## Configure in Codex

`perseus-vault-codex-setup` writes this into `~/.codex/config.toml`:

```toml
[mcp_servers.perseus-vault]
command = "perseus-vault-codex"
args = []
```

Restart Codex (or start a new session) and the five `perseus_*` tools are
available. To enable `perseus_reflect` synthesis, expose your OpenAI key:

```toml
[mcp_servers.perseus-vault.env]
OPENAI_API_KEY = "sk-..."
OPENAI_MODEL = "gpt-5.6"
```

See [`examples/codex_config.toml`](examples/codex_config.toml) for every option.

## Example usage

Inside a Codex session:

```
you> Set up the project. First, check what you already know.

codex> [calls perseus_recall {"query": "project build and test conventions"}]
       I recall from a previous session:
       - This project formats with `ruff format` and lints with `ruff check`.
       - We chose SQLite + FTS5 over Postgres for the local dev store.
       Running `ruff check` before I start...

you> We just decided to switch auth to short-lived JWTs with refresh tokens in Redis.

codex> [calls perseus_remember {"category": "decision", "key": "auth",
        "text": "Auth uses short-lived JWTs; refresh tokens live in Redis."}]
       Remembered. I'll apply that convention going forward — including in
       future sessions.
```

Tomorrow, in a **brand-new session**, `perseus_recall "auth"` returns that
decision. The context survived.

### Try the demo

```bash
PERSEUS_VAULT_BIN=/path/to/perseus-vault python scripts/demo.py
```

It simulates two separate Codex sessions: session 1 learns three project facts
and tears the vault process down completely; session 2 — a fresh process —
recalls them, reflects on them, and reports encrypted status. Sample output is
in [`docs/`](docs/architecture.md).

## Architecture

```
Codex (GPT-5.6)  ──MCP stdio──▶  perseus-vault-codex  ──MCP stdio──▶  perseus-vault binary
                    5 tools        (this package)        55+ tools      SQLite+FTS5, AES-256-GCM
```

Two hops on purpose: Perseus Vault exposes 55+ low-level memory tools; this
package collapses them into five verbs a coding agent can reason about, and the
binary does the encrypted storage and retrieval. Full write-up:
[`docs/architecture.md`](docs/architecture.md).

## Benchmarks

Measured against the real `perseus-vault` binary (v2.17.0), encrypted at rest —
full methodology and reproducible harness in [`benchmarks/`](benchmarks/):

- **Recall is fast and accurate at scale.** Seeding 10,000 developer memories,
  recall runs at **p50 8 ms / p95 13 ms** with **5/5 recall@10** on distinctive
  needle memories (1,000-memory corpus: p50 1.4 ms). The recall hot path — what a
  Codex agent hits every task — stays in single/low-double-digit milliseconds.
- **Persistent memory cuts context tokens ~72%.** Over a 30-session horizon,
  recalling the top-k relevant memories per task uses **110,512 fewer tokens
  (72.5% reduction)** than re-priming each new session with the full project
  knowledge base — per-unit token costs measured with tiktoken against real vault
  recalls.

Every number is measured or explicitly labeled as a stated assumption; nothing is
hardcoded. Reproduce with `python benchmarks/bench_recall.py` and
`python benchmarks/bench_token_savings.py`.

## How Codex + GPT-5.6 built this

This integration was built **with Codex during OpenAI Build Week**, and Codex
is genuinely load-bearing in the workflow — not a footnote:

- **Scaffolding in one prompt.** Codex generated the MCP server skeleton — the
  JSON-RPC stdio loop, `initialize`/`tools/list`/`tools/call` dispatch, and the
  content/`structuredContent` envelope — from a single prompt describing the
  five-tool surface. That became `server.py`.
- **Protocol implementation.** Codex implemented the tricky parts of the MCP
  stdio transport: newline-delimited framing, the reentrant-lock handshake, and
  deadline-bounded reads with subprocess teardown so a hung vault can never wedge
  a session (`_vault_client.py`).
- **Tool translation.** Codex wrote the mapping from the five curated verbs onto
  Perseus Vault's underlying tools, including the recall-result normalization and
  the idempotent-key remember semantics (`tools.py`).
- **Test suite.** Codex produced the fake-vault fixture and the 31-test suite —
  protocol-level server tests, tool-translation tests, the config installer
  merge tests, and the real-binary integration tests (including the
  encryption-at-rest proof that plaintext never hits disk).
- **GPT-5.6 for the hard calls.** GPT-5.6 drove the architecture decisions
  (two-hop MCP design; five verbs, not fifty-five; lazy vault start so
  `tools/list` never blocks) and debugged the stdio lifecycle — specifically the
  "child accepts stdin but never emits a newline" hang, which is why reads are
  deadline-bounded on a daemon thread.
- **GPT-5.6 powers `perseus_reflect`.** The same model the agent runs on becomes
  the synthesis engine: `reflect` recalls grounding memories and asks GPT-5.6 for
  a cited answer.

The session where the core was built is referenced in
[`SUBMISSION.md`](SUBMISSION.md).

## Development

```bash
git clone https://github.com/Perseus-Computing-LLC/perseus-vault-codex
cd perseus-vault-codex
pip install -e ".[dev]"
pytest -q                                   # unit tests (no binary needed)
PERSEUS_VAULT_BIN=/path/to/perseus-vault pytest -q   # + integration tests
```

## About

Built by [Perseus Computing LLC](https://perseus.observer). Perseus Vault is the
only fully-local, encrypted memory store for AI agents, with existing
integrations for Haystack, LangChain, LlamaIndex, CrewAI, Pydantic AI, and
Google ADK. MIT licensed.
