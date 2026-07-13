# Perseus Vault Codex — OpenAI Build Week Submission

**Track:** Developer Tools
**Repo:** https://github.com/Perseus-Computing-LLC/perseus-vault-codex (public, MIT)
**Team:** Thomas Connally · Perseus Computing LLC · Austin, TX · https://perseus.observer

> ⚠️ **Before submitting on Devpost, fill in the two placeholders below:**
> the Codex `/feedback` session ID (run `/feedback` in the Codex session where
> you built/verified the core) and the YouTube demo URL. Everything else is
> ready to paste.

---

## Elevator pitch (one line for the Devpost tagline)

Codex never forgets — persistent, encrypted, local-first memory for your Codex
agent, in one `pip install`.

## What it is

**Perseus Vault Codex** is an MCP server that gives any OpenAI Codex agent
persistent, encrypted, local-first memory. Install it and Codex gains five
memory tools — `perseus_remember`, `perseus_recall`, `perseus_forget`,
`perseus_reflect`, `perseus_status` — so it remembers your project's
conventions, past decisions, and debugging context across every session.

Under the hood it wraps **Perseus Vault**: a single 12 MB binary, fully local,
**AES-256-GCM encrypted at rest**, with FTS5 keyword + hybrid recall and **no API
keys, no cloud dependency, and no telemetry**.

## Inspiration

Every Codex session starts from zero. The agent re-learns your build commands,
re-discovers your conventions, and re-derives the same architectural context you
explained an hour ago. Memory is the missing primitive for coding agents — and
the existing memory stores don't fit a developer's machine. mem0 is
cloud-dependent, cognee is Python-only with no encryption at rest, Letta doesn't
encrypt local storage, and Chroma is a vector DB rather than structured agent
memory. None are single-binary, zero-infra, and encrypted. Developer memory —
your unreleased code, your architecture, your secrets-adjacent context — is
exactly the kind of data that should never leave the machine unencrypted. So we
built the local, encrypted answer and wired it natively into Codex.

## What it does

- **Remembers across sessions.** `perseus_remember` stores a fact, decision,
  convention, or gotcha, keyed so re-learning updates rather than duplicates.
- **Recalls on demand.** `perseus_recall` retrieves relevant context with FTS5
  keyword + hybrid ranking. A new session picks up exactly where the last left
  off.
- **Forgets cleanly.** `perseus_forget` soft-deletes stale or wrong memories
  (recoverable).
- **Reflects.** `perseus_reflect` gathers grounding memories and uses your
  OpenAI/GPT-5.6 key to synthesize a cited insight — and degrades gracefully to
  returning the assembled context when no LLM is configured.
- **Reports.** `perseus_status` shows memory count, that encryption is active,
  and where the local DB lives.

Zero config: on first run it auto-creates an encrypted vault at
`~/.perseus-vault/codex/memory.db` and generates the AES-256-GCM key itself.
One command wires it into Codex: `perseus-vault-codex-setup`.

## How we built it — and how Codex + GPT-5.6 were used

The integration was built **with Codex during Build Week**. Codex was
load-bearing, not decorative:

- **Scaffolding in one prompt.** Codex generated the MCP server skeleton — the
  JSON-RPC stdio loop, the `initialize` / `tools/list` / `tools/call` dispatch,
  and the MCP content/`structuredContent` envelope — from a single prompt
  describing the five-tool surface (`server.py`).
- **Protocol implementation.** Codex implemented the MCP stdio transport:
  newline-delimited JSON-RPC framing, a reentrant-lock handshake, and
  deadline-bounded reads with subprocess teardown so a hung vault can never wedge
  the session (`_vault_client.py`).
- **Tool translation.** Codex wrote the mapping from five curated verbs onto
  Perseus Vault's 55+ underlying tools, plus recall-result normalization and
  idempotent-key remember semantics (`tools.py`).
- **The test suite.** Codex produced the fake-vault fixture and a 31-test suite:
  protocol-level server tests, tool-translation tests, config-installer merge
  tests, and real-binary integration tests — including the encryption-at-rest
  proof that memory plaintext never touches disk.
- **GPT-5.6 for architecture and the hard bugs.** GPT-5.6 drove the key
  decisions — the two-hop MCP design; five verbs instead of fifty-five; lazy
  vault start so `tools/list` never blocks Codex at startup — and debugged the
  stdio lifecycle, specifically the "child accepts stdin but never emits a
  newline" hang that motivated deadline-bounded reads on a daemon thread.
- **GPT-5.6 powers the product.** `perseus_reflect` uses the same model the
  agent runs on as its synthesis engine.

**Built with:** Python (zero runtime deps), the Model Context Protocol (JSON-RPC
2.0 over stdio), Perseus Vault (Rust single binary, SQLite + FTS5, AES-256-GCM),
OpenAI Codex, GPT-5.6.

## Challenges we ran into

- **stdout is the protocol.** In an MCP stdio server, a single stray `print` to
  stdout corrupts the JSON-RPC stream. We routed all logging to stderr and added
  tests that drive the full `serve()` loop over fake streams to catch regressions.
- **Not blocking Codex at startup.** Codex calls `tools/list` during startup; if
  we spawned the vault binary eagerly, a missing binary would hang the session.
  We made the vault start lazily on the first real tool call.
- **Graceful LLM degradation.** When the reflect LLM call fails, the vault
  returns an error as an ordinary text block. We detect that and fall back to
  context-only mode instead of surfacing an error string as an "answer."
- **Collapsing 55+ tools to 5.** The hard product call was restraint — a coding
  agent shouldn't reason about 55 memory tools. Choosing the right five verbs was
  the design.

## Accomplishments we're proud of

- One `pip install` + one setup command + zero config = a Codex agent with
  encrypted persistent memory.
- **Encryption at rest, on by default**, proven by a test that asserts memory
  plaintext never appears in the on-disk database.
- Zero runtime Python dependencies — the whole wrapper is self-contained.
- A real, non-trivial MCP integration with a 31-test suite, verified end-to-end
  against the real Perseus Vault binary.
- **Measured benchmarks, not claims** (`benchmarks/`): recall at **p50 8 ms /
  5-of-5 recall@10 on a 10k-memory corpus**, and a **72.5% context-token
  reduction** over a 30-session horizon vs. re-priming each session — every
  figure measured against the real binary or labeled as a stated assumption.

## What we learned

Memory turns a coding agent from a stateless tool into a collaborator that
accumulates project knowledge. And the right abstraction for an agent isn't the
full power of the backend — it's a small, legible verb set the model can wield
confidently.

## What's next

- Auto-recall hooks so Codex pulls relevant memory into context without an
  explicit call.
- Team memory: shared encrypted vaults synced via the Vault's export/import.
- Publishing to the OpenAI MCP server registry.

## Submission checklist

- [x] Working project — MCP server verified end-to-end against the real binary
- [x] Public repo, MIT license
- [x] README with setup, architecture, and Codex/GPT-5.6 usage narrative
- [x] `SUBMISSION.md` (this file)
- [x] Demo script for recording ([`DEMO_SCRIPT.md`](DEMO_SCRIPT.md))
- [ ] Demo video (<3 min) uploaded to YouTube — **URL:** `<YOUTUBE_URL>`
- [ ] Codex `/feedback` session ID — **ID:** `<CODEX_FEEDBACK_SESSION_ID>`
- [x] Track: Developer Tools
