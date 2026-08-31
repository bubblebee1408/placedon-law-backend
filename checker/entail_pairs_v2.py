"""Paraphrase pairs under the strict grounding convention.

The v1 set contained a contradiction I introduced and did not notice: four
positives stated a rule unconditionally while the provision qualified it, and
structurally identical claims were labelled NOT_ENTAILED elsewhere in the same
file. A checker trained on both receives opposite signal from the same shape.

Under the fail-closed convention an unqualified claim is NOT_ENTAILED whenever
its source carries a material proviso, exception, threshold, condition, scope
limit, or delegated-rule limitation. The defective positives are therefore
**rewritten to carry their qualifiers**, and their original unqualified forms are
**kept as negatives** — which is where they always belonged, and which turns a
mistake into six extra pairs testing precisely the failure mode that motivated
the convention.

## The model does not certify its own work

Every positive whose label rests on reading the provision is `HUMAN_JUDGED` and
carries `reviewer_status = PENDING_REVIEW`. `frozen_candidates()` excludes them.
A model may propose a rewrite and may flag a defect; it may not sign one off.

Negatives built by mechanical rebinding are `CONSTRUCTED` — false because they
were built false. Qualifier inventories are `SOURCE_CHECKED`: each qualifier is
asserted only if its trigger phrase is verified present in the source span, so a
mis-stated inventory fails a test rather than travelling silently.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict, field
from pathlib import Path

from checker.grounding_policy import (
    CONSTRUCTED, ENTAILED, HUMAN_JUDGED, INVALID_FIXTURE, NOT_ENTAILED,
    PENDING_REVIEW, REVIEW_APPROVED, REVIEW_PENDING, SOURCE_CHECKED,
)



@dataclass
class Qualifier:
    kind: str
    trigger: str        # the phrase in the source that creates it
    effect: str         # what it does to the general rule


@dataclass
class Pair:
    id: str
    section: str
    subsection: str
    source_span: str
    claim: str
    label: str
    label_basis: str
    qualifiers: list[dict] = field(default_factory=list)
    preserves_all_qualifiers: bool | None = None
    reviewer_status: str = REVIEW_PENDING
    reviewer: str | None = None
    reviewed_at: str | None = None
    rationale: str = ""
    kind: str = ""
    supersedes: str | None = None

    @property
    def frozen_eligible(self) -> bool:
        """May this enter the frozen benchmark without a human?"""
        if self.label in (PENDING_REVIEW, INVALID_FIXTURE):
            return False
        if self.label_basis == HUMAN_JUDGED:
            return self.reviewer_status == REVIEW_APPROVED
        return True


# A whole-provision fallback, not a 400-char head. At 400 the s.96 slice cut
# into the middle of the first proviso, so the premise stopped before "nine
# months" while a pair labelled ENTAILED asserted exactly that. The premise did
# not contain the evidence for its own label. The cap stays only to bound a
# pathologically long section; the longest fallback section here is 1858 chars.
_FALLBACK_PREMISE_CHARS = 2500


def provision(number: str) -> str:
    from checker.section_index import section_by_number
    rec = section_by_number(number)
    if not rec:
        raise KeyError(f"s.{number} not in the corpus")
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", rec["content"])).strip()


def span(number: str, start: str, length: int) -> str:
    t = provision(number)
    m = re.search(start, t)
    if not m:
        raise ValueError(f"s.{number}: span anchor not found: {start!r}")
    return t[m.start():m.start() + length].strip()


# --- qualifier inventories, each tied to a verified trigger phrase -----------
# (section, subsection) -> qualifiers. Every trigger is asserted present in the
# source span by a test; an inventory that drifts from the text fails loudly.
QUALIFIERS: dict[tuple[str, str], list[Qualifier]] = {
    ("173", "1"): [
        Qualifier("government_exemption",
                  "the Central Government may, by notification, direct",
                  "may disapply s.173(1) to prescribed classes of companies"),
    ],
    ("173", "2"): [
        Qualifier("delegated_rule", "as may be prescribed",
                  "the permitted means of participation are set by rules"),
        Qualifier("government_exemption", "the Central Government may, by notification, specify",
                  "may bar specified matters from being dealt with by video conferencing"),
    ],
    ("103", "1"): [
        Qualifier("articles_override", "Unless the articles of the company provide for a larger number",
                  "the articles may require a larger quorum than the statutory floor"),
        Qualifier("threshold", "not more than one thousand",
                  "the public-company quorum steps with membership size"),
        Qualifier("scope_limit", "in the case of a private company",
                  "the two-member quorum reaches private companies only"),
    ],
    ("103", "2"): [
        Qualifier("exception", "if called by requisitionists under section 100",
                  "such a meeting stands cancelled rather than adjourned"),
        Qualifier("scope_limit", "as the Board may determine",
                  "the Board may fix a different date, time or place"),
    ],
    ("101", "1"): [
        Qualifier("proviso", "Provided that a general meeting may be called after giving shorter notice",
                  "shorter notice is permitted with the prescribed consent"),
        Qualifier("delegated_rule", "in such manner as maybe prescribed",
                  "the manner of giving notice is set by rules"),
    ],
    # Was an EMPTY list, which the INVALID_FIXTURE routing reads as "this
    # provision carries no qualifier" — so three unqualified positives were
    # emitted as ENTAILED. s.174(1) fixes the quorum at one-third of total
    # strength OR two directors, WHICHEVER IS HIGHER. Stating either limb alone
    # is wrong on a small board: on three directors one-third is 1, the quorum
    # is 2. Found by entail_qualifier.inventory_gaps().
    ("174", "1"): [
        Qualifier("selector", "whichever is higher",
                  "the quorum is the greater of one-third of total strength and "
                  "two directors; neither limb states it alone"),
    ],
    ("174", "2"): [
        Qualifier("exception", "if and so long as their number is reduced below the quorum",
                  "continuing directors may then act only for limited purposes"),
    ],
}

_SPANS: dict[tuple[str, str], tuple[str, int]] = {
    ("173", "1"): (r"\(1\) Every company shall hold", 430),
    ("173", "2"): (r"\(2\) The participation of directors", 430),
    # 620, not 480: the private-company limb sits at offset 483 and the
    # "in the case of a private company" qualifier must fall inside the span it
    # is asserted against. The trigger-verification test caught this.
    ("103", "1"): (r"Unless the articles", 620),
    ("103", "2"): (r"\(2\) If the quorum is not present", 400),
    ("101", "1"): (r"\(1\) A general meeting", 330),
    ("174", "1"): (r"\(1\) The quorum for a meeting", 300),
    ("174", "2"): (r"\(2\) The continuing directors", 360),
}


def subsection_of(section: str, quantity: str) -> str:
    """Which numbered sub-section the quantity actually sits in.

    The pair builder used to assume "1" for every constructed pair, so s.174's
    "whichever is higher" — a qualifier on the sub-section (1) quorum — was
    applied to a claim about the two-thirds interested-director rule in
    sub-section (3), and invalidated a fixture that was sound. The quantity is
    recorded by the builder, so its sub-section is read from the text rather
    than assumed. Falls back to "1" when the provision carries no markers or
    the quantity cannot be located: this must never narrow silently.
    """
    text = provision(section)
    at = text.lower().find(quantity.lower())
    if at < 0:
        return "1"
    marks = [(m.start(), m.group(1)) for m in re.finditer(r"\((\d+)\)\s", text)]
    before = [num for start, num in marks if start <= at]
    return before[-1] if before else "1"


def source_span(section: str, sub: str) -> str:
    pat, ln = _SPANS[(section, sub)]
    return span(section, pat, ln)


# --- the rewritten pairs ----------------------------------------------------
# (id, sec, sub, claim, label, basis, preserves, rationale, kind, supersedes)
_REWRITTEN: list[tuple] = [
    # J1 -> qualified positive + its unqualified form as a negative
    ("v2-173-1-pos", "173", "1",
     "The first meeting of the Board must ordinarily be held within thirty days of "
     "incorporation, subject to the Central Government's power to exempt prescribed "
     "classes of companies.",
     PENDING_REVIEW, HUMAN_JUDGED, True,
     "restates the first-meeting deadline and carries the s.173(1) exemption",
     "paraphrase_qualified", "p173-auth-11"),
    ("v2-173-1-neg", "173", "1",
     "A company must convene the first meeting of its Board no later than thirty days "
     "after it is incorporated.",
     NOT_ENTAILED, CONSTRUCTED, False,
     "states the rule as unconditional; drops the Central Government exemption in "
     "the s.173(1) proviso",
     "dropped_government_exemption", "p173-auth-11"),

    # J2
    ("v2-173-1b-pos", "173", "1",
     "A company must ordinarily hold at least four Board meetings each year, subject "
     "to the Central Government's power to exempt prescribed classes of companies.",
     PENDING_REVIEW, HUMAN_JUDGED, True,
     "restates the minimum number and carries the exemption",
     "paraphrase_qualified", "p173-auth-12"),
    ("v2-173-1b-neg", "173", "1",
     "At least four Board meetings must be held by a company in each year.",
     NOT_ENTAILED, CONSTRUCTED, False,
     "unconditional; drops the Central Government exemption",
     "dropped_government_exemption", "p173-auth-12"),

    # J3
    # REVOKED 2026-08-26. The prior wording read "except for matters the Central
    # Government HAS BARRED", which converts a conferred statutory power into an
    # assertion that the power has been exercised. s.173(2) says the Central
    # Government "may, by notification, specify" such matters; whether any
    # notification exists, and what it specifies, are separate facts this corpus
    # does not hold. The replacement keeps the three apart: the power, its
    # exercise by notification, and the matters any notification specifies.
    ("v2-173-2-pos-r2", "173", "2",
     "Directors may take part in a Board meeting through video conferencing or other "
     "audio visual means in the manner prescribed, subject to the Central "
     "Government's power to specify by notification matters that may not be dealt "
     "with by those means.",
     PENDING_REVIEW, HUMAN_JUDGED, True,
     "carries the delegated-rule condition and states the excluded-matters bar as a "
     "power conferred, not as a power exercised; supersedes v2-173-2-pos, which "
     "asserted that matters had been barred",
     "paraphrase_qualified", "v2-173-2-pos"),
    ("v2-173-2-neg", "173", "2",
     "Directors are permitted to take part in a Board meeting by video link rather "
     "than in person.",
     NOT_ENTAILED, CONSTRUCTED, False,
     "drops 'as may be prescribed' and the Central Government's power to bar "
     "specified matters from video conferencing",
     "dropped_delegated_rule", "p173-auth-13"),

    # J5
    ("v2-103-1-pos", "103", "1",
     "Unless the company's articles require a larger number, a private company's "
     "meeting is quorate when two members are personally present.",
     PENDING_REVIEW, HUMAN_JUDGED, True,
     "restates the private-company quorum and carries the articles override",
     "paraphrase_qualified", "p103-auth-15"),
    ("v2-103-1-neg", "103", "1",
     "A meeting of a private company is quorate when two members attend in person.",
     NOT_ENTAILED, CONSTRUCTED, False,
     "drops 'Unless the articles of the company provide for a larger number', which "
     "opens s.103(1)",
     "dropped_articles_override", "p103-auth-15"),

    # J6
    ("v2-103-2-pos", "103", "2",
     "Where a quorum is absent within half an hour, the meeting stands adjourned to "
     "the same day in the next week unless the Board determines another date, time or "
     "place, or, if the meeting was called by requisitionists under section 100, it "
     "stands cancelled.",
     PENDING_REVIEW, HUMAN_JUDGED, True,
     "carries both the Board's power to fix another date and the requisitionist "
     "cancellation limb",
     "paraphrase_qualified", "p103-auth-16"),
    ("v2-103-2-neg", "103", "2",
     "If too few members attend within half an hour, the meeting is put off to the "
     "same day the following week.",
     NOT_ENTAILED, CONSTRUCTED, False,
     "drops the requisitionist-cancellation exception and the Board's power to fix "
     "another date",
     "dropped_exception", "p103-auth-16"),

    # J7
    ("v2-101-1-pos", "101", "1",
     "A general meeting ordinarily requires not less than clear twenty-one days' "
     "notice, subject to the statutory shorter-notice consent requirement.",
     PENDING_REVIEW, HUMAN_JUDGED, True,
     "restates the notice period and carries the shorter-notice proviso",
     "paraphrase_qualified", "p101-auth-18"),
    ("v2-101-1-neg", "101", "1",
     "Twenty-one clear days' notice must be given before a general meeting is held.",
     NOT_ENTAILED, CONSTRUCTED, False,
     "unconditional; drops the proviso permitting shorter notice with consent",
     "dropped_proviso", "p101-auth-18"),

    # J4 and J8 survived the adversarial read. Still HUMAN_JUDGED: a model that
    # failed to break a claim has not thereby established it.
    ("v2-174-1-pos", "174", "1",
     "Where one-third of the Board's total strength is fewer than two, two directors "
     "are required for a quorum.",
     PENDING_REVIEW, HUMAN_JUDGED, True,
     "arithmetic on 'one-third of its total strength or two directors, whichever is "
     "higher'; s.174(1) carries no proviso",
     "arithmetic_claim", None),
    ("v2-174-2-pos", "174", "2",
     "A vacancy on the Board does not by itself stop the remaining directors from "
     "acting.",
     PENDING_REVIEW, HUMAN_JUDGED, True,
     "'by itself' preserves the s.174(2) restriction that applies once the number "
     "falls below the quorum",
     "by_itself_claim", None),

    # An arithmetic claim that drops a statutory condition — the failure mode the
    # J4 shape could take if written carelessly.
    ("v2-174-1-neg", "174", "1",
     "Two directors are always sufficient to form a quorum for a Board meeting.",
     NOT_ENTAILED, CONSTRUCTED, False,
     "drops 'whichever is higher': where one-third of total strength exceeds two, "
     "two directors are not enough",
     "dropped_threshold", None),
    ("v2-174-2-neg", "174", "2",
     "The continuing directors may act for any purpose notwithstanding any vacancy "
     "in the Board.",
     NOT_ENTAILED, CONSTRUCTED, False,
     "drops the exception restricting them to increasing the number of directors or "
     "summoning a general meeting once below quorum",
     "dropped_exception", None),
    ("v2-103-1-neg-scope", "103", "1",
     "Five members personally present shall be the quorum for a meeting of a public "
     "company, whatever the number of its members.",
     NOT_ENTAILED, CONSTRUCTED, False,
     "drops the membership threshold: five applies only up to one thousand members",
     "dropped_threshold", None),
]


def rewritten_pairs() -> list[Pair]:
    from checker.reviews import status_of
    out = []
    for (pid, sec, sub, claim, label, basis, preserves, why, kind, sup) in _REWRITTEN:
        quals = [asdict(q) for q in QUALIFIERS.get((sec, sub), [])]
        st, who, when = status_of(pid)
        # A HUMAN_JUDGED pair carries PENDING_REVIEW until a person decides. Once
        # approved it takes the gold label the reviewer signed off; the model
        # never writes that transition itself.
        if basis == HUMAN_JUDGED and st == REVIEW_APPROVED:
            label = ENTAILED
        out.append(Pair(
            id=pid, section=sec, subsection=sub, source_span=source_span(sec, sub),
            claim=claim, label=label, label_basis=basis, qualifiers=quals,
            preserves_all_qualifiers=preserves, reviewer_status=st, reviewer=who,
            reviewed_at=when, rationale=why, kind=kind, supersedes=sup,
        ))
    return out


def constructed_pairs() -> list[Pair]:
    """The mechanical rebinds from v1, re-expressed in the v2 schema."""
    from checker.entail_paraphrase import rebind_pairs, SUPPORTED
    out = []
    for p in rebind_pairs():
        sub = subsection_of(p.section, p.provenance.get("real_quantity", "")) \
            if p.provenance.get("real_quantity") else "1"
        quals = [asdict(q) for q in QUALIFIERS.get((p.section, sub), [])]
        is_positive = p.gold == SUPPORTED
        if is_positive and quals:
            # The strict convention invalidates these. "Section 103 sets two
            # members as the quorum for a private company" drops the articles
            # override that opens s.103(1), so it is not entailed — and it was
            # built as a positive under the old convention, not the new one.
            # Relabelling it NOT_ENTAILED would be worse: it is a true statement
            # of the binding, wrongly framed. INVALID_FIXTURE says exactly that,
            # and rebuilding it as a qualified positive is a HUMAN_JUDGED task.
            label = INVALID_FIXTURE
            preserves = False
            why = (f"unqualified statement of a rule carrying "
                   f"{', '.join(q['kind'] for q in quals)}; invalid under the "
                   f"strict convention, rebuild as a qualified positive")
        else:
            label = ENTAILED if is_positive else NOT_ENTAILED
            # Vacuously true where the provision carries no material qualifier.
            preserves = True if is_positive else False
            why = p.rationale
        out.append(Pair(
            id=f"v2-{p.id}", section=p.section, subsection=sub,
            source_span=source_span(p.section, sub) if (p.section, sub) in _SPANS
            else provision(p.section)[:_FALLBACK_PREMISE_CHARS],
            claim=p.claim, label=label, label_basis=CONSTRUCTED, qualifiers=quals,
            preserves_all_qualifiers=preserves, rationale=why, kind=p.kind,
        ))
    return out


def approved_replacements() -> list[Pair]:
    """Rebuilt fixtures that a human has approved.

    Imported here rather than defined in this module so the proposal machinery
    stays separate from the pair set: a proposal that nobody approved must not
    be able to reach the benchmark by being in the same file as pairs that were.
    """
    from checker.fixture_rebuild import propose
    from checker.reviews import status_of
    out = []
    for pr in propose():
        st, who, when = status_of(pr.pair_id)
        if st != REVIEW_APPROVED:
            continue
        out.append(Pair(
            id=pr.pair_id, section=pr.section, subsection=pr.subsection,
            source_span=pr.source_span, claim=pr.claim, label=ENTAILED,
            label_basis=HUMAN_JUDGED, qualifiers=pr.qualifiers,
            preserves_all_qualifiers=True, reviewer_status=st, reviewer=who,
            reviewed_at=when, rationale=pr.transformation,
            kind="paraphrase_qualified", supersedes=pr.supersedes,
        ))
    return out


def base_pairs() -> list[Pair]:
    """Pairs before approved replacements are folded in.

    `propose()` reads this rather than `all_pairs()`: a replacement is derived
    from an invalid fixture, so having the proposal generator read the set that
    already contains approved replacements is a cycle.
    """
    return rewritten_pairs() + constructed_pairs()


def all_pairs() -> list[Pair]:
    return base_pairs() + approved_replacements()


def frozen_candidates() -> list[Pair]:
    return [p for p in all_pairs() if p.frozen_eligible]


# --- contradiction scan -----------------------------------------------------
_STOP = {"the", "a", "an", "of", "in", "to", "and", "or", "for", "by", "with",
         "that", "is", "are", "be", "shall", "may", "as", "on", "at", "any",
         "such", "its", "from", "under", "section", "must", "ordinarily"}

# Words that signal a qualifier is being carried. Their presence is what should
# separate an entailed positive from its unqualified negative twin.
_HEDGES = {"unless", "subject", "ordinarily", "except", "prescribed", "provided",
           "itself", "whichever", "requisitionists", "determines"}


def _content(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z][a-z'-]+", s.lower())
            if w not in _STOP and len(w) > 2}


def contradictions(pairs: list[Pair] | None = None) -> list[dict]:
    """Positive/negative pairs on the same provision differing only by a hedge.

    Two claims about the same section and subsection whose content words are
    nearly identical, labelled oppositely, and where the difference is entirely
    hedging language, are either the qualified/unqualified pair this convention
    is built on — legitimate, and marked by `supersedes` — or an unreconciled
    contradiction. Anything unmarked is reported.
    """
    pairs = pairs if pairs is not None else all_pairs()
    found = []
    for i, a in enumerate(pairs):
        for b in pairs[i + 1:]:
            if (a.section, a.subsection) != (b.section, b.subsection):
                continue
            if a.label == b.label or PENDING_REVIEW in (a.label, b.label):
                continue
            ca, cb = _content(a.claim), _content(b.claim)
            if not ca or not cb:
                continue
            overlap = len(ca & cb) / min(len(ca), len(cb))
            if overlap < 0.55:
                continue
            # The difference must be *driven* by hedging, not consist solely of
            # hedge words: "unless the articles provide otherwise" contributes
            # 'articles' and 'otherwise' alongside 'unless', and requiring an
            # exact subset of _HEDGES missed the planted case entirely.
            diff = (ca ^ cb)
            if diff and (diff & _HEDGES) and len(diff - _HEDGES) <= 3:
                found.append({"a": a.id, "b": b.id, "overlap": round(overlap, 2),
                              "differ_by": sorted(diff),
                              "reconciled": bool(a.supersedes or b.supersedes)})
    return [f for f in found if not f["reconciled"]]


def qualifier_failures(pairs: list[Pair] | None = None) -> list[dict]:
    """Positives labelled ENTAILED that do not claim to preserve qualifiers."""
    pairs = pairs if pairs is not None else all_pairs()
    out = []
    for p in pairs:
        if p.label != ENTAILED or not p.qualifiers:
            continue
        if p.preserves_all_qualifiers is not True:
            out.append({"id": p.id, "section": p.section,
                        "qualifiers": [q["kind"] for q in p.qualifiers]})
    return out


# write() and its OUT path are deliberately gone. They emitted
# corpus/benchmark/entailment_pairs_v2.jsonl, an ungoverned copy of the gold
# labels that nothing read, that the freeze manifest did not hash, and that
# drifted 71 -> 78 records across several sessions while looking exactly like
# benchmark data. It also carried a reviewer's email address for eight records
# long after reviews.record() began refusing one. The governed artefact is
# corpus/benchmark/approved_pairs.jsonl, written only by
# benchmark_v2_freeze.freeze(promote=True). Two files that both look like the
# benchmark is how the wrong one eventually gets cited.


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

    print("entail_pairs_v2")

    pairs = all_pairs()
    by_id = {p.id: p for p in pairs}

    # --- qualifier inventories must match the source, not my memory of it ---
    for (sec, sub), quals in QUALIFIERS.items():
        sp = source_span(sec, sub).lower()
        for q in quals:
            assert q.trigger.lower() in sp, f"s.{sec}({sub}): {q.trigger!r} not in span"
    check(True, "every qualifier's trigger phrase is verified present in its source span")

    # --- the ten regression cases -------------------------------------------
    cases = [
        ("dropped proviso",              "v2-101-1-neg",       "dropped_proviso"),
        ("dropped exception",            "v2-103-2-neg",       "dropped_exception"),
        ("dropped threshold",            "v2-103-1-neg-scope", "dropped_threshold"),
        ("dropped scope restriction",    "v2-103-1-neg",       "dropped_articles_override"),
        ("'subject to rules prescribed'","v2-173-2-neg",       "dropped_delegated_rule"),
        ("'unless articles' omission",   "v2-103-1-neg",       "dropped_articles_override"),
        ("government exemption omission","v2-173-1-neg",       "dropped_government_exemption"),
        ("arithmetic w/ omitted condition","v2-174-1-neg",     "dropped_threshold"),
    ]
    for name, pid, kind in cases:
        p = by_id.get(pid)
        check(p is not None and p.label == NOT_ENTAILED and p.kind == kind,
              f"regression: {name} is NOT_ENTAILED ({pid})")

    j4 = by_id["v2-174-1-pos"]; j8 = by_id["v2-174-2-pos"]
    check(j4.kind == "arithmetic_claim" and j8.kind == "by_itself_claim",
          "regression: arithmetic and 'by itself' claims are represented")
    check(j8.label_basis == HUMAN_JUDGED,
          "a claim a model failed to break is still HUMAN_JUDGED, not established")

    # --- contradiction detection --------------------------------------------
    cons = contradictions()
    check(cons == [], f"no unreconciled contradictions ({len(cons)}): {cons[:2]}")

    # The detector must actually fire; a scanner that never triggers proves nothing.
    planted = [
        Pair("x-pos", "103", "1", "src", "A private company meeting is quorate with "
             "two members present.", ENTAILED, CONSTRUCTED),
        Pair("x-neg", "103", "1", "src", "Unless the articles provide otherwise, a "
             "private company meeting is quorate with two members present.",
             NOT_ENTAILED, CONSTRUCTED),
    ]
    check(len(contradictions(planted)) == 1,
          "regression: a positive/negative differing only by a dropped qualifier is caught")

    # --- qualifier preservation ---------------------------------------------
    qf = qualifier_failures()
    check(qf == [], f"no ENTAILED pair silently drops a qualifier ({len(qf)})")
    bad = [Pair("y", "101", "1", "src", "Notice must be given.", ENTAILED,
                HUMAN_JUDGED, qualifiers=[{"kind": "proviso", "trigger": "t", "effect": "e"}],
                preserves_all_qualifiers=False)]
    check(len(qualifier_failures(bad)) == 1,
          "regression: an ENTAILED pair not preserving qualifiers is flagged")

    # --- every negative documents WHY ---------------------------------------
    negs = [p for p in pairs if p.label == NOT_ENTAILED]
    check(all(p.rationale for p in negs),
          f"every negative has a documented reason ({len(negs)})")

    # --- human approval gate ------------------------------------------------
    # These four asserted the pre-approval state, which approval made obsolete.
    # The safety property is what must survive, so they now test the invariant on
    # a synthetic unapproved pair rather than on whatever the queue happens to
    # hold today.
    judged = [p for p in pairs if p.label_basis == HUMAN_JUDGED]
    unapproved = Pair("z-unapproved", "173", "1", "src", "some claim",
                      PENDING_REVIEW, HUMAN_JUDGED)
    check(not unapproved.frozen_eligible,
          "an unapproved HUMAN_JUDGED pair may never enter the frozen benchmark")
    check(unapproved.label == PENDING_REVIEW and unapproved.reviewer is None,
          "an unapproved pair carries no gold label and no reviewer")

    # Identities and timestamps must come from the review record, never invented.
    from checker.reviews import load as load_reviews
    rec = load_reviews()
    approved = [p for p in judged if p.reviewer_status == REVIEW_APPROVED]
    check(all(p.id in rec and p.reviewer == rec[p.id]["reviewer"]
              and p.reviewed_at == rec[p.id]["reviewed_at"] for p in approved),
          f"every approval's reviewer and timestamp come from the record ({len(approved)})")
    check(all(p.reviewer is None for p in judged if p.reviewer_status != REVIEW_APPROVED),
          "no reviewer identity is attached to an unapproved pair")
    check(all(p.label == ENTAILED for p in approved),
          "an approved HUMAN_JUDGED pair takes the gold label its reviewer signed off")

    # --- E3 recorded separately from grounding ------------------------------
    from checker.entail_baseline import judge
    from checker.grounding_policy import CLAIM_PARTIALLY_MATCHED, may_be_grounded
    cand = frozen_candidates()
    tp = sum(judge(p.source_span, p.claim).entailed for p in cand if p.label == ENTAILED)
    pos = sum(p.label == ENTAILED for p in cand)
    fp = sum(judge(p.source_span, p.claim).entailed for p in cand if p.label == NOT_ENTAILED)
    neg = sum(p.label == NOT_ENTAILED for p in cand)
    check(not may_be_grounded(CLAIM_PARTIALLY_MATCHED),
          "E3 acceptance is CLAIM_PARTIALLY_MATCHED and is never GROUNDED")
    print(f"\n  E3 on frozen candidates: {tp}/{pos} true accepted, "
          f"{fp}/{neg} FALSE accepted")
    check(fp > 0, f"E3 still fails these pairs ({fp} false accepts) — they remain hard")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
