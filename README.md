# Perseus Vault Codex

**Persistent, encrypted, local-first memory for OpenAI Codex agents.**

> Codex never forgets. Perseus Vault gives your Codex agent persistent encrypted
> memory — so it remembers your project conventions, past decisions, and
> debugging context across every session.

[![CI](https://github.com/Perseus-Computing-LLC/perseus-vault-codex/actions/workflows/ci.yml/badge.svg)](https://github.com/Perseus-Computing-LLC/perseus-vault-codex/actions/workflows/ci.yml)
License: MIT | Built for **OpenAI Build Week** — Developer Tools track

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
  recall runs at **p50 7 ms** (p95 27 ms) with **5/5 recall@10** on distinctive
  needle memories (1,000-memory corpus: p50 1.3 ms). The recall hot path — what a
  Codex agent hits every task — stays in single/low-double-digit milliseconds.
- **The engine scales to 1,000,000 memories.** A separate 2× H100 validation
  (run `#619`, [`results/scale_1m_2xh100.json`](benchmarks/results/scale_1m_2xh100.json))
  embedded ~1M memories (995,562 persisted, 0 errors) and hit **hybrid recall@5 =
  recall@10 = 1.00** over 2,000 semantic queries, at sub-second latency (p50
  479 ms). This is an engine-scale result on GPU, not the laptop path — reported
  separately and honestly (keyword-only recall is near-zero on that semantic
  workload; hybrid carries it).
- **Persistent memory cuts context tokens ~72%.** Over a 30-session horizon,
  recalling the top-k relevant memories per task uses **110,493 fewer tokens
  (72.5% reduction)** than re-priming each new session with the full project
  knowledge base — per-unit token costs measured with tiktoken against real vault
  recalls.

Every number is measured or explicitly labeled as a stated assumption; nothing is
hardcoded. Reproduce with `python benchmarks/bench_recall.py` and
`python benchmarks/bench_token_savings.py`.

## How Codex was used

Codex was used during Build Week as an implementation and verification partner.
In the final review session, it read the complete wrapper and its tests, ran the
suite against the real `perseus-vault 2.17.0` binary, exercised the two-session
demo, and checked a unique marker was absent from the raw default database file.
It also hardened stdout-EOF recovery in the subprocess client and added a
regression test. Those are review-session contributions; this README does not
attribute all pre-existing code to that session.

See [`SUBMISSION.md`](SUBMISSION.md) for the precise verification record and
benchmark caveats.

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
