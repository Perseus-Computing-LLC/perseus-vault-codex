#!/usr/bin/env python3
"""Recall latency + recall@k benchmark for the memory store behind Codex.

For each corpus size we: seed N synthetic developer memories into a fresh
encrypted vault (measuring ingest throughput), then issue a mix of recall
queries (measuring wall-clock latency percentiles), and finally verify that the
distinctive "needle" memories are retrieved in the top-k (recall@k).

Honesty rules baked in:
  * Every number is measured against the real perseus-vault binary — nothing is
    modeled or hardcoded. If the binary is missing, the script errors, it does
    not emit a number.
  * The vault process is warmed (one untimed call) before latency sampling so
    the subprocess spawn does not pollute the first sample.
  * Results are written with the exact config (binary version, sizes, seed,
    query count) so the row is reproducible.

Usage:
    PERSEUS_VAULT_BIN=/path/to/perseus-vault python benchmarks/bench_recall.py
    ... --sizes 1000,10000,100000 --queries 200 --out benchmarks/results/recall.json
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from perseus_vault_codex._vault_client import VaultClient  # noqa: E402
from perseus_vault_codex.config import load_config  # noqa: E402
import _corpus  # noqa: E402


def _pct(sorted_vals, p):
    if not sorted_vals:
        return None
    k = min(len(sorted_vals) - 1, int(round((p / 100.0) * (len(sorted_vals) - 1))))
    return sorted_vals[k]


def _binary_version(binary: str) -> str:
    try:
        out = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=15)
        return (out.stdout or out.stderr).strip()
    except Exception:
        return "unknown"


def bench_size(cfg, size: int, queries: int, seed: int) -> dict:
    mems, needles = _corpus.generate(size, seed=seed)

    db = os.path.join(tempfile.mkdtemp(prefix=f"pvbench-{size}-"), "memory.db")
    scfg = load_config(db_path=db, encrypt=cfg.encrypted)

    with VaultClient(
        binary=scfg.binary, db_path=scfg.db_path, encryption_key=scfg.encryption_key,
        timeout=120.0,
    ) as v:
        # --- ingest -------------------------------------------------------
        t0 = time.perf_counter()
        for args in _corpus.iter_remember_args(mems):
            v.call_tool("perseus_vault_remember", args)
        ingest_s = time.perf_counter() - t0

        total = v.call_tool("perseus_vault_stats", {}).get("total_entities")

        # --- warm up ------------------------------------------------------
        v.call_tool("perseus_vault_recall", {"query": "widget region retries", "limit": 5, "mode": "hybrid"})

        # --- latency ------------------------------------------------------
        # Build a query workload from needle queries + generic filler queries.
        workload = [nd.query for nd in needles]
        generic = [
            "auth service retries region", "billing worker batches events",
            "cache layer p99 under load", "rate limiter tokens header",
            "migration runner primary replica", "webhook dispatcher outbox rows",
        ]
        i = 0
        lat_ms = []
        while len(lat_ms) < queries:
            q = (workload + generic)[i % (len(workload) + len(generic))]
            t = time.perf_counter()
            v.call_tool("perseus_vault_recall", {"query": q, "limit": 10, "mode": "hybrid"})
            lat_ms.append((time.perf_counter() - t) * 1000.0)
            i += 1
        lat_ms.sort()

        # --- recall@k -----------------------------------------------------
        hits_at_10 = 0
        for nd in needles:
            res = v.call_tool("perseus_vault_recall", {"query": nd.query, "limit": 10, "mode": "hybrid"})
            items = res.get("items", []) if isinstance(res, dict) else []
            found = any(
                nd.marker.lower() in (json.dumps(it).lower()) for it in items
            )
            hits_at_10 += 1 if found else 0

    return {
        "size": size,
        "entities_stored": total,
        "ingest_seconds": round(ingest_s, 3),
        "ingest_per_sec": round(size / ingest_s, 1) if ingest_s else None,
        "recall_queries": len(lat_ms),
        "recall_latency_ms": {
            "p50": round(_pct(lat_ms, 50), 3),
            "p95": round(_pct(lat_ms, 95), 3),
            "p99": round(_pct(lat_ms, 99), 3),
            "mean": round(statistics.fmean(lat_ms), 3),
            "max": round(lat_ms[-1], 3),
        },
        "needles": len(needles),
        "recall_at_10": f"{hits_at_10}/{len(needles)}",
        "recall_at_10_frac": round(hits_at_10 / len(needles), 3),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sizes", default="1000,10000",
                    help="Comma-separated corpus sizes (default 1000,10000).")
    ap.add_argument("--queries", type=int, default=200,
                    help="Recall queries to time per size (default 200).")
    ap.add_argument("--seed", type=int, default=1729)
    ap.add_argument("--out", default="benchmarks/results/recall.json")
    ap.add_argument("--plaintext", action="store_true",
                    help="Run without encryption (default: encrypted at rest).")
    ns = ap.parse_args()

    cfg = load_config(encrypt=not ns.plaintext)
    version = _binary_version(cfg.binary)
    if version == "unknown" or not version:
        print("ERROR: perseus-vault binary not runnable. Set PERSEUS_VAULT_BIN.",
              file=sys.stderr)
        sys.exit(1)

    sizes = [int(s) for s in ns.sizes.split(",") if s.strip()]
    print(f"perseus-vault: {version}")
    print(f"encrypted at rest: {not ns.plaintext}")
    print(f"sizes: {sizes} | queries/size: {ns.queries} | seed: {ns.seed}\n")

    rows = []
    for size in sizes:
        print(f"[{size}] seeding + measuring ...", flush=True)
        row = bench_size(cfg, size, ns.queries, ns.seed)
        rows.append(row)
        lm = row["recall_latency_ms"]
        print(f"[{size}] ingest {row['ingest_per_sec']}/s | "
              f"recall p50 {lm['p50']}ms p95 {lm['p95']}ms p99 {lm['p99']}ms | "
              f"recall@10 {row['recall_at_10']}\n", flush=True)

    report = {
        "benchmark": "recall_latency_and_accuracy",
        "engine": "perseus-vault",
        "binary_version": version,
        "encrypted_at_rest": not ns.plaintext,
        "seed": ns.seed,
        "queries_per_size": ns.queries,
        "data_source": "measured",
        "results": rows,
    }
    out = Path(ns.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
