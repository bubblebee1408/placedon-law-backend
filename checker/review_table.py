"""The human-review table for the eleven fixture proposals. Decides nothing.

Every invalid fixture in the benchmark has a proposed replacement. A reviewer
has to rule on each one, and to do that they need more than the new claim: they
need the premise it rests on, every qualifier the provision carries, which of
those the replacement restores, which it still omits, and whether the source
text under it is sound.

This module assembles exactly that and stops. It emits a recommendation because
a reviewer asked for one, but the recommendation is a reading of the accounting
below it, not a decision, and nothing here writes a gold label.

## The accounting rule

Three states, and the default is the strict one:

    PRESERVED       the replacement carries the qualifier, by the statute's
                    words or its own
    MISSING         it does not
    NOT_APPLICABLE  the qualifier governs a case the claim is not about

NOT_APPLICABLE is deliberately hard to reach. It fires only on an explicit
company-type mismatch — s.103(1)'s "in the case of a private company" against a
claim about public companies — because that is the one case where the statute
names its own scope and the claim names a different one. Everything else that
is not preserved is MISSING. A qualifier waved away as inapplicable is how a
dropped qualifier gets lost a second time.

## What does not count as preserving

Quantity hedges. "At least four meetings" hedges the number; it says nothing
about a power to disapply the section or a prescribed manner of giving notice.
Counting it would let a claim satisfy a qualifier it never addressed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# What phrasing restores each kind of qualifier. Keyed on kind because a
# replacement restores a qualifier in its own words, not the statute's:
# s.174's selector returns as "whichever is higher" and s.101's proviso as
# "subject to the shorter-notice consent requirement".
_RESTORING: dict[str, tuple[str, ...]] = {
    "selector": ("whichever is",),
    "threshold": ("not more than", "more than", "up to", "not less than"),
    "proviso": ("subject to", "shorter notice", "unless", "provided"),
    "articles_override": ("unless", "articles"),
    "government_exemption": ("central government", "exempt", "notification"),
    "delegated_rule": ("prescribed", "prescribed manner"),
    "scope_limit": ("private company", "only", "for the purposes of"),
    "exception": ("except", "unless", "if and so long as"),
}

# Explicitly NOT preserving. A quantity hedge addresses the number, not the
# condition attached to the rule. The reviewer asked for this to be stated
# rather than left implicit.
_NOT_PRESERVING = ("at least", "a minimum of", "no fewer than", "or more")

_COMPANY_TYPES = ("private company", "public company")

# Transcription defects in the served text — see docs/SOURCE_DEFECTS.md SD-004.
# Recorded, never repaired.
_TRANSCRIPTION: tuple[tuple[str, str, str], ...] = (
    ("hall be", "s.174(1) reads 'of a company hall be one-third'; apparent intent "
                "'shall be'", "cosmetic — does not change legal effect"),
    ("maybe prescribed", "s.101(1) reads 'in such manner as maybe prescribed'; "
                         "apparent intent 'may be prescribed'",
     "MATERIAL TO TOOLING — entail_qualifier's 'as may be prescribed' pattern "
     "cannot match this text, so the delegated-rule qualifier is present in law "
     "and invisible to the checker"),
)

PRESERVED, MISSING, NOT_APPLICABLE = "PRESERVED", "MISSING", "NOT_APPLICABLE"
ACCEPT, REJECT, SEND_BACK = "ACCEPT", "REJECT", "SEND BACK"


@dataclass
class QualifierStatus:
    kind: str
    trigger: str
    effect: str
    status: str
    why: str


@dataclass
class Row:
    proposal_id: str
    supersedes: str
    section: str
    subsection: str
    original_claim: str
    original_premise: str
    defect: str
    replacement_claim: str
    supporting_premise: str
    qualifiers: list[QualifierStatus] = field(default_factory=list)
    near_duplicates: list[str] = field(default_factory=list)
    transcription_warnings: list[str] = field(default_factory=list)
    recommendation: str = SEND_BACK
    reason: str = ""

    @property
    def missing(self) -> list[QualifierStatus]:
        return [q for q in self.qualifiers if q.status == MISSING]

    @property
    def preserved(self) -> list[QualifierStatus]:
        return [q for q in self.qualifiers if q.status == PRESERVED]


def _company_type(text: str) -> str | None:
    # Hyphens normalised: the inventory writes "the public-company quorum steps"
    # while claims write "a public company", and a hyphen is not a distinction
    # in scope.
    low = text.lower().replace("-", " ")
    for t in _COMPANY_TYPES:
        if t in low:
            return t
    return None


def _status_of(q, claim: str) -> QualifierStatus:
    low = claim.lower()

    # The one route to NOT_APPLICABLE: the qualifier names a company type and
    # the claim names a different one. Not restricted to scope_limit — s.103(1)'s
    # membership threshold steps the PUBLIC company quorum and has nothing to say
    # about the two-member private-company rule, and charging that claim with
    # dropping it would be false accounting.
    q_type = _company_type(q.trigger + " " + q.effect)
    c_type = _company_type(claim)
    if q_type and c_type and q_type != c_type:
        return QualifierStatus(
            q.kind, q.trigger, q.effect, NOT_APPLICABLE,
            f"governs {q_type} only; this claim is about a {c_type}")

    if q.trigger.lower() in low:
        return QualifierStatus(q.kind, q.trigger, q.effect, PRESERVED,
                               "the claim carries the statute's own words")

    hits = [p for p in _RESTORING.get(q.kind, ()) if p in low]
    if hits:
        return QualifierStatus(q.kind, q.trigger, q.effect, PRESERVED,
                               f"restored in the claim's own words ({hits[0]!r})")

    hedged_only = [h for h in _NOT_PRESERVING if h in low]
    note = "not carried by the replacement"
    if hedged_only:
        note = (f"the claim hedges the quantity ({hedged_only[0]!r}) but does not "
                f"address this qualifier — a quantity hedge does not preserve a "
                f"condition")
    return QualifierStatus(q.kind, q.trigger, q.effect, MISSING, note)


def _content(claim: str) -> set[str]:
    stop = {"the", "of", "for", "a", "at", "as", "is", "in", "or", "and", "to",
            "section", "sets", "that", "an", "by", "be", "with", "its"}
    return {w for w in re.findall(r"[a-z\-]{2,}", claim.lower()) if w not in stop}


_NUMBER_WORD = re.compile(
    r"\b(one|two|three|four|five|six|seven|eight|nine|ten|fifteen|twenty|thirty|"
    r"ninety|hundred|thousand|one-third|two-thirds|per cent)\b", re.I)


def _quantities(claim: str) -> frozenset[str]:
    return frozenset(m.group(0).lower() for m in _NUMBER_WORD.finditer(claim))


def _near_duplicates(rows: list[Row]) -> None:
    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            ca, cb = _content(a.replacement_claim), _content(b.replacement_claim)
            if not ca or not cb:
                continue
            # Two claims about different quantities are different fixtures,
            # however alike their framing. s.103's five/fifteen/thirty-member
            # bands share almost every other word and test three distinct rules.
            if _quantities(a.replacement_claim) != _quantities(b.replacement_claim):
                continue
            jaccard = len(ca & cb) / len(ca | cb)
            if jaccard >= 0.75:
                a.near_duplicates.append(f"{b.proposal_id} (overlap {jaccard:.0%})")
                b.near_duplicates.append(f"{a.proposal_id} (overlap {jaccard:.0%})")


def _warnings(premise: str) -> list[str]:
    # Word-bounded: a substring test matched "hall be" inside "shall be" and
    # reported s.174's typo against every provision in the table.
    low = premise.lower()
    return [f"{desc} [{severity}]" for token, desc, severity in _TRANSCRIPTION
            if re.search(rf"\b{re.escape(token)}\b", low)]


def _recommend(r: Row) -> tuple[str, str]:
    material = [w for w in r.transcription_warnings if "MATERIAL" in w]
    if r.missing:
        kinds = ", ".join(q.kind for q in r.missing)
        return SEND_BACK, (
            f"the replacement still omits {len(r.missing)} qualifier(s) "
            f"({kinds}); a claim that purports to state the rule must carry them")
    if material:
        return SEND_BACK, (
            "a transcription defect in the served text hides a qualifier from the "
            "checker; the replacement cannot be relied on until that is resolved")
    if r.near_duplicates:
        return SEND_BACK, (
            f"asserts substantially the same proposition as "
            f"{', '.join(r.near_duplicates)}; two fixtures carrying one item's "
            f"worth of signal, and one should be replaced with a genuine negative")
    return ACCEPT, ("restores every qualifier the provision attaches to this rule, "
                    "on a complete premise from a clean source span")


def build() -> list[Row]:
    from checker.entail_pairs_v2 import QUALIFIERS, base_pairs, provision, _SPANS
    from checker.fixture_rebuild import propose
    from checker.grounding_policy import INVALID_FIXTURE

    originals = {p.id: p for p in base_pairs() if p.label == INVALID_FIXTURE}
    rows: list[Row] = []
    for p in sorted(propose(), key=lambda x: x.pair_id):
        orig = originals[p.supersedes]
        key = (p.section, p.subsection)
        inv = QUALIFIERS.get(key, [])
        full = provision(p.section)
        row = Row(
            proposal_id=p.pair_id, supersedes=p.supersedes,
            section=p.section, subsection=p.subsection,
            original_claim=p.original_claim,
            original_premise=orig.source_span,
            defect=("stated a real quantity-to-obligation binding unconditionally "
                    "where the provision qualifies it"),
            replacement_claim=p.claim,
            supporting_premise=p.source_span,
            qualifiers=[_status_of(q, p.claim) for q in inv],
            transcription_warnings=_warnings(full),
        )
        rows.append(row)

    _near_duplicates(rows)
    for r in rows:
        r.recommendation, r.reason = _recommend(r)
    return rows


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

    print("review_table")
    rows = build()
    check(len(rows) == 11, f"one row per proposal ({len(rows)})")
    check(all(r.supporting_premise for r in rows),
          "every row carries the premise the replacement rests on")
    check(all(r.reason for r in rows), "every recommendation states its reason")

    by_id = {r.proposal_id: r for r in rows}

    # The reviewer's explicit instruction: s.101's two qualifiers are separate
    # questions and must be reported separately.
    s101 = by_id["v2-p101-qbind-0"]
    kinds = {q.kind for q in s101.qualifiers}
    check(kinds == {"proviso", "delegated_rule"},
          f"s.101 reports both qualifiers separately ({kinds})")
    check(any(q.kind == "delegated_rule" and q.status == MISSING
              for q in s101.qualifiers),
          "s.101's prescribed-manner delegated rule is reported MISSING")
    check(s101.recommendation == SEND_BACK, "...so s.101 goes back, not through")

    # "At least" must never read as preserving a condition.
    q = _status_of(type("Q", (), {"kind": "government_exemption",
                                  "trigger": "the Central Government may, by "
                                             "notification, direct",
                                  "effect": "may disapply the sub-section"})(),
                   "At least four Board meetings must be held each year.")
    check(q.status == MISSING, "'at least' does not preserve a government power")
    check("quantity hedge does not preserve" in q.why, "...and the row says why")

    # s.174's two proposals assert the same proposition.
    a, b = by_id["v2-p174-qbind-0"], by_id["v2-p174-qbind-1"]
    check(a.near_duplicates and b.near_duplicates,
          "the two s.174 proposals are flagged as near-duplicates of each other")

    # s.174(1)'s selector must not be attributed to the sub-section (3) rule.
    check(all(r.subsection == "1" for r in rows if r.section == "174"),
          "only s.174(1) proposals are in the table; the (3) rule is untouched")

    # The transcription defect that hides a qualifier must be surfaced.
    check(any("MATERIAL" in w for w in s101.transcription_warnings),
          "s.101 carries the material transcription warning")
    check(not any("hall be" in w for w in s101.transcription_warnings),
          "...and not s.174's, which a substring test matched inside 'shall be'")
    check(all(not r.transcription_warnings for r in rows if r.section == "103"),
          "a clean provision reports no transcription warning")

    # s.103's three public-company bands differ only in their quantities, and
    # that is exactly what each one tests. They are not duplicates.
    bands = [r for r in rows if r.section == "103"]
    check(all(not r.near_duplicates for r in bands),
          "s.103's membership bands are not flagged as duplicates of each other")
    check(all(not r.missing for r in bands),
          "...and none is charged with a qualifier governing another company type")

    # Nothing here may write a label. A Row has no label field to write, and
    # no row carries one — the reviewer decides, and this table only informs.
    check(not any(f.name == "label" for f in __import__("dataclasses").fields(Row)),
          "a Row has no gold-label field to assign")
    check(all(not hasattr(r, "label") for r in rows),
          "...and no row acquired one")
    check({r.recommendation for r in rows} <= {ACCEPT, REJECT, SEND_BACK},
          "recommendations stay within the three review outcomes")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
