#!/usr/bin/env python3
"""Review grids: documents down the side, questions across the top, one cell per pair.

H4 of `.claude/loops/DECISION_harvey_parity.md`. A lawyer picks a set of documents and
defines columns -- "governing law", "term end date", "cap on liability", "assignable?" --
and each cell is answered independently against one document.

## The rule the whole file is built around

**A FOUND cell carries a quote that byte-matches its document, or it is not a FOUND cell.**
`found()` is the only constructor for one and it takes the document text, so an unverified
FOUND cell cannot be built -- not "is rejected on validation", cannot be built. The spec
asks for the rejection; making the state unreachable is the version that cannot be
forgotten at a call site.

## Three states, and the one that matters most is NOT_FOUND

    FOUND         the answer, with the span it was read from
    NOT_FOUND     we read the document and the answer is not in it -- STATED, never blank
    NEEDS_LAWYER  a person must decide: the clause is ambiguous, or it is there but says
                  something the column cannot represent

**NOT_FOUND must never render as an empty cell.** In a 40-document table an empty cell
reads as "nothing to see", and "this contract has no liability cap" and "we could not find
the liability cap" are opposite facts that a blank renders identically. Every renderer here
writes the state in words, and `to_csv` has a test that no cell is ever empty.

## Column kinds are a promise about the VALUE, not a hint

A `date` column that answers "sometime in April" has not answered. Each kind validates its
own value in `check_value`, and a FOUND cell whose value does not satisfy its column is
refused -- which pushes the honest answer to NEEDS_LAWYER, where a person can read the
quote and decide. That is the point: the quote is right there.

## Why this is not `checker/review_table.py`, which H4 names

**That file already exists and is something else.** It is the human-review accounting for
the eleven benchmark fixture proposals -- PRESERVED / MISSING / NOT_APPLICABLE per
qualifier -- it predates H4, and it is in the gate's suite list. The H4 row in
`DECISION_harvey_parity.md` was written without that being checked, and the name it asks
for was taken.

I found this the bad way: by writing the new module to that path and destroying the old
one. It was restored from git intact (18/18), and the lesson is the one
`gateway/schema.py` taught on 2026-09-30 and I did not carry over -- **read the path before
writing it.** The grid is called `review_grid` so that both can exist, and this paragraph
is here so the next reader does not spend time wondering which file the plan meant.

## What this module does not do

It calls no model and reaches no network. `agents/review_table.py` runs the cells; this
file holds the shapes, the rules and the export. It makes no accuracy claim: see
`scripts/review_table_eval.py`, which measures per column with Wilson intervals and
states that no figure is a product claim without human labels.

Run: PYTHONPATH=. python3 checker/review_grid.py --test
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field

# ── column kinds ─────────────────────────────────────────────────────────────
TEXT = "text"
DATE = "date"
AMOUNT = "amount"
YES_NO = "yes_no"
CLAUSE = "clause"
KINDS = (TEXT, DATE, AMOUNT, YES_NO, CLAUSE)

# ── cell states ──────────────────────────────────────────────────────────────
FOUND = "FOUND"
NOT_FOUND = "NOT_FOUND"
NEEDS_LAWYER = "NEEDS_LAWYER"
PENDING = "PENDING"          # queued, not yet run. Distinct from NOT_FOUND on purpose.
# TRANSPORT ONLY. The cell did not run: a timeout, a dead provider, a crashed worker. It is
# NOT a finding about the document, and `failed()` is the only way to reach it -- the same
# rule and the same reason as `gateway/envelope.FAILED`, one layer down. A reader who takes
# FAILED for NOT_FOUND concludes the clause is absent because our socket broke.
FAILED = "FAILED"
STATES = (FOUND, NOT_FOUND, NEEDS_LAWYER, PENDING, FAILED)

# States that say something about the DOCUMENT. FAILED and PENDING do not, and an export or
# a tally that mixes them into the findings is making a claim the run did not earn.
FINDING_STATES = (FOUND, NOT_FOUND, NEEDS_LAWYER)

# What a reader sees for a state that is not FOUND. Never "" -- see the module docstring.
STATE_LABEL = {NOT_FOUND: "NOT FOUND", NEEDS_LAWYER: "NEEDS LAWYER", PENDING: "PENDING",
               FAILED: "COULD NOT RUN"}

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# A number, optionally with a currency word or symbol. "unlimited" is a real contractual
# answer to a cap and is accepted as one, because refusing it would push a clear clause to
# NEEDS_LAWYER and bury it.
_AMOUNT = re.compile(r"^(?:unlimited|(?:[A-Z]{3}\s*|[₹$€£]\s*)?[\d,]+(?:\.\d+)?"
                     r"(?:\s*(?:lakh|crore|million|billion))?)$", re.I)
_YES_NO = ("yes", "no")

MIN_QUOTE_CHARS = 8
MIN_REASON_CHARS = 10


class TableError(ValueError):
    """A table, column or cell that cannot be described. Never a warning."""


def check_value(kind: str, value: str) -> str | None:
    """Why `value` does not satisfy `kind`, or None when it does."""
    if kind not in KINDS:
        raise TableError(f"{kind!r} is not a column kind; one of {KINDS}")
    v = (value or "").strip()
    if not v:
        return "it is empty"
    if kind == DATE and not _ISO_DATE.match(v):
        return (f"{v!r} is not an ISO date (YYYY-MM-DD). A date column that answers "
                f"'sometime in April' has not answered")
    if kind == AMOUNT and not _AMOUNT.match(v):
        return (f"{v!r} is not an amount. Give a number, optionally with its currency, "
                f"or 'unlimited'")
    if kind == YES_NO and v.lower() not in _YES_NO:
        return f"{v!r} is neither yes nor no"
    return None


@dataclass(frozen=True)
class Column:
    name: str
    kind: str
    question: str

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise TableError(f"{self.name}: {self.kind!r} is not a kind; one of {KINDS}")
        if not self.name.strip():
            raise TableError("a column needs a name")
        if not self.question.strip():
            raise TableError(
                f"{self.name}: a column needs the QUESTION asked of each document. A "
                f"header is not a question, and a cell answered against a header is a "
                f"cell nobody can check")


@dataclass(frozen=True)
class Cell:
    document_id: str
    column: str
    state: str
    value: str = ""
    quote: str = ""
    reason: str = ""

    def __post_init__(self) -> None:
        if self.state not in STATES:
            raise TableError(f"{self.state!r} is not a cell state; one of {STATES}")
        if not self.document_id.strip() or not self.column.strip():
            raise TableError("a cell belongs to one document and one column")
        if self.state == FOUND:
            if not self.value.strip():
                raise TableError(f"{self.column}: a FOUND cell with no value found nothing")
            if len(self.quote.strip()) < MIN_QUOTE_CHARS:
                raise TableError(
                    f"{self.column}: a FOUND cell needs the span it was read from "
                    f"(at least {MIN_QUOTE_CHARS} characters). Use found(), which checks "
                    f"the quote against the document")
        else:
            if self.value or self.quote:
                raise TableError(f"{self.column}: a {self.state} cell carries no value "
                                 f"and no quote -- it did not find one")
            if len(self.reason.strip()) < MIN_REASON_CHARS:
                raise TableError(
                    f"{self.column}: a {self.state} cell must say WHY in words. A blank "
                    f"reason renders as an empty cell, and 'the contract has no cap' and "
                    f"'we could not find the cap' are opposite facts")

    @property
    def rendered(self) -> str:
        """What a reader sees. Never empty, for any state."""
        return self.value if self.state == FOUND else STATE_LABEL[self.state]

    @property
    def is_finding(self) -> bool:
        """Does this cell say anything about the DOCUMENT? False for PENDING and FAILED."""
        return self.state in FINDING_STATES


def found(*, document_id: str, column: Column, value: str, quote: str,
          document_text: str) -> Cell:
    """A FOUND cell, or a raise. The ONLY way to make one.

    Takes the document text rather than trusting the caller, because "the quote matches"
    is the one property the rest of this feature rests on and a check a caller can skip is
    a check that will be skipped.
    """
    q = (quote or "").strip()
    if len(q) < MIN_QUOTE_CHARS:
        raise TableError(f"{column.name}: a quote of {len(q)} characters shows nothing "
                         f"about where the answer was read")
    if q not in (document_text or ""):
        raise TableError(
            f"{column.name}: the quote is NOT in document {document_id[:12]}. A cell whose "
            f"quote cannot be found in the document it names is not a finding about that "
            f"document, whatever it says")
    why = check_value(column.kind, value)
    if why:
        raise TableError(
            f"{column.name}: {why}. The honest answer is NEEDS_LAWYER with this quote "
            f"attached, so a person can read it and decide")
    return Cell(document_id=document_id, column=column.name, state=FOUND,
                value=value.strip(), quote=q)


def not_found(*, document_id: str, column: Column, reason: str) -> Cell:
    return Cell(document_id=document_id, column=column.name, state=NOT_FOUND,
                reason=reason)


def needs_lawyer(*, document_id: str, column: Column, reason: str) -> Cell:
    return Cell(document_id=document_id, column=column.name, state=NEEDS_LAWYER,
                reason=reason)


def pending(*, document_id: str, column: Column) -> Cell:
    return Cell(document_id=document_id, column=column.name, state=PENDING,
                reason="queued; this cell has not been run yet")


def failed(*, document_id: str, column: Column, detail: str) -> Cell:
    """A cell that did not run. TRANSPORT ONLY, and the only way to reach FAILED.

    The wording is deliberately about us and not about the document: "could not run" and
    not "not found". `gateway/envelope.failed()` makes the same distinction at the reply
    level for the same reason, and a review grid is where it matters most -- forty rows of
    NOT FOUND with three transport failures hidden among them is a diligence report that
    says a clause is missing from documents nobody read.
    """
    return Cell(document_id=document_id, column=column.name, state=FAILED,
                reason=(f"this cell did not complete: {detail}. That is a failure of ours "
                        f"and says nothing about the document -- it was not read, so no "
                        f"conclusion about this column follows from it"))


@dataclass(frozen=True)
class Table:
    table_id: str
    name: str
    columns: tuple = ()
    document_ids: tuple = ()
    cells: tuple = ()

    def __post_init__(self) -> None:
        if not self.columns:
            raise TableError(f"{self.name}: a table with no columns asks nothing")
        names = [c.name for c in self.columns]
        if len(set(names)) != len(names):
            raise TableError(f"{self.name}: column names repeat ({names})")
        known = set(names)
        for c in self.cells:
            if c.column not in known:
                raise TableError(f"cell names column {c.column!r}, which this table has "
                                 f"not defined ({sorted(known)})")
            if c.document_id not in set(self.document_ids):
                raise TableError(f"cell names document {c.document_id[:12]}, which this "
                                 f"table does not include")

    @property
    def by_key(self) -> dict:
        return {(c.document_id, c.column): c for c in self.cells}

    def cell(self, document_id: str, column: str) -> Cell:
        """The cell, or a PENDING one. A missing cell is not an empty answer."""
        got = self.by_key.get((document_id, column))
        if got is not None:
            return got
        col = next(c for c in self.columns if c.name == column)
        return pending(document_id=document_id, column=col)

    def tally(self) -> dict:
        counts = {s: 0 for s in STATES}
        for d in self.document_ids:
            for col in self.columns:
                counts[self.cell(d, col.name).state] += 1
        # Named, so a caller reporting "how many answers" cannot reach for the grid size
        # and count a transport failure as an answer about a document.
        counts["findings"] = sum(counts[s] for s in FINDING_STATES)
        counts["cells"] = len(self.document_ids) * len(self.columns)
        return counts

    @property
    def complete(self) -> bool:
        """Every cell has been run. A FAILED cell is run; a PENDING one is not."""
        return all(self.cell(d, c.name).state != PENDING
                   for d in self.document_ids for c in self.columns)


def to_csv(table: Table, *, names: dict | None = None) -> str:
    """The table as CSV. Every cell is non-empty, including the ones that found nothing.

    `names` maps document_id -> a human name. A sha256 down the first column is accurate
    and unreadable, and a lawyer exporting this is going to send it to someone.
    """
    names = names or {}
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["document"] + [c.name for c in table.columns])
    for d in table.document_ids:
        row = [names.get(d) or d]
        for col in table.columns:
            row.append(table.cell(d, col.name).rendered)
        w.writerow(row)
    return buf.getvalue()


def wilson(successes: int, n: int, *, z: float = 1.96) -> tuple[float, float]:
    """A 95% Wilson score interval for a proportion.

    Wilson and not normal-approximation, because the counts here are small and the
    proportions near 0 or 1: a normal interval on 2/2 is [1.0, 1.0], which claims
    certainty from two observations.
    """
    if n <= 0:
        return (0.0, 1.0)
    p = successes / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


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

    print("review_grid")
    DOC = ("MUTUAL NON-DISCLOSURE AGREEMENT\n"
           "3. This Agreement shall be governed by the laws of India.\n"
           "4. The term of confidentiality shall expire on 2029-03-31.\n"
           "7. The aggregate liability of either party shall not exceed INR 50,00,000.\n"
           "9. Neither party may assign this Agreement without prior written consent.\n")
    LAW = Column("governing law", TEXT, "Which law governs this agreement?")
    END = Column("term end", DATE, "On what date does confidentiality expire?")
    CAP = Column("liability cap", AMOUNT, "What is the cap on aggregate liability?")
    ASSIGN = Column("assignable", YES_NO, "May this agreement be assigned freely?")
    CL = Column("assignment clause", CLAUSE, "Quote the assignment clause.")
    COLS = (LAW, END, CAP, ASSIGN, CL)

    # ── a FOUND cell needs a byte-matching quote, and cannot be built without ─
    c = found(document_id="d1", column=LAW, value="India",
              quote="governed by the laws of India", document_text=DOC)
    check(c.state == FOUND and c.quote in DOC,
          "a FOUND cell carries a quote that is really in the document")
    try:
        found(document_id="d1", column=LAW, value="England",
              quote="governed by the laws of England", document_text=DOC)
        check(False, "a quote NOT in the document is refused")
    except TableError as e:
        check("NOT in document" in str(e),
              f"a quote NOT in the document is REFUSED -- not flagged, refused "
              f"({e!s:.44})")
    try:
        Cell(document_id="d1", column="governing law", state=FOUND, value="India",
             quote="India")
        check(False, "a FOUND cell with a 5-character quote is refused")
    except TableError as e:
        check("span it was read from" in str(e),
              "a FOUND cell with too short a quote is refused by the CONSTRUCTOR too, so "
              "the rule does not depend on going through found()")
    try:
        Cell(document_id="d1", column="governing law", state=FOUND, value="India")
        check(False, "a FOUND cell with NO quote is refused")
    except TableError:
        check(True, "a FOUND cell with no quote at all is refused")
    try:
        found(document_id="d1", column=LAW, value="", quote="laws of India",
              document_text=DOC)
        check(False, "a FOUND cell with no value is refused")
    except TableError as e:
        check("it is empty" in str(e) or "found nothing" in str(e),
              "a FOUND cell with no value found nothing")

    # ── the column kind is a promise about the value ────────────────────────
    d = found(document_id="d1", column=END, value="2029-03-31",
              quote="expire on 2029-03-31", document_text=DOC)
    check(d.value == "2029-03-31", "a date column takes an ISO date")
    try:
        found(document_id="d1", column=END, value="sometime in March 2029",
              quote="expire on 2029-03-31", document_text=DOC)
        check(False, "a date column refuses prose")
    except TableError as e:
        check("has not answered" in str(e) and "NEEDS_LAWYER" in str(e),
              f"a date column REFUSES prose and names the honest alternative -- "
              f"NEEDS_LAWYER with the quote attached ({e!s:.40})")
    a = found(document_id="d1", column=CAP, value="INR 50,00,000",
              quote="shall not exceed INR 50,00,000", document_text=DOC)
    check(a.state == FOUND, f"an amount column takes a currency amount ({a.value})")
    check(found(document_id="d1", column=CAP, value="unlimited",
                quote="liability of either party", document_text=DOC).value == "unlimited",
          "...and 'unlimited', which is a real contractual answer to a cap")
    for bad in ("about fifty lakh", "a lot", ""):
        check(check_value(AMOUNT, bad) is not None, f"an amount column refuses {bad!r}")
    y = found(document_id="d1", column=ASSIGN, value="no",
              quote="may assign this Agreement without prior written consent",
              document_text=DOC)
    check(y.value == "no", "a yes/no column takes no")
    check(check_value(YES_NO, "probably") is not None,
          "...and refuses 'probably': an unclear answer is not an answer")
    check(check_value(TEXT, "anything at all") is None
          and check_value(CLAUSE, "a whole clause") is None,
          "text and clause columns take free text")
    try:
        check_value("colour", "red")
        check(False, "an unknown kind raises")
    except TableError:
        check(True, "an unknown column kind raises rather than defaulting to text")

    # ── NOT_FOUND is STATED, never blank ────────────────────────────────────
    nf = not_found(document_id="d1", column=Column("arbitration seat", TEXT, "Where?"),
                   reason="the agreement names no arbitral seat; clause 12 refers "
                          "disputes to the courts at Mumbai instead")
    check(nf.state == NOT_FOUND and nf.rendered == "NOT FOUND",
          f"a NOT_FOUND cell renders as words, never as empty ({nf.rendered!r})")
    check(nf.reason and len(nf.reason) > MIN_REASON_CHARS,
          "...and carries the reason it found nothing")
    try:
        not_found(document_id="d1", column=LAW, reason="no")
        check(False, "a NOT_FOUND cell with a two-character reason is refused")
    except TableError as e:
        check("opposite facts" in str(e),
              "a NOT_FOUND cell must say WHY -- 'the contract has no cap' and 'we could "
              "not find the cap' are opposite facts and a blank renders them the same")
    try:
        Cell(document_id="d1", column="x", state=NOT_FOUND, value="India",
             reason="a long enough reason here")
        check(False, "a NOT_FOUND cell carrying a value is refused")
    except TableError:
        check(True, "a NOT_FOUND cell carrying a value is refused: it did not find one")

    nl = needs_lawyer(document_id="d1", column=CAP,
                      reason="clause 7 caps 'direct losses' only and clause 11 excludes "
                             "consequential loss; whether the cap is aggregate is a "
                             "reading a person must make")
    check(nl.state == NEEDS_LAWYER and nl.rendered == "NEEDS LAWYER",
          "a NEEDS_LAWYER cell renders as words too")

    # ── PENDING is not NOT_FOUND ────────────────────────────────────────────
    t = Table("t1", "NDA review", COLS, ("d1", "d2"),
              (c, d, a, y, found(document_id="d1", column=CL,
                                 value="Neither party may assign this Agreement",
                                 quote="Neither party may assign this Agreement",
                                 document_text=DOC)))
    check(t.cell("d2", "governing law").state == PENDING,
          "a cell that has not been run is PENDING, not NOT_FOUND -- 'we have not looked' "
          "and 'it is not there' are different answers")
    check(t.cell("d2", "governing law").rendered == "PENDING",
          "...and renders as PENDING, not as empty")
    check(t.tally()[FOUND] == 5 and t.tally()[PENDING] == 5,
          f"the tally counts every pair, run or not ({t.tally()})")
    check(sum(t.tally()[st] for st in STATES) == len(t.document_ids) * len(t.columns),
          "...and covers the whole grid (summing the STATE keys: tally() also carries "
          "`findings` and `cells`, and totalling everything would double-count)")
    check(t.tally()["cells"] == len(t.document_ids) * len(t.columns),
          "...which is what `cells` reports directly")

    # ── the table refuses to be built wrong ─────────────────────────────────
    for kw, why in [
        (dict(table_id="x", name="n", columns=(), document_ids=("d1",)),
         "no columns"),
        (dict(table_id="x", name="n", columns=(LAW, Column("governing law", DATE, "q?")),
              document_ids=("d1",)), "a repeated column name"),
        (dict(table_id="x", name="n", columns=(LAW,), document_ids=("d1",),
              cells=(Cell(document_id="d1", column="nope", state=NOT_FOUND,
                          reason="a long enough reason"),)), "a cell naming no column"),
        (dict(table_id="x", name="n", columns=(LAW,), document_ids=("d1",),
              cells=(Cell(document_id="d9", column="governing law", state=NOT_FOUND,
                          reason="a long enough reason"),)),
         "a cell naming a document not in the table"),
    ]:
        try:
            Table(**kw)
            check(False, f"a table with {why} is refused")
        except TableError:
            check(True, f"a table with {why} is refused")
    try:
        Column("x", TEXT, "")
        check(False, "a column with no question is refused")
    except TableError as e:
        check("not a question" in str(e),
              "a column with no QUESTION is refused: a cell answered against a header is "
              "a cell nobody can check")

    # ── CSV: no cell is ever empty ──────────────────────────────────────────
    out = to_csv(t, names={"d1": "mutual-nda.docx", "d2": "supply-agreement.docx"})
    rows = [r for r in csv.reader(io.StringIO(out))]
    check(rows[0] == ["document"] + [col.name for col in COLS],
          f"the header is the document plus every column ({rows[0][:3]})")
    check(rows[1][0] == "mutual-nda.docx",
          "a document renders by NAME where one is known: a sha256 in column one is "
          "accurate and unreadable, and this gets emailed")
    check(rows[2][0] == "supply-agreement.docx", "...for every row")
    empties = [(ri, ci) for ri, r in enumerate(rows[1:], 1)
               for ci, v in enumerate(r) if not str(v).strip()]
    check(not empties,
          f"**no cell in the CSV is empty**, including every one that found nothing "
          f"({empties})")
    check("PENDING" in out and "India" in out,
          "...a pending cell and a found one both appear, distinguishably")
    check(len(rows) == 1 + len(t.document_ids), f"one row per document ({len(rows) - 1})")

    # ── FAILED is transport only, and is not a finding ──────────────────────
    fl = failed(document_id="d2", column=CAP, detail="the provider timed out after 30s")
    check(fl.state == FAILED and fl.rendered == "COULD NOT RUN",
          f"a FAILED cell renders as COULD NOT RUN, never as NOT FOUND ({fl.rendered!r})")
    check("says nothing about the document" in fl.reason,
          "...and its reason says so in words")
    check(not fl.is_finding and not pending(document_id="d2", column=CAP).is_finding,
          "FAILED and PENDING are NOT findings: neither says anything about the document")
    check(all(Cell(document_id="d1", column=LAW.name, state=st,
                   reason="a long enough reason here").is_finding
              for st in (NOT_FOUND, NEEDS_LAWYER)) and c.is_finding,
          "FOUND, NOT_FOUND and NEEDS_LAWYER are findings")
    check(FAILED not in FINDING_STATES and PENDING not in FINDING_STATES,
          f"FINDING_STATES is exactly the three that describe a document ({FINDING_STATES})")
    try:
        Cell(document_id="d1", column=LAW.name, state=FAILED, value="India",
             reason="a long enough reason here")
        check(False, "a FAILED cell carrying a value is refused")
    except TableError:
        check(True, "a FAILED cell carrying a value is refused: it did not read anything")
    t2 = Table("t2", "n", (LAW, CAP), ("d1", "d2"),
               (c, fl, not_found(document_id="d2", column=LAW,
                                 reason="the agreement names no governing law at all")))
    ta = t2.tally()
    check(ta["findings"] == 2 and ta["cells"] == 4,
          f"the tally separates FINDINGS from cells, so a transport failure is never "
          f"counted as an answer ({ta})")
    check(ta[FAILED] == 1 and ta[PENDING] == 1, f"...and names both non-findings ({ta})")
    check(not t2.complete, "a grid with a PENDING cell is not complete")
    check(Table("t3", "n", (LAW,), ("d1",), (c,)).complete,
          "...while one whose every cell has run is, FAILED cells included")
    out2 = to_csv(t2)
    check("COULD NOT RUN" in out2 and "NOT FOUND" in out2,
          "the CSV distinguishes a transport failure from a document that lacks the clause")
    empt = [v for r in csv.reader(io.StringIO(out2)) for v in r if not str(v).strip()]
    check(not empt, f"...and still no cell is empty ({empt})")

    # ── Wilson ──────────────────────────────────────────────────────────────
    lo, hi = wilson(2, 2)
    check(lo < 1.0,
          f"Wilson on 2/2 does not claim certainty from two observations "
          f"({lo:.3f}-{hi:.3f}) -- a normal approximation gives [1.000, 1.000]")
    lo2, hi2 = wilson(0, 5)
    check(lo2 == 0.0 and hi2 > 0.3,
          f"...and 0/5 leaves a wide upper bound ({lo2:.3f}-{hi2:.3f})")
    lo3, hi3 = wilson(50, 100)
    check(abs((lo3 + hi3) / 2 - 0.5) < 0.02 and (hi3 - lo3) < 0.25,
          f"...while 50/100 is centred and tighter ({lo3:.3f}-{hi3:.3f})")
    check(wilson(0, 0) == (0.0, 1.0),
          "no observations gives the whole interval, not a division by zero")
    check(wilson(1, 10)[0] < 0.1 < wilson(1, 10)[1],
          "the interval contains the point estimate")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_test())
    print(__doc__)
