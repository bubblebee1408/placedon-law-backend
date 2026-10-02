#!/usr/bin/env python3
"""Ranking metrics, as pure functions, with the denominators written down.

M3. `scripts/retrieval_recall.py` measures whether retrieval reaches the right provision at
all. These are the finer-grained questions: how far down the list, and how much of what was
wanted came back. They live here rather than in the script because they are arithmetic with
real edge cases -- ties, k past the end of the list, no relevant item, several relevant items
-- and arithmetic with edge cases belongs somewhere it can be tested against hand-computed
values.

## recall@k is NOT what this repository has been calling recall@k

`retrieval_recall.py` reports `recall@1` and `recall@5` computed as `if want & set(got)`.
That is HIT RATE: did any wanted item appear. True recall is the FRACTION of wanted items
that appeared. The two coincide when every row wants exactly one item and diverge the moment
one wants two -- and the gold set's dev rows want exactly one each today (13/13, measured
02-10-2026), which is why the existing name has never been wrong in practice and will be the
day a row names a second provision.

Both are provided, under their own names, because CLAUDE.md records this project being
burned twice by two denominators printed as though they were one. `hit_rate_at_k` is the
existing measure; `recall_at_k` is the metric M3 names.

## What nDCG@5 adds over MRR, and when it adds nothing

With BINARY relevance and ONE relevant item per query, nDCG@k = 1/log2(rank+1) and
reciprocal rank = 1/rank. Both are monotone transforms of the same rank, so they carry the
same information and differ only in how steeply they discount position. Reporting them as
two independent metrics on such a set overstates how much is being measured. They separate
only when a query has several relevant items, where nDCG rewards getting more of them high
and RR stops caring after the first.

The functions below handle the multi-relevant case correctly and are tested on it, because
the degenerate case passing is not evidence that the general one does.

## Ties

A ranker that returns a list has already broken its ties. These functions read the order
given and do not re-rank; a ranker with unstable tie-breaking will produce unstable metrics,
which is a property of the ranker and should not be hidden here.

Run: PYTHONPATH=. python3 checker/retrieval_metrics.py --test
"""
from __future__ import annotations

import math
import random

__all__ = ["recall_at_k", "hit_rate_at_k", "reciprocal_rank", "ndcg_at_k",
           "bootstrap_ci", "BOOTSTRAP_B", "BOOTSTRAP_SEED", "SMALL_SAMPLE"]

BOOTSTRAP_B = 10_000        # resamples
BOOTSTRAP_SEED = 20261002   # fixed, so a reported interval is reproducible
SMALL_SAMPLE = 30           # below this the percentile bootstrap is itself unreliable


def _rels(ranked: list, relevant) -> list[bool]:
    want = set(relevant)
    return [item in want for item in ranked]


def recall_at_k(ranked: list, relevant, k: int) -> float | None:
    """Fraction of the relevant items that appear in the top k. None if nothing is relevant.

    None rather than 0.0: a query with no relevant item has no recall to measure, and a
    0.0 would drag a mean down as though retrieval had failed at something.
    """
    want = set(relevant)
    if not want:
        return None
    return len(want & set(ranked[:k])) / len(want)


def hit_rate_at_k(ranked: list, relevant, k: int) -> float | None:
    """1.0 if ANY relevant item is in the top k. The measure already in use; see docstring."""
    want = set(relevant)
    if not want:
        return None
    return 1.0 if want & set(ranked[:k]) else 0.0


def reciprocal_rank(ranked: list, relevant, k: int | None = None) -> float | None:
    """1/rank of the FIRST relevant item, 1-indexed. 0.0 if none is in the top k."""
    want = set(relevant)
    if not want:
        return None
    for i, item in enumerate(ranked if k is None else ranked[:k], start=1):
        if item in want:
            return 1.0 / i
    return 0.0


def ndcg_at_k(ranked: list, relevant, k: int) -> float | None:
    """Normalised discounted cumulative gain at k, binary relevance.

    IDCG is taken over min(number relevant, k) positions -- the best any ranker COULD do
    given k slots -- so a query with more relevant items than slots is not scored against an
    unreachable ideal.
    """
    want = set(relevant)
    if not want or k <= 0:
        return None
    dcg = sum(1.0 / math.log2(i + 1)
              for i, hit in enumerate(_rels(ranked[:k], want), start=1) if hit)
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, min(len(want), k) + 1))
    return 0.0 if idcg == 0 else dcg / idcg


def bootstrap_ci(values, *, confidence: float = 0.95, b: int = BOOTSTRAP_B,
                 seed: int = BOOTSTRAP_SEED) -> dict:
    """Percentile bootstrap interval for the MEAN of `values`.

    Returns the point estimate, the interval, n, and `reliable` -- which is False below
    SMALL_SAMPLE. The percentile bootstrap resamples the sample it was given; at n=13 it
    reports the spread of thirteen numbers, not the spread of the population they came from,
    and an interval that looks rigorous because it has two decimal places is worse than no
    interval at all. The flag travels WITH the number so a caller cannot print one without
    the other.
    """
    vals = [v for v in values if v is not None]
    n = len(vals)
    if not n:
        return {"mean": None, "lo": None, "hi": None, "n": 0, "reliable": False,
                "note": "no measurable rows: every row had nothing relevant"}
    mean = sum(vals) / n
    if n == 1:
        return {"mean": mean, "lo": None, "hi": None, "n": 1, "reliable": False,
                "note": "n=1: an interval from one observation is not an interval"}
    rng = random.Random(seed)
    means = []
    for _ in range(b):
        means.append(sum(rng.choice(vals) for _ in range(n)) / n)
    means.sort()
    tail = (1.0 - confidence) / 2.0
    lo = means[max(0, int(tail * b) - 1)]
    hi = means[min(b - 1, int((1.0 - tail) * b))]
    return {"mean": mean, "lo": lo, "hi": hi, "n": n, "reliable": n >= SMALL_SAMPLE,
            "note": ("" if n >= SMALL_SAMPLE else
                     f"n={n} is below {SMALL_SAMPLE}: this interval describes the spread of "
                     f"{n} observations, not of the population they came from")}


def _test() -> int:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    def close(a, b, tol=1e-9) -> bool:
        return a is not None and abs(a - b) < tol

    print("retrieval_metrics")

    RANK = ["173", "96", "177", "101", "174", "103"]

    # ── recall vs hit rate: the distinction the module exists to keep ───────
    check(close(recall_at_k(RANK, {"173"}, 1), 1.0) and
          close(hit_rate_at_k(RANK, {"173"}, 1), 1.0),
          "one relevant item, found at rank 1: recall and hit rate agree, as they must")

    # Two wanted, one found in the top 3. Hit rate says 1.0 -- "yes, something came back".
    # Recall says 0.5 -- "half of what you asked for". This is the divergence.
    check(close(recall_at_k(RANK, {"173", "174"}, 3), 0.5),
          "TWO relevant, one in top 3: recall is 0.5")
    check(close(hit_rate_at_k(RANK, {"173", "174"}, 3), 1.0),
          "...and hit rate is 1.0 on the same input -- the two are different questions")
    check(close(recall_at_k(RANK, {"173", "174"}, 5), 1.0),
          "...and at k=5 recall reaches 1.0, because 174 is at rank 5")

    check(recall_at_k(RANK, set(), 5) is None and hit_rate_at_k(RANK, set(), 5) is None,
          "nothing relevant returns None, NOT 0.0 -- a query with no relevant item has no "
          "recall to measure, and a 0.0 would drag a mean down as a failure")

    check(close(recall_at_k(RANK, {"999"}, 5), 0.0),
          "a relevant item that never appears IS 0.0 -- that is a real miss, not an N/A")
    check(close(recall_at_k(RANK, {"103"}, 100), 1.0),
          "k past the end of the list does not raise or over-count")

    # ── reciprocal rank ────────────────────────────────────────────────────
    check(close(reciprocal_rank(RANK, {"177"}), 1.0 / 3),
          "reciprocal rank is 1/3 for an item at rank 3, 1-indexed")
    check(close(reciprocal_rank(RANK, {"174"}, 3), 0.0),
          "...and 0.0 when the only relevant item is below k")
    check(close(reciprocal_rank(RANK, {"174", "177"}), 1.0 / 3),
          "...and reads the FIRST relevant item only, ignoring later ones")

    # ── nDCG, against values computed by hand ──────────────────────────────
    check(close(ndcg_at_k(RANK, {"173"}, 5), 1.0),
          "nDCG@5 is 1.0 when the single relevant item is first")
    # rank 3 -> DCG = 1/log2(4) = 0.5; IDCG (1 relevant) = 1/log2(2) = 1.0
    check(close(ndcg_at_k(RANK, {"177"}, 5), 0.5),
          "nDCG@5 = 1/log2(4) = 0.5 for a lone relevant item at rank 3")
    # ranks 1 and 5 -> DCG = 1 + 1/log2(6); IDCG (2 relevant) = 1 + 1/log2(3)
    want2 = 1 + 1 / math.log2(6)
    check(close(ndcg_at_k(RANK, {"173", "174"}, 5), want2 / (1 + 1 / math.log2(3))),
          "nDCG@5 with TWO relevant at ranks 1 and 5 matches the hand computation")
    # IDCG is capped at k slots, not at the number relevant
    check(close(ndcg_at_k(["173"], {"173", "174", "177"}, 1), 1.0),
          "three relevant and only ONE slot: nDCG is 1.0, because IDCG is taken over "
          "min(relevant, k) -- a ranker is not scored against an unreachable ideal")
    check(ndcg_at_k(RANK, {"173"}, 0) is None,
          "k=0 returns None rather than dividing by a zero ideal")

    # ── nDCG and RR carry the same information at one relevant item ─────────
    # Stated in the docstring, so it is asserted rather than claimed.
    singles = [ndcg_at_k(RANK, {s}, 6) for s in RANK]
    rrs = [reciprocal_rank(RANK, {s}, 6) for s in RANK]
    order_ndcg = [i for i, _ in sorted(enumerate(singles), key=lambda p: -p[1])]
    order_rr = [i for i, _ in sorted(enumerate(rrs), key=lambda p: -p[1])]
    check(order_ndcg == order_rr and singles != rrs,
          "with ONE relevant item nDCG and RR rank queries identically while differing in "
          "value -- same information, different discount, as the docstring says")
    # ...and they genuinely separate when a query has several relevant items.
    a = (ndcg_at_k(RANK, {"173", "174"}, 5), reciprocal_rank(RANK, {"173", "174"}, 5))
    b = (ndcg_at_k(RANK, {"173", "96"}, 5), reciprocal_rank(RANK, {"173", "96"}, 5))
    check(a[1] == b[1] and a[0] != b[0],
          "...and they SEPARATE on multi-relevant queries: identical RR, different nDCG, "
          "which is what nDCG is for")

    # ── bootstrap ──────────────────────────────────────────────────────────
    ci = bootstrap_ci([1.0] * 20)
    check(close(ci["mean"], 1.0) and close(ci["lo"], 1.0) and close(ci["hi"], 1.0),
          "a constant sample gives a zero-width interval, not a spurious spread")

    ci = bootstrap_ci([0.0, 1.0] * 25)
    check(ci["lo"] < 0.5 < ci["hi"] and ci["n"] == 50,
          f"a half-and-half sample brackets 0.5 ({ci['lo']:.2f}-{ci['hi']:.2f})")
    check(ci["reliable"] is True, "...and n=50 is marked reliable")

    small = bootstrap_ci([1.0, 0.0, 1.0] * 4 + [0.5])
    check(small["n"] == 13 and small["reliable"] is False and "below" in small["note"],
          f"n=13 is marked NOT reliable and says why -- the dev split's real size, and an "
          f"interval that looks rigorous because it has two decimals is worse than none "
          f"({small['note'][:40]}...)")

    check(bootstrap_ci([])["mean"] is None and "no measurable rows" in bootstrap_ci([])["note"],
          "an empty sample returns None with a reason, never 0.0")
    check(bootstrap_ci([0.7])["lo"] is None and bootstrap_ci([0.7])["n"] == 1,
          "n=1 reports the mean but refuses an interval")
    check(bootstrap_ci([None, 1.0, None, 0.0])["n"] == 2,
          "None values are EXCLUDED from the sample, not coerced to 0.0")

    r1 = bootstrap_ci([1.0, 0.0, 1.0, 0.5] * 3)
    r2 = bootstrap_ci([1.0, 0.0, 1.0, 0.5] * 3)
    check((r1["lo"], r1["hi"]) == (r2["lo"], r2["hi"]),
          "the interval is REPRODUCIBLE -- the seed is fixed, so a number in a report can "
          "be checked later")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(_test())
