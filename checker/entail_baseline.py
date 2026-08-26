"""Deterministic entailment baseline. No model.

This is the number a model has to beat before it earns a place in the pipeline.
It exists because the mining measurement was surprising: I expected lexical
overlap to be near-useless on the hard negatives and it reached 87% on the
matched subset. If simple checks get most of the way, the honest outcome may be
to ship them and skip the model entirely — a deterministic checker can be read,
tested, and explained to a regulator, which no fine-tuned classifier can.

## What it checks, in order of legal weight

1. **Quoted spans must appear.** If a hypothesis quotes text in double quotes,
   that text must be present in the premise. This decides the matched subset
   outright — the whole difference between a prior-wording claim and a
   current-wording claim is whether the quoted words are there.
2. **Numbers must agree.** Every numeral and word-numeral in the hypothesis must
   appear in the premise. A claim inventing "two years" where the premise says
   "one year" is refused on the number alone.
3. **Dates must agree.** A date in the hypothesis must be derivable from a date
   in the premise. This catches the shifted-year negatives.
4. **Named instruments must appear.** "Act 1 of 2018" in a claim must be in the
   premise.
5. **Lexical support**, last and weakest: the remaining content words must be
   sufficiently covered.

The ordering matters. Checks 1-4 are *hard* and refuse outright; only step 5 is a
threshold. A system that reduced all of this to one similarity score would accept
a claim that matched in tone and lied about the date.

## The score is 1.00 and that is a warning, not a result

On the frozen set this baseline reaches accuracy 1.00 overall and 1.00 on the
matched subset, with a false-current rate of 0.00. **Do not read that as evidence
that grounding is solved.**

The frozen hypotheses are constructed by altering exactly one checkable token —
a date, a numeral, a named instrument, a quoted span. This checker inspects
exactly those tokens. The benchmark therefore cannot distinguish a genuinely
capable checker from one tuned to its own construction, and a near-perfect score
is what near-circularity looks like from the inside.

What the number does support: for claims of this *shape* — quoting a span,
naming an instrument, stating a commencement date, asserting a period — the
deterministic checks are sufficient, and no model is needed. That covers a real
part of what the drafting layer emits, and a checker that can be read and tested
beats a classifier that cannot.

What it does not support: any claim about paraphrased output. A real model
hallucination restates rather than token-swaps, and surface matching will do far
worse there. Closing that needs pairs whose hypotheses preserve meaning while
changing surface form — which is E4's actual job, and is not "train something to
beat 1.00".

## Bias toward refusal

Ambiguity resolves to NOT_ENTAILED. In this domain a false accept means repealed
wording served as current law; a false reject means an abstention. Those are not
symmetric costs and the threshold is not tuned as though they were.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from checker.benchmark_freeze import Row

# Word numerals that carry legal force. Kept explicit rather than inferred: an
# unknown numeral must not silently pass a check it was never compared against.
_WORDS = {
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "eleven", "twelve", "fifteen", "twenty", "thirty", "forty", "fifty",
    "sixty", "ninety", "hundred", "thousand", "lakh", "crore",
}
_MONTHS = {m.lower(): i + 1 for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December"])}

# A leading "Section 96 ..." names which provision the claim is about. That
# identity is established by retrieval, not asserted by the premise — the
# footnote for s.96 has no reason to contain the string "96". Requiring it
# refused every well-formed positive on its own section number and dropped
# recall to 0.12.
_SECTION_REF = re.compile(r"^\s*section\s+[\dA-Za-z]+\s*", re.I)
_QUOTED = re.compile(r'"([^"]{4,})"')
_NUM = re.compile(r"\b\d{1,4}\b")
# Gazette notifications write "dated 24th July, 2014". Requiring the bare
# "24 July 2014" form refused genuine S.O. amendments on their own date.
_DATE_TEXT = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+),?\s+(\d{4})\b",
                        re.I)
_DATE_NUM = re.compile(r"\b(\d{1,2})-(\d{1,2})-(\d{4})\b")
_QUANTITY = re.compile(
    rf"(?<![\w-])((?:\d{{1,4}}|{'|'.join(_WORDS)}))\s+(days?|months?|years?|weeks?)\b",
    re.I)
_INSTRUMENT = re.compile(r"\b(?:Act\s+\d+\s+of\s+\d{4}|S\.O\.\s*\d+\(E\)|"
                         r"G\.S\.R\.\s*\d+\(E\))", re.I)

# Function words carry no evidential weight; requiring them would reward padding.
_STOP = {
    "the", "a", "an", "of", "in", "to", "and", "or", "for", "by", "with", "that",
    "this", "is", "are", "be", "shall", "may", "as", "on", "at", "any", "such",
    "it", "its", "from", "under", "section", "sub-section", "clause", "provided",
    "currently", "includes", "words", "provides", "specifies", "period",
    "amended", "effect", "was", "with",
}


def _norm(s: str) -> str:
    s = (s.replace("’", "'").replace("‘", "'")
          .replace("“", '"').replace("”", '"')
          .replace("–", "-").replace("—", "-"))
    return re.sub(r"\s+", " ", s).strip().lower()


def _dates(s: str) -> set[tuple[int, int, int]]:
    out = set()
    for d, mon, y in _DATE_TEXT.findall(s):
        m = _MONTHS.get(mon.lower())
        if m:
            out.add((int(y), m, int(d)))
    for d, m, y in _DATE_NUM.findall(s):
        out.add((int(y), int(m), int(d)))
    return out


def _numbers(s: str) -> set[str]:
    n = set(_NUM.findall(s))
    n |= {w for w in re.findall(r"[a-z]+", s.lower()) if w in _WORDS}
    return n


@dataclass
class Verdict:
    entailed: bool
    reason: str
    coverage: float = 0.0


def judge(premise: str, hypothesis: str, *, threshold: float = 0.60) -> Verdict:
    """Is `hypothesis` supported by `premise`? Ambiguity resolves to no."""
    p = _norm(premise)
    h = _SECTION_REF.sub("", _norm(hypothesis))

    # 1. Quoted spans must be present verbatim.
    for q in _QUOTED.findall(h):
        if _norm(q) not in p:
            return Verdict(False, f"quoted span absent from premise: {q[:60]!r}")

    # 2. Dates in the claim must appear in the premise.
    hd, pd = _dates(h), _dates(p)
    if hd and not hd <= pd:
        missing = sorted(hd - pd)[0]
        return Verdict(False, f"date not in premise: {missing[2]}-{missing[1]}-{missing[0]}")

    # 3. Named instruments must appear.
    for inst in _INSTRUMENT.findall(_SECTION_REF.sub("", hypothesis.strip())):
        if _norm(inst) not in p:
            return Verdict(False, f"instrument not in premise: {inst}")

    # 4a. A quantity is a numeral AND its unit, checked together. Testing the two
    #     independently accepted "a period of seven months" against a premise that
    #     said "six months" but mentioned "seven" elsewhere with a different unit.
    for qty in _QUANTITY.findall(h):
        num, unit = qty[0].lower(), qty[1].lower()
        stem = unit.rstrip("s")
        if not re.search(rf"(?<![\w-]){re.escape(num)}\s+{stem}s?\b", p):
            return Verdict(False, f"quantity not in premise: {num} {unit}")

    # 4b. Remaining numerals must appear. Date components are excluded, since
    #     their surface form legitimately differs and step 2 already proved them.
    date_parts = {str(x) for t in hd for x in t}
    hn = _numbers(h) - date_parts
    pn = _numbers(p)
    if hn and not hn <= pn:
        return Verdict(False, f"number not in premise: {sorted(hn - pn)[0]!r}")

    # 5. Lexical support, weakest and last.
    #
    # Dates validated in step 2 are removed first. The premise writes "9-2-2018"
    # and the claim writes "9 February 2018"; re-checking "february" as a content
    # word fails a date that has already been proven equal, and double-counts one
    # fact against itself. Each fact is checked once, by the check that suits it.
    h_lex = _DATE_TEXT.sub(" ", h) if hd else h
    hw = {w for w in re.findall(r"[a-z][a-z-]+", h_lex)
          if w not in _STOP and len(w) > 2}
    pw = set(re.findall(r"[a-z][a-z-]+", p))
    cov = len(hw & pw) / len(hw) if hw else 1.0
    if cov < threshold:
        return Verdict(False, f"content words unsupported ({cov:.0%})", cov)
    return Verdict(True, "quoted spans, dates, instruments and numbers all present", cov)


def predict(row: Row, *, threshold: float = 0.60) -> bool:
    return judge(row.premise, row.hypothesis, threshold=threshold).entailed


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

    print("entail_baseline")

    P = ("(1) Every company other than a One Person Company shall in each year hold "
         "a general meeting as its annual general meeting, and not more than fifteen "
         "months shall elapse between the date of one annual general meeting and that "
         "of the next.")

    check(judge(P, 'Section 96 currently includes the words "not more than fifteen '
                'months shall elapse".').entailed,
          "a quoted span present in the premise is accepted")
    check(not judge(P, 'Section 96 currently includes the words "not more than twelve '
                    'months shall elapse".').entailed,
          "a quoted span absent from the premise is refused")
    check(not judge(P, "Section 96 specifies a period of twelve months.").entailed,
          "an invented numeral is refused")
    check(judge(P, "Section 96 requires a general meeting each year as its annual "
                "general meeting.").entailed,
          "a supported paraphrase is accepted")

    F = "1. Subs. by Act 1 of 2018, s. 26, for \"Provided that\" (w.e.f. 13-6-2018)."
    check(judge(F, "Section 96 was amended by Act 1 of 2018 with effect from "
                "13 June 2018.").entailed,
          "instrument and date both present are accepted")
    check(not judge(F, "Section 96 was amended by Act 1 of 2018 with effect from "
                    "13 June 2019.").entailed,
          "a shifted year is refused")
    check(not judge(F, "Section 96 was amended by Act 29 of 2020 with effect from "
                    "13 June 2018.").entailed,
          "a substituted instrument is refused")

    v = judge(P, 'Section 96 currently includes the words "twelve months".')
    check("quoted span absent" in v.reason, "the refusal names the failing check")

    # The frozen benchmark.
    from checker.benchmark_freeze import evaluate, load, report
    rows = load()
    scores = evaluate(predict, rows)
    print()
    print(report(scores))
    print()

    m = scores["MATCHED"]
    check(m.n >= 100, f"the matched subset was scored ({m.n} rows)")
    check(m.accuracy > 0.80, f"the baseline is strong on matched pairs ({m.accuracy:.2f})")
    check(m.false_current_rate < 0.20,
          f"repealed wording is rarely served as current ({m.false_current_rate:.2f})")

    a = scores["ALL"]
    check(a.accuracy > 0.70, f"the baseline is credible overall ({a.accuracy:.2f})")

    # A near-perfect score on a self-constructed set is a limitation to keep
    # visible, not an achievement to bank. Pinned so it cannot quietly become a
    # capability claim in a deck.
    src = __import__("pathlib").Path(__file__).read_text()
    check("warning, not a result" in src,
          "the near-circularity of this benchmark is documented in the module")
    check(a.accuracy < 1.0 or "cannot distinguish" in src,
          "a perfect score is accompanied by its caveat")

    # Every kind must be scored, so no subset hides.
    for k in ("prior_as_current", "current_wording", "wrong_date",
              "wrong_instrument", "wrong_number", "quoted_span", "amended_by"):
        check(k in scores, f"{k} was scored")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
