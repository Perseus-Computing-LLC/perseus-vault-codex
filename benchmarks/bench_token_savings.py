#!/usr/bin/env python3
"""Cross-session token-savings benchmark.

The core value of persistent memory for a coding agent is *not* speed — it's
that a new session doesn't have to be re-primed with everything the agent
already learned. This benchmark quantifies that.

Two regimes over a horizon of `sessions` × `tasks_per_session`:

  * **Re-prime baseline** — with no persistent memory, each session is bootstrapped
    with the whole durable project knowledge base (conventions, decisions,
    architecture) so the agent "knows the project". Cost = tokens(KB) per session.
  * **Recall-on-demand (Perseus Vault)** — the KB lives in the vault; per task the
    agent recalls the top-k relevant memories. Cost = tokens(query) +
    tokens(retrieved) per task.

What's measured vs modeled (stated plainly, no hand-waving):
  * MEASURED: the KB token count, and the **actual tokens the vault returns** for
    each recall (we run real recalls against the real binary and count the real
    payload with tiktoken).
  * MODELED: the horizon (how many sessions/tasks) — a parameter you set. The
    per-unit costs are real; the multiplier is your assumption.

Token counting uses tiktoken when available; otherwise a clearly-labeled
chars/4 approximation.

Usage:
    PERSEUS_VAULT_BIN=/path/to/perseus-vault python benchmarks/bench_token_savings.py
    ... --kb 200 --sessions 30 --tasks 8 --k 8 --out benchmarks/results/token_savings.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from perseus_vault_codex._vault_client import VaultClient  # noqa: E402
from perseus_vault_codex.config import load_config  # noqa: E402
import _corpus  # noqa: E402


def _item_text(it: dict) -> str:
    """Best-effort extraction of a recall item's content text."""
    if it.get("content"):
        return it["content"]
    if it.get("summary"):
        return it["summary"]
    body = it.get("body_json")
    if body:
        try:
            return json.loads(body).get("content", "")
        except (json.JSONDecodeError, TypeError):
            return str(body)
    return ""


def _make_counter():
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return (lambda s: len(enc.encode(s))), "tiktoken/cl100k_base (measured)"
    except Exception:
        return (lambda s: max(1, len(s) // 4)), "chars/4 approximation (tiktoken unavailable)"


TASK_QUERIES = [
    "how do we format and lint code here",
    "what did we decide about the storage engine",
    "auth service retry and failover behavior",
    "how should I write commit messages",
    "known timezone or DST bugs to avoid",
    "which library versions are pinned and why",
    "how does the cache layer behave under load",
    "rate limiting and header token rules",
    "the retry decorator and circuit breaker pattern",
    "billing worker batching of events",
]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kb", type=int, default=200,
                    help="Size of the durable project knowledge base (default 200).")
    ap.add_argument("--sessions", type=int, default=30,
                    help="Number of Codex sessions in the horizon (default 30).")
    ap.add_argument("--tasks", type=int, default=8,
                    help="Tasks (recalls) per session (default 8).")
    ap.add_argument("--k", type=int, default=8, help="Memories recalled per task (default 8).")
    ap.add_argument("--seed", type=int, default=1729)
    ap.add_argument("--out", default="benchmarks/results/token_savings.json")
    ns = ap.parse_args()

    count, counter_desc = _make_counter()
    mems, _needles = _corpus.generate(ns.kb, seed=ns.seed)

    # The re-prime baseline: the full KB an agent would be bootstrapped with each
    # session, rendered as a bulleted context block (measured token count).
    kb_block = "\n".join(f"- [{m.category}] {m.content}" for m in mems)
    kb_tokens = count(kb_block)

    cfg = load_config(encrypt=True)
    db = os.path.join(tempfile.mkdtemp(prefix="pv-tok-"), "memory.db")
    scfg = load_config(db_path=db, encrypt=True)

    per_task_tokens = []
    with VaultClient(binary=scfg.binary, db_path=scfg.db_path,
                     encryption_key=scfg.encryption_key, timeout=120.0) as v:
        for args in _corpus.iter_remember_args(mems):
            v.call_tool("perseus_vault_remember", args)
        v.call_tool("perseus_vault_recall", {"query": "warmup", "limit": ns.k, "mode": "hybrid"})

        # Measure the ACTUAL tokens returned per recall (query + retrieved content).
        for i in range(ns.sessions * ns.tasks):
            q = TASK_QUERIES[i % len(TASK_QUERIES)]
            res = v.call_tool("perseus_vault_recall", {"query": q, "limit": ns.k, "mode": "hybrid"})
            items = res.get("items", []) if isinstance(res, dict) else []
            retrieved = "\n".join(_item_text(it) for it in items)
            per_task_tokens.append(count(q) + count(retrieved))

    n_tasks = ns.sessions * ns.tasks
    baseline_total = kb_tokens * ns.sessions                       # re-prime every session
    memory_total = sum(per_task_tokens)                            # recall per task
    saved = baseline_total - memory_total
    avg_task = sum(per_task_tokens) / len(per_task_tokens)

    report = {
        "benchmark": "cross_session_token_savings",
        "engine": "perseus-vault",
        "binary_version": _version(scfg.binary),
        "token_counter": counter_desc,
        "assumptions": {
            "kb_memories": ns.kb,
            "sessions": ns.sessions,
            "tasks_per_session": ns.tasks,
            "recall_k": ns.k,
        },
        "measured": {
            "kb_tokens_full_context": kb_tokens,
            "avg_tokens_per_recall": round(avg_task, 1),
        },
        "totals_over_horizon": {
            "reprime_baseline_tokens": baseline_total,
            "recall_on_demand_tokens": memory_total,
            "tokens_saved": saved,
            "reduction_pct": round(100.0 * saved / baseline_total, 1) if baseline_total else None,
        },
        "note": (
            "Per-unit token costs are measured against the real binary; the "
            "horizon (sessions x tasks) is a stated assumption, not a measurement."
        ),
    }
    Path(ns.out).parent.mkdir(parents=True, exist_ok=True)
    Path(ns.out).write_text(json.dumps(report, indent=2), encoding="utf-8")

    t = report["totals_over_horizon"]
    print(f"token counter : {counter_desc}")
    print(f"KB ({ns.kb} memories) full-context tokens : {kb_tokens:,}")
    print(f"avg tokens per recall (k={ns.k})          : {report['measured']['avg_tokens_per_recall']:,}")
    print(f"horizon: {ns.sessions} sessions x {ns.tasks} tasks = {n_tasks} tasks")
    print(f"re-prime baseline : {t['reprime_baseline_tokens']:,} tokens")
    print(f"recall-on-demand  : {t['recall_on_demand_tokens']:,} tokens")
    print(f"SAVED             : {t['tokens_saved']:,} tokens  ({t['reduction_pct']}% reduction)")
    print(f"wrote {ns.out}")


def _version(binary: str) -> str:
    import subprocess
    try:
        o = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=15)
        return (o.stdout or o.stderr).strip()
    except Exception:
        return "unknown"


if __name__ == "__main__":
    main()
