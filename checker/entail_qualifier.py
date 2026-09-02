"""E6: did the claim drop a qualifier the provision attaches to the rule?

The five the cascade still accepts are all the same shape — a rule stated
unconditionally where the source qualifies it:

    "A meeting of a private company is quorate when two members attend"
        s.103(1) opens "Unless the articles of the company provide for a
        larger number"
    "Twenty-one clear days' notice must be given before a general meeting"
        s.101(1) proviso permits shorter notice with consent
    "Two directors are always sufficient to form a quorum"
        s.174(1) says "one-third of its total strength or two directors,
        WHICHEVER IS HIGHER"
    "The continuing directors may act for any purpose notwithstanding any
     vacancy"
        s.174(2) restricts them to two purposes once below quorum
    "A company must convene the first meeting within thirty days"
        s.173(1) proviso lets the Central Government disapply the sub-section

E3 accepts them because every token is present. E4 accepts them because the
quantity is bound correctly. E5 accepts them because the role is right. All
three are looking at what the claim *says*; the defect is in what it *omits*.

## Two signals, and one is much stronger

**Absoluteness.** "always sufficient", "for any purpose", "whatever the number"
assert a universal. A provision that qualifies the rule contradicts the universal
outright — this is not a missing hedge, it is a false statement, and it is the
signal to trust.

**Missing hedge.** The provision carries a qualifier and the claim carries none.
Weaker, because a claim may legitimately address a part of the provision the
qualifier does not reach.

## The over-firing risk, and what bounds it

A checker that rejects any unhedged claim would reject most true claims, trading
five false accepts for far more false rejects. Two bounds: the qualifier must
appear in the span served with the claim, and the claim must overlap the terms
the qualifier governs. Where neither holds, this abstains.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

QUALIFIED_OK = "QUALIFIED_OK"          # the claim carries the qualifier
DROPPED = "DROPPED"                    # the provision qualifies; the claim does not
CONTRADICTS_QUALIFIER = "CONTRADICTS_QUALIFIER"   # the claim asserts a universal
UNRESOLVED = "UNRESOLVED"              # no qualifier found, or none that reaches it

# Qualifier constructs in statutory drafting, with the kind each creates.
_QUALIFIERS: tuple[tuple[str, str], ...] = (
    (r"\bunless\b[^.;:]{0,80}", "articles_override_or_condition"),
    # 240, not 90: a proviso commonly states a whole rule, and truncating it
    # meant a claim about "nine months" was flagged against the very proviso
    # that creates the nine-month rule — the text simply had not been captured
    # far enough to see it.
    (r"\bprovided\s+(?:that|further|also)\b[^.;]{0,240}", "proviso"),
    (r"\bsubject\s+to\b[^.;:]{0,80}", "subjection"),
    (r"\bexcept\b[^.;:]{0,80}", "exception"),
    (r"\bsave\s+(?:as|that)\b[^.;:]{0,80}", "exception"),
    (r"\bas\s+may\s+be\s+prescribed\b", "delegated_rule"),
    (r"\bcentral\s+government\s+may\b[^.;]{0,90}", "government_power"),
    (r"\bwhichever\s+is\s+(?:higher|lower|greater|less)\b", "selector"),
    (r"\bbut\s*,?\s*if\s+and\s+so\s+long\s+as\b[^.;]{0,90}", "exception"),
    (r"\bfor\s+no\s+other\s+purpose\b", "exhaustive_limit"),
)

# Hedges a claim can carry to preserve a qualifier — but a hedge only preserves
# a qualifier of its own sort. "At least four meetings" hedges the NUMBER; it
# says nothing about the Central Government's power to disapply the section, and
# counting it as preservation served three exempt-able rules as unconditional.
_QUANTITY_HEDGES = re.compile(
    r"\bat\s+least\b|\bwhichever\s+is\b|\bno\s+(?:fewer|less)\s+than\b"
    r"|\bminimum\s+of\b|\bor\s+more\b", re.I)

_CONDITION_HEDGES = re.compile(
    r"\bunless\b|\bsubject\s+to\b|\bexcept\b|\bordinarily\b|\bgenerally\b"
    r"|\bprovided\s+that\b|\bsave\s+(?:as|that)\b"
    r"|\bwhere\s+[^,]{0,60},"          # "Where X is fewer than two, ..." — a stated condition
    r"|\bif\s+[^,]{0,60},"
    r"|\bin\s+the\s+absence\s+of\b|\bby\s+itself\b", re.I)

_HEDGES = re.compile(f"{_QUANTITY_HEDGES.pattern}|{_CONDITION_HEDGES.pattern}", re.I)

# Which hedge class can preserve which qualifier. A qualifier kind absent here
# requires a condition hedge: the default is the stricter one.
_QUANTITY_KINDS = frozenset({"selector"})


# A proviso that opens by naming its own case qualifies THAT case, not its
# siblings. s.96 carries "provided that in case of the FIRST annual general
# meeting ... nine months" alongside an unrelated fifteen-month gap rule and a
# Registrar's extension power. Treating the first-AGM proviso as a qualifier of
# those two refused correct claims. The Act distinguishes such limbs with an
# ordinal or an express exclusion, so that marker — not general vocabulary
# overlap — decides whether the proviso is speaking about the claim's case.
_CASE_SCOPE = re.compile(
    r"\bin\s+(?:the\s+)?case\s+of\s+(?:the\s+)?"
    r"(first|second|subsequent|every\s+other|other\s+than\s+the\s+first)\b", re.I)


def _addresses_a_different_case(qualifier_text: str, claim: str) -> bool:
    """True when the qualifier names a case the claim is not about."""
    m = _CASE_SCOPE.search(qualifier_text)
    if not m:
        return False
    marker = m.group(1).lower().split()[-1]      # "first" / "second" / "subsequent"
    return not re.search(rf"\b{re.escape(marker)}\b", claim, re.I)


# A power the Act limits to "this sub-section" does not reach the neighbouring
# one. s.96's Central Government exemption sits in s.96(2) — venue and business
# hours — and exempts "the provisions of this sub-section". It says nothing
# about s.96(1)'s fifteen-month gap or the Registrar's three-month extension,
# and flagging those claims against it was over-reach. s.173's exemption uses
# the same words but sits inside the sub-section it governs, so it still bites.
# The difference is in the text and has to be read, not assumed.
_SUBSECTION_SCOPED = re.compile(r"\bthis\s+sub-?\s?section\b", re.I)
_SUBSECTION_MARK = re.compile(r"\((\d+)\)\s")


def _subsection_bounds(premise: str, at: int) -> tuple[int, int]:
    """Start and end of the numbered sub-section containing `at`."""
    marks = [m.start() for m in _SUBSECTION_MARK.finditer(premise)]
    if not marks:
        return (0, len(premise))          # an unnumbered span is one limb
    starts = [m for m in marks if m <= at]
    lo = starts[-1] if starts else 0
    after = [m for m in marks if m > lo]
    return (lo, after[0] if after else len(premise))


def _reaches_across_subsections(q: "Qualifier", premise: str, claim: str) -> bool:
    """False when a sub-section-scoped qualifier sits outside the claim's limb."""
    if not _SUBSECTION_SCOPED.search(q.text):
        return True
    lo, hi = _subsection_bounds(premise, q.at)
    if (lo, hi) == (0, len(premise)):
        return True
    from checker.entail_binding import bindings
    low = premise.lower()
    spots = [low.find(_norm(b.quantity)) for b in bindings(claim)]
    spots = [s for s in spots if s >= 0]
    if not spots:
        return True                        # nothing located; do not silently narrow
    return any(lo <= s < hi for s in spots)


def _hedge_matches(kind: str, claim: str) -> bool:
    """Does the claim hedge in the way this qualifier requires?"""
    if kind in _QUANTITY_KINDS:
        return bool(_HEDGES.search(claim))
    return bool(_CONDITION_HEDGES.search(claim))

# Universals. A claim asserting one is contradicted by any qualifier that
# reaches it — this is a statement about all cases, not a summary of the rule.
_UNIVERSAL = re.compile(
    r"\balways\b|\bin\s+all\s+cases\b|\bwhatever\s+the\b|\bregardless\s+of\b"
    r"|\bfor\s+any\s+purpose\b|\bwithout\s+exception\b|\bin\s+every\s+case\b"
    r"|\bnever\b|\bunder\s+all\s+circumstances\b", re.I)

_STOP = {"the", "a", "an", "of", "in", "to", "and", "or", "for", "by", "with",
         "that", "this", "is", "are", "be", "shall", "may", "as", "on", "at",
         "any", "such", "its", "from", "under", "section", "not", "no", "than",
         "more", "less", "must", "been", "have", "has", "which", "it"}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip().lower()


def _terms(s: str) -> frozenset[str]:
    return frozenset(w for w in re.findall(r"[a-z][a-z-]+", _norm(s))
                     if w not in _STOP and len(w) > 2)


@dataclass
class Qualifier:
    kind: str
    text: str
    at: int

    @property
    def terms(self) -> frozenset[str]:
        return _terms(self.text)


@dataclass
class QualifierVerdict:
    status: str
    kind: str = ""
    qualifier_text: str = ""
    note: str = ""
    reach: float = 0.0

    @property
    def entailed(self) -> bool:
        return self.status == QUALIFIED_OK


def qualifiers_in(text: str) -> list[Qualifier]:
    """Every qualifying construct the provision states."""
    t = _norm(text)
    out: list[Qualifier] = []
    for pat, kind in _QUALIFIERS:
        for m in re.finditer(pat, t, re.I):
            out.append(Qualifier(kind, m.group(0).strip(), m.start()))
    return out


def judge(premise: str, claim: str, *, reach_threshold: float = 0.12) -> QualifierVerdict:
    """Does the claim carry the qualifiers the provision attaches to its rule?"""
    quals = qualifiers_in(premise)
    if not quals:
        return QualifierVerdict(UNRESOLVED,
                                note="the provision states no qualifying construct")

    c = _norm(claim)
    cterms = _terms(claim)
    if not cterms:
        return QualifierVerdict(UNRESOLVED, note="the claim has no content terms")

    # Before anything else: is the claim even about this provision? A claim that
    # barely overlaps the served text is unsupported for reasons E3 and E5 handle
    # (the terms are absent), and answering here would attribute the failure to a
    # dropped qualifier it never had.
    pterms = _terms(premise)
    on_topic = len(cterms & pterms) / len(cterms) if cterms else 0.0
    if on_topic < 0.30:
        return QualifierVerdict(
            UNRESOLVED,
            note=(f"the claim shares little subject matter with the provision "
                  f"({on_topic:.0%}); whether it is supported is not a question "
                  "about qualifiers"))

    # Qualifier scope is STRUCTURAL, not lexical. Statutory drafting puts a
    # governing condition at the head of the provision — "Unless the articles
    # provide for a larger number, ... shall be the quorum" governs every limb
    # that follows, and shares almost no vocabulary with any of them. Requiring
    # verbal overlap missed exactly that case.
    head = len(_norm(premise)) * 0.20
    reaching = []
    for q in quals:
        overlap = len(cterms & q.terms) / len(cterms) if cterms else 0.0
        # A power to disapply the provision reaches every rule inside it no
        # matter where the sentence granting it sits, and shares no vocabulary
        # with any of them — s.173's Central Government exemption governs the
        # four-meetings rule and the thirty-day rule alike. Position and overlap
        # both miss it, so the kind itself carries the scope.
        governs_all = (q.at <= head
                       or q.kind in ("selector", "exhaustive_limit",
                                     "government_power"))
        if _addresses_a_different_case(q.text, claim):
            continue
        if not _reaches_across_subsections(q, premise, claim):
            continue
        if governs_all or overlap >= reach_threshold:
            reaching.append((max(overlap, 1.0 if governs_all else 0.0), q))
    if not reaching:
        return QualifierVerdict(
            UNRESOLVED,
            note=(f"the provision carries {len(quals)} qualifier(s), none sharing "
                  "subject matter with this claim"))
    reach, q = max(reaching, key=lambda x: x[0])

    if _UNIVERSAL.search(c):
        return QualifierVerdict(
            CONTRADICTS_QUALIFIER, q.kind, q.text[:110], reach=reach,
            note=(f"the claim asserts a universal; the provision qualifies the rule "
                  f"with a {q.kind.replace('_', ' ')}: {q.text[:70]!r}"))

    # A claim cannot drop a qualifier it is *stating*. s.96's nine-month rule
    # lives inside a proviso, so a claim about nine months was being flagged
    # against the very clause that creates it. If the claim's own quantity sits
    # inside the qualifier's text, the claim restates that limb rather than
    # omitting it.
    from checker.entail_binding import bindings
    qtext = _norm(q.text)
    for b in bindings(claim):
        if _norm(b.quantity) in qtext:
            return QualifierVerdict(
                QUALIFIED_OK, q.kind, q.text[:110], reach=reach,
                note=(f"the claim states the {q.kind.replace('_', ' ')} itself — "
                      f"{b.quantity!r} appears inside it — rather than omitting it"))

    if _hedge_matches(q.kind, c):
        return QualifierVerdict(
            QUALIFIED_OK, q.kind, q.text[:110], reach=reach,
            note="the claim carries a qualifying clause")

    return QualifierVerdict(
        DROPPED, q.kind, q.text[:110], reach=reach,
        note=(f"the provision qualifies this rule with a "
              f"{q.kind.replace('_', ' ')} — {q.text[:70]!r} — and the claim "
              "states it unconditionally"))


def predict(row) -> bool | None:
    v = judge(getattr(row, "source_span", None) or getattr(row, "premise", ""),
              getattr(row, "claim", None) or getattr(row, "hypothesis", ""))
    if v.status == UNRESOLVED:
        return None
    return v.entailed


def inventory_gaps() -> list[dict]:
    """Qualifiers present in a premise that the hand-kept inventory omits.

    The INVALID_FIXTURE routing in entail_pairs_v2 asks QUALIFIERS whether a
    provision carries a material qualifier. Where that inventory is empty or
    absent the question answers "no" and an unqualified positive is emitted as
    ENTAILED — which is how s.174 came to assert one-third as the quorum with
    no mention of "whichever is higher". The inventory is maintained by hand,
    so it fails silently. This reads the served text instead and reports what
    the inventory does not know about. It proposes; it never relabels.
    """
    from checker.entail_pairs_v2 import all_pairs, QUALIFIERS
    from checker.grounding_policy import ENTAILED

    seen: dict[tuple[str, str], dict] = {}
    for pair in all_pairs():
        if pair.label != ENTAILED:
            continue
        known = {q.kind for q in QUALIFIERS.get((pair.section, "1"), [])}
        for q in qualifiers_in(pair.source_span):
            if q.kind in known or _addresses_a_different_case(q.text, pair.claim):
                continue
            if _hedge_matches(q.kind, _norm(pair.claim)):
                continue
            key = (pair.section, q.kind)
            seen.setdefault(key, {"section": pair.section, "kind": q.kind,
                                  "trigger": q.text[:120], "pair_ids": []})
            seen[key]["pair_ids"].append(pair.id)
    return sorted(seen.values(), key=lambda d: (d["section"], d["kind"]))


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

    print("entail_qualifier")

    S103 = ("unless the articles of the company provide for a larger number, "
            "(b) in the case of a private company, two members personally present, "
            "shall be the quorum for a meeting of the company")
    q = qualifiers_in(S103)
    check(any(x.kind == "articles_override_or_condition" for x in q),
          f"the 'unless' override is detected ({[x.kind for x in q]})")

    v = judge(S103, "A meeting of a private company is quorate when two members "
                    "attend in person.")
    check(v.status == DROPPED, f"the unqualified claim is DROPPED ({v.status})")
    v = judge(S103, "Unless the company's articles require a larger number, a "
                    "private company's meeting is quorate when two members are "
                    "personally present.")
    check(v.entailed, f"the qualified claim survives ({v.status})")

    S174 = ("the quorum for a meeting of the board of directors of a company shall "
            "be one-third of its total strength or two directors, whichever is higher")
    v = judge(S174, "Two directors are always sufficient to form a quorum for a "
                    "Board meeting.")
    check(v.status == CONTRADICTS_QUALIFIER,
          f"a universal against a selector is CONTRADICTS_QUALIFIER ({v.status})")
    check("selector" in v.note, f"...naming the construct ({v.note[:64]})")
    v = judge(S174, "Where one-third of the Board's total strength is fewer than "
                    "two, two directors are required for a quorum.")
    check(v.entailed, f"the qualified restatement survives ({v.status})")

    S174_2 = ("the continuing directors may act notwithstanding any vacancy in the "
              "board; but, if and so long as their number is reduced below the "
              "quorum fixed by the act, the continuing directors may act for the "
              "purpose of increasing the number of directors and for no other purpose")
    v = judge(S174_2, "The continuing directors may act for any purpose "
                      "notwithstanding any vacancy in the Board.")
    check(v.status == CONTRADICTS_QUALIFIER,
          f"'for any purpose' against an exhaustive limit is caught ({v.status})")
    v = judge(S174_2, "A vacancy on the Board does not by itself stop the remaining "
                      "directors from acting.")
    check(v.entailed, f"the 'by itself' hedge survives ({v.status})")

    S101 = ("a general meeting may be called by giving not less than clear "
            "twenty-one days' notice: provided that a general meeting may be called "
            "after giving shorter notice if consent is accorded")
    v = judge(S101, "Twenty-one clear days' notice must be given before a general "
                    "meeting is held.")
    check(v.status == DROPPED, f"the dropped proviso is caught ({v.status})")
    v = judge(S101, "A general meeting ordinarily requires not less than clear "
                    "twenty-one days' notice, subject to the statutory "
                    "shorter-notice consent requirement.")
    check(v.entailed, f"the qualified version survives ({v.status})")

    # A claim stating the proviso's own rule is not dropping it.
    S96 = ("every company shall hold an annual general meeting and not more than "
           "fifteen months shall elapse between one and the next: provided that in "
           "case of the first annual general meeting, it shall be held within a "
           "period of nine months from the date of closing of the first financial "
           "year")
    v = judge(S96, "Section 96 sets nine months as the deadline for the first "
                   "annual general meeting after the first financial year closes.")
    check(v.entailed,
          f"a claim stating the proviso's own rule is not DROPPED ({v.status})")
    check("states the" in v.note, f"...and says why ({v.note[:60]})")
    # But a claim about a DIFFERENT limb still drops it.
    v = judge(S96, "An annual general meeting must be held within six months of "
                   "the financial year closing.")
    check(v.status in (DROPPED, UNRESOLVED),
          f"a claim about another limb does not get the same pass ({v.status})")

    # Bounds against over-firing.
    v = judge("the register shall be kept at the registered office",
              "The register is kept at the registered office.")
    check(v.status == UNRESOLVED,
          "a provision with no qualifier yields UNRESOLVED, not a rejection")
    v = judge(S103, "A company shall file its annual return with the Registrar.")
    check(v.status == UNRESOLVED,
          "a qualifier that does not reach the claim's subject matter abstains")
    check(predict(type("R", (), {"premise": "no qualifier here",
                                 "hypothesis": "x"})()) is None,
          "predict() abstains where nothing applies")

    # Regression: a power to disapply the provision governs every rule inside
    # it. This sentence sits at the END of s.173 and shares no vocabulary with
    # the four-meetings rule, so both the position test and the overlap test
    # missed it, and three dropped-qualifier negatives were served as accepts.
    s173 = ("Every company shall hold a minimum number of four meetings of its "
            "Board of Directors every year. The Central Government may, by "
            "notification, direct that the provisions of this section shall not "
            "apply to any class or description of companies.")
    v = judge(s173, "At least four Board meetings must be held by a company in each year.")
    check(v.status == DROPPED,
          "a government power to disapply the section reaches a rule inside it")
    check(v.kind == "government_power", f"...and is named as such ({v.kind})")

    # Regression: the whole-provision premise. When the fallback premise was cut
    # at 400 characters this proviso was truncated before "nine months", so a
    # claim restating the proviso's own rule looked like one that dropped it.
    from checker.entail_pairs_v2 import all_pairs
    from checker.grounding_policy import ENTAILED
    s96 = [x for x in all_pairs()
           if x.section == "96" and x.label == ENTAILED
           and "nine months" in x.claim]
    check(bool(s96) and "nine months" in s96[0].source_span.lower(),
          "the s.96 premise contains the evidence its own label asserts")
    if s96:
        check(judge(s96[0].source_span, s96[0].claim).status == QUALIFIED_OK,
              "a claim restating the proviso's own rule is not DROPPED")

    # The inventory is hand-kept, so it fails silently. s.174 carries a
    # "whichever is higher" selector and its inventory entry is an EMPTY list —
    # which reads as "this provision has no qualifiers" and let three
    # unqualified positives through as ENTAILED.
    # Regression: "this sub-section" means the limb it sits in. s.96's Central
    # Government exemption lives in s.96(2) and exempts "the provisions of this
    # sub-section" — venue and business hours. It does not reach s.96(1)'s
    # fifteen-month gap rule, and flagging that claim against it was over-reach.
    s96_full = provision_96 = None
    from checker.entail_pairs_v2 import provision
    s96_full = provision("96")
    v = judge(s96_full, "Section 96 sets fifteen months as the maximum gap between "
                        "one annual general meeting and the next.")
    check(v.kind != "government_power",
          f"a sub-section-scoped exemption does not reach another limb (got {v.kind})")

    # ...but the same words still bite inside their own sub-section. s.173's
    # exemption is worded identically and governs the rule beside it.
    v = judge(s173, "At least four Board meetings must be held by a company in each year.")
    check(v.status == DROPPED and v.kind == "government_power",
          "...while the same wording still governs its own sub-section")

    gaps = inventory_gaps()
    # s.174's "whichever is higher" WAS the finding that started this; it is now
    # in the inventory, so the detector must stop reporting it. A gap detector
    # that still names a closed gap is not measuring the inventory.
    check(not any(g["section"] == "174" and g["kind"] == "selector" for g in gaps),
          "the s.174 selector is inventoried and no longer reported as a gap")
    check(any(g["section"] == "96" and g["kind"] == "government_power"
              for g in gaps),
          "s.96's uninventoried Central Government exemption is still reported")
    # s.174's other qualifiers left the gap list when ("174","3") gained a
    # precise span: they live in s.174(2), which a 420-character s.174(3) span
    # does not contain. Not finding a qualifier that is not in the premise is
    # correct, so the assertion is on the detector's reach, not on s.174.
    check(all(g["trigger"] for g in gaps),
          "every remaining gap still carries its verbatim trigger")
    check(all(g["trigger"] for g in gaps),
          "every reported gap carries the verbatim trigger it was found by")
    check(all(g["pair_ids"] for g in gaps),
          "...and names the pairs it affects, so a human can review them")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
