"""Negative paraphrase candidates. Proposed for review; none is promoted.

The `paraphrase` bucket holds 15 pairs and every one is positive, so it cannot
detect a false accept: there is nothing there to falsely accept. Until F4 that
was permanent by construction — a reviewer recorded approval, approval compiled
to ENTAILED, and no human-judged pair could carry NOT_ENTAILED. With F4 repaired
the bucket can hold both classes, and these are the candidates that would give
it one.

## What makes a negative worth having

Not grammatical awkwardness. A useful negative is a claim a competent
practitioner might actually write, which a specific phrase in the provision
defeats. Each candidate below therefore records:

    defect        the mechanism — a qualifier dropped, a comparator reversed
    breaks_on     the statutory words, verbatim, that make the claim false
    why           a worked case where believing the claim gives a wrong answer

A candidate with no `breaks_on` is not a negative, it is an opinion, and
`_test()` refuses to let one through.

## Why none of these is promoted

Authoring a claim and labelling it are two jobs. Doing both alone is precisely
the failure F4 closed: a self-certified label is not a human judgement, however
carefully reasoned. Every candidate here is PENDING_REVIEW with a *proposed*
label of NOT_ENTAILED, and a second reviewer decides. Some of them should be
rejected — that is the point of asking.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

from checker.grounding_policy import NOT_ENTAILED, PENDING_REVIEW

# Defect taxonomy. Each names a mechanism by which a fluent claim goes wrong.
QUALIFIER_DROPPED = "qualifier_dropped"
PROVISO_OMITTED = "proviso_omitted"
THRESHOLD_REVERSED = "threshold_reversed"
CONNECTIVE_FLIPPED = "connective_flipped"
TEMPORAL_MISFRAME = "temporal_misframe"
EXCEPTION_SUPPRESSED = "exception_suppressed"
COMPARATOR_WRONG = "comparator_wrong"
SECTION_SUBSTITUTED = "section_substituted"
MODALITY_SHIFTED = "modality_shifted"

DEFECTS = (QUALIFIER_DROPPED, PROVISO_OMITTED, THRESHOLD_REVERSED,
           CONNECTIVE_FLIPPED, TEMPORAL_MISFRAME, EXCEPTION_SUPPRESSED,
           COMPARATOR_WRONG, SECTION_SUBSTITUTED, MODALITY_SHIFTED)


@dataclass(frozen=True)
class Candidate:
    id: str
    section: str
    subsection: str
    claim: str
    defect: str
    breaks_on: str          # the statutory words, verbatim, that defeat it
    why: str                # a worked case where the claim gives a wrong answer
    proposed_label: str = NOT_ENTAILED
    label: str = PENDING_REVIEW
    kind: str = "paraphrase"


CANDIDATES: tuple[Candidate, ...] = (
    # ── s.103: quorum for a general meeting ─────────────────────────────────
    Candidate("neg-103-1-a", "103", "1",
              "Five members personally present constitute a quorum for a public "
              "company's general meeting.",
              QUALIFIER_DROPPED,
              "Unless the articles of the company provide for a larger number",
              "the articles may require more, and a meeting held with five where "
              "the articles demand seven is inquorate; the claim would tell a "
              "company its meeting was valid when it was not"),
    Candidate("neg-103-1-b", "103", "1",
              "A public company with more than five thousand members needs "
              "fifteen members personally present for a quorum.",
              THRESHOLD_REVERSED,
              "thirty members personally present if the number of members as on "
              "the date of the meeting exceeds five thousand",
              "fifteen is the band for more than one thousand and up to five "
              "thousand; above five thousand it is thirty, so the claim "
              "understates the quorum for the largest companies"),
    Candidate("neg-103-1-c", "103", "1",
              "Two members personally present are a quorum for any company's "
              "general meeting.",
              QUALIFIER_DROPPED,
              "in the case of a private company, two members personally present",
              "the two-member quorum reaches private companies only; applied to "
              "a public company it understates the quorum by at least three"),
    Candidate("neg-103-2-a", "103", "2",
              "If a quorum is not present within half an hour, the meeting stands "
              "adjourned to the same day in the next week.",
              EXCEPTION_SUPPRESSED,
              "the meeting, if called by requisitionists under section 100, shall "
              "stand cancelled",
              "a requisitioned meeting is CANCELLED, not adjourned; telling "
              "requisitionists to reconvene next week would have them attend a "
              "meeting that does not exist"),
    Candidate("neg-103-2-b", "103", "2",
              "An inquorate meeting is always adjourned to the same time and "
              "place in the following week.",
              QUALIFIER_DROPPED,
              "or to such other date and such other time and place as the Board "
              "may determine",
              "the Board may fix a different date, time or place; 'always' "
              "denies a discretion the section grants"),

    # ── s.101: notice of a general meeting ──────────────────────────────────
    Candidate("neg-101-1-a", "101", "1",
              "A general meeting requires twenty-one clear days' notice in every "
              "case.",
              PROVISO_OMITTED,
              "Provided that a general meeting may be called after giving shorter "
              "notice",
              "the proviso permits shorter notice with the prescribed consent; "
              "'in every case' would have a company refuse a validly shortened "
              "meeting its members had already consented to"),
    Candidate("neg-101-1-b", "101", "1",
              "Twenty-one days' notice means twenty-one days counted from the "
              "date of despatch to the date of the meeting.",
              TEMPORAL_MISFRAME,
              "not less than clear twenty-one days' notice",
              "'clear' days exclude both the day of service and the day of the "
              "meeting, so a notice computed inclusively is two days short and "
              "the meeting is irregular"),
    Candidate("neg-101-1-c", "101", "1",
              "Notice of a general meeting must be given in writing.",
              CONNECTIVE_FLIPPED,
              "either in writing or through electronic mode",
              "the section offers alternatives; reading it as writing-only would "
              "reject a validly served electronic notice"),

    # ── s.96: annual general meeting ────────────────────────────────────────
    Candidate("neg-96-1-a", "96", "1",
              "A company complies with section 96 so long as no more than fifteen "
              "months elapse between one annual general meeting and the next.",
              QUALIFIER_DROPPED,
              "Every company other than a One Person Company shall in each year "
              "hold ... a general meeting as its annual general meeting",
              "two meetings 397 days apart can skip a calendar year entirely — "
              "31-12-2023 and 31-01-2025 hold no AGM in 2024 at all — so the gap "
              "limb alone reports a defaulting company as compliant"),
    Candidate("neg-96-1-b", "96", "1",
              "The first annual general meeting must be held within six months of "
              "the close of the first financial year.",
              THRESHOLD_REVERSED,
              "in case of the first annual general meeting, it shall be held "
              "within a period of nine months from the date of closing of the "
              "first financial year",
              "six months is the limit for any OTHER AGM; applying it to the "
              "first would have a new company believe it is three months late "
              "when it is in time"),
    Candidate("neg-96-1-c", "96", "1",
              "Turnover for the purpose of section 96 is measured for the "
              "financial year in which the meeting is held.",
              TEMPORAL_MISFRAME,
              "from the date of closing of the financial year",
              "the deadline runs from the CLOSE of the financial year being "
              "reported on, not the year of the meeting; the wrong year moves "
              "every deadline by twelve months"),
    Candidate("neg-96-1-d", "96", "1",
              "The Registrar may extend the time for holding any annual general "
              "meeting by up to three months.",
              QUALIFIER_DROPPED,
              "other than the first annual general meeting",
              "the extension power expressly excludes the FIRST AGM; a company "
              "relying on it for its first meeting would have no extension at all"),

    # ── s.173: board meetings ───────────────────────────────────────────────
    Candidate("neg-173-1-a", "173", "1",
              "A company must hold at least four board meetings a year and no "
              "fewer than one hundred and twenty days may separate two "
              "consecutive meetings.",
              COMPARATOR_WRONG,
              "not more than one hundred and twenty days shall intervene between "
              "two consecutive meetings",
              "120 days is a CEILING, not a floor; the claim inverts it and would "
              "tell a diligent board meeting monthly that it is in breach"),
    Candidate("neg-173-1-b", "173", "1",
              "Every company must hold four board meetings in each year without "
              "exception.",
              PROVISO_OMITTED,
              "Central Government may, by notification, direct that the "
              "provisions of this subsection shall not apply",
              "the Central Government may disapply the sub-section to a class of "
              "companies; 'without exception' denies an exemption a company may "
              "actually hold"),
    Candidate("neg-173-2-a", "173", "2",
              "Directors may attend a board meeting by video conferencing or any "
              "other audio visual means they choose.",
              QUALIFIER_DROPPED,
              "as may be prescribed, which are capable of recording and "
              "recognising the participation of the directors",
              "the means are prescribed and must record and recognise "
              "participation; a call that does neither is not valid attendance "
              "and the meeting may be inquorate"),
    Candidate("neg-173-2-b", "173", "2",
              "Any matter may be dealt with at a board meeting held by video "
              "conferencing.",
              EXCEPTION_SUPPRESSED,
              "the Central Government may, by notification, specify such matters "
              "which shall not be dealt with in a meeting through video "
              "conferencing",
              "specified matters are barred from video conferencing; approving "
              "one that way would leave the resolution open to challenge"),

    # ── s.174: quorum for a board meeting ───────────────────────────────────
    Candidate("neg-174-1-a", "174", "1",
              "One-third of the total strength of the Board is the quorum for a "
              "board meeting.",
              QUALIFIER_DROPPED,
              "or two directors, whichever is higher",
              "on a board of three, one-third is 1 while the quorum is 2; a "
              "meeting held with one director would be treated as valid"),
    Candidate("neg-174-1-b", "174", "1",
              "Two directors are always sufficient to constitute a quorum for a "
              "board meeting.",
              COMPARATOR_WRONG,
              "one-third of its total strength or two directors, whichever is "
              "higher",
              "on a board of nine, one-third is 3, so two directors is one short; "
              "'always sufficient' fails on every board larger than six"),
    Candidate("neg-174-1-c", "174", "1",
              "Directors participating by video conferencing are not counted "
              "towards the quorum.",
              SECTION_SUBSTITUTED,
              "the participation of the directors by video conferencing or by "
              "other audio visual means shall also be counted for the purposes of "
              "quorum",
              "the section says the opposite; a company following the claim would "
              "adjourn meetings that were quorate all along"),
    Candidate("neg-174-2-a", "174", "2",
              "Where the number of directors falls below the quorum, the "
              "continuing directors may not act at all.",
              EXCEPTION_SUPPRESSED,
              "the continuing directors or director may act for the purpose of "
              "increasing the number of directors",
              "they may act for limited purposes, including increasing the number "
              "of directors and calling a general meeting; the claim would leave "
              "a depleted board unable to fix itself"),
    Candidate("neg-174-2-b", "174", "2",
              "Continuing directors may carry on the ordinary business of the "
              "company notwithstanding a vacancy that puts them below quorum.",
              QUALIFIER_DROPPED,
              "for no other purpose",
              "below quorum they may act ONLY for the two named purposes; "
              "ordinary business transacted in that state is open to challenge"),

    # ── s.2(85): small company ──────────────────────────────────────────────
    Candidate("neg-2-85-a", "2", "85",
              "A company is a small company if either its paid-up capital or its "
              "turnover is within the prescribed limit.",
              CONNECTIVE_FLIPPED,
              "and",
              "the two limbs are conjunctive since the 2017 amendment inserted "
              "'and'; reading them disjunctively would classify a company with "
              "small capital and very large turnover as small, and hand it "
              "relaxations it does not qualify for"),
    Candidate("neg-2-85-b", "2", "85",
              "Any company whose paid-up capital and turnover are within the "
              "prescribed limits is a small company.",
              EXCEPTION_SUPPRESSED,
              "Provided that nothing in this clause shall apply to-- (A) a "
              "holding company or a subsidiary company",
              "a subsidiary is excluded however small; the claim would grant "
              "small-company relaxations to a subsidiary of a large group"),
    Candidate("neg-2-85-c", "2", "85",
              "Turnover for the small-company test is the turnover of the current "
              "financial year.",
              TEMPORAL_MISFRAME,
              "as per profit and loss account for the immediately preceding "
              "financial year",
              "the test reads the PRECEDING year; using the current year both "
              "measures an incomplete figure and answers a different question"),
    Candidate("neg-2-85-d", "2", "85",
              "A small company must have paid-up capital of not more than fifty "
              "lakh rupees.",
              THRESHOLD_REVERSED,
              "or such higher amount as may be prescribed",
              "fifty lakh is the floor that applies absent any prescription; a "
              "Rule has prescribed a higher amount, so the claim excludes "
              "companies that are in fact small"),
)


def pending() -> list[dict]:
    """Every candidate, as a review-queue record. None is promoted."""
    return [dict(asdict(c), reviewer_status=PENDING_REVIEW,
                 note="drafted by the model; a second reviewer decides the label")
            for c in CANDIDATES]


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

    print("paraphrase_negatives")
    from checker.entail_pairs_v2 import provision

    n = len(CANDIDATES)
    check(15 <= n <= 25, f"between 15 and 25 candidates ({n})")
    check(len({c.id for c in CANDIDATES}) == n, "every candidate id is unique")

    # A candidate with no statutory words that defeat it is an opinion.
    check(all(c.breaks_on.strip() for c in CANDIDATES),
          "every candidate names the words that defeat it")
    check(all(c.why.strip() for c in CANDIDATES),
          "every candidate gives a worked wrong answer")
    check(all(c.defect in DEFECTS for c in CANDIDATES),
          "every defect is from the taxonomy")

    # THE ONE THAT MATTERS: the quoted words must really be in the provision.
    # A negative built against text the Act does not contain teaches the checker
    # to reject a claim for a reason that does not exist.
    missing = []
    for c in CANDIDATES:
        text = " ".join(provision(c.section).lower().split())
        needle = " ".join(c.breaks_on.lower().split())
        # Elisions are written as "..."; check the fragments around them.
        for frag in [f.strip() for f in needle.split("...") if f.strip()]:
            if frag not in text:
                missing.append((c.id, frag[:48]))
                break
    check(not missing, f"every quoted phrase is verbatim in its provision ({missing[:2]})")

    # Coverage of the defect taxonomy.
    used = {c.defect for c in CANDIDATES}
    check(len(used) >= 7, f"the candidates span the taxonomy ({len(used)} defects)")
    secs = {c.section for c in CANDIDATES}
    check(len(secs) >= 5, f"...across several provisions ({sorted(secs)})")

    # NOTHING is promoted. This is the F4 discipline, restated as a test.
    check(all(c.label == PENDING_REVIEW for c in CANDIDATES),
          "every candidate is PENDING_REVIEW")
    check(all(c.proposed_label == NOT_ENTAILED for c in CANDIDATES),
          "...with a PROPOSED label, which is not a label")
    recs = pending()
    check(all(r["reviewer_status"] == PENDING_REVIEW for r in recs),
          "the queue records are pending too")
    check(not any(r.get("label") == NOT_ENTAILED for r in recs),
          "no candidate carries a settled negative label")

    # They must not silently enter the benchmark.
    from checker.entail_pairs_v2 import all_pairs
    live = {p.id for p in all_pairs()}
    check(not (live & {c.id for c in CANDIDATES}),
          "no candidate has reached the live pair set")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
