"""
Fixed-window per-IP rate limit. ~25 lines instead of a dependency.

PROMPT 2 asks for slowapi. This does the same job without adding a package to a solo
founder's stack, and it lets the limitation below be stated honestly rather than inherited:

**On serverless this is per-instance, not global.** Vercel may run each request in a fresh
process, so the counter resets and the limit is advisory at best. That is equally true of
slowapi's in-memory backend — the difference is that this file says so. A real limit needs a
shared store (Redis, Supabase), which is worth adding when there is traffic to abuse it.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

_HITS: dict[str, deque[float]] = defaultdict(deque)


def check(client_ip: str, *, limit: int = 5, window_s: int = 60) -> tuple[bool, int]:
    """Returns (allowed, retry_after_seconds)."""
    now = time.monotonic()
    hits = _HITS[client_ip]
    while hits and now - hits[0] > window_s:
        hits.popleft()
    if len(hits) >= limit:
        return False, max(1, int(window_s - (now - hits[0])) + 1)
    hits.append(now)
    if len(_HITS) > 10_000:            # crude bound; a shared store makes this unnecessary
        for k in [k for k, v in _HITS.items() if not v][:5_000]:
            del _HITS[k]
    return True, 0
