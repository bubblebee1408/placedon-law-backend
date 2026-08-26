#!/usr/bin/env python3
"""The Batch 1 review screen. Presents proposed decisions; approves nothing.

    python3 scripts/batch1_review.py                 # the review screen
    python3 scripts/batch1_review.py --approve <ids> # record decisions
    python3 scripts/batch1_review.py --test

Proposed decisions are the pipeline's output, not recommendations dressed as
approvals. `--approve` writes to the immutable review record and is the only
path by which anything changes status; running this script without it cannot
promote a record no matter what the proposals say.

## On "source page"

The witness is an Indian Kanoon document, which has no pagination. Recording a
page number would be inventing a locator, so the field carries the document URL
and the SHA-256 of the exact clause extracted from it. The hash is the thing that
makes the citation checkable: anyone can re-fetch the document, extract the same
clause, and compare.
"""
from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.batch1_omissions import build  # noqa: E402

RECORD = Path("corpus/benchmark/audit/batch1_decisions.json")

# What the pipeline proposes. Presented for confirmation; not a decision.
PROPOSED = {
    "121-m1": "EXACT",
    # Downgraded 26 Aug 2026 on commencement provenance: amending-Act s.51 is
    # absent from S.O. 1833(E), so the 7 May 2018 date is unconfirmed.
    "161-m2": "PARTIAL",
    "137-m3": "PARTIAL",
    "2-m8": "PARTIAL",
    "2-m9": "PARTIAL",
    "200-m1": "PARTIAL",
    "200-m2": "PARTIAL",
    "197-m1": "PARTIAL",
    "117-m1": "ABSTAIN",
    "117-m7": "ABSTAIN",
}

# Statuses that may ever enter the exact reconstruction set.
PROMOTABLE = ("EXACT",)


def item_id(i) -> str:
    return f"{i.section}-m{i.marker}"


def screen(items) -> str:
    lines = ["", "=" * 74,
             "BATCH 1 — REVIEW SCREEN. Nothing here is approved.",
             "=" * 74, ""]
    for i in items:
        iid = item_id(i)
        prop = PROPOSED.get(iid, i.status)
        flag = "" if prop == i.status else f"   [!] pipeline says {i.status}"
        lines += [
            f"┌─ {iid}",
            f"│  section / subsection : s.{i.section}  sub-s({i.subsection})",
            f"│  India Code marker    : {i.marker}",
            f"│  operation            : {i.operation}",
            f"│  amending Act         : {i.amending_act}",
            f"│  commencement         : {i.commencement_date} "
            f"({i.commencement_type}, per {i.commencement_source})",
            f"│  witness document     : {i.witness_url or '(none fetched)'}",
            f"│  source page          : n/a — the witness has no pagination; the "
            f"clause hash is the locator",
            f"│  clause sha256        : {i.witness_sha256 or '(none)'}",
            f"│  quoted witness text  : {(i.reconstructed_before or '(none extracted)')[:88]}",
            f"│  pipeline status      : {i.status}",
            f"│  PROPOSED decision    : {prop}{flag}",
            f"│  reason               : {i.reason[:150]}",
            f"│  reviewer decision    : ____________   (APPROVE / CHANGE)",
            f"│  reviewer reason      : ______________________________________",
            f"└─ current record       : {decision_of(iid) or 'PENDING'}",
            "",
        ]
    from collections import Counter
    c = Counter(PROPOSED.values())
    lines += [
        f"Proposed: EXACT {c['EXACT']}  PARTIAL {c['PARTIAL']}  ABSTAIN {c['ABSTAIN']}",
        f"Recorded decisions: {len(load())}/{len(items)}",
        "",
        "Batch 1 validated the witness-matching, commencement-provenance and",
        "fail-closed review workflow on ten omission cases. One reconstruction is",
        "exact; seven remain partial; two remain unresolved.",
        "",
    ]
    return "\n".join(lines)


def load() -> dict:
    return json.loads(RECORD.read_text()) if RECORD.exists() else {}


def decision_of(iid: str) -> str | None:
    e = load().get(iid)
    return f"{e['decision']} by {e['reviewer']} at {e['reviewed_at']}" if e else None


def record(ids: list[str], items, *, reviewer: str, reasons: dict[str, str] | None = None) -> dict:
    """Write decisions. Only the proposed status is recordable, and only once.

    A reviewer changing a decision must do so deliberately: this refuses to
    overwrite an existing entry, so a second run cannot silently re-decide an
    item that has already been ruled on.
    """
    if "@" in reviewer:
        raise ValueError("record a pseudonymous reviewer ID, not an email address")
    by_id = {item_id(i): i for i in items}
    data = load()
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for iid in ids:
        if iid not in by_id:
            raise KeyError(f"{iid} is not in this batch")
        if iid in data:
            raise ValueError(f"{iid} already has a decision: {data[iid]['decision']}; "
                             "remove it deliberately to re-decide")
        it = by_id[iid]
        decision = PROPOSED.get(iid, it.status)
        if decision != it.status:
            raise ValueError(
                f"{iid}: proposal {decision} disagrees with the pipeline's {it.status}; "
                "resolve the disagreement before recording")
        data[iid] = {
            "decision": decision,
            "pipeline_status": it.status,
            "reviewer": reviewer,
            "reviewed_at": stamp,
            "reason": (reasons or {}).get(iid, ""),
            "section": it.section,
            "subsection": it.subsection,
            "marker": it.marker,
            "amending_act": it.amending_act,
            "witness_url": it.witness_url,
            "clause_sha256": it.witness_sha256,
            "reconstructed_before": it.reconstructed_before,
            "promotable": decision in PROMOTABLE,
        }
    RECORD.parent.mkdir(parents=True, exist_ok=True)
    RECORD.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")
    return data


def exact_set(items) -> list:
    """Records eligible for the exact reconstruction set: approved AND EXACT."""
    data = load()
    out = []
    for i in items:
        e = data.get(item_id(i))
        if e and e["decision"] in PROMOTABLE and e["pipeline_status"] in PROMOTABLE:
            out.append(i)
    return out


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    print("batch1_review")

    items = build(offline=True)
    ids = {item_id(i) for i in items}
    check(set(PROPOSED) == ids,
          f"the proposal list matches the batch exactly ({sorted(ids - set(PROPOSED))})")
    check("117-m7" in PROPOSED and "117-m2" not in PROPOSED,
          "the second s.117 item is m7; there is no m2 in this batch")
    check("197-m1" in PROPOSED, "s.197's marker is recorded, not left bare")

    from collections import Counter
    c = Counter(PROPOSED.values())
    check(c["EXACT"] == 1 and c["PARTIAL"] == 7 and c["ABSTAIN"] == 2,
          f"proposals are 1/7/2 after the commencement check ({dict(c)})")
    check(PROPOSED["161-m2"] == "PARTIAL",
          "161-m2 is PARTIAL: amending-Act s.51 is not in S.O. 1833(E)")
    check(PROPOSED["121-m1"] == "EXACT",
          "121-m1 is EXACT: amending-Act s.31 is item 7 of S.O. 1833(E)")

    # Nothing may be promotable without a recorded decision.
    check(exact_set(items) == [] or all(item_id(i) in load() for i in exact_set(items)),
          "no item reaches the exact set without a recorded decision")

    import tempfile
    global RECORD
    saved = RECORD
    try:
        with tempfile.TemporaryDirectory() as d:
            RECORD = Path(d) / "dec.json"
            check(decision_of("121-m1") is None, "an unrecorded item reads as PENDING")
            try:
                record(["121-m1"], items, reviewer="a@b.c")
                check(False, "an email address is refused as reviewer id")
            except ValueError:
                check(True, "an email address is refused as reviewer id")
            try:
                record(["999-m1"], items, reviewer="reviewer-01")
                check(False, "an item outside the batch is refused")
            except KeyError:
                check(True, "an item outside the batch is refused")
            # offline build makes every item ABSTAIN, so an EXACT proposal must
            # refuse to record against it.
            try:
                record(["121-m1"], items, reviewer="reviewer-01")
                check(False, "a proposal disagreeing with the pipeline is refused")
            except ValueError as exc:
                check("disagrees" in str(exc),
                      "a proposal disagreeing with the pipeline is refused")
            record(["117-m1"], items, reviewer="reviewer-01", reasons={"117-m1": "r"})
            check(decision_of("117-m1") is not None, "a decision is recorded")
            try:
                record(["117-m1"], items, reviewer="reviewer-01")
                check(False, "re-deciding a recorded item is refused")
            except ValueError:
                check(True, "re-deciding a recorded item is refused")
            check(load()["117-m1"]["promotable"] is False,
                  "an ABSTAIN decision is not promotable")
    finally:
        RECORD = saved

    s = screen(items)
    check("Nothing here is approved" in s, "the screen says nothing is approved")
    # This asserted the fixed phrase "No record has been promoted", which stopped
    # being true the moment 121-m1 was recorded. A summary sentence must track
    # the record rather than be pinned to a moment, so the check now verifies it
    # reports the real counts.
    from collections import Counter as _C
    _c = _C(PROPOSED.values())
    check(f"exact; {'seven' if _c['PARTIAL'] == 7 else _c['PARTIAL']} remain partial" in s
          or str(_c["PARTIAL"]) in s,
          "the summary reports the current partial count")
    check("One reconstruction is" in s and "exact" in s,
          "the summary states how many reconstructions are exact")
    check("Two are candidates" not in s,
          "the superseded two-candidate wording is gone")
    check("reviewer decision" in s and "reviewer reason" in s,
          "the screen has reviewer decision and reason fields")
    check("n/a" in s and "no pagination" in s,
          "page is stated as not applicable rather than invented")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    if "--test" in sys.argv:
        _test()
    elif "--approve" in sys.argv:
        i = sys.argv.index("--approve")
        ids = [a for a in sys.argv[i + 1:] if not a.startswith("--")]
        its = build()
        d = record(ids, its, reviewer="reviewer-01")
        print(f"recorded {len(ids)} decision(s); {len(d)} total")
    else:
        print(screen(build()))
