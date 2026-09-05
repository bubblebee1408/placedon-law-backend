"""Replacements for proposals a reviewer sent back. Proposes; changes nothing.

A sent-back proposal is not discarded. It is superseded by a resubmission that
names it, states what was wrong, and carries the evidence the reviewer relied
on — so the trail from the original invalid fixture through the rejected
replacement to the accepted one stays readable.

Nothing here writes a gold label or edits the benchmark. Each record is
PENDING_REVIEW and waits for a second human decision.

## The s.174 resubmission, and why it is not what was asked for

The instruction was to propose one replacement fixture for the unqualified
"two directors is the quorum" claim. That fixture already exists and is already
frozen:

    v2-174-1-neg  NOT_ENTAILED
    "Two directors are always sufficient to form a quorum for a Board meeting."
    rationale: drops 'whichever is higher'

Adding another would duplicate a frozen fixture — the exact defect that sent
v2-p174-qbind-0 and -1 back. So the resubmission proposes what s.174(1) is
actually missing instead.

What the sub-section holds after the two send-backs:

    v2-174-1-neg   negative, unqualified two-director claim   frozen
    v2-174-1-pos   positive, arithmetic on the edge case      frozen

Both are about the boundary. Neither states the rule. The resubmission supplies
one positive that states the whole selector — the thing both sent-back
proposals were reaching for — and stops at one, because a second phrasing of
the same proposition is what went wrong the first time.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from pathlib import Path

from checker.grounding_policy import HUMAN_JUDGED, PENDING_REVIEW, REVIEW_PENDING

OUT = Path("corpus/benchmark/resubmissions.jsonl")


@dataclass
class Resubmission:
    pair_id: str
    supersedes: list[str]              # the sent-back proposal ids
    supersedes_original: list[str]     # the invalid fixtures beneath them
    section: str
    subsection: str
    source_id: str
    claim: str
    proposed_label: str                # what a reviewer is being asked to affirm
    rationale: str
    why_resubmitted: str
    evidence: dict = field(default_factory=dict)
    label: str = PENDING_REVIEW
    label_basis: str = HUMAN_JUDGED
    reviewer_status: str = REVIEW_PENDING
    not_proposed: list[str] = field(default_factory=list)


def resubmissions() -> list[Resubmission]:
    from checker.entail_pairs_v2 import source_span
    from checker.review_table import build

    rows = {r.proposal_id: r for r in build()}
    a, b = rows["v2-p174-qbind-0"], rows["v2-p174-qbind-1"]

    return [Resubmission(
        pair_id="v2-174-1-rule-pos",
        supersedes=["v2-p174-qbind-0", "v2-p174-qbind-1"],
        supersedes_original=[a.supersedes, b.supersedes],
        section="174", subsection="1",
        source_id="companies-act-2013-s174",
        claim=("The quorum for a meeting of the Board is one-third of the total "
               "strength or two directors, whichever is higher."),
        proposed_label="ENTAILED",
        rationale=("states s.174(1)'s rule as the statute sets it: both limbs and "
                   "the selector that chooses between them, so it holds on a board "
                   "of three (where one-third is 1 and the quorum is 2) and on a "
                   "board of nine (where two directors is not enough)"),
        why_resubmitted=(
            "v2-p174-qbind-0 and -1 asserted the identical proposition, differing "
            "only in which limb they named first — 100% content overlap. Both were "
            "sent back. One statement of the rule replaces both."),
        evidence={
            "duplicate_detection": {
                "method": "content-word Jaccard over the replacement claims, "
                          "computed only where the claims' quantity sets match",
                "overlap": a.near_duplicates,
                "quantities_identical": True,
            },
            "source_span": source_span("174", "1"),
            "transcription_warnings": a.transcription_warnings,
        },
        not_proposed=[
            "A negative for the unqualified two-director claim was NOT proposed: "
            "v2-174-1-neg already carries it ('Two directors are always sufficient "
            "to form a quorum for a Board meeting', NOT_ENTAILED, drops 'whichever "
            "is higher'). Adding a second would repeat the duplication that sent "
            "the original proposals back.",
        ],
    )]


def write(path: Path = OUT) -> str:
    import hashlib
    body = "".join(json.dumps(asdict(r), ensure_ascii=False, sort_keys=True) + "\n"
                   for r in sorted(resubmissions(), key=lambda r: r.pair_id))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return hashlib.sha256(body.encode()).hexdigest()[:16]


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

    print("resubmission")
    rs = resubmissions()
    check(len(rs) == 1, f"one resubmission, not two ({len(rs)})")
    r = rs[0]

    check(r.label == PENDING_REVIEW, "it is pending review, not labelled")
    check(r.reviewer_status == REVIEW_PENDING, "...and awaits a reviewer")
    check(sorted(r.supersedes) == ["v2-p174-qbind-0", "v2-p174-qbind-1"],
          "it names both sent-back proposals")
    check(len(r.supersedes_original) == 2,
          "...and the invalid fixtures beneath them")

    # It must state the whole rule, not one limb.
    c = r.claim.lower()
    check("one-third" in c and "two directors" in c and "whichever is higher" in c,
          "the claim carries both limbs and the selector")

    # The duplicate-detection evidence has to survive, not just the conclusion.
    check(r.evidence["duplicate_detection"]["overlap"],
          "the duplicate-detection evidence is retained")
    check(r.evidence["source_span"], "the source span is retained")

    # And it must be honest about what it deliberately did not propose.
    check(any("v2-174-1-neg" in n for n in r.not_proposed),
          "it records that the negative already exists and was not duplicated")

    # That existing negative must really be there — if it is not, this
    # resubmission is wrong to omit one.
    from checker.entail_pairs_v2 import all_pairs
    from checker.grounding_policy import NOT_ENTAILED
    neg = [p for p in all_pairs() if p.id == "v2-174-1-neg"]
    check(len(neg) == 1 and neg[0].label == NOT_ENTAILED,
          "the frozen unqualified-two-director negative exists as claimed")
    check("two directors" in neg[0].claim.lower(),
          f"...and is the claim described ({neg[0].claim[:50]!r})")

    # The resubmitted claim must not duplicate anything already in the set.
    existing = {p.claim.strip().lower().rstrip(".") for p in all_pairs()}
    check(r.claim.strip().lower().rstrip(".") not in existing,
          "the resubmitted claim is not already a fixture")

    # Writing must not touch the benchmark.
    import checker.resubmission as mod
    paths = [v for v in vars(mod).values() if isinstance(v, Path)]
    check(paths == [OUT], f"the only path this module holds is its own file ({paths})")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
