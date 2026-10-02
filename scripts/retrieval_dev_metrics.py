#!/usr/bin/env python3
"""recall@1/5/10, MRR and nDCG@5 on the dev split, with bootstrap intervals.

M3. `scripts/retrieval_recall.py` answers "does the right provision come back at all". This
answers "how far down, and how much of it" -- and puts an interval on every number, because
the dev split is 13 rows and a point estimate from 13 rows invites a decision the sample
cannot support.

## The held-out split is not read here

`eval/goldset/split.py` decides which rows are dev. This reads dev only, via
`retrieval_recall.dev_runs`, and never opens a held-out row -- the test asserts it, because
a metric that quietly improved by reading the held-out set is the one thing the split exists
to prevent.

## What 13 rows can and cannot support

Every interval below is marked `reliable: false`. That is not a formality:

  * The percentile bootstrap resamples the sample it was handed. At n=13 it describes the
    spread of thirteen numbers, not of the population they came from.
  * All 13 dev rows name EXACTLY ONE provision (measured 02-10-2026). So on this set
    recall@k equals hit rate, and nDCG@5 is a monotone transform of reciprocal rank -- the
    four metrics M3 asks for carry fewer independent degrees of freedom than four. They
    separate when a row names two provisions, and none does yet.

So the numbers are reported with their denominators and their caveats attached, and nothing
here is an accuracy claim.

## The title floor, and why it is shown alongside

Every section's own heading is a query whose right answer is that section -- the trick
`retrieval_recall.py` introduced to get a sample without an answer key. That gives ~500
queries instead of 13, so its intervals mean something. It is a MECHANICAL FLOOR, not a
substitute for practitioner questions: a heading shares vocabulary with its own section in a
way a real question does not, so it measures the easiest possible case. Shown because an
interval over 13 rows and an interval over 500 answer different questions, and reporting
only the first would leave the wide one looking like the best available.

Run: PYTHONPATH=. python3 scripts/retrieval_dev_metrics.py
     PYTHONPATH=. python3 scripts/retrieval_dev_metrics.py --json
"""
from __future__ import annotations

import json
import sys

RECALL_KS = (1, 5, 10)
NDCG_K = 5
TOP_K = 10              # the deepest k any metric here needs


def _metrics(runs: list[dict], *, label: str, caveat: str = "") -> dict:
    from checker.retrieval_metrics import (bootstrap_ci, hit_rate_at_k, ndcg_at_k,
                                           recall_at_k, reciprocal_rank)

    out = {"set": label, "queries": len(runs), "caveat": caveat, "metrics": {}}
    for k in RECALL_KS:
        out["metrics"][f"recall@{k}"] = bootstrap_ci(
            [recall_at_k(r["ranked"], r["want"], k) for r in runs])
        out["metrics"][f"hit_rate@{k}"] = bootstrap_ci(
            [hit_rate_at_k(r["ranked"], r["want"], k) for r in runs])
    out["metrics"]["MRR"] = bootstrap_ci(
        [reciprocal_rank(r["ranked"], r["want"], TOP_K) for r in runs])
    out["metrics"][f"nDCG@{NDCG_K}"] = bootstrap_ci(
        [ndcg_at_k(r["ranked"], r["want"], NDCG_K) for r in runs])

    # Does recall differ from hit rate on this set at all? If not, say so rather than let a
    # reader believe two independent things were measured.
    same = all(abs(out["metrics"][f"recall@{k}"]["mean"]
                   - out["metrics"][f"hit_rate@{k}"]["mean"]) < 1e-12
               for k in RECALL_KS
               if out["metrics"][f"recall@{k}"]["mean"] is not None)
    multi = sum(1 for r in runs if len(set(r["want"])) > 1)
    out["recall_equals_hit_rate"] = same
    out["multi_relevant_queries"] = multi
    out["degrees_of_freedom_note"] = (
        f"{multi} of {len(runs)} queries name more than one provision. "
        + ("With one relevant item per query, recall@k IS hit rate and nDCG@5 is a monotone "
           "transform of reciprocal rank: fewer independent metrics than the count suggests."
           if not multi else
           "recall@k and nDCG separate from hit rate and MRR on the multi-relevant rows."))
    return out


def dev_metrics() -> dict:
    from scripts.retrieval_recall import dev_runs
    return _metrics(dev_runs(top_k=TOP_K), label="gold dev rows",
                    caveat=("Practitioner questions, but only 13 of them. Every interval "
                            "here is marked unreliable and the reason travels with it."))


def title_metrics(limit: int = 0) -> dict:
    """The mechanical floor: each section's heading as a query for that section."""
    from checker.text_search import search
    from scripts.retrieval_recall import live_sections

    rows = live_sections()
    runs = []
    for number, title in (rows[:limit] if limit else rows):
        runs.append({"question_id": f"title-{number}", "question": title,
                     "want": [number],
                     "ranked": [h["section_number"] for h in search(title, top_k=TOP_K)]})
    return _metrics(runs, label="section headings (mechanical floor)",
                    caveat=("A heading shares vocabulary with its own section in a way a "
                            "real question does not. This is the EASIEST case, not a "
                            "substitute for practitioner questions."))


def measure(*, title_limit: int = 0) -> dict:
    return {"dev": dev_metrics(), "title_floor": title_metrics(limit=title_limit),
            "held_out_read": False}


def report(r: dict) -> str:
    import textwrap
    lines = []
    for key in ("dev", "title_floor"):
        s = r[key]
        lines.append(f"  {s['set']}  (n={s['queries']})")
        for chunk in textwrap.wrap(s["caveat"], 84):
            lines.append(f"    | {chunk}")
        for name, m in s["metrics"].items():
            if m["mean"] is None:
                lines.append(f"    {name:<13} not measured: {m['note'][:50]}")
                continue
            ci = ("" if m["lo"] is None
                  else f"  95% CI [{m['lo']:.3f}, {m['hi']:.3f}]")
            flag = "" if m["reliable"] else "   (n too small: interval not reliable)"
            lines.append(f"    {name:<13} {m['mean']:.3f}{ci}{flag}")
        for chunk in textwrap.wrap(s["degrees_of_freedom_note"], 84):
            lines.append(f"    > {chunk}")
        lines.append("")
    lines.append("  The held-out split was not read. No number here is an accuracy claim.")
    return "\n".join(lines)


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

    print("retrieval_dev_metrics")

    d = dev_metrics()
    check(d["queries"] > 0, f"the dev split yields ranked runs ({d['queries']})")
    check(set(d["metrics"]) >= {"recall@1", "recall@5", "recall@10", "MRR", "nDCG@5"},
          f"every metric M3 names is reported ({sorted(d['metrics'])})")

    # ── the held-out split is never read ───────────────────────────────────
    from eval.goldset.split import ids_for
    from scripts.retrieval_recall import dev_runs
    held = set(ids_for("heldout"))
    seen = {r["question_id"] for r in dev_runs(top_k=TOP_K)}
    check(bool(held) and not (seen & held),
          f"NO held-out row is read -- the split exists to prevent exactly that "
          f"({len(held)} held out, {len(seen & held)} leaked)")

    # ── monotonicity: recall@k cannot fall as k grows ──────────────────────
    means = [d["metrics"][f"recall@{k}"]["mean"] for k in RECALL_KS]
    check(all(a <= b + 1e-12 for a, b in zip(means, means[1:])),
          f"recall@1 <= recall@5 <= recall@10 ({[round(m, 3) for m in means]})")

    # ── the intervals are marked unreliable, and say why ───────────────────
    check(all(not m["reliable"] for m in d["metrics"].values()),
          "every dev interval is marked NOT reliable -- 13 rows is below the floor")
    check(all("below" in m["note"] for m in d["metrics"].values() if m["note"]),
          "...and each says why, so the flag cannot be dropped on the way to a report")

    # ── the degrees-of-freedom claim is MEASURED, not asserted ─────────────
    check(d["multi_relevant_queries"] == 0 and d["recall_equals_hit_rate"],
          f"recall@k equals hit rate on this set BECAUSE no row names two provisions "
          f"({d['multi_relevant_queries']} multi-relevant) -- measured, not assumed")
    check("fewer independent metrics" in d["degrees_of_freedom_note"],
          "...and the report says so, rather than presenting four independent metrics")

    # The note must FLIP when a row names two provisions, or it is decoration.
    fake = _metrics([{"question_id": "x", "want": ["173", "174"],
                      "ranked": ["173", "96", "174"]}], label="probe")
    check(fake["multi_relevant_queries"] == 1 and not fake["recall_equals_hit_rate"]
          and "separate" in fake["degrees_of_freedom_note"],
          "...and on a multi-relevant query the note FLIPS, so it is computed rather than "
          "hard-coded")

    # ── the title floor is bigger, and labelled as a floor ─────────────────
    t = title_metrics(limit=40)
    check(t["queries"] == 40, f"the title floor draws its own queries ({t['queries']})")
    check("EASIEST case" in t["caveat"],
          "...and says it is the easiest case, not a substitute for real questions")

    text = report({"dev": d, "title_floor": t, "held_out_read": False})
    check("not reliable" in text and "accuracy" in text.lower(),
          "the report carries the reliability flag and refuses an accuracy claim")
    check(json.loads(json.dumps(d)) == d, "the result is JSON-serialisable")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    if "--test" in sys.argv:
        raise SystemExit(_test())
    result = measure()
    print(json.dumps(result, indent=2) if "--json" in sys.argv else report(result))
