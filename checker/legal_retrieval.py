"""
Exact/structural retrieval: turn what a lawyer typed into the provisions they named.

This is the deliberately dumb half of retrieval. It does not rank, guess, or paraphrase. It reads
citation syntax -- "s.173", "Sec 173(2)(a)", "ss. 173-175", "ACT:COMPANIES_ACT_2013:S173" -- and
returns the records those citations name, or nothing.

Three properties are load-bearing, in this order:

1. A number is not an identity. `checker/legal_ref.py` documents the real collision: the Act's s.56
   and the Board-Meeting Rules' r.56 are different provisions. So "rule 4" is NOT answered with
   Act s.4. The Rules corpus does not exist yet (acquisition blocked -- see
   `checker/provenance.py`), and the honest answer to a question about a text we do not hold is
   silence, not the nearest text we do hold.

2. Defects travel with the text. `docs/SOURCE_DEFECTS.md` records two confirmed source defects.
   A caller that never reads that file must still be unable to serve s.16 without knowing the
   corpus wording there is pre-amendment. Attaching the defect id to the Hit is the only way that
   holds; a note in prose does not survive a function boundary.

3. Unmapped is an answer. `section_by_number` returns None for sections it could not map (s.378ZA)
   or that the Act omits (s.11). Those return no Hit. Fabricating one would be the exact failure
   this repo exists to prevent.

Subsection references resolve to the SECTION, not the sub-provision: we hold section-level records,
so "s.173(2)" can honestly say "here is s.173, you asked about (2)" and cannot honestly say "here
is s.173(2)".

Run: python3 checker/legal_retrieval.py
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

# Imports below are `checker.*`, but this file is executed as a script (repo convention: every
# module self-tests). Python then puts checker/ on sys.path, not the repo root, and the import
# dies with ModuleNotFoundError -- which scripts/run_tests.sh warns reads as a silent pass.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from checker.legal_ref import ACT, RULE, LegalRef, parse_key  # noqa: E402
from checker.section_index import section_by_number  # noqa: E402

__all__ = ["Hit", "resolve", "names_a_provision", "DEFECT_REGISTER", "WITHHELD_DEFECTS",
           "COMPANIES_ACT_2013"]

COMPANIES_ACT_2013 = "COMPANIES_ACT_2013"

# The only instrument we hold text for. Anything else -- any Rules, any other Act -- resolves to
# nothing, however well-formed the citation.
CORPUS_INSTRUMENTS = frozenset({COMPANIES_ACT_2013})

# docs/SOURCE_DEFECTS.md, both entries. Keyed by section number because that is what a citation
# carries; the corpus record id is an India Code internal that no user ever types.
#   SD-001  corpus record 184 (s.1) ends with the editorial instruction "To be deleted", which is
#           not statutory text. The section is otherwise sound.
#   SD-002  the JSON corpus carries PRE-amendment wording where the PDF carries current text.
#           "fine" -> "penalty" is the Companies (Amendment) Act 2020 decriminalisation signature.
DEFECT_REGISTER: dict[str, tuple[str, ...]] = {
    "1": ("SD-001",),
    "16": ("SD-002",),
    "124": ("SD-002",),
    "76A": ("SD-002",),
    "329": ("SD-002",),
}

# SOURCE_DEFECTS.md: "no section in the table above may be served" until an independent source says
# which vintage is authoritative. We cannot refuse to return the Hit -- the caller asked for that
# section by number and hiding it would be a silent drop -- so it comes back at the lowest
# confidence the contract has, carrying the defect id. SD-001 is not withheld: its defect is a
# quotable tail, not a wrong statement of the law.
WITHHELD_DEFECTS = frozenset({"SD-002"})

# A wider span is far more likely a mis-parse (a date, a page range) than a citation. The named
# endpoints are still returned; only the invented middle is refused.
MAX_RANGE_SPAN = 25

ROUTE_EXACT = "exact-number"
ROUTE_KEY = "qualified-key"
ROUTE_SUBSECTION = "subsection"
ROUTE_RANGE = "range"


@dataclass(frozen=True)
class Hit:
    ref: LegalRef
    section_id: str | None          # corpus record id
    title: str
    route: str                      # ROUTE_* above
    confidence: str                 # "high" | "medium" | "low"
    defects: tuple[str, ...] = ()   # source defect ids, e.g. ("SD-001",)
    # Recorded, never resolved. Appended after `defects` so the five-field contract other modules
    # were written against still constructs and unpacks unchanged.
    subsection: str = ""            # e.g. "(2)(a)" for "s.173(2)(a)"


# --- citation syntax ---------------------------------------------------------------------------

# Longest alternatives first: `sections` must win over `s` at the same position.
_ACT_WORDS = r"§§|§|sections|section|secs|sec|ss|s"
_RULE_WORDS = r"rules|rule|rr|r"

# A prefix only counts when a number actually follows, so prose ("...as such") cannot trip it.
# The lookbehind stops the `s` alternative firing inside a word or on a possessive ("what's 173").
_PREFIX = re.compile(
    rf"(?<![\w'’])(?:(?P<act>{_ACT_WORDS})|(?P<rule>{_RULE_WORDS}))\s*\.?\s*(?=[0-9])",
    re.IGNORECASE,
)

# Section numbers per legal_ref's key grammar: digits then an optional inserted-section suffix
# (3A, 378ZA). The trailing lookahead stops "s.2013" being read as s.201.
_ITEM = re.compile(
    r"(?P<num>[0-9]{1,3}[A-Za-z]{0,3})(?![0-9A-Za-z])"
    r"(?P<sub>(?:\s*\([0-9A-Za-z]{1,4}\))*)",
)

# `and`/`,` enumerate; `-`/`to` span. Both continue the same citation, so "ss. 173-175 and 179"
# parses as one run rather than four unrelated numbers.
#
# Continuation is allowed after a SINGULAR prefix too, because "s.173 and 174" is written
# constantly, and refusing it would silently drop a section the user did ask for.
#
# The cost of that permissiveness is "section 173 and 5 directors" also yielding s.5. That is not
# free noise: a spurious provision reaching an evidence pack is a lawyer reading law nobody cited.
# So a continuation number is rejected when a word follows it directly -- a real citation ends at
# punctuation, a connector, or the end of the clause, whereas a quantity is attached to the thing
# it counts ("5 directors", "30 days"). This keeps every genuine citation form and drops the
# quantity reading.
_SEP = re.compile(
    r"\s*(?:(?P<range>-|–|—|to|through)|,|;|&|and)\s+?|"
    r"\s*(?:(?P<range2>-|–|—)|,|;|&)\s*",
    re.IGNORECASE,
)

# A citation prefix followed by digits. Deliberately looser than _ITEM: this asks "did the user
# cite something", not "can we resolve it".
_CITATION_SHAPE = re.compile(
    r"(?:\bu/s\b|\bs{1,2}\b|\bsec(?:tion|s)?\b|\brules?\b|\br\b|§+)\s*\.?\s*[0-9]",
    re.IGNORECASE)

_QUALIFIED_KEY = re.compile(r"\b(?:ACT|RULE):[A-Z0-9_]+:[SR][0-9]{1,3}[A-Z]{0,3}\b")


@dataclass(frozen=True)
class _Cite:
    """One citation as written, before any corpus lookup."""
    namespace: str    # ACT | RULE
    instrument: str   # COMPANIES_ACT_2013, or whatever the citation named
    number: str
    subsection: str
    route: str


def _expand(low: str, high: str) -> list[str]:
    """Section numbers strictly between two range endpoints.

    Only pure digits expand. "173A-175" has no defined enumeration -- inserted sections are not
    evenly spaced and some do not exist -- so the endpoints stand alone rather than inventing a run.
    """
    if not (low.isdigit() and high.isdigit()):
        return []
    a, b = int(low), int(high)
    if not 0 < b - a <= MAX_RANGE_SPAN:
        return []
    return [str(n) for n in range(a + 1, b)]


# Words that may legitimately follow a citation number. Anything else following directly means the
# number was counting something, not naming a provision.
_CITE_TAIL = re.compile(
    r"\s*(?:$|[),;.:\]]|and\b|or\b|to\b|read\b|of\b|thereof\b|ibid\b|"
    r"[-–—]|&|s{1,2}\.|section|sub-?section|proviso|clause|rule)", re.IGNORECASE)


def _is_quantity(text: str, m: re.Match) -> bool:
    """True when the number at `m` is counting something rather than naming a provision.

    "section 173 and 5 directors" -- the 5 is attached to `directors`. "sections 173 and 174" --
    the 174 ends the clause. Only the first should be dropped.
    """
    return not _CITE_TAIL.match(text, m.end())


def _scan_run(text: str, pos: int, namespace: str, instrument: str) -> list[_Cite]:
    """Read one comma/range-joined run of numbers following a single prefix."""
    out: list[_Cite] = []
    pending_range_from: str | None = None
    while True:
        m = _ITEM.match(text, pos)
        if not m:
            break
        number = m.group("num").upper()
        subsection = re.sub(r"\s+", "", m.group("sub"))
        if pending_range_from is not None:
            # Only the interior of a range is inferred. Both endpoints were typed by the user, so
            # they keep ROUTE_EXACT -- the route says how the reference was obtained, and a caller
            # weighing "did they actually ask for this" needs that distinction.
            out += [_Cite(namespace, instrument, n, "", ROUTE_RANGE)
                    for n in _expand(pending_range_from, number)]
        pending_range_from = None
        out.append(_Cite(namespace, instrument, number, subsection,
                         ROUTE_SUBSECTION if subsection else ROUTE_EXACT))
        pos = m.end()
        sep = _SEP.match(text, pos)
        nxt = _ITEM.match(text, sep.end()) if sep else None
        if not sep or not nxt:
            break
        if _is_quantity(text, nxt):
            break
        if sep.group("range") or sep.group("range2"):
            pending_range_from = number
        pos = sep.end()
    return out


def _scan(query: str) -> list[_Cite]:
    """Every citation in the query, in the order written, deduplicated."""
    cites: list[_Cite] = []
    text = query or ""

    # Qualified keys first, then blanked out: ":S173" would otherwise be re-read as a bare "s.173"
    # by the prefix scanner and produce a duplicate under the wrong route.
    for m in _QUALIFIED_KEY.finditer(text):
        try:
            ref = parse_key(m.group(0))
        except ValueError:
            continue
        cites.append(_Cite(ref.instrument_type, ref.instrument_id, ref.number, "", ROUTE_KEY))
    text = _QUALIFIED_KEY.sub(lambda m: " " * len(m.group(0)), text)

    for m in _PREFIX.finditer(text):
        # An unqualified "s.173" can only mean the one Act whose text we hold. Naming the
        # instrument here rather than leaving it blank keeps the assumption visible in the Hit.
        cites += _scan_run(text, m.end(), RULE if m.group("rule") else ACT, COMPANIES_ACT_2013)

    seen: set[tuple[str, str, str, str]] = set()
    unique: list[_Cite] = []
    for c in cites:
        k = (c.namespace, c.instrument, c.number, c.subsection)
        if k not in seen:
            seen.add(k)
            unique.append(c)
    return unique


# --- resolution --------------------------------------------------------------------------------


def _to_hit(cite: _Cite) -> Hit | None:
    # A Rules citation has no corpus to resolve against. Returning the Act section of the same
    # number is the precise mistake legal_ref.py exists to make impossible.
    if cite.namespace != ACT:
        return None
    # A correctly-formed citation to an Act we never ingested is still unanswerable. Section
    # numbers collide across Acts exactly as they do across an Act and its Rules.
    if cite.instrument not in CORPUS_INSTRUMENTS:
        return None

    record = section_by_number(cite.number)
    if record is None:
        return None

    defects = DEFECT_REGISTER.get(cite.number, ())
    confidence = record.get("index_confidence")
    if confidence not in ("high", "medium"):
        confidence = "low"
    if any(d in WITHHELD_DEFECTS for d in defects):
        confidence = "low"

    ref = LegalRef(ACT, COMPANIES_ACT_2013, cite.number, record["title"], record["section_id"])
    return Hit(
        ref=ref,
        section_id=record["section_id"],
        title=record["title"],
        route=cite.route,
        confidence=confidence,
        defects=defects,
        subsection=cite.subsection,
    )


def names_a_provision(query: str) -> bool:
    """Whether the query explicitly cites a provision, whether or not we can resolve it.

    The distinction matters at the composition layer. "rule 4" names a provision we do not hold;
    "related party transactions" names none. Both make resolve() return nothing, but they must be
    treated oppositely -- the first must abstain, the second may fall through to a text search.
    Without this, a keyword search silently answers a citation it was never asked to interpret.
    """
    if _scan(query):
        return True
    # _scan only accepts well-formed numbers (1-3 digits + optional letters), so "s.9999" parses
    # as nothing at all. Syntactically it is still plainly a citation, and letting it fall through
    # to a keyword search returns whatever sections happen to share its words -- an answer to a
    # question nobody asked. Detect the SYNTAX, not just the resolvable cases.
    return bool(_CITATION_SHAPE.search(query))


def resolve(query: str) -> list[Hit]:
    """The provisions this query names, in the order written. Empty when it names none we hold.

    An empty list is a real answer: the query cited nothing, cited an instrument we have not
    acquired, or cited a section the index could not map. None of those are improved by a guess.
    """
    return [h for h in (_to_hit(c) for c in _scan(query)) if h is not None]


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"[PASS] {label}")
        else:
            fail += 1; print(f"[FAIL] {label}")

    # --- the forms lawyers actually write, all naming the same provision ---
    baseline = resolve("s.173")
    check(len(baseline) == 1 and baseline[0].ref.number == "173", "s.173 -> one hit, s.173")
    expect_id = baseline[0].section_id
    check(expect_id == section_by_number("173")["section_id"],
          "section_id comes from section_index, not a private copy")

    for form in ("section 173", "Sec 173", "SECTION 173", "§173", "s 173", "s. 173",
                 "u/s 173", "what does s.173 require?"):
        hits = resolve(form)
        check(len(hits) == 1 and hits[0].section_id == expect_id, f"{form!r} -> s.173")

    check(resolve("s.173")[0].route == "exact-number", "bare number route is exact-number")
    check(resolve("s.173")[0].confidence == "high", "mapped MVP section is high confidence")
    check(resolve("s.173")[0].ref.key() == "ACT:COMPANIES_ACT_2013:S173", "hit carries a qualified key")
    check(resolve("s.173")[0].title.lower().startswith("meetings of board"), "title travels with the hit")

    # --- qualified key ---
    k = resolve("ACT:COMPANIES_ACT_2013:S173")
    check(len(k) == 1 and k[0].section_id == expect_id, "qualified key resolves to the same record")
    check(k[0].route == "qualified-key", "qualified key route recorded")
    check(len(resolve("ACT:COMPANIES_ACT_2013:S173 and s.173")) == 1,
          "the same section cited twice yields one hit")
    check(resolve("RULE:COMPANIES_MEETINGS_BOARD_POWERS_2014:R56") == [],
          "a well-formed RULE key still resolves to nothing -- no Rules corpus")
    check(resolve("ACT:SOME_OTHER_ACT_1956:S56") == [],
          "an Act we hold no text for resolves to nothing")

    # --- subsections resolve to the section, and say so ---
    sub = resolve("section 173(2)(a)")
    check(len(sub) == 1 and sub[0].section_id == expect_id, "s.173(2)(a) -> the s.173 record")
    check(sub[0].route == "subsection", "subsection route recorded")
    check(sub[0].subsection == "(2)(a)", "the subsection asked for is preserved verbatim")
    check(resolve("s 173(1)")[0].subsection == "(1)", "s 173(1) records (1)")
    check(resolve("s.173")[0].subsection == "", "a section-level citation records no subsection")

    # --- alphanumeric sections ---
    a3 = resolve("s.3A")
    check(len(a3) == 1 and a3[0].ref.number == "3A", "s.3A resolves as 3A, not 3")
    check(a3[0].section_id == section_by_number("3A")["section_id"], "s.3A -> its own record")
    check(len(resolve("s.3")) == 1 and resolve("s.3")[0].ref.number == "3", "s.3 is a different hit")

    # --- unmapped / omitted / unknown: no Hit, never a fabricated one ---
    check(any(c.number == "378ZA" for c in _scan("s.378ZA")), "s.378ZA parses as 378ZA")
    check(resolve("s.378ZA") == [], "unmapped s.378ZA yields no hit rather than a wrong one")
    check(section_by_number("11") is None and resolve("s.11") == [],
          "omitted s.11 yields no hit")
    check(resolve("s.999") == [], "unknown section number yields no hit")
    check(resolve("") == [] and resolve("what are the rules on board meetings") == [],
          "a query naming no provision yields no hits")

    # --- ABSTENTION: a Rules citation is never answered with an Act section ---
    check(resolve("rule 4") == [], "'rule 4' abstains -- no Rules corpus exists")
    check(resolve("r.4") == [], "'r.4' abstains")
    check(resolve("r 56") == [], "'r 56' abstains despite the Act having an s.56")
    check(section_by_number("56") is not None, "...and s.56 does exist, so that was a real refusal")
    mixed = resolve("s.173 read with rule 4")
    check([h.ref.number for h in mixed] == ["173"], "mixed query returns only what we hold")

    # --- multiple and ranges ---
    two = resolve("sections 173 and 174")
    check([h.ref.number for h in two] == ["173", "174"], "'sections 173 and 174' -> both, in order")
    check(len(resolve("ss. 173, 174 and 175")) == 3, "comma-and enumeration -> three hits")
    rng = resolve("ss. 173-175")
    check([h.ref.number for h in rng] == ["173", "174", "175"], "'ss. 173-175' expands inclusively")
    check(rng[1].route == "range", "an expanded member is routed as range")
    check(rng[0].route == "exact-number" and rng[2].route == "exact-number",
          "both named endpoints keep the exact route -- only the interior is inferred")
    check([h.ref.number for h in resolve("sections 173 to 175")] == ["173", "174", "175"],
          "'173 to 175' expands too")
    wide = [h.ref.number for h in resolve("ss. 1-400")]
    check("1" in wide and "400" in wide and "200" not in wide,
          "an implausibly wide range keeps its endpoints and invents no middle")
    check(len(resolve("§§ 173, 179")) == 2, "double-section sign enumerates")
    check([h.ref.number for h in resolve("s.173 and 174")] == ["173", "174"],
          "continuation works after a singular prefix, as lawyers write it")
    # A number a word is attached to was counting, not citing. Both readings must be kept apart:
    # a spurious provision in an evidence pack is a lawyer reading law nobody cited.
    check([h.ref.number for h in resolve("section 173 and 5 directors")] == ["173"],
          "'5 directors' is a quantity, not a citation")
    check([h.ref.number for h in resolve("section 96 and 30 days notice")] == ["96"],
          "'30 days' is a quantity, not a citation")
    check([h.ref.number for h in resolve("board of 5 directors under section 149")] == ["149"],
          "a leading quantity does not become a citation")
    check([h.ref.number for h in resolve("ss. 173, 174 and 175")] == ["173", "174", "175"],
          "genuine enumeration survives the quantity rule")

    # --- DEFECTS: docs/SOURCE_DEFECTS.md must reach the caller ---
    check(resolve("s.1")[0].defects == ("SD-001",), "s.1 carries SD-001 (editorial 'To be deleted')")
    for num in ("16", "124", "76A", "329"):
        hits = resolve(f"s.{num}")
        check(len(hits) == 1 and hits[0].defects == ("SD-002",),
              f"s.{num} carries SD-002 (pre-amendment corpus text)")
    check(all(resolve(f"s.{n}")[0].confidence == "low" for n in ("16", "124", "76A", "329")),
          "SD-002 sections are low confidence -- SOURCE_DEFECTS says they may not be served")
    check(resolve("ACT:COMPANIES_ACT_2013:S16")[0].defects == ("SD-002",),
          "defects attach by section, not by which route found it")
    check(resolve("s.16(3)")[0].defects == ("SD-002",), "a subsection citation carries them too")
    check(resolve("s.173")[0].defects == (), "a clean section carries no defect id")
    check(set(DEFECT_REGISTER) == {"1", "16", "124", "76A", "329"},
          "the register holds exactly the five sections SOURCE_DEFECTS.md confirms")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
