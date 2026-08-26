"""Rebuild invalid fixtures as *proposed* qualified claims. Nothing is approved here.

Nine fixtures were invalidated by the fail-closed convention: each states a real
quantity-to-obligation binding, but states it unconditionally where the provision
carries a material qualifier. "Section 103 sets two members as the quorum for a
private company" is a true statement of the binding and a misleading statement of
the law, because s.103(1) opens with "Unless the articles of the company provide
for a larger number".

This module proposes replacements. It does not decide them.

## Why the originals are preserved rather than edited

An invalid fixture is evidence. It records a claim shape that looked correct to
its author and was not, which is exactly the material a benchmark exists to
capture. Overwriting it would destroy the only record of why the replacement was
needed, and would make the transformation unauditable. So originals are kept
permanently with their invalidation reason, and every replacement names the
fixture it supersedes and the exact transformation applied.

## The model proposes; it does not label

Every replacement is emitted `HUMAN_JUDGED` / `PENDING_REVIEW`. Prepending a
verified qualifier is mechanical, but deciding that the result *preserves the
legal meaning* is not — it is the judgement under test. A replacement that
assigned itself ENTAILED would be a model marking its own homework, which is the
failure both cited studies refuse.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict, field
from pathlib import Path

from checker.grounding_policy import (
    HUMAN_JUDGED, INVALID_FIXTURE, PENDING_REVIEW, REVIEW_PENDING,
)

PROPOSALS = Path("corpus/benchmark/pending_reviews.jsonl")
INVALID = Path("corpus/benchmark/invalid_fixtures.jsonl")

INVALID_REASON = ("Claim omitted a material legal qualifier and cannot be used as "
                  "a gold positive or negative example.")


@dataclass
class Proposal:
    pair_id: str
    supersedes: str
    section: str
    subsection: str
    source_id: str
    source_span: str
    source_span_hash: str
    original_claim: str
    claim: str
    transformation: str
    label: str = PENDING_REVIEW
    label_basis: str = HUMAN_JUDGED
    qualifiers: list[dict] = field(default_factory=list)
    preserves_all_qualifiers: bool | None = None   # a reviewer decides this
    reviewer_status: str = REVIEW_PENDING
    reviewer: str | None = None
    reviewed_at: str | None = None
    scope: str = ""


def _sha(s: str) -> str:
    import hashlib
    return "sha256:" + hashlib.sha256(s.encode("utf-8")).hexdigest()


# The qualifying clause each subsection contributes, phrased so it can be
# prepended or appended without restating the provision. Written out rather than
# generated: a generated hedge that subtly changed the legal effect would be the
# very defect this rebuild exists to remove.
_PREFIX: dict[tuple[str, str], str] = {
    ("103", "1"): "Unless the company's articles provide for a larger number, ",
    ("101", "1"): "",
    ("173", "1"): "",
}
_SUFFIX: dict[tuple[str, str], str] = {
    ("103", "1"): "",
    ("101", "1"): ", subject to the statutory shorter-notice consent requirement",
    ("173", "1"): (", subject to the Central Government's power to exempt "
                   "prescribed classes of companies by notification"),
}

# s.101's second binding is itself part of the shorter-notice proviso, so
# appending "subject to the shorter-notice requirement" would be circular. It
# needs its own framing.
_SPECIAL: dict[str, tuple[str, str]] = {
    "v2-p101-bind-1": (
        "Where shorter notice is given for an annual general meeting, section 101 "
        "requires the consent of not less than ninety-five per cent of the members "
        "entitled to vote at that meeting.",
        "reframed: the original stated the threshold as a free-standing rule; the "
        "replacement states it as the condition of the shorter-notice proviso it "
        "belongs to, since appending 'subject to the shorter-notice requirement' "
        "to its own condition would be circular"),
}


def propose() -> list[Proposal]:
    from checker.entail_pairs_v2 import base_pairs, source_span
    out: list[Proposal] = []
    for p in base_pairs():
        if p.label != INVALID_FIXTURE:
            continue
        key = (p.section, p.subsection)
        span = source_span(p.section, p.subsection)

        if p.id in _SPECIAL:
            claim, how = _SPECIAL[p.id]
        else:
            pre, suf = _PREFIX.get(key, ""), _SUFFIX.get(key, "")
            body = p.claim.rstrip(".")
            if pre:
                body = pre + body[0].lower() + body[1:]
            claim = body + suf + "."
            how = (f"prepended {pre!r} " if pre else "") + \
                  (f"appended {suf!r}" if suf else "")
            how = how.strip() or "no change"

        out.append(Proposal(
            pair_id=p.id.replace("-bind-", "-qbind-"),
            supersedes=p.id, section=p.section, subsection=p.subsection,
            source_id=f"companies-act-2013-s{p.section}",
            source_span=span, source_span_hash=_sha(span),
            original_claim=p.claim, claim=claim, transformation=how,
            qualifiers=p.qualifiers,
            scope=_scope_of(p.claim),
        ))
    return out


def _scope_of(claim: str) -> str:
    for pat, scope in [
        (r"private company", "private company meeting"),
        (r"public company", "public company meeting"),
        (r"annual general meeting", "annual general meeting"),
        (r"general meeting", "general meeting"),
        (r"Board meeting", "board meeting"),
    ]:
        if re.search(pat, claim, re.I):
            return scope
    return "unspecified"


def invalid_records() -> list[dict]:
    """The originals, preserved permanently with their invalidation reason."""
    from checker.entail_pairs_v2 import base_pairs
    return [{
        "pair_id": p.id, "section": p.section, "subsection": p.subsection,
        "source_id": f"companies-act-2013-s{p.section}",
        "claim": p.claim, "label": INVALID_FIXTURE, "reason": INVALID_REASON,
        "qualifiers_omitted": [q["kind"] for q in p.qualifiers],
        "superseded_by": p.id.replace("-bind-", "-qbind-"),
    } for p in base_pairs() if p.label == INVALID_FIXTURE]


def write(proposals_path: Path = PROPOSALS, invalid_path: Path = INVALID) -> tuple[str, str]:
    import hashlib
    props = propose()
    pb = "".join(json.dumps(asdict(x), ensure_ascii=False, sort_keys=True) + "\n"
                 for x in sorted(props, key=lambda x: x.pair_id))
    ib = "".join(json.dumps(x, ensure_ascii=False, sort_keys=True) + "\n"
                 for x in sorted(invalid_records(), key=lambda x: x["pair_id"]))
    proposals_path.parent.mkdir(parents=True, exist_ok=True)
    proposals_path.write_text(pb, encoding="utf-8")
    invalid_path.write_text(ib, encoding="utf-8")
    return (hashlib.sha256(pb.encode()).hexdigest(),
            hashlib.sha256(ib.encode()).hexdigest())


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

    print("fixture_rebuild")

    props = propose()
    check(len(props) == 9, f"one proposal per invalid fixture ({len(props)})")
    check(all(p.label == PENDING_REVIEW for p in props),
          "every proposal is PENDING_REVIEW — none assigns itself ENTAILED")
    check(all(p.label_basis == HUMAN_JUDGED for p in props),
          "every proposal is HUMAN_JUDGED")
    check(all(p.reviewer is None and p.reviewed_at is None for p in props),
          "no reviewer identity or timestamp is fabricated")
    check(all(p.preserves_all_qualifiers is None for p in props),
          "qualifier preservation is left for a reviewer to assert, not claimed")
    check(all(p.supersedes and p.transformation for p in props),
          "every proposal names what it supersedes and how it was transformed")
    check(all(p.source_span and p.source_span_hash.startswith("sha256:") for p in props),
          "every proposal carries the source span and its hash")
    check(all(p.qualifiers for p in props),
          "every proposal carries the qualifier inventory of its subsection")

    # The replacement must actually differ from the claim it replaces.
    check(all(p.claim != p.original_claim for p in props),
          "no proposal is identical to the invalid claim it replaces")

    # And it must mention the qualifier it was meant to restore.
    hedges = ("unless", "subject to", "where shorter notice")
    missing = [p.pair_id for p in props
               if not any(h in p.claim.lower() for h in hedges)]
    check(not missing, f"every proposal carries a qualifying clause ({missing})")

    # Originals preserved, not edited.
    inv = invalid_records()
    check(len(inv) == 9, f"all nine originals are preserved ({len(inv)})")
    check(all(r["reason"] == INVALID_REASON for r in inv),
          "each original carries the standard invalidation reason")
    check(all(r["superseded_by"] for r in inv),
          "each original points at its replacement")
    orig_ids = {r["pair_id"] for r in inv}
    check(all(p.supersedes in orig_ids for p in props),
          "every proposal supersedes a preserved original")

    # Contradiction detection against everything already decided.
    from checker.entail_pairs_v2 import Pair, contradictions, all_pairs, base_pairs
    from checker.grounding_policy import CONSTRUCTED
    as_pairs = [Pair(id=p.pair_id, section=p.section, subsection=p.subsection,
                     source_span=p.source_span, claim=p.claim, label=p.label,
                     label_basis=p.label_basis, qualifiers=p.qualifiers,
                     supersedes=p.supersedes) for p in props]
    cons = contradictions(all_pairs() + as_pairs)
    check(cons == [], f"no contradiction against approved or rejected pairs ({cons[:2]})")

    # A proposal must not collide with a PRE-EXISTING pair. Checked against
    # base_pairs(), not all_pairs(): once approved, a proposal is folded into
    # all_pairs() under its own id, so comparing there would flag success as a
    # collision.
    existing = {p.id for p in base_pairs()}
    check(not (existing & {p.pair_id for p in props}),
          "no proposal reuses a pre-existing pair id")
    approved_ids = {p.id for p in all_pairs()} - existing
    check(approved_ids <= {p.pair_id for p in props},
          "every pair beyond the base set came from an approved proposal")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    import sys
    if "--emit" in sys.argv:
        a, b = write()
        print(f"proposals -> {PROPOSALS}  sha256:{a}")
        print(f"invalid   -> {INVALID}  sha256:{b}")
    else:
        _test()
