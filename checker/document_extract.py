"""Grounding an extractor's proposals in the document it claims to have read.

`extraction_schema.py` checks the SHAPE of a proposed field -- could this string
be a CIN at all. This module checks something different and, for F1, more
important: **is this value actually in the document?**

A model asked to read a board resolution will happily return a paid-up capital
figure. Shape validation cannot tell whether it read that figure or recalled it
from a similar document, and the difference is the whole product. So nothing here
accepts a bare value. An extractor must supply the verbatim span it read, the
span must appear in the document, and the parsed value must be derivable from the
span. Any one of those failing rejects the field -- it is never repaired, and
never quietly promoted.

## Why the extractor must quote itself

Requiring a span is what converts "the model says capital is Rs 6 crore" into a
checkable claim. The alternative -- matching a parsed number against the document
-- forces us to normalise the document's own text to find it, and normalisation
is repair by another name. Making the extractor quote the source moves the burden
to the party making the claim, which is where it belongs.

## What this does not do

It does not decide whether the document is genuine (`doc_verification.py`), nor
whether the extracted facts produce a compliant company (`obligations.py`), nor
whether the law has moved (`api.document_check`). It answers one question: of the
things the extractor said, which are demonstrably in front of it.

No model is called here. Nothing here trusts one.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field as _field
from datetime import date

# ── verdicts ──────────────────────────────────────────────────────────────────
GROUNDED = "GROUNDED"                  # span found, value consistent with it
ABSENT = "ABSENT"                      # extractor proposed nothing. Not a defect
NO_SPAN = "NO_SPAN"                    # a value with no quoted source
NOT_IN_DOCUMENT = "NOT_IN_DOCUMENT"    # the quoted span is not in the document
VALUE_MISMATCH = "VALUE_MISMATCH"      # span is present but does not yield the value

REJECTING = (NO_SPAN, NOT_IN_DOCUMENT, VALUE_MISMATCH)

# Fields the document check consumes. A field outside this set is ignored rather
# than rejected -- an extractor volunteering extra detail is not a defect -- but
# nothing unlisted is ever promoted into the payload.
DATE_FIELDS = ("document_date", "incorporation_date")
MONEY_FIELDS = ("paid_up_capital_rupees", "turnover_rupees",
                "net_worth_rupees", "net_profit_rupees")
TEXT_FIELDS = ("company_class", "financial_year", "cin")
INT_FIELDS = ("director_count",)
KNOWN_FIELDS = DATE_FIELDS + MONEY_FIELDS + TEXT_FIELDS + INT_FIELDS


@dataclass(frozen=True)
class Grounded:
    """One proposed field, and whether the document actually supports it."""
    name: str
    value: object | None
    span: str | None
    start: int | None
    end: int | None
    verdict: str
    reason: str = ""

    @property
    def usable(self) -> bool:
        return self.verdict == GROUNDED


@dataclass(frozen=True)
class GroundedExtraction:
    fields: tuple[Grounded, ...]
    source_id: str | None = None
    warnings: tuple[str, ...] = _field(default_factory=tuple)

    def get(self, name: str) -> Grounded | None:
        return next((f for f in self.fields if f.name == name), None)

    @property
    def rejected(self) -> tuple[Grounded, ...]:
        return tuple(f for f in self.fields if f.verdict in REJECTING)

    @property
    def admissible(self) -> bool:
        """Strict, and deliberately so.

        One ungrounded field poisons the record. A resolution whose date is read
        correctly and whose capital was invented is not "mostly right" -- it is a
        document about a company we cannot identify the position of, and passing
        the good half downstream is how a hallucinated figure acquires the
        authority of the fields around it.
        """
        return self.source_id is not None and not self.rejected

    def refusal_reason(self) -> str | None:
        if self.source_id is None:
            return "no source id: an extraction with no document behind it is not admitted"
        if self.rejected:
            return "ungrounded field(s): " + "; ".join(
                f"{f.name} ({f.verdict}: {f.reason})" for f in self.rejected)
        return None

    def to_payload(self) -> dict:
        """The `POST /v1/document-check` body. Only grounded fields appear."""
        return {f.name: f.value for f in self.fields if f.usable}


# ── span location ─────────────────────────────────────────────────────────────
def _normalise(text: str) -> str:
    """Fold the differences a PDF text layer introduces but a reader does not see.

    Deliberately narrow: NFKC (so a ligature or a full-width digit matches its
    plain form) and whitespace runs collapsed to one space. This is NOT repair --
    it changes only how we SEARCH, never what we store or report. The stored span
    stays exactly as the extractor supplied it. G.S.R. 880(E)'s own text layer
    encodes "s hall" for "shall", which is why a byte-exact search would fail on a
    correctly-read document.
    """
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text))


def locate(span: str, document: str) -> tuple[int, int] | None:
    """Character offsets of `span` in `document`, or None. Case-sensitive."""
    if not span or not span.strip():
        return None
    hay, needle = _normalise(document), _normalise(span)
    i = hay.find(needle)
    if i < 0:
        return None
    return i, i + len(needle)


# ── value/span consistency ────────────────────────────────────────────────────
_CRORE = 10_000_000
_LAKH = 100_000
_MONEY_WORDS = {"crore": _CRORE, "crores": _CRORE, "cr": _CRORE,
                "lakh": _LAKH, "lakhs": _LAKH, "lac": _LAKH, "lacs": _LAKH}
_NUM = re.compile(r"(\d[\d,\s]*(?:\.\d+)?)")
_DATE_PATTERNS = (
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), ("y", "m", "d")),
    (re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b"), ("d", "m", "y")),
)
_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], start=1)}
_LONG_DATE = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:day\s+of\s+)?([A-Za-z]+),?\s+(\d{4})\b")


def _money_from_span(span: str) -> int | None:
    """The rupee amount a span states, or None if it states none unambiguously."""
    s = _normalise(span).lower()
    m = _NUM.search(s)
    if not m:
        return None
    raw = m.group(1).replace(",", "").replace(" ", "")
    try:
        n = float(raw)
    except ValueError:
        return None
    tail = s[m.end():].strip()
    word = re.match(r"([a-z]+)", tail)
    if word and word.group(1) in _MONEY_WORDS:
        n *= _MONEY_WORDS[word.group(1)]
    if n != int(n):
        return None
    return int(n)


def _date_from_span(span: str) -> date | None:
    s = _normalise(span)
    for pat, order in _DATE_PATTERNS:
        m = pat.search(s)
        if m:
            parts = dict(zip(order, m.groups()))
            try:
                return date(int(parts["y"]), int(parts["m"]), int(parts["d"]))
            except ValueError:
                return None
    m = _LONG_DATE.search(s)
    if m:
        mon = _MONTHS.get(m.group(2).lower())
        if mon is None:
            return None
        try:
            return date(int(m.group(3)), mon, int(m.group(1)))
        except ValueError:
            return None
    return None


# Counts in corporate documents are written in words as often as digits ("seven
# directors"). Zero to twenty covers board and member counts as written; a count
# above twenty in words is refused as no number rather than guessed at.
_NUMBER_WORDS = {w: n for n, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen "
    "fourteen fifteen sixteen seventeen eighteen nineteen twenty".split())}


def _integers(span: str) -> set[int]:
    """Every distinct whole number a span states, in digits or in words."""
    text = _normalise(span)
    found = {int(m.group(1).replace(",", "").replace(" ", "")) for m in _NUM.finditer(text)}
    found |= {_NUMBER_WORDS[w] for w in re.findall(r"[a-z]+", text.lower())
              if w in _NUMBER_WORDS}
    return found


def value_supported_by_span(name: str, value: object, span: str) -> tuple[bool, str]:
    """Does the quoted span actually yield the proposed value?

    Public because it has two callers. `reasoning.review()` used to check only
    that a span EXISTED in the document, which a prompt injection defeats: an
    attacker who controls the document controls the span too, so
    {"value": 999999999, "span": "verified"} passed review clean when the word
    "verified" appeared inside the injection itself. Span presence is necessary
    and never sufficient.
    """
    if name in MONEY_FIELDS:
        got = _money_from_span(span)
        if got is None:
            return False, "the quoted span states no unambiguous rupee amount"
        return (got == value,
                f"span states {got}, extractor proposed {value}" if got != value else "")
    if name in DATE_FIELDS:
        got = _date_from_span(span)
        if got is None:
            return False, "the quoted span states no date this parser recognises"
        want = value if isinstance(value, date) else _as_date(value)
        return (got == want,
                f"span states {got}, extractor proposed {value}" if got != want else "")
    if name in INT_FIELDS:
        # One number, or no support. "Four directors of the Company's seven were
        # present" states two counts; gpt-5-mini proposed the wrong one (4) from it
        # on 15-09-2026, and the first-number rule this replaced would have taken
        # the first number of "4 directors of the Company's 7" the same way.
        got = _integers(span)
        if not got:
            return False, "the quoted span states no number"
        if len(got) > 1:
            return False, (f"the quoted span states more than one number "
                           f"({', '.join(str(n) for n in sorted(got))}) and does "
                           f"not say which is {name}")
        (n,) = got
        return n == value, f"span states {n}, extractor proposed {value}" if n != value else ""
    if name == "cin":
        # A CIN has a fixed 21-character structure. A value that is not one is not
        # a CIN, however faithfully its span quotes it -- and a damaged one is
        # reported as written, never repaired (party_resolution's rule).
        from checker.party_resolution import CIN_RE
        if not CIN_RE.match(str(value or "")):
            return False, (f"{str(value)!r} is not a well-formed CIN (L/U, 5-digit "
                           f"activity, state, year, ownership, 6-digit number)")
    # text: the value must appear in what was quoted -- and must say something.
    # An empty value is a substring of every span, so it is supported by none.
    if value is None or not str(value).strip():
        return False, "the proposed value is empty; no span can support it"
    return (str(value).lower() in _normalise(span).lower(),
            f"{value!r} does not appear in the quoted span")


def _as_date(v: object) -> date | None:
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v))
    except (ValueError, TypeError):
        return None


# ── the entry point ───────────────────────────────────────────────────────────
def ground(document: str, proposed: dict, *, source_id: str | None = None
           ) -> GroundedExtraction:
    """Check every proposed field against the document. No repair, no promotion.

    `proposed` maps a field name to either a bare value (rejected -- NO_SPAN) or
    `{"value": ..., "span": "<verbatim text read>"}`.
    """
    out: list[Grounded] = []
    warnings: list[str] = []

    extra = set(proposed) - set(KNOWN_FIELDS)
    if extra:
        warnings.append(
            f"unknown key(s) ignored, not promoted: {', '.join(sorted(extra))}")

    for name in KNOWN_FIELDS:
        item = proposed.get(name)
        if item is None:
            out.append(Grounded(name, None, None, None, None, ABSENT,
                                "the extractor proposed nothing for this field"))
            continue
        if not isinstance(item, dict) or "span" not in item:
            out.append(Grounded(name, item if not isinstance(item, dict) else item.get("value"),
                                None, None, None, NO_SPAN,
                                "a value with no quoted span cannot be checked against "
                                "the document; quote what you read"))
            continue

        value, span = item.get("value"), item.get("span")
        at = locate(span or "", document)
        if at is None:
            out.append(Grounded(name, value, span, None, None, NOT_IN_DOCUMENT,
                                "the quoted span does not appear in the document"))
            continue
        ok, why = value_supported_by_span(name, value, span or "")
        if not ok:
            out.append(Grounded(name, value, span, at[0], at[1], VALUE_MISMATCH, why))
            continue
        out.append(Grounded(name, value, span, at[0], at[1], GROUNDED))

    return GroundedExtraction(tuple(out), source_id, tuple(warnings))


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

    print("document_extract")
    DOC = ("CERTIFIED TRUE COPY of a resolution passed at the meeting of the Board "
           "of Directors held on the 1st day of June, 2024. The Company is a private "
           "company incorporated on 2015-04-01. Its paid up share capital is "
           "Rs. 6,00,00,000 and turnover for the financial year 2024-25 was "
           "Rs. 55 crore. The Board comprises 2 directors.")

    good = {
        "document_date": {"value": "2024-06-01", "span": "1st day of June, 2024"},
        "incorporation_date": {"value": "2015-04-01", "span": "incorporated on 2015-04-01"},
        "company_class": {"value": "private", "span": "is a private company"},
        "paid_up_capital_rupees": {"value": 60000000, "span": "Rs. 6,00,00,000"},
        "turnover_rupees": {"value": 550000000, "span": "Rs. 55 crore"},
        "financial_year": {"value": "2024-25", "span": "financial year 2024-25"},
        "director_count": {"value": 2, "span": "2 directors"},
    }
    g = ground(DOC, good, source_id="doc-1")
    check(g.admissible, f"a fully quoted extraction is admissible ({g.refusal_reason()})")
    check(all(f.usable for f in g.fields if f.name in good),
          "...every quoted field is grounded")
    check(g.get("paid_up_capital_rupees").start is not None,
          "...and carries the character offsets where it was found")
    check(g.get("turnover_rupees").value == 550000000,
          "'Rs. 55 crore' resolves to 550000000")
    check(g.get("cin").verdict == ABSENT,
          "a field the extractor did not propose is ABSENT, not a defect")
    check(g.admissible, "...and ABSENT does not block admissibility")

    # ── the failure this module exists to catch ──────────────────────────────
    invented = dict(good, paid_up_capital_rupees={
        "value": 40000000, "span": "paid up share capital is Rs. 4,00,00,000"})
    g2 = ground(DOC, invented, source_id="doc-1")
    check(not g2.admissible, "a figure quoted from text not in the document is refused")
    check(g2.get("paid_up_capital_rupees").verdict == NOT_IN_DOCUMENT,
          f"...as NOT_IN_DOCUMENT ({g2.get('paid_up_capital_rupees').verdict})")
    check("does not appear" in (g2.refusal_reason() or ""),
          "...and the refusal says why")

    # right span, wrong number: the subtler failure
    mismatch = dict(good, paid_up_capital_rupees={
        "value": 40000000, "span": "Rs. 6,00,00,000"})
    g3 = ground(DOC, mismatch, source_id="doc-1")
    check(g3.get("paid_up_capital_rupees").verdict == VALUE_MISMATCH,
          "a real span that does not yield the proposed value is VALUE_MISMATCH")
    check("60000000" in g3.get("paid_up_capital_rupees").reason,
          "...and the reason names what the span actually says")

    # a bare value cannot be checked at all
    bare = dict(good, turnover_rupees=550000000)
    g4 = ground(DOC, bare, source_id="doc-1")
    check(g4.get("turnover_rupees").verdict == NO_SPAN,
          "a value with no quoted span is NO_SPAN, never accepted on trust")

    # ── strictness: one bad field poisons the record ─────────────────────────
    check(not g2.admissible and g2.get("document_date").usable,
          "one ungrounded field blocks the record even though others are grounded")
    check("paid_up_capital_rupees" not in g2.to_payload(),
          "...and the ungrounded field never reaches the payload")
    check("document_date" in g.to_payload() and "cin" not in g.to_payload(),
          "the payload carries grounded fields only")

    # ── no source is not admissible ──────────────────────────────────────────
    check(not ground(DOC, good).admissible, "an extraction with no source id is refused")

    # ── the PDF-text-layer case that motivated the search normalisation ──────
    odd = "the small company s hall not exceed rupees ten crores"
    check(locate("small company s hall not exceed", odd) is not None,
          "a span is found in text whose PDF layer split a word")
    check(locate("small  company   s hall", odd) is not None,
          "...and whitespace runs do not defeat the search")
    check(locate("company shall not exceed", odd) is None,
          "but the search does NOT repair the source to make a span match")

    # ── an empty value is not supported by every span ────────────────────────
    # 14-09-2026, llama3 via the realrun probe: {"cin": {"value": "", "span":
    # "The Company was incorporated on 01 April 2015."}} was SERVED. The text
    # check asked whether the value appears in the span, and "" appears in every
    # string. An empty value says nothing, so no span can support it.
    t05_span = "The Company was incorporated on 01 April 2015."
    for blank in ("", "   "):
        for field in TEXT_FIELDS:
            ok_blank, why = value_supported_by_span(field, blank, t05_span)
            check(not ok_blank,
                  f"{field}={blank!r} is not supported by an unrelated span ({why})")
    g6 = ground(t05_span, {"cin": {"value": "", "span": t05_span}}, source_id="d")
    check(not g6.get("cin").usable and "cin" not in g6.to_payload(),
          "...and ground() refuses it, so the empty CIN never reaches a payload")
    check(value_supported_by_span("company_class", "private", "is a private company")[0],
          "a real text value its span contains is still supported")

    # ── a CIN value must be a CIN ────────────────────────────────────────────
    # 14-09-2026, llama3 (T04): {"cin": {"value": "ACME HOLDINGS PUBLIC LIMITED",
    # "span": "Its holding company, ACME HOLDINGS PUBLIC LIMITED, is a public
    # limited company."}} served when proposed alone -- the span contains the
    # value, so the text check passed. A company name is not a CIN.
    t04_span = ("Its holding company, ACME HOLDINGS PUBLIC LIMITED, is a public "
                "limited company.")
    ok_name, why_name = value_supported_by_span("cin", "ACME HOLDINGS PUBLIC LIMITED",
                                                t04_span)
    check(not ok_name, f"a company name filed as a CIN is refused ({why_name})")
    check(value_supported_by_span("cin", "U74999KA2019PTC123456",
                                  "CIN U74999KA2019PTC123456,")[0],
          "a well-formed CIN its span contains is supported")
    damaged = "U74999KA2O19PTC123456"          # letter O where the year has a 0
    ok_dmg, why_dmg = value_supported_by_span("cin", damaged, f"CIN {damaged}")
    check(not ok_dmg and damaged in why_dmg,
          "a scanner-damaged CIN is refused and reported as written -- never "
          "repaired into a lookup against a different company")
    g7 = ground(t04_span, {"cin": {"value": "ACME HOLDINGS PUBLIC LIMITED",
                                   "span": t04_span}}, source_id="d")
    check("cin" not in g7.to_payload(), "...and ground() keeps it out of the payload")

    # ── an integer is read in words too, and only from an unambiguous span ───
    # 14/15-09-2026, realrun R03 on real models. "Four directors of the Company's
    # seven were present." Llama-3.3-70B quoted "the Company's seven" for
    # director_count=7 and was refused: the check looked for a digit. gpt-5-mini
    # quoted the whole sentence and proposed 4 -- the PRESENT count, the wrong
    # answer. A fix that only learned number words and kept "first number wins"
    # would have served that 4. So the span must state exactly one number.
    ok7, why7 = value_supported_by_span("director_count", 7, "the Company's seven")
    check(ok7, f"'the Company's seven' supports director_count=7 ({why7 or 'ok'})")
    sentence = "Four directors of the Company's seven were present."
    ok4, why4 = value_supported_by_span("director_count", 4, sentence)
    check(not ok4 and "4" in why4 and "7" in why4,
          f"gpt-5-mini's 4 from a span stating two counts is refused as ambiguous ({why4})")
    check(not value_supported_by_span("director_count", 7, sentence)[0],
          "...and so is 7 from the same span -- the span does not say which count it is")
    ok_d4, why_d4 = value_supported_by_span("director_count", 4,
                                            "4 directors of the Company's 7")
    check(not ok_d4,
          f"digits too: '4 directors of the Company's 7' no longer supports 4 "
          f"-- the first-number rule accepted it ({why_d4})")
    check(value_supported_by_span("director_count", 2, "2 directors")[0]
          and value_supported_by_span("director_count", 12, "twelve directors")[0],
          "a span stating one count, in digits or words, still supports it")
    check(not value_supported_by_span("director_count", 3, "the Board of Directors")[0],
          "a span stating no number supports none")

    # unknown keys are ignored, not rejected
    g5 = ground(DOC, dict(good, auditor_name={"value": "X", "span": "X"}), source_id="d")
    check(any("auditor_name" in w for w in g5.warnings),
          "an unknown key is warned about, not promoted")
    check("auditor_name" not in g5.to_payload(), "...and never reaches the payload")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
