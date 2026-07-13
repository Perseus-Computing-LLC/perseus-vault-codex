# Demo Video Script — Perseus Vault Codex

**Target length:** under 3:00 · **Format:** screen recording + voiceover ·
**Upload:** YouTube (unlisted or public), paste URL into `SUBMISSION.md`.

The audio **must** cover how Codex + GPT-5.6 were used — that's a judging
criterion. Lines flagged **[JUDGING]** below carry that; don't cut them.

Timings are targets. Record the terminal at a readable font size. A full dry-run
of the on-screen commands is in the shot list at the bottom.

---

### 0:00–0:20 — Hook (talking head or title card over terminal)

> "Every Codex session starts from zero. It re-learns your build commands,
> re-discovers your conventions, re-derives the context you explained an hour
> ago. Memory is the missing primitive for coding agents. This is Perseus Vault
> Codex — persistent, encrypted, local-first memory for Codex, in one install."

### 0:20–0:45 — The problem, concretely

> "There are memory stores out there, but none fit a developer's machine. mem0
> is cloud-dependent. cognee has no encryption at rest. Chroma's a vector DB,
> not agent memory. Your unreleased code and architecture shouldn't leave your
> machine in the clear. Perseus Vault is the only fully-local, encrypted answer —
> a single 12-megabyte binary, AES-256 encrypted, no cloud, no telemetry."

### 0:45–1:15 — Install & configure (screen: terminal)

Show, narrating as you go:

```bash
pip install perseus-vault-codex
perseus-vault-codex-setup
```

> "One pip install — zero Python dependencies. Then one setup command. It writes
> the MCP server into my Codex config, non-destructively, and backs up the old
> one."

Show the stanza it added in `~/.codex/config.toml`:

```toml
[mcp_servers.perseus-vault]
command = "perseus-vault-codex"
```

> "That's it. No config file to write, no database to provision. On first run it
> creates an encrypted vault in my home directory and generates the key itself."

### 1:15–2:05 — The payoff: memory across sessions (screen: `scripts/demo.py`)

Run the demo (it simulates two separate Codex sessions):

```bash
PERSEUS_VAULT_BIN=/path/to/perseus-vault python scripts/demo.py
```

Narrate over the output:

> "Session one: the agent learns three things about my project — that we format
> with ruff, that we picked SQLite and FTS5 over Postgres, and a Windows path
> gotcha. It remembers each one. Then I tear the whole vault process down —
> nothing's held in memory."
>
> "Session two — a brand-new process. I ask how we format code, why SQLite, the
> Windows bug. Every answer comes straight back out of the encrypted store. The
> context survived. Codex never forgets."

Point at the status line:

> "And it's encrypted at rest — there's a test in the repo that proves the
> memory plaintext never touches the database file on disk."

### 2:05–2:40 — How Codex + GPT-5.6 built it **[JUDGING]**

> "I built this with Codex during Build Week, and Codex did the real work. From a
> single prompt describing five tools, Codex scaffolded the whole MCP server —
> the JSON-RPC stdio loop, the tool dispatch, the response envelope. It
> implemented the tricky transport: the handshake, and deadline-bounded reads so
> a hung backend can never wedge a session. And it wrote the 31-test suite,
> including the integration tests against the real binary."
>
> "GPT-5.6 made the architecture calls — two-hop MCP, five verbs instead of the
> backend's fifty-five, lazy startup so Codex never blocks — and debugged the
> stdio lifecycle with me. And GPT-5.6 powers the product itself: the reflect
> tool uses it to synthesize insights across everything the agent has stored."

### 2:40–3:00 — Close

> "Perseus Vault Codex. One install, zero config, encrypted memory that survives
> every session. It's open source, MIT licensed, on GitHub. Give your Codex
> agent a memory."

Show on screen: `github.com/Perseus-Computing-LLC/perseus-vault-codex`

---

## Shot list / dry-run commands

```bash
# Terminal 1 — install & config
pip install perseus-vault-codex
perseus-vault-codex-setup --dry-run        # show what it writes, safely
cat ~/.codex/config.toml                    # show the stanza

# Terminal 2 — the memory demo (the money shot)
export PERSEUS_VAULT_BIN=/path/to/perseus-vault
python scripts/demo.py

# Optional — show reflect with real GPT-5.6 synthesis
export OPENAI_API_KEY=sk-...
export OPENAI_MODEL=gpt-5.6
python scripts/demo.py                       # reflect now says mode: llm-synthesis
```

**Tip:** record the `scripts/demo.py` run in a wide terminal — its section
banners (SESSION 1 / SESSION 2 / REFLECT / STATUS) frame the story on screen with
no editing required.
