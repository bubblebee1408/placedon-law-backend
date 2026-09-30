#!/usr/bin/env python3
"""What the cascade actually cost, from recorded runs. Never from an assumption.

PLAN_23 O3. `checker/model_cascade.py` records every stage it tried, why the verifier
rejected it, which bodies the answer touched and what each stage cost. This reads those
records back and answers the two questions that decide whether the cascade is worth having:

    how often does each stage get rejected?
    what does an answer cost, in expectation?

    E = c1 + r1·c2 + r1·r2·c3

`r1` is the rejection rate of stage 1 and `c2` the mean cost of stage 2, so each term is the
cost of a stage times the probability of reaching it. Grouped by body, because a Companies
Act question and a question reaching an unheld body are different workloads and averaging
them produces a number true of neither.

## Three ways this refuses to produce a comforting number

**A stage with no priced call has no mean cost, and E is then UNPRICED.** Not zero. Zero
would say those calls were free, and `backend/azure_pricing.py` exists because that
falsehood was shipped once already. The report prints which stage is unpriced and stops.

**FAILED stages are excluded from the rejection rate.** A transport error is not the
verifier rejecting anything -- nobody decided. Counting it as a rejection would inflate `r`,
which inflates every later term of E, which would make the cascade look more expensive than
it is for a reason that has nothing to do with the cascade.

**NO_ANSWER is excluded too**, and for the opposite reason: no model ran, so there is
nothing to have rejected and nothing to have spent.

Run:  PYTHONPATH=. python3 scripts/cascade_report.py --store
      PYTHONPATH=. python3 scripts/cascade_report.py runs.jsonl
      PYTHONPATH=. python3 scripts/cascade_report.py --test

`--store` reads `cascade_runs` through `gateway/store.py`, which is where the records
actually live. The JSONL path is kept because the tests must reach no database: a report
whose own suite needs Postgres is a report nobody runs.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from checker.model_cascade import (ACCEPTED, FAILED, NO_ANSWER,  # noqa: E402
                                   REJECTED, STAGE_ORDER)

NO_BODY = "(no body recorded)"


def load(source) -> list[dict]:
    """Records from a path, an open file, or an iterable of lines. Blank lines skipped.

    A malformed line RAISES rather than being skipped: a report that quietly drops the runs
    it could not read is a report whose denominator nobody can check.
    """
    if isinstance(source, (str, Path)):
        text = Path(source).read_text(encoding="utf-8")
        lines = text.splitlines()
    elif hasattr(source, "read"):
        lines = source.read().splitlines()
    else:
        lines = list(source)
    out = []
    for i, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except ValueError as e:
            raise ValueError(f"line {i} is not a cascade record: {e}") from None
    return out


def stage_stats(records) -> dict:
    """Per stage: how often it ran, how often the verifier rejected it, what it cost."""
    stats = {}
    for stage in STAGE_ORDER:
        ran = rejected = 0
        costs: list[float] = []
        unpriced = 0
        failed = skipped = 0
        reasons: dict[str, int] = {}
        for rec in records:
            for a in rec.get("attempts", []):
                if a.get("stage") != stage:
                    continue
                outcome = a.get("outcome")
                if outcome == FAILED:
                    failed += 1
                    continue          # transport: nobody decided, so it is not a rejection
                if outcome == NO_ANSWER:
                    skipped += 1
                    continue          # no model ran: nothing rejected, nothing spent
                ran += 1
                if outcome == REJECTED:
                    rejected += 1
                    key = (a.get("reason") or "(no reason recorded)").split(":")[0][:70]
                    reasons[key] = reasons.get(key, 0) + 1
                if a.get("cost_inr") is None:
                    unpriced += 1
                else:
                    costs.append(float(a["cost_inr"]))
        stats[stage] = {
            "ran": ran,
            "rejected": rejected,
            "accepted": ran - rejected,
            "failed": failed,
            "skipped": skipped,
            # None, not 0.0: a stage nobody ran has no rate, and printing 0% would say it
            # never gets rejected.
            "rejection_rate": (rejected / ran) if ran else None,
            "priced_calls": len(costs),
            "unpriced_calls": unpriced,
            "mean_cost_inr": (sum(costs) / len(costs)) if costs else None,
            "reasons": reasons,
        }
    return stats


def expected_cost(stats) -> tuple[float | None, str]:
    """E = c1 + r1·c2 + r1·r2·c3, or None and the reason it cannot be computed.

    A missing mean cost is UNPRICED and stops the sum. A missing rejection rate for a stage
    that was never reached is NOT a blocker -- the term is multiplied by a probability of
    reaching it, and a stage nobody reached contributes nothing.
    """
    total = 0.0
    reach = 1.0
    for stage in STAGE_ORDER:
        st = stats[stage]
        if st["ran"] == 0:
            # Never ran in these records: it contributes no cost, and `reach` is LEFT
            # ALONE. Zeroing it here was the first version's bug — it made every later
            # term vanish, so a workload that never uses the deterministic stage reported
            # E = ₹0.0000 while spending money on two models.
            continue
        if st["mean_cost_inr"] is None:
            return None, (
                f"{stage} ran {st['ran']} time(s) and NONE of them was priced, so its mean "
                f"cost is UNPRICED. E is not computed: printing a number here would treat "
                f"those calls as free.")
        total += reach * st["mean_cost_inr"]
        r = st["rejection_rate"]
        reach *= 0.0 if r is None else r
    return total, "E = c1 + r1·c2 + r1·r2·c3, over the records supplied"


def by_body(records) -> dict:
    """{body_id: [record]}. A record touching two bodies appears under BOTH.

    So the group counts sum to more than the number of runs, on purpose: a run that reaches
    the Companies Act and FEMA is a data point about each. The report says so rather than
    letting a reader add the columns up.
    """
    groups: dict[str, list] = {}
    for rec in records:
        ids = rec.get("body_ids") or [NO_BODY]
        for b in ids:
            groups.setdefault(b, []).append(rec)
    return groups


def _pct(x) -> str:
    return "—" if x is None else f"{x * 100:.1f}%"


def _rupees(x) -> str:
    return "UNPRICED" if x is None else f"₹{x:.4f}"


def report_text(records) -> str:
    lines: list[str] = []
    lines.append(f"cascade report — {len(records)} run(s)")
    statuses: dict[str, int] = {}
    for rec in records:
        statuses[rec.get("status", "?")] = statuses.get(rec.get("status", "?"), 0) + 1
    lines.append("  outcomes: " + ", ".join(f"{k}={v}" for k, v in sorted(statuses.items())))
    lines.append("")

    def block(title: str, recs) -> None:
        stats = stage_stats(recs)
        lines.append(title)
        lines.append(f"  {'stage':<16}{'ran':>5}{'rejected':>10}{'rate':>9}"
                     f"{'mean cost':>13}{'unpriced':>10}{'failed':>8}")
        for stage in STAGE_ORDER:
            st = stats[stage]
            lines.append(
                f"  {stage:<16}{st['ran']:>5}{st['rejected']:>10}"
                f"{_pct(st['rejection_rate']):>9}{_rupees(st['mean_cost_inr']):>13}"
                f"{st['unpriced_calls']:>10}{st['failed']:>8}")
        e, why = expected_cost(stats)
        lines.append(f"  expected cost per answer: {_rupees(e)}")
        lines.append(f"    {why}")
        for stage in STAGE_ORDER:
            for reason, n in sorted(stats[stage]["reasons"].items(),
                                    key=lambda kv: -kv[1]):
                lines.append(f"    {stage} rejected {n}x: {reason}")
        lines.append("")

    block("ALL RUNS", records)

    groups = by_body(records)
    if groups:
        lines.append("BY BODY — a run touching two bodies is counted under each, so these")
        lines.append("          do not sum to the run count.")
        lines.append("")
        for body in sorted(groups):
            block(f"  {body} ({len(groups[body])} run(s))", groups[body])
    return "\n".join(lines)


def from_store(backend=None, *, run_id: str | None = None, limit: int = 1000) -> list[dict]:
    """Records as `gateway/store.py` holds them, shaped as this report reads them.

    The store keeps `claim_count` and `refusal_count` rather than the claims themselves --
    a report counts them and does not need the text, and the text is another firm's answer.
    They are re-expanded into the list shapes `stage_stats` and `by_body` expect, so one
    code path serves both sources.
    """
    if backend is None:
        from gateway.store import select
        backend = select()
    out = []
    for row in backend.read_cascades(run_id=run_id, limit=limit):
        out.append({
            "status": row["status"],
            "error": row.get("error"),
            "attempts": list(row.get("attempts") or []),
            "body_ids": list(row.get("body_ids") or []),
            # Length is all the report uses. Rebuilt as placeholders rather than invented
            # text, so nothing here can be mistaken for the answer that was served.
            "claims": [{}] * int(row.get("claim_count") or 0),
            "refusals": [{}] * int(row.get("refusal_count") or 0),
            "total_cost_inr": row.get("total_cost_inr"),
            "stages_tried": [a.get("stage") for a in (row.get("attempts") or [])],
        })
    return out


def main(argv) -> int:
    if "--store" in argv:
        records = from_store()
        if not records:
            print("no cascade records are stored yet. Nothing is reported rather than an "
                  "empty table, which would read as a cascade that never rejects.")
            return 0
        print(report_text(records))
        return 0
    args = [a for a in argv[1:] if not a.startswith("-")]
    if not args:
        print(__doc__.strip().splitlines()[0])
        print("usage: python3 scripts/cascade_report.py [--store | <records.jsonl>]")
        return 2
    print(report_text(load(args[0])))
    return 0


# ── self-test ────────────────────────────────────────────────────────────────

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

    from checker import scope
    from checker.model_cascade import (ANSWERED, LARGE, PARTIAL, SMALL, Attempt, Claim,
                                       Result)

    def rec(status, attempts, bodies=("CA2013",), claims=(), error=None):
        # A FAILED Result must carry its transport error; model_cascade refuses to build one
        # without it, which is the invariant doing its job on this fixture.
        if status == FAILED and error is None:
            error = "ConnectionError: reset"
        return Result(status, tuple(attempts), tuple(claims), touched=tuple(bodies),
                      error=error).to_dict()

    def att(stage, outcome, cost=None, reason="", model="m"):
        return Attempt(stage, outcome, reason=reason, model=model, cost_inr=cost,
                       cost_note="" if cost is not None else "no verified price")

    # Two runs the small model handled; two it did not and the large model did.
    cheap = rec(ANSWERED, [att(SMALL, ACCEPTED, 0.02)])
    escalated = rec(ANSWERED, [att(SMALL, REJECTED, 0.02, reason="NO_CITATION: invented"),
                               att(LARGE, ACCEPTED, 0.10)])
    records = [cheap, cheap, escalated, escalated]

    stats = stage_stats(records)
    check(stats[SMALL]["ran"] == 4 and stats[SMALL]["rejected"] == 2,
          f"the small stage ran 4 and was rejected twice ({stats[SMALL]['ran']}, "
          f"{stats[SMALL]['rejected']})")
    check(abs(stats[SMALL]["rejection_rate"] - 0.5) < 1e-9,
          f"...a rejection rate of 50% ({stats[SMALL]['rejection_rate']})")
    check(abs(stats[SMALL]["mean_cost_inr"] - 0.02) < 1e-9,
          "...and a mean cost taken from the priced calls")
    check(stats[LARGE]["ran"] == 2 and stats[LARGE]["rejection_rate"] == 0.0,
          "the large stage ran only on the escalations, and was never rejected")

    e, why = expected_cost(stats)
    # E = 0.02 + 0.5*0.10 + (0.5*0.0)*c3 = 0.07
    check(e is not None and abs(e - 0.07) < 1e-9,
          f"E = c1 + r1·c2 + r1·r2·c3 = 0.02 + 0.5×0.10 = ₹0.07 (got {e})")
    check("r1·c2" in why, "...and the formula is printed with it, not just the number")

    # ── a FAILED stage is not a rejection ───────────────────────────────────
    with_fail = records + [rec(FAILED, [att(SMALL, FAILED, None,
                                            reason="ConnectionError: reset")],
                               bodies=())]
    sf = stage_stats(with_fail)
    check(sf[SMALL]["ran"] == 4 and sf[SMALL]["failed"] == 1,
          f"a transport failure is counted separately, NOT as a run "
          f"({sf[SMALL]['ran']} ran, {sf[SMALL]['failed']} failed)")
    check(abs(sf[SMALL]["rejection_rate"] - 0.5) < 1e-9,
          "...so it does not move the rejection rate: nobody decided anything, and "
          "counting it would inflate every later term of E")

    # ── NO_ANSWER is excluded too ───────────────────────────────────────────
    with_skip = records + [rec(ANSWERED, [att("deterministic", NO_ANSWER, None,
                                              reason="no callable"),
                                          att(SMALL, ACCEPTED, 0.02)])]
    ss = stage_stats(with_skip)
    check(ss["deterministic"]["ran"] == 0 and ss["deterministic"]["skipped"] == 1,
          "a stage that never ran is skipped, not counted as having answered")
    check(ss["deterministic"]["rejection_rate"] is None,
          "...and has NO rejection rate: 0% would say it never gets rejected, which is a "
          "claim about a stage nobody ran")

    # ── UNPRICED stops E rather than becoming zero ──────────────────────────
    unpriced = [rec(ANSWERED, [att(SMALL, REJECTED, None, reason="NO_CITATION"),
                               att(LARGE, ACCEPTED, None)])]
    eu, whyu = expected_cost(stage_stats(unpriced))
    check(eu is None, "a stage with no priced call gives NO expected cost")
    check("UNPRICED" in whyu and "free" in whyu,
          f"...and says why rather than printing 0, which would claim the calls were free "
          f"({whyu[:80]})")

    # ── grouped by body ─────────────────────────────────────────────────────
    two = rec(PARTIAL, [att(SMALL, ACCEPTED, 0.02)], bodies=("CA2013", "FEMA1999"))
    groups = by_body(records + [two])
    check(set(groups) == {"CA2013", "FEMA1999"},
          f"runs group by every body they touch ({sorted(groups)})")
    check(len(groups["CA2013"]) == 5 and len(groups["FEMA1999"]) == 1,
          f"...and a run touching two appears under BOTH "
          f"({len(groups['CA2013'])}, {len(groups['FEMA1999'])})")
    check(sum(len(v) for v in groups.values()) > len(records) + 1,
          "...so the groups deliberately do not sum to the run count")
    check(by_body([rec(FAILED, [att(SMALL, FAILED, None, reason="x")], bodies=())])
          == {NO_BODY: [rec(FAILED, [att(SMALL, FAILED, None, reason="x")], bodies=())]},
          "a run that touched no body is grouped as such, not dropped from the report")

    # ── loading ─────────────────────────────────────────────────────────────
    jsonl = "\n".join(json.dumps(r) for r in records)
    check(len(load(jsonl.splitlines())) == 4, "records load from lines")
    check(len(load(("\n" + jsonl + "\n\n").splitlines())) == 4, "...blank lines are skipped")
    try:
        load(["{not json"])
        check(False, "a malformed record is refused")
    except ValueError as e:
        check("line 1" in str(e),
              "a malformed record RAISES with its line number: a report that silently drops "
              "the runs it could not read has a denominator nobody can check")

    # ── the printed report ──────────────────────────────────────────────────
    text = report_text(records + [two])
    check("cascade report — 5 run(s)" in text, "the report states its denominator")
    # 5 runs here, not 4: `two` adds a fifth the small model handled, so the rate is 2/5.
    # The first version asserted 50% and was reading the 4-run figure from further up.
    check("rate" in text and "40.0%" in text,
          "...prints the rejection rate per stage, over THESE records")
    check("expected cost per answer" in text and "₹0.0" in text, "...and the expected cost")
    check("BY BODY" in text and "FEMA1999" in text, "...grouped by body")
    check("do not sum to the run count" in text,
          "...saying in terms that the groups overlap, so nobody adds the columns up")
    check("NO_CITATION" in text, "...and the rejection reasons, which is what it is for")
    unp_text = report_text(unpriced)
    check("UNPRICED" in unp_text and "₹0.0000" not in unp_text.split("expected cost")[1][:30],
          "an unpriced cascade prints UNPRICED where the number would go, never ₹0.0000")

    # ── reading from the store ──────────────────────────────────────────────
    from gateway.store import MemoryBackend
    b = MemoryBackend()
    check(from_store(b) == [],
          "an empty store yields no records, rather than an empty table that would read "
          "as a cascade that never rejects")
    b.write_cascade({"status": "PARTIAL", "attempts": [
        {"stage": SMALL, "outcome": REJECTED, "reason": "NO_CITATION: invented",
         "model": "s", "cost_inr": 0.02, "cost_note": ""},
        {"stage": LARGE, "outcome": ACCEPTED, "reason": "", "model": "l",
         "cost_inr": 0.10, "cost_note": ""}],
        "body_ids": ["CA2013", "FEMA1999"], "claims": [{}], "refusals": [{}],
        "total_cost_inr": 0.12})
    stored = from_store(b)
    check(len(stored) == 1 and stored[0]["status"] == "PARTIAL",
          "a stored record reads back for the report")
    st_stats = stage_stats(stored)
    check(st_stats[SMALL]["rejected"] == 1 and st_stats[LARGE]["ran"] == 1,
          "...with its stages and their outcomes intact")
    e_st, _ = expected_cost(st_stats)
    check(e_st is not None and abs(e_st - 0.12) < 1e-9,
          f"...and E computes from it exactly as from JSONL ({e_st})")
    check(set(by_body(stored)) == {"CA2013", "FEMA1999"},
          "...grouped by every body the answer touched")
    check(all(c == {} for c in stored[0]["claims"]),
          "...and the claims are placeholders: the report counts them and never needs the "
          "text, which is another firm's answer")
    check("cascade report — 1 run(s)" in report_text(stored),
          "...and the printed report reads the same from either source")

    # ── the scope invariant, restated where a report could break it ─────────
    check(all(not scope.body(b).answerable for b in ("FEMA1999",)),
          "FEMA1999 is still unheld, so grouping runs under it never makes it answerable")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    if "--test" in sys.argv:
        raise SystemExit(_test())
    raise SystemExit(main(sys.argv))
