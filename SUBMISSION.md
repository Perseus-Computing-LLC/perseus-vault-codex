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

Codex was used as an implementation and verification partner during Build Week.
This final review session does not claim authorship of the pre-existing core; it
read the complete implementation and test suite, then independently exercised
and hardened it.

- **Reviewed the real integration.** Codex traced the Codex-facing JSON-RPC
  server, five-verb translation layer, zero-config setup, and the vendored client
  that starts the `perseus-vault` subprocess.
- **Verified, rather than assumed.** It ran all 33 tests against
  `perseus-vault 2.17.0`, ran the two-session demo, and confirmed a memory saved
  before a complete client teardown was recalled by a new client.
- **Checked encryption at rest directly.** It wrote a unique marker to the
  default `~/.perseus-vault/codex/memory.db`, read the database as raw bytes, and
  confirmed that marker was absent before soft-deleting the audit memory.
- **Hardened a transport edge case.** On an unexpected vault stdout EOF, the
  client now tears down its unusable subprocess before raising. A regression test
  confirms the next call can auto-respawn instead of repeatedly receiving EOF.
- **Measured and challenged the benchmarks.** Codex ran the real encrypted-vault
  benchmarks and documented their limits: latency/recall numbers apply to the
  supplied synthetic workload; the token-savings percentage is scenario
  modeling, not a universal observed outcome.

`perseus_reflect` can use the user's configured OpenAI-compatible model to
synthesize recalled memories; it falls back to inspectable context when no LLM
endpoint is configured.

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
- A real, non-trivial MCP integration with a 33-test suite, verified end-to-end
  against the real Perseus Vault binary.
- **Measured benchmarks, not claims** (`benchmarks/`): recall at **p50 7 ms /
  5-of-5 recall@10 on a 10k-memory corpus**, and a **72.5% context-token
  reduction** over a 30-session horizon vs. re-priming each session — every
  figure measured against the real binary or labeled as a stated assumption.
- **Validated at 1,000,000 memories** on a 2× H100 run (engine-scale, GPU
  embedding): **hybrid recall@5 = recall@10 = 1.00** at sub-second p50 latency,
  0 embedding errors. Reported separately from the laptop numbers and with its
  caveats stated (semantic workload; keyword-only recall near-zero; sub-second
  not sub-10ms). Verbatim data in `benchmarks/results/scale_1m_2xh100.json`.

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
