# AGENTS.md — guidance for Codex working in this repo

This file is read by Codex to understand the project. It also documents how the
memory tools this package provides should be used by an agent.

## What this project is

`perseus-vault-codex` is an MCP stdio server that gives a Codex agent persistent,
encrypted, local-first memory by wrapping the [Perseus Vault](https://github.com/Perseus-Computing-LLC/perseus-vault)
binary. It exposes five tools: `perseus_remember`, `perseus_recall`,
`perseus_forget`, `perseus_reflect`, `perseus_status`.

## Using the memory tools (for any Codex agent with this server installed)

- **At the start of a task**, call `perseus_recall` with a short description of
  what you're about to do. Pull in past decisions, conventions, and gotchas.
- **When you learn something durable** — a build command, a code-style rule, an
  architectural decision, a non-obvious gotcha, a user preference — call
  `perseus_remember`. Use a stable `key` so re-learning updates rather than
  duplicates.
- **When a memory is wrong or stale**, `perseus_forget` it by key.
- **To synthesize across many memories**, use `perseus_reflect`.
- Memories persist across sessions and are encrypted at rest. Do not store
  secrets you wouldn't want in a local encrypted DB.

## Developing this package

- Python ≥ 3.9, zero runtime dependencies (the stdio transport is vendored in
  `src/perseus_vault_codex/_vault_client.py`).
- Run tests: `pytest -q`. Unit tests use a fake vault client and need no binary.
  Integration tests run only when `PERSEUS_VAULT_BIN` points at a real
  `perseus-vault` binary (or it's on PATH).
- **stdout is the JSON-RPC channel** — never `print()` to stdout in the server
  path; log to stderr via the `_log` helpers.
- The curated tool schemas live in `tools.py::TOOL_SCHEMAS`; keep the surface at
  five tools — that minimalism is the point.
