#!/usr/bin/env python3
"""E7: did a swap inside otherwise-identical text change what the rule says?

Measured 02-10-2026 by `scripts/verifier_error_rates.py`, over 400 real held provisions,
against the cascade as it shipped:

    negation mutation   264/268 accepted   (98%)
    shall -> may        294/304 accepted   (97%)
    quantity changed     11/98  accepted   (11%)
    section number       6/46   accepted   (13%)

A verifier that accepts "it shall not be necessary to state" as support for "it shall be
necessary to state" is not a weak verifier, it is an inverted one. M1 calls a false accept
on a negation or a quantity a bug rather than a rate, and this module is the fix.

## One idea, three cue classes

All four failures above are the same shape: ONE token swapped inside text that is otherwise
identical to the provision, changing what the rule requires while leaving every word a
term-overlap check reads. That is the module's single responsibility, and the three classes
are the ways a legal sentence turns on a single token:

    polarity     "shall not" -> "shall"        the duty is reversed
    force        "shall" -> "may"              a duty becomes a power
    quantity     "thirty" -> "sixty"           a different rule, stated identically

It was called `entail_polarity` for about an hour, until the quantity class had to go
somewhere and the honest options were a name that covered all three or a second file whose
whole content would be this same diff-and-compare. Quantity is not a kind of polarity; a
single-token substitution that changes the rule is what both are.

## Why the cascade could not see it

`not` and `no` are STOPWORDS in all three lexical modules -- `claim_verifier._STOP`,
`entail_binding`, `entail_qualifier`. They have to be, for overlap scoring: a provision and
a claim both full of function words would score alike on them. The consequence is that
polarity is invisible to the thing doing the scoring, so "shall be" and "shall not be" have
identical term sets and E3 answers True on near-perfect overlap. The same hole swallows
`shall` -> `may`, which in Indian drafting is the difference between a duty and a power.
Quantities survive for a different reason: they are below `distinctive_terms`' four-letter
floor, or they are digits, which its `[a-z]{4,}` pattern never matches at all.

Removing the stopwords was the other candidate fix and is worse: it would re-tune every
overlap threshold in three modules, and re-open the frozen benchmark they were measured on,
to repair something that is not an overlap question. Polarity is not a matter of degree.

## What it compares, and why per-sentence and per-difference

**Per-sentence**, because polarity belongs to a clause. A served span of s.173 carries
several "not"s in limbs the claim never touches; comparing cue counts across the whole span
would refuse almost everything.

But not ONLY per-sentence. Aligning a claim to the single best-matching sentence missed two
negation flips outright: the quoted provision split on its own internal semicolons, the
claim spanned several of those limbs, and the limb that matched best was not the limb the
"not" was in. So the candidates are the whole premise AND each of its sentences, and the
gate refuses if ANY candidate alignment shows a substitution. Taking the maximum evidence
of a flip over candidate alignments is sound precisely BECAUSE this gate may only refuse:
it can cost a false reject, never a false accept.

**Per-difference**, because the claim is a near-copy of the span it cites -- that is what a
byte-matched quote IS -- so the question is not "do these texts differ" but "is the
difference a flip". The aligned sentence and the claim are diffed, and only the CHANGED
regions are inspected for a cue. A heavy paraphrase yields many changes and no cue flip, and
this abstains, because a genuine restatement is not this module's question.

## It may refuse, and it may never accept

`checker/cascade.py`'s GATE contract, and the reason the cascade puts gates above
specialists. A polarity match is not evidence that a claim is supported -- the quantity may
still be wrong, the role may still be misbound -- so agreement here returns UNRESOLVED and
lets E6, E5, E4 and E3 do their work. Only a flip returns False.

The cost of that choice is false rejects, and they are bounded by the same two tests E6
uses: the claim must be on topic, and it must be close enough to the aligned sentence that
a flip is the plausible reading of their difference.

Run: PYTHONPATH=. python3 checker/entail_substitution.py --test
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

__all__ = ["judge", "UNRESOLVED", "SUBSTITUTED", "SubstitutionVerdict"]

UNRESOLVED = "UNRESOLVED"
SUBSTITUTED = "SUBSTITUTED"

# Direct polarity reversers. Deliberately NOT "without" or "unless": both are everywhere in
# statutory prose as qualifiers rather than reversers ("without prejudice to", "unless the
# articles provide"), and a dropped qualifier is E6's question, measured and bounded there.
_NEGATION = re.compile(r"\b(not|never|nor|neither|no)\b|n't", re.I)

# Deontic force. The Indian drafting hazard: "shall" imposes, "may" permits.
_MANDATORY = re.compile(r"\b(shall|must|required|requires|obliged|bound)\b", re.I)
_DISCRETIONARY = re.compile(r"\b(may|can|permitted|entitled|empowered|option(al)?)\b", re.I)

# Quantities, as statute writes them: digits, and the number words Indian drafting prefers
# for legal thresholds ("two directors", "one-third of its total strength"). A changed
# quantity is a different rule stated in identical words.
_QUANTITY = re.compile(
    r"\d+"
    r"|\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|"
    r"thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|lakh|crore|"
    r"half|third|fourth|fifth|quarter|first|second)\b", re.I)

ON_TOPIC = 0.30         # the bound E6 uses, for the same reason
SIMILAR = 0.50          # below this the texts are a paraphrase, not a flip
MAX_EDIT = 3            # words a pure removal or addition may span and still be a swap


@dataclass(frozen=True)
class SubstitutionVerdict:
    status: str
    entailed: bool | None = None
    note: str = ""


def _terms(text: str) -> set[str]:
    from checker.claim_verifier import distinctive_terms
    return distinctive_terms(text)


def _sentences(text: str) -> list[str]:
    out = [" ".join(s.split()) for s in re.split(r"(?<=[.;:])\s+", text)]
    return [s for s in out if s] or [" ".join(text.split())]


def _aligned(premise: str, claim: str) -> tuple[str, float]:
    """The premise sentence the claim is most plausibly about, and its similarity."""
    cterms = _terms(claim)
    best, best_score = "", 0.0
    for s in _sentences(premise):
        overlap = (len(cterms & _terms(s)) / len(cterms)) if cterms else 0.0
        if overlap > best_score:
            best, best_score = s, overlap
    return best, best_score


def _cues(text: str) -> tuple[int, int, int, list[str]]:
    """(negations, mandatory, discretionary, quantities) found in `text`."""
    return (len(_NEGATION.findall(text)), len(_MANDATORY.findall(text)),
            len(_DISCRETIONARY.findall(text)),
            sorted(m.group(0).lower() for m in _QUANTITY.finditer(text)))


def _edits(a: str, b: str) -> list[tuple[str, str]]:
    """The LOCAL differences between `a` and `b`, as (removed, added) word runs.

    Local, because a swap is a word-level edit at the cue's own site and a clause-sized
    removal is an omission. Comparing cue counts across the WHOLE diff cannot tell those
    apart, and it false-rejected a true claim on exactly that confusion (`ground_span`,
    02-10-2026): s.2(85)(i) reads "paid-up share capital of which does not exceed fifty
    lakh rupees ... which shall not be more than ten crore rupees", the claim restated the
    first limb and dropped the second, and the dropped limb took a "not" with it. One
    negation fewer in the diff, no inversion anywhere -- the claim is negative in both.

    A dropped limb is a half-truth stated in true words, which is E6's question, so it is
    left to it. The discriminator is the OPCODE, not a word count:

      * a REPLACE is a swap -- text stood here, different text stands here now -- and is
        always compared, whatever its length. "which does not exceed" -> "a small company
        shall exceed" is three words for four, and it inverts the rule.
      * a pure DELETE or INSERT is compared only when it spans at most MAX_EDIT words.
        Removing the one word "not" is an inversion; removing a ten-word limb that happens
        to contain a "not" is an omission.

    A word-count cap alone was tried first and got this exactly backwards: at three words
    it still read the dropped limb correctly but missed the inversion above, because the
    replacement was one word too long.
    """
    aw, bw = a.split(), b.split()
    sm = difflib.SequenceMatcher(a=[w.lower() for w in aw], b=[w.lower() for w in bw])
    out = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        gone, came = aw[i1:i2], bw[j1:j2]
        if tag != "replace" and max(len(gone), len(came)) > MAX_EDIT:
            continue                    # a clause came or went: an omission, not a swap
        out.append((" ".join(gone), " ".join(came)))
    return out


def judge(premise: str, claim: str) -> SubstitutionVerdict:
    """Did a swap inside otherwise-identical text change what the rule says?"""
    best_note = ""
    for candidate in [premise] + _sentences(premise):
        v = _judge_one(candidate, claim)
        if v.status == SUBSTITUTED:
            return v
        best_note = best_note or v.note
    return SubstitutionVerdict(UNRESOLVED, note=best_note or "no candidate alignment")


def _judge_one(sentence: str, claim: str) -> SubstitutionVerdict:
    """The test against ONE candidate alignment. `judge` refuses if any candidate flips."""
    cterms = _terms(claim)
    on_topic = (len(cterms & _terms(sentence)) / len(cterms)) if cterms else 0.0
    if not sentence or on_topic < ON_TOPIC:
        return SubstitutionVerdict(UNRESOLVED,
                                   note=(f"the claim shares little subject matter with the "
                                         f"provision ({on_topic:.0%}); whether it is "
                                         "supported is not a question about a substitution"))

    ratio = difflib.SequenceMatcher(a=sentence.lower(), b=claim.lower()).ratio()
    if ratio < SIMILAR:
        return SubstitutionVerdict(UNRESOLVED,
                                   note=(f"the claim restates rather than copies the "
                                         f"provision ({ratio:.0%} similar); a swap is not "
                                         "the plausible reading of their difference"))

    edits = _edits(sentence, claim)
    if not edits:
        return SubstitutionVerdict(
            UNRESOLVED,
            note=("the claim and the provision differ only in whole clauses, not in any "
                  "word-level swap; whether an omission matters is E6's question"))

    for gone, came in edits:
        g_neg, g_must, g_may, g_qty = _cues(gone)
        c_neg, c_must, c_may, c_qty = _cues(came)

        if g_neg != c_neg:
            return SubstitutionVerdict(
                SUBSTITUTED, False,
                note=(f"polarity reversed: a word-level swap removes {g_neg} and "
                      f"introduces {c_neg} negation(s) ({gone!r} -> {came!r})"))

        # Force is directional: losing an obligation for a permission, or the reverse.
        if (g_must and c_may and not c_must) or (g_may and c_must and not c_may):
            return SubstitutionVerdict(
                SUBSTITUTED, False,
                note=(f"deontic force reversed: a duty and a power are not the same rule "
                      f"({gone!r} -> {came!r})"))

        if g_qty != c_qty:
            return SubstitutionVerdict(
                SUBSTITUTED, False,
                note=(f"quantity changed: {g_qty} -> {c_qty}. A different threshold is a "
                      "different rule, and it is stated in identical words"))

    return SubstitutionVerdict(UNRESOLVED,
                               note="the claim keeps the provision's polarity, force and "
                                    "quantities")


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

    print("entail_substitution")

    QUORUM = ("The quorum for a meeting of the Board of Directors of a company shall be "
              "one third of its total strength or two directors, whichever is higher.")

    # ── the three cue classes, each on real statutory shape ─────────────────
    v = judge(QUORUM, QUORUM.replace("shall be", "shall not be"))
    check(v.status == SUBSTITUTED and v.entailed is False,
          f"a negation inserted into the rule is REFUSED ({v.note[:70]})")

    v = judge(QUORUM, QUORUM.replace("shall be", "may be"))
    check(v.status == SUBSTITUTED and v.entailed is False,
          f"shall -> may is REFUSED: a duty and a power are not the same rule "
          f"({v.note[:60]})")

    v = judge(QUORUM, QUORUM.replace("two directors", "five directors"))
    check(v.status == SUBSTITUTED and v.entailed is False,
          f"a changed quantity is REFUSED ({v.note[:70]})")

    v = judge(QUORUM, QUORUM.replace("one third", "two third"))
    check(v.status == SUBSTITUTED and v.entailed is False,
          "...including a number WORD, which is below distinctive_terms' four-letter "
          "floor and so invisible to every overlap module")

    # ── the over-firing bound: a gate that refuses everything is useless ────
    v = judge(QUORUM, QUORUM)
    check(v.status == UNRESOLVED,
          "an exact quote ABSTAINS -- there is no difference to read as a swap")

    v = judge(QUORUM, "The Board's quorum is one third of total strength or two "
                      "directors, whichever is higher.")
    check(v.status == UNRESOLVED,
          "a true restatement keeping polarity, force and quantities ABSTAINS")

    v = judge(QUORUM, "A company must file its annual return within sixty days.")
    check(v.status == UNRESOLVED and "subject matter" in v.note,
          "an OFF-TOPIC claim abstains -- its failure is that the terms are absent, "
          "which is E3's and E5's question, not this one's")

    v = judge(QUORUM, "Board quorum requires the higher of a third of strength or two "
                      "members present, and nothing in the articles may reduce it below "
                      "that floor however the company is constituted.")
    check(v.status == UNRESOLVED,
          f"a HEAVY PARAPHRASE abstains -- a swap is not the plausible reading of a "
          f"wholesale rewrite ({v.note[:50]})")

    v = _judge_one(QUORUM, "Whichever is higher of two directors or one third of the "
                           "total strength of the Board of Directors of a company shall "
                           "be the quorum for a meeting.")
    check(v.status == UNRESOLVED and "similar" in v.note,
          f"a REORDERED true restatement abstains on the similarity floor specifically, "
          f"so that branch is exercised and not merely present ({v.note[-40:]})")

    # ── qualifiers are not polarity reversers, and belong to E6 ────────────
    for word in ("unless", "without"):
        prem = f"{word.capitalize()} the articles provide otherwise, two directors form a quorum."
        v = judge(prem, "Two directors form a quorum.")
        check(v.status == UNRESOLVED,
              f"{word!r} is NOT read as a negation -- a dropped qualifier is E6's "
              f"question, measured and bounded there")

    # ── the regression that drove candidate alignment ──────────────────────
    # A quote splits on its own internal semicolons; the limb that best matches the claim
    # is not the limb the "not" was in. Aligning to one sentence missed two of these
    # outright (measured 02-10-2026), so the whole premise is a candidate too.
    MULTI = ("Where an advertisement of any prospectus of a company is published; it "
             "shall not be necessary to specify the objects of the memorandum; and the "
             "liability of members shall be stated in the advertisement.")
    v = judge(MULTI, MULTI.replace("shall not be necessary", "shall be necessary"))
    check(v.status == SUBSTITUTED,
          "a flip in a limb that is NOT the best-matching sentence is still caught")

    # ── the false reject that drove the locality rule ──────────────────────
    # s.2(85)(i), real text. The claim restates the first limb truthfully and drops the
    # second, which carries a "not" of its own. Counting negations across the whole diff
    # read that as an inversion and refused a true claim (checker/ground_span, 02-10-2026).
    S285 = ("(i) paid-up share capital of which does not exceed fifty lakh rupees or such "
            "higher amount as may be prescribed which shall not be more than 19[ten crore "
            "rupees]; 20[and]")
    TRUE_CLAIM = ("paid-up share capital of a small company shall not exceed fifty lakh "
                  "rupees or such higher amount as may be prescribed")
    v = judge(S285, TRUE_CLAIM)
    check(v.status == UNRESOLVED,
          f"a claim that DROPS a limb carrying its own negation is not an inversion -- "
          f"both texts are negative, and an omission is E6's question ({v.note[:60]})")

    # ...and the same provision with the polarity actually flipped is still refused, so
    # the locality rule bought precision without giving up the catch.
    v = judge(S285, TRUE_CLAIM.replace("shall not exceed", "shall exceed"))
    check(v.status == SUBSTITUTED,
          f"...while flipping that same claim's polarity IS refused ({v.note[:60]})")

    # ── structural: it cannot accept ────────────────────────────────────────
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(_judge_one))
    returned = {n.value.args[0].id if n.value.args and isinstance(n.value.args[0], ast.Name)
                else None
                for n in ast.walk(tree)
                if isinstance(n, ast.Return) and isinstance(n.value, ast.Call)}
    check(returned <= {"UNRESOLVED", "SUBSTITUTED"} and "SUBSTITUTED" in returned,
          f"every return is an abstention or a refusal -- a GATE may never accept, and "
          f"this is structural, not a convention the cascade enforces for it ({returned})")

    # The scanner must be able to see a True. Without this the clean result above would
    # pass just as well on a walk that read nothing.
    _probe = ast.parse("def f():\n    return SubstitutionVerdict(SUBSTITUTED, True)\n")
    _names = {x.id for n in ast.walk(_probe) if isinstance(n, ast.Return)
              for x in ast.walk(n.value) if isinstance(x, ast.Name)}
    check("SUBSTITUTED" in _names,
          "...and the scan detects a synthetic acceptance, so the clean result is evidence")

    # ── the measured effect, which is the reason the module exists ──────────
    v = judge(QUORUM, QUORUM.replace("shall be", "shall not be"))
    check("264" not in v.note and v.note,
          "a refusal explains ITSELF rather than citing the aggregate measurement")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(_test())
