"""
Parse the Companies (Meetings of Board and its Powers) Rules, 2014 into addressable records.

Structure only. This script extracts what the document says and where it says it; it draws no
legal conclusion, and every record it emits is UNREVIEWED. The Rules are a source, not an answer.

Two things it is careful about:

1. **Page provenance.** Every rule records the page it starts and ends on, so a reviewer can open
   the gazette and check it. A legal record that cannot be traced back to a page is not evidence.

2. **Act links are graded, not asserted.** The Rules' preamble names the sections they are made
   under; that is MADE_UNDER and it is quotable. A rule that mentions "section 185" in its own
   text REFERS_TO it. Nothing here infers that a rule implements a section it does not name --
   "the Act" alone is not a section reference.

Run: python3 scripts/parse_board_rules.py
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from checker.pdf_pages import extract_pages  # noqa: E402

PDF = ROOT / "corpus/sources/companies_meetings_board_powers_rules_2014.pdf"
OUT = ROOT / "corpus/rules/board_powers_2014.json"
REPORT = ROOT / "reports/board_rules_review.md"

INSTRUMENT_ID = "COMPANIES_MEETINGS_BOARD_POWERS_2014"
ARTIFACT_SHA = "b8b2e01b3d151ee038215c81d4fb10d802e4b84b8762ac385c2347417597167c"

# "3. Meetings of Board through video conferencing ... .-"  The heading runs to the ".-" dash that
# opens the body. It may itself contain full stops ("10. Loans to Director etc. under section
# 185.-"), so the terminator is the dash, not the first period.
_HEADING = re.compile(r"(?<![\d.])(\d{1,2})\s*\.\s*(?:\(1\)\s*)?([A-Z][^\n]{5,160}?)\s*\.\s*[-–—]")
# The preamble names the enabling sections. This is the only MADE_UNDER evidence in the document.
_PREAMBLE = re.compile(
    r"In exercise of powers conferred under (.{20,400}?) of\s*t\s?he\s+Companies\s+Act,\s*2013",
    re.I | re.S)
_SECTION_REF = re.compile(r"s\s?e\s?c\s?t\s?i\s?o\s?n\s+(\d{1,3}[A-Z]{0,2})", re.I)
_SUBRULE = re.compile(r"\((\d{1,2})\)")


def despace(s: str) -> str:
    """Collapse whitespace and rejoin ONLY single-letter fragments.

    The gazette's text layer breaks words at line-wrap points: "Board an d its Powers",
    "throug h video", "percen t", "secti on 188". It is tempting to repair these generally, and
    the first attempt here did -- and turned "the Act or in the said Rules" into "the Actor in the
    said Rules". Silently altering statutory wording is worse than leaving it visibly broken,
    because the damage is invisible downstream.

    So this joins only a stranded single letter to the word before it, which is unambiguous
    ("an"+"d", "throug"+"h"), and never touches anything else. "na me" therefore stays split.
    That is deliberate: `text_raw` is the unmodified extraction, this is a reading aid, and
    `split_words` in the record tells a reviewer how much is still broken.

    "a" and "I" are excluded -- they are real one-letter words.
    """
    s = re.sub(r"\s+", " ", s).strip()
    return re.sub(r"\b([A-Za-z]{2,})\s+(?![aAI]\b)([b-hj-zB-HJ-Z])\b", r"\1\2", s)


# Section references survive the same splitting ("secti on 188"), so the matcher tolerates a space
# inside the word. Matching the number is what matters; the label just has to be recognisable.
_SPLITTABLE_SECTION = re.compile(r"s\s?e\s?c\s?t\s?i\s?o\s?n\s+(\d{1,3}[A-Z]{0,2})", re.I)


# A trailing fragment is extraction damage only when rejoining it produces a token
# the document itself uses elsewhere. No dictionary, no hand-written word list: the
# document is its own evidence, which is the same principle as corroborating a span
# against the amending Act rather than against our own confidence.
def count_split_words(s: str, vocabulary: frozenset[str] | None = None) -> int:
    """Fragments that are extraction damage, not English.

    **This counted ordinary prose until 25-09-2026**, and the correction took two
    passes, both recorded because each was wrong in an instructive way.

    The original rule was "any word followed by a short word", which matches "with
    the", "convening and", "if any". It reported 299 split words in rule 3, whose
    text reads "A company shall comply with the following procedure..." -- clean
    English. That false signal is part of why this instrument's rules sat in
    HUMAN_REVIEW_PENDING looking unreadable, and it is what a reviewer would have
    been sent in to proofread.

    The first correction added a list of real short words. Better, and still wrong:
    it kept flagging "take due", "income tax", "think fit", "notice pay" -- the list
    can never be finished, and an unfinished list fails in the direction of crying
    wolf.

    The rule now asks the document. `head + tail` is a split only if that joined
    token appears SOMEWHERE ELSE in the instrument as a word in its own right. "an"
    + "d" -> "and", which the document uses constantly, so it is damage. "take" +
    "due" -> "takedue", which appears nowhere, so it is two words.

    Rejoining is NOT performed here. This counts; `despace` does the only repair this
    file makes, and only for stranded single letters. CLAUDE.md's rule against
    repairing a source stands, and the count is the unresolved marker a reviewer sees.
    """
    if vocabulary is None:
        vocabulary = frozenset(w.lower() for w in re.findall(r"[A-Za-z]{3,}", s))
    # Adjacent PAIRS, not a consuming regex. A regex match eats its head, so in
    # "own na me" it pairs "own"+"na", decides that is not a word, and never looks at
    # "na"+"me" -- the actual split. Candidates overlap, so the scan must too.
    tokens = re.findall(r"[A-Za-z]+", s)
    n = 0
    for head, tail in zip(tokens, tokens[1:]):
        if len(head) >= 2 and 1 <= len(tail) <= 3 and tail.islower():
            if (head + tail).lower() in vocabulary:
                n += 1
    return n


# Text rendered in a legacy non-Unicode Hindi font (Kruti Dev and relatives) extracts
# as Latin letters that spell nothing: "Hkkjr dk". It is not a split word and the
# counter above must not be asked to find it -- a different defect needs a different
# name, or one number ends up meaning two things.
_LEGACY_FONT = re.compile(r"\b(?=[a-zA-Z]{4,}\b)(?:[bcdfghjklmnpqrstvwxyzBCDFGHJKLMNPQRSTVWXYZ]"
                          r"[a-zA-Z]*){1}\b")


def count_legacy_font_runs(s: str) -> int:
    """Tokens that look like a legacy Hindi font decoded as Latin.

    Heuristic and labelled as one: 4+ letters with no vowel at all. "Hkkjr", "dk".
    English has almost no such tokens; this document has them wherever the Hindi
    half was set in a pre-Unicode font.
    """
    return sum(1 for w in re.findall(r"\b[A-Za-z]{4,}\b", s)
               if not re.search(r"[aeiouAEIOU]", w))


@dataclass
class ActLink:
    to_section: str
    relation: str          # MADE_UNDER | REFERS_TO
    evidence_text: str
    confidence: str
    review_status: str = "PENDING_HUMAN_REVIEW"


@dataclass
class RuleRecord:
    rule_id: str
    instrument_id: str
    rule_number: str
    heading: str
    text_raw: str
    text_reading: str
    page_start: int
    page_end: int
    sub_rules: list[str]
    act_links: list[ActLink] = field(default_factory=list)
    status: str = "UNREVIEWED"
    source_artifact_sha256: str = ARTIFACT_SHA
    warnings: list[str] = field(default_factory=list)


def enabling_sections(text: str) -> tuple[list[str], str]:
    """The sections the Rules say they are made under, and the sentence saying so."""
    m = _PREAMBLE.search(text)
    if not m:
        return [], ""
    clause = despace(m.group(1))
    return sorted({s for s in _SECTION_REF.findall(clause)} |
                  set(re.findall(r"\b(\d{2,3})\b", clause)), key=int), clause


def parse(pages: list[str]) -> tuple[list[RuleRecord], list[str], str]:
    # Offsets let a match be mapped back to the page it came from.
    joined, bounds, pos = "", [], 0
    for i, p in enumerate(pages, start=1):
        joined += p + "\n"
        bounds.append((pos, len(joined), i))
        pos = len(joined)

    def page_of(off: int) -> int:
        for lo, hi, n in bounds:
            if lo <= off < hi:
                return n
        return bounds[-1][2]

    enabling, clause = enabling_sections(joined)

    hits = [(m.start(), m.end(), m.group(1), despace(m.group(2))) for m in _HEADING.finditer(joined)]
    # Rule numbers run 1..N once, in order. A repeat is the number appearing inside body text (a
    # cross-reference), not a new rule, so the first occurrence in ascending order wins.
    seen, ordered = set(), []
    expect = 1
    for start, end, num, heading in hits:
        if num in seen or int(num) != expect:
            continue
        seen.add(num); ordered.append((start, end, num, heading)); expect += 1

    records: list[RuleRecord] = []
    for i, (start, end, num, heading) in enumerate(ordered):
        stop = ordered[i + 1][0] if i + 1 < len(ordered) else len(joined)
        raw = joined[end:stop]
        reading = despace(raw)
        links: list[ActLink] = []
        if num in ():  # placeholder, no per-rule MADE_UNDER without evidence
            pass
        for sec in sorted(set(_SECTION_REF.findall(reading + " " + heading)), key=lambda x: int(re.sub(r"\D", "", x) or 0)):
            snippet = ""
            sm = re.search(r"[^.]{0,90}section\s+" + re.escape(sec) + r"[^.]{0,60}", reading, re.I)
            if sm:
                snippet = sm.group(0).strip()
            # "section 12" in a rule that also numbers its own sub-rules is ambiguous without
            # reading it; confidence reflects whether the surrounding words were captured.
            conf = "HIGH" if snippet else "LOW"
            links.append(ActLink(f"ACT:COMPANIES_ACT_2013:S{sec}", "REFERS_TO", snippet, conf))
        warnings = []
        # The last rule's body runs to end-of-document, so it swallows the Annexure and forms.
        # The same shape caused s.470 to score 0.004 in the corpus cross-validation. Flag it
        # rather than guessing where the operative text stops.
        if i == len(ordered) - 1 and re.search(r"ANNEXURE|Form\s+No\.|FORM\s+MBP", reading, re.I):
            warnings.append("body runs to end-of-document and contains Annexure/Form matter -- "
                            "the operative text ends earlier; a reviewer must set the boundary")
        splits = count_split_words(reading)
        if splits:
            warnings.append(f"{splits} word(s) still split by extraction -- read text_raw against "
                            f"pages {page_of(start)}-{page_of(max(start, stop - 1))}")
        if len(reading) < 120:
            warnings.append("very short body -- check the heading regex did not split a rule")
        records.append(RuleRecord(
            rule_id=f"RULE:{INSTRUMENT_ID}:R{num}",
            instrument_id=INSTRUMENT_ID,
            rule_number=num,
            heading=heading,
            text_raw=raw.strip(),
            text_reading=reading,
            page_start=page_of(start),
            page_end=page_of(max(start, stop - 1)),
            sub_rules=sorted(set(_SUBRULE.findall(reading[:4000])), key=int)[:20],
            act_links=links,
            warnings=warnings,
        ))
    return records, enabling, clause


def main() -> None:
    if not PDF.is_file():
        print(f"missing {PDF}"); raise SystemExit(2)
    pages = extract_pages(PDF)
    records, enabling, clause = parse(pages)

    made_under = [ActLink(f"ACT:COMPANIES_ACT_2013:S{s}", "MADE_UNDER", clause, "HIGH")
                  for s in enabling]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "instrument_id": INSTRUMENT_ID,
        "short_title": "The Companies (Meetings of Board and its Powers) Rules, 2014",
        "gazette": "G.S.R. 240(E)",
        "gazette_date": "2014-03-31",
        "source_artifact": "corpus/sources/companies_meetings_board_powers_rules_2014.pdf",
        "source_artifact_sha256": ARTIFACT_SHA,
        "extractor": "checker/pdf_pages.py",
        "pages": len(pages),
        "status": "UNREVIEWED",
        "production_usable": False,
        "made_under": [asdict(l) for l in made_under],
        "rules": [asdict(r) for r in records],
    }, indent=2, ensure_ascii=False))

    lines = [
        "# Review — Companies (Meetings of Board and its Powers) Rules, 2014", "",
        "**Nothing here is reviewed.** Every record is `UNREVIEWED` and the instrument is",
        "`production_usable: false`. This report exists so a human can check the extraction against",
        f"the gazette, page by page.", "",
        f"- Artifact: `corpus/sources/companies_meetings_board_powers_rules_2014.pdf`",
        f"- sha256: `{ARTIFACT_SHA[:16]}…`",
        f"- Pages: {len(pages)}   Rules parsed: {len(records)}", "",
        "## Made under (from the Rules' own preamble)", "",
        f"> {clause}" if clause else "> NOT FOUND — the preamble did not parse.", "",
        f"Sections: {', '.join('s.' + s for s in enabling) or 'none'}", "",
        "## Rules", "",
        "| Rule | Heading | Pages | Sub-rules | Sections referred to |",
        "|---|---|---|---|---|",
    ]
    for r in records:
        refs = ", ".join(sorted({l.to_section.split(":S")[1] for l in r.act_links},
                                key=lambda x: int(re.sub(r"\D", "", x) or 0))) or "—"
        lines.append(f"| r.{r.rule_number} | {r.heading[:58]} | {r.page_start}–{r.page_end} "
                     f"| {len(r.sub_rules)} | {refs} |")
    warned = [r for r in records if r.warnings]
    lines += ["", f"## Warnings ({len(warned)})", ""]
    lines += [f"- r.{r.rule_number}: {'; '.join(r.warnings)}" for r in warned] or ["- none"]
    lines += ["", "## What a reviewer must check", "",
              "1. Every rule number 1..N is present and none is missing.",
              "2. Each heading matches the gazette at the stated page.",
              "3. `text_reading` has not altered meaning — `text_raw` is the unmodified extraction.",
              "4. The made-under list matches the preamble exactly.",
              "5. `REFERS_TO` links point at sections the rule actually names."]
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n")

    print(f"pages           : {len(pages)}")
    print(f"rules parsed    : {len(records)}  ({', '.join('r.'+r.rule_number for r in records)})")
    print(f"made under      : {', '.join('s.'+s for s in enabling) or 'NONE'}")
    print(f"rules with refs : {sum(1 for r in records if r.act_links)}")
    print(f"warnings        : {sum(len(r.warnings) for r in records)}")
    print(f"written         : {OUT.relative_to(ROOT)}  |  {REPORT.relative_to(ROOT)}")


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"[PASS] {label}")
        else:
            fail += 1; print(f"[FAIL] {label}")

    check(despace("Board an d its Powers") == "Board and its Powers",
          "rejoins a stranded single letter")
    check(despace("throug h video") == "through video", "rejoins 'throug h'")
    check(despace("the Act or in the said Rules") == "the Act or in the said Rules",
          "does NOT corrupt correctly-spaced text ('Act or' must not become 'Actor')")
    check(despace("in its own na me") == "in its own na me",
          "leaves an ambiguous two-letter split alone rather than guessing")
    check(despace("such a company") == "such a company", "'a' is a real word, never joined")
    # The detector asks the document, so the fixture must supply the evidence: "name"
    # appears as a word, which is what makes "na me" a split rather than two words.
    check(count_split_words("the name on the register, in its own na me.") >= 1,
          "a fragment is counted when rejoining it makes a word the text itself uses")
    # The regression that mattered: this counted ordinary English for months.
    check(count_split_words("A company shall comply with the following procedure, "
                            "for convening and conducting the Board meetings.") == 0,
          "ordinary prose counts zero -- 'with the', 'convening and' are not damage")
    check(count_split_words("the annual turnover as mentioned in clause (a).") == 0,
          "'turnover as' is English unless the text elsewhere uses 'turnoveras'")
    check(count_legacy_font_runs("Hkkjr dk jkti=") >= 1,
          "legacy-font Hindi is counted separately, not as a split word")
    check(count_legacy_font_runs("the company shall maintain a register") == 0,
          "English is not mistaken for legacy-font Hindi")

    secs, clause = enabling_sections(
        "In exercise of powers conferred under sections 173, 175 and section 191 read with "
        "section 469 of the Companies Act, 2013 and in supersession")
    check(secs == ["173", "175", "191", "469"], f"preamble sections parsed: {secs}")
    check("read with" in clause, "the enabling clause is captured verbatim for quoting")

    if not OUT.is_file():
        print("[SKIP] parsed corpus not present -- run this script without --test first")
        print(f"\n{ok}/{ok + fail} passed")
        return

    d = json.loads(OUT.read_text())
    nums = [r["rule_number"] for r in d["rules"]]
    check(nums == [str(i) for i in range(1, len(nums) + 1)],
          f"rule numbers are consecutive 1..{len(nums)} with no gap")
    # 16, not 15. The old pypdf reader merged rules 15 and 16 into one 13,322-char
    # body -- which is why that record carried a "runs to end-of-document" warning --
    # and rule 16, "Register of contracts or arrangements in which directors are
    # interested", was absent from the corpus entirely. It is a real rule of this
    # instrument. Changing the reader recovered it; this number records that.
    check(len(nums) == 16, f"16 rules parsed (got {len(nums)})")
    r16 = [r for r in d["rules"] if r["rule_number"] == "16"]
    check(bool(r16) and "Register of contracts" in r16[0]["heading"],
          "rule 16 is the register of contracts in which directors are interested")
    check(all(r["page_start"] >= 1 and r["page_end"] >= r["page_start"] for r in d["rules"]),
          "every rule carries a sane page range")
    check(all(r["status"] == "UNREVIEWED" for r in d["rules"]), "every rule is UNREVIEWED")
    check(d["production_usable"] is False, "the instrument is not production-usable")
    check(all(l["review_status"] == "PENDING_HUMAN_REVIEW"
              for r in d["rules"] for l in r["act_links"]),
          "every Act link is pending human review")
    check({l["relation"] for l in d["made_under"]} == {"MADE_UNDER"},
          "preamble links are MADE_UNDER")
    check(all(l["relation"] == "REFERS_TO" for r in d["rules"] for l in r["act_links"]),
          "in-text links are only ever REFERS_TO -- nothing infers IMPLEMENTS")

    # Every enabling section must exist in the Act corpus, or the link is to nothing.
    from checker.legal_retrieval import resolve
    unresolved = [l["to_section"] for l in d["made_under"]
                  if not resolve("s." + l["to_section"].split(":S")[1])]
    check(not unresolved, f"every made-under section resolves in the Act corpus ({unresolved})")

    # THE GATE. Rules now exist on disk. They must still not be servable, because nobody has read
    # them. If this ever fails, someone has wired the Rules into retrieval without the review step
    # -- which is precisely the failure this project exists to prevent.
    from checker.retrieve import retrieve, ROUTE_ABSTAIN
    for q in ("rule 4", "r.15", "RULE:COMPANIES_MEETINGS_BOARD_POWERS_2014:R15"):
        pack, route = retrieve(q)
        check(route == ROUTE_ABSTAIN and not pack.to_dict()["provisions"],
              f"{q!r} still abstains -- Rules are parsed but UNREVIEWED")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        _test()
    else:
        main()
