"""Deterministic synthetic corpus of developer memories.

Generates the kind of facts a Codex agent would accumulate about a project —
conventions, decisions, gotchas, code snippets, dependencies — plus a small set
of distinctive **needles** whose retrieval we can verify (recall@k). Everything
is seeded, so a run is reproducible and a result is reproducible with it.

No network, no randomness beyond a fixed seed.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from typing import Dict, Iterator, List, Tuple

CATEGORIES = ["convention", "decision", "gotcha", "snippet", "dependency"]

_SUBJECTS = [
    "the auth service", "the billing worker", "the ingest pipeline", "the web gateway",
    "the search indexer", "the notification fanout", "the metrics collector",
    "the migration runner", "the cache layer", "the rate limiter", "the job scheduler",
    "the file uploader", "the webhook dispatcher", "the session store", "the audit log",
]
_VERBS = [
    "retries", "batches", "shards", "throttles", "debounces", "caches", "encrypts",
    "compresses", "validates", "rehydrates", "backpressures", "fans out",
]
_OBJECTS = [
    "requests to region us-east", "writes to the primary replica", "events on the bus",
    "payloads over 1MB", "tokens in the header", "rows in the outbox",
    "connections to the pool", "frames on the socket", "keys in redis",
]
_RATIONALE = [
    "because the p99 spiked under load", "to keep the working set signal-dense",
    "after the 2am incident", "so cold starts stay under 200ms",
    "to avoid the thundering-herd on deploy", "because Postgres locked up otherwise",
    "per the security review", "to keep the bill under budget",
]


@dataclass
class Memory:
    category: str
    key: str
    content: str


@dataclass
class Needle:
    category: str
    key: str
    content: str
    query: str          # a query that should retrieve this needle
    marker: str         # a rare token unique to this needle


# Distinctive needles: rare tokens ("zarqux42") make retrieval unambiguous, so
# recall@k is a true hit/miss rather than a fuzzy judgment.
def _needles() -> List[Needle]:
    specs = [
        ("convention", "commit-style",
         "All commits use the trailer 'Change-Id: zarqux42' enforced by a pre-push hook.",
         "zarqux42 commit trailer", "zarqux42"),
        ("decision", "storage-engine",
         "We chose the storage engine 'quibblestore vlex9' over Postgres for the edge cache.",
         "quibblestore vlex9 storage engine", "vlex9"),
        ("gotcha", "timezone-bug",
         "Never call normalize() before parse() — it triggers the 'plurnak' offset bug on DST.",
         "plurnak offset bug dst", "plurnak"),
        ("snippet", "retry-decorator",
         "Use @retry(marker='glimbert7') on all outbound calls; it wires in the circuit breaker.",
         "glimbert7 retry decorator circuit breaker", "glimbert7"),
        ("dependency", "pinned-lib",
         "Pin 'frobnicate==3.14.zeta' exactly; 3.15 breaks the ONNX embedding path.",
         "frobnicate zeta onnx embedding", "frobnicate"),
    ]
    return [Needle(*s) for s in specs]


def generate(n: int, *, seed: int = 1729) -> Tuple[List[Memory], List[Needle]]:
    """Return ``n`` memories (including the needles) plus the needle list.

    The needles are always present and always distinct from the filler, so a
    recall@k check is meaningful at any corpus size.
    """
    rng = random.Random(seed)
    needles = _needles()
    mems: List[Memory] = [Memory(nd.category, nd.key, nd.content) for nd in needles]

    filler = max(0, n - len(needles))
    for i in range(filler):
        cat = CATEGORIES[i % len(CATEGORIES)]
        content = (
            f"{rng.choice(_SUBJECTS)} {rng.choice(_VERBS)} {rng.choice(_OBJECTS)} "
            f"{rng.choice(_RATIONALE)} (note #{i})."
        )
        mems.append(Memory(cat, f"mem-{i:07d}", content))

    rng.shuffle(mems)
    return mems, needles


def to_remember_args(m: Memory) -> Dict[str, str]:
    return {
        "category": m.category,
        "key": m.key,
        "body_json": json.dumps({"content": m.content}),
    }


def iter_remember_args(mems: List[Memory]) -> Iterator[Dict[str, str]]:
    for m in mems:
        yield to_remember_args(m)
