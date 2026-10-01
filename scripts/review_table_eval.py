#!/usr/bin/env python3
"""Per-column precision, recall and false-NOT_FOUND rate for review grids, on CUAD.

H4's measurement. **EVALUATION ONLY.** Nothing here is imported by a served path, no figure
it prints may be shown to a user, and `_test()` asserts the first of those.

## Why CUAD fits, and the three ways it does not

CUAD (`corpus/benchmark/cuad/test.json`) is 102 contracts, each with the same 41 clause
questions, SQuAD-style: `answers` holds the gold spans and `is_impossible` marks a category
the contract does not contain. That maps onto a review grid exactly -- a contract is a
document, a category is a column, and a gold absence is the NOT_FOUND we are most likely to
get wrong.

What it is not:

1. **CUAD's labels are about CUAD's task**, which is span highlighting for a lawyer to
   review, not "fill this cell with a value". A category we mark FOUND with a correct span
   may still be a cell a lawyer would call unhelpful.
2. **The contracts are EDGAR filings.** `DECISION_harvey_parity` permits CUAD to MEASURE
   clause extraction and nothing else: it is never shown to a user and never cited in an
   answer. This file reads it and prints counts.
3. **No human has labelled OUR output.** Every figure below is agreement with a third
   party's labels on a third party's framing. It is a regression number, not an accuracy
   claim, and `headline()` refuses to produce one.

## The three metrics, and why the third is the one that matters

    precision             of the cells we called FOUND, how many hit a gold span
    recall                of the cells whose clause IS present, how many we found
    false NOT_FOUND rate  of the cells whose clause IS present, how many we called
                          NOT_FOUND

The first two are the usual pair. The third is the one a diligence product lives or dies on,
and it is NOT 1 - recall: a missed clause can come back NEEDS_LAWYER or FAILED, which tell
a reader to look. **NOT_FOUND tells them not to.** A grid that answers "no cap on liability"
about a contract that caps liability is worse than one that says "a person should read this",
so the two failure modes are counted separately and the dangerous one is named.

Every rate carries a **Wilson** interval (`checker/review_grid.wilson`): the per-column
counts are small and the proportions near 0 and 1, which is exactly where a normal
approximation claims certainty it has not got.

Run:  PYTHONPATH=. python3 scripts/review_table_eval.py --test
      PYTHONPATH=. python3 scripts/review_table_eval.py                 # sample
      PYTHONPATH=. python3 scripts/review_table_eval.py --documents 40 --columns 10
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CUAD = ROOT / "corpus" / "benchmark" / "cuad" / "test.json"

from checker import review_grid as rg                          # noqa: E402

# The gate runs a small sample so the suite stays fast; the figures it prints are therefore
# about a sample and say so. A real measurement passes --documents/--columns.
SAMPLE_DOCUMENTS = 6
SAMPLE_COLUMNS = 5


class EvalError(RuntimeError):
    """The evaluation cannot run. Never a silent zero."""


def category(question: str) -> str:
    """"Highlight the parts ... related to "Anti-Assignment" that ..." -> Anti-Assignment."""
    m = re.search(r'related to "([^"]+)"', question)
    return m.group(1) if m else question[:40]


@dataclass(frozen=True)
class Case:
    """One (contract, category) pair with its gold label."""
    document_id: str
    title: str
    text: str
    column: str
    question: str
    gold_spans: tuple          # empty => the clause is absent from this contract


def load_cases(*, documents: int = SAMPLE_DOCUMENTS,
               columns: int = SAMPLE_COLUMNS) -> list[Case]:
    """Cases from CUAD, deterministically: the first N contracts and N categories.

    Deterministic rather than random, so two runs of the same size are comparable. A random
    sample would make every re-run a different measurement and hide a regression inside the
    sampling noise.
    """
    if not CUAD.is_file():
        raise EvalError(
            f"{CUAD.relative_to(ROOT)} is not present. It is acquired by "
            f"scripts/acquire_cuad.py and is not committed; without it there is no "
            f"evaluation, which is different from an evaluation that scores zero")
    data = json.loads(CUAD.read_text(encoding="utf-8")).get("data") or []
    if not data:
        raise EvalError("CUAD holds no contracts; refusing to report on an empty set")
    out: list[Case] = []
    wanted: list[str] = []
    for entry in data[:documents]:
        para = (entry.get("paragraphs") or [{}])[0]
        text = str(para.get("context") or "")
        if not text.strip():
            continue
        qas = para.get("qas") or []
        if not wanted:
            wanted = [category(q.get("question") or "") for q in qas][:columns]
        import hashlib
        doc_id = hashlib.sha256(text.encode("utf-8")).hexdigest()
        for qa in qas:
            cat = category(qa.get("question") or "")
            if cat not in wanted:
                continue
            spans = tuple(str(a.get("text") or "") for a in (qa.get("answers") or [])
                          if str(a.get("text") or "").strip())
            out.append(Case(doc_id, str(entry.get("title") or "")[:60], text, cat,
                            str(qa.get("question") or ""), spans))
    if not out:
        raise EvalError("no cases were built; refusing to report 0/0 as a result")
    return out


def baseline_answer(case: Case):
    """A deliberately weak, deterministic finder. Returns (value, quote) or None.

    It looks for the category's own words in the contract and quotes the sentence around
    the hit. It is **not** a model and not a product baseline: it exists so the harness can
    be measured without a network, and so a change to the SCORING shows up as a change in
    the numbers while the finder is held still.
    """
    needle = case.column.lower().replace("-", " ")
    low = case.text.lower()
    at = low.find(needle)
    if at < 0:
        first = needle.split()[0] if needle.split() else ""
        at = low.find(first) if len(first) > 4 else -1
        if at < 0:
            return None
    start = max(0, case.text.rfind(".", 0, at) + 1)
    end = case.text.find(".", at)
    end = len(case.text) if end < 0 else end + 1
    quote = case.text[start:end].strip()
    if len(quote) < rg.MIN_QUOTE_CHARS:
        return None
    return (quote[:120], quote)


def hits_gold(quote: str, gold_spans) -> bool:
    """Does our quote overlap any gold span? Containment either way counts.

    Overlap and not equality: CUAD's spans are a lawyer's highlight and ours is a sentence,
    so demanding the same bytes would score a correct find as a miss. Both directions
    count, because the gold span is sometimes a clause and sometimes a phrase inside one.
    """
    q = " ".join((quote or "").split()).lower()
    if not q:
        return False
    for span in gold_spans:
        g = " ".join(str(span).split()).lower()
        if g and (g in q or q in g):
            return True
    return False


@dataclass(frozen=True)
class ColumnScore:
    column: str
    present: int = 0          # cases where the clause IS in the contract
    absent: int = 0
    found: int = 0            # cells we called FOUND
    found_correct: int = 0    # ...and the quote hit a gold span
    false_not_found: int = 0  # clause present, we said NOT_FOUND
    needs_lawyer: int = 0
    failed: int = 0

    @property
    def precision(self):
        return (self.found_correct / self.found) if self.found else None

    @property
    def recall(self):
        return (self.found_correct / self.present) if self.present else None

    @property
    def false_not_found_rate(self):
        return (self.false_not_found / self.present) if self.present else None

    def rows(self):
        return [("precision", self.found_correct, self.found),
                ("recall", self.found_correct, self.present),
                ("false NOT_FOUND", self.false_not_found, self.present)]


def score(cases, *, answer=baseline_answer) -> dict:
    """{column: ColumnScore}. Runs the grid's own constructors, so a FOUND here is a FOUND
    there: the quote is checked against the contract by `review_grid.found()`."""
    out: dict = {}
    for case in cases:
        col = rg.Column(case.column, rg.TEXT, case.question)
        s = out.get(case.column) or ColumnScore(case.column)
        present = bool(case.gold_spans)
        got = None
        try:
            got = answer(case)
        except Exception:                                       # noqa: BLE001
            out[case.column] = ColumnScore(
                case.column, s.present + int(present), s.absent + int(not present),
                s.found, s.found_correct, s.false_not_found, s.needs_lawyer, s.failed + 1)
            continue
        state, correct = rg.NOT_FOUND, False
        if got is not None:
            value, quote = got
            try:
                rg.found(document_id=case.document_id, column=col, value=value,
                         quote=quote, document_text=case.text)
                state = rg.FOUND
                correct = hits_gold(quote, case.gold_spans)
            except rg.TableError:
                state = rg.NEEDS_LAWYER
        out[case.column] = ColumnScore(
            case.column,
            s.present + int(present), s.absent + int(not present),
            s.found + int(state == rg.FOUND),
            s.found_correct + int(state == rg.FOUND and correct),
            s.false_not_found + int(state == rg.NOT_FOUND and present),
            s.needs_lawyer + int(state == rg.NEEDS_LAWYER), s.failed)
    return out


DISCLAIMER = (
    "EVALUATION ONLY. Every figure above is agreement with CUAD's labels, which are a "
    "third party's, on a third party's task framing, produced by a deliberately weak "
    "deterministic finder. NO HUMAN HAS LABELLED THIS PRODUCT'S OUTPUT. These are "
    "regression numbers for the harness and NOT an accuracy claim; none of them may be "
    "shown to a user, put in a deck, or quoted to a client.")


def headline(scores) -> str:
    """Refuses to produce a single number. Deliberately."""
    raise EvalError(
        "there is no headline figure, and that is the point. A single number over 41 "
        "unrelated clause categories averages a thing nobody asked about, and it is the "
        "shape a product claim takes. Read the per-column table.")


def report(cases, scores) -> str:
    docs = len({c.document_id for c in cases})
    lines = ["REVIEW-GRID EVALUATION on CUAD -- per column, with Wilson intervals.", "",
             f"  {docs} contract(s) x {len(scores)} column(s) = {len(cases)} cells.",
             "",
             f"  {'column':<26}{'n present':>10}{'precision':>22}{'recall':>22}"
             f"{'false NOT_FOUND':>24}",
             f"  {'-' * 104}"]
    for col in sorted(scores):
        s = scores[col]
        cells = []
        for _name, k, n in s.rows():
            if not n:
                cells.append("        n=0        ")
                continue
            lo, hi = rg.wilson(k, n)
            cells.append(f"{k}/{n} {lo:.2f}-{hi:.2f}")
        lines.append(f"  {col[:25]:<26}{s.present:>10}{cells[0]:>22}{cells[1]:>22}"
                     f"{cells[2]:>24}")
    tot_present = sum(s.present for s in scores.values())
    tot_fnf = sum(s.false_not_found for s in scores.values())
    lines += ["",
              f"  across all columns: {tot_fnf}/{tot_present} present clauses were called "
              f"NOT_FOUND.",
              "  A false NOT_FOUND is not 1 - recall: a miss can also come back "
              "NEEDS_LAWYER,",
              "  which tells a reader to look. NOT_FOUND tells them not to.",
              "", "  " + DISCLAIMER]
    return "\n".join(lines)


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

    print("review_table_eval")

    # ── EVALUATION ONLY: the served path must not import this ───────────────
    served = [ROOT / "checker" / "api.py", ROOT / "gateway" / "verbs.py",
              ROOT / "gateway" / "app.py", ROOT / "gateway" / "envelope.py",
              ROOT / "checker" / "review_grid.py", ROOT / "agents" / "review_grid.py"]
    # Parsed, not grepped. The first version searched the text for the module name and
    # fired on `checker/review_grid.py`, whose docstring POINTS AT this file -- a prose
    # reference, which is the opposite of a leak. Fourth time this session that grepping
    # prose for a structural fact has produced a false positive, so this one reads the
    # import statements.
    import ast as _ast
    leaked = []
    for f in served:
        if not f.is_file():
            continue
        for node in _ast.walk(_ast.parse(f.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, _ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, _ast.ImportFrom):
                names = [node.module or ""] + [a.name for a in node.names]
            if any("review_table_eval" in (n or "") for n in names):
                leaked.append(f.name)
                break
    check(not leaked,
          f"no served or feature module IMPORTS this evaluation ({leaked}) -- a figure "
          f"from here reaching a user is the accuracy claim this file refuses to make")
    check("review_table_eval" in (ROOT / "checker" / "review_grid.py").read_text(
              encoding="utf-8"),
          "...while review_grid's docstring may POINT AT it, which is a reference and not "
          "a dependency -- the check above parses imports so it can tell them apart")
    check("EVALUATION ONLY" in DISCLAIMER and "NOT an accuracy claim" in DISCLAIMER,
          "the disclaimer says evaluation only, in words")
    try:
        headline({})
        check(False, "there is no headline figure")
    except EvalError as e:
        check("no headline figure" in str(e),
              "headline() REFUSES to produce one number: a single figure over 41 unrelated "
              "clause categories is the shape a product claim takes")

    if not CUAD.is_file():
        check(False, "CUAD is present (acquired by scripts/acquire_cuad.py)")
        print(f"\n{ok}/{ok + fail} passed")
        return 1

    cases = load_cases(documents=3, columns=3)
    check(len(cases) == 9, f"a 3x3 sample is 9 cells ({len(cases)})")
    check(len({c.document_id for c in cases}) == 3, "...three distinct contracts")
    check(len({c.column for c in cases}) == 3, "...and three columns")
    check(all(len(c.document_id) == 64 for c in cases),
          "each contract is identified by the sha256 of its text, as a document is")
    check(load_cases(documents=3, columns=3) == cases,
          "the sample is DETERMINISTIC: two runs of the same size are comparable, and a "
          "random one would hide a regression inside the sampling noise")
    check(any(c.gold_spans for c in cases) and any(not c.gold_spans for c in cases),
          "the sample holds both present and absent clauses -- without both, precision or "
          "the false NOT_FOUND rate would have no denominator")

    sc = score(cases)
    check(set(sc) == {c.column for c in cases}, "every column is scored")
    for col, s in sc.items():
        check(s.present + s.absent == len([c for c in cases if c.column == col]),
              f"{col[:20]}: present + absent covers every case")
        check(s.found_correct <= s.found,
              f"{col[:20]}: correct finds cannot exceed finds")
        check(s.false_not_found <= s.present,
              f"{col[:20]}: a false NOT_FOUND needs the clause to be present")

    # The metrics are None rather than 0 when the denominator is empty.
    empty = ColumnScore("x")
    check(empty.precision is None and empty.recall is None
          and empty.false_not_found_rate is None,
          "with no cases the rates are None, never 0.0 -- a zero would read as 'we got "
          "them all wrong' where the truth is 'we have not measured'")

    # hits_gold: overlap either way, and it can say no.
    check(hits_gold("the term of this Agreement shall be three years",
                    ("term of this Agreement shall be three years",)),
          "a gold span inside our quote counts")
    check(hits_gold("three years", ("the term shall be three years",)),
          "...and our quote inside a gold span counts, because CUAD's spans are a lawyer's "
          "highlight and ours is a sentence")
    check(not hits_gold("governed by the laws of Delaware",
                        ("the term shall be three years",)),
          "...and an unrelated quote does NOT count -- the check can say no")
    check(not hits_gold("", ("anything",)) and not hits_gold("x", ()),
          "an empty quote or no gold span is not a hit")

    # A FOUND here is a FOUND there: the grid's own constructor checks the quote.
    bad_case = Case("c" * 64, "t", "A contract about nothing.", "Term", "q?", ("x",))
    sc2 = score([bad_case], answer=lambda c: ("invented", "a quote not in the contract"))
    check(sc2["Term"].found == 0 and sc2["Term"].needs_lawyer == 1,
          "an answer whose quote is not in the contract is NEEDS_LAWYER, never counted as "
          "a find -- scoring goes through review_grid.found(), the same gate the product "
          "uses")
    sc3 = score([bad_case], answer=lambda c: (_ for _ in ()).throw(TimeoutError("x")))
    check(sc3["Term"].failed == 1 and sc3["Term"].found == 0,
          "a transport error counts as FAILED and never as a finding")

    text = report(cases, sc)
    check("Wilson" in text and "false NOT_FOUND" in text,
          "the report names its interval and the dangerous rate")
    check(DISCLAIMER in text, "...and carries the disclaimer in full")
    check("not 1 - recall" in text,
          "...and states that a false NOT_FOUND is not 1 - recall, because a miss can come "
          "back NEEDS_LAWYER, which tells a reader to look")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    if "--test" in sys.argv:
        raise SystemExit(_test())
    def _arg(flag, default):
        return int(sys.argv[sys.argv.index(flag) + 1]) if flag in sys.argv else default
    cs = load_cases(documents=_arg("--documents", SAMPLE_DOCUMENTS),
                    columns=_arg("--columns", SAMPLE_COLUMNS))
    print(report(cs, score(cs)))
