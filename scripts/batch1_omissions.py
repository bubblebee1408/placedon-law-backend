#!/usr/bin/env python3
"""Batch 1 — ten omission spans against amending Acts we hold. Report, then stop.

    python3 scripts/batch1_omissions.py          # the batch report
    python3 scripts/batch1_omissions.py --test   # self-test, no network

An omission is the one case a parser fix can never reach. When text is omitted
from a consolidation the words are simply gone: India Code shows a marker where
they used to be and nothing else. The prior wording exists in exactly one place —
the Act that omitted it — which is why these, and only these, are worth the
witness work.

## Nothing here is promoted

Every item ends `human_review: PENDING`. A status of EXACT means the evidence
*supports* the reconstruction; it does not mean the reconstruction has been
accepted. Promotion is a separate, human act, and this script cannot perform it.

## What EXACT requires

All of: the amending Act located; a clause naming this section; the operation
confirmed as an omission; the omitted text quoted in that clause; and the
commencement date agreeing with India Code's footnote. Any disagreement is
CONFLICT rather than a silent preference for one source. Anything unestablished
is PARTIAL or ABSTAIN.

The status is not a judgement about the law. It is a statement about how much of
the record we could independently corroborate.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from checker.corroborate import WITNESS_ACTS, Corroborator, normalise  # noqa: E402
from checker.span_inventory import batch_candidates  # noqa: E402

OUT = Path("corpus/benchmark/batch1_omissions.json")

EXACT = "EXACT"
PARTIAL = "PARTIAL"
ABSTAIN = "ABSTAIN"
CONFLICT = "CONFLICT"

# "omitted by <instrument>, s. <n>" / "omitted by s. 15, ibid." — the clause in
# an amending Act that performs an omission, and the section it names.
_OMIT_CLAUSE = re.compile(
    r"(?:^|[.;])\s*(\d+)\.\s*(?:Omission|Amendment)\s+of\s+section\s+([\dA-Z]+)[.\s]",
    re.I | re.M)
_OMIT_VERB = re.compile(r"\bshall\s+be\s+omitted\b|\bomitted\b", re.I)
_QUOTED = re.compile(r'[""“"]([^""”"]{3,400})[""”"]')

# Language belonging to the amending Act's own machinery. If it appears inside
# what we extracted as "the omitted words", we captured the clause's scaffolding
# rather than statutory text — s.197 produced
# "shall be omitted; (f) after sub-section (15), the following sub-sections
# shall be inserted, namely:—" and it was scored EXACT.
_OPERATIVE = re.compile(
    r"shall\s+be\s+(?:omitted|inserted|substituted)|following\s+sub-?sections?"
    r"|namely\s*[:—-]|the\s+principal\s+Act", re.I)


@dataclass
class Item:
    section: str
    subsection: str
    marker: int
    operation: str
    amending_act: str
    commencement_date: str
    commencement_type: str
    commencement_source: str
    witness_url: str | None = None
    witness_clause: str | None = None
    witness_sha256: str | None = None
    india_code_state: str = ""
    reconstructed_before: str | None = None
    reconstructed_after: str | None = None
    status: str = ABSTAIN
    reason: str = ""
    missing_evidence: str = ""
    next_source: str = ""
    needs_legal_interpretation: bool = False
    human_review: str = "PENDING"
    reason_prefix: str = ""


def _sha(s: str) -> str:
    return "sha256:" + hashlib.sha256(s.encode("utf-8")).hexdigest()


def _act_text(c: Corroborator, instrument: str) -> tuple[str, str] | None:
    return c.witness_text(instrument)


def _clause_number(text: str, section: str) -> int | None:
    """The amending Act's own section number that amends this principal section.

    Needed because a commencement notification lists the AMENDING Act's sections,
    not the principal Act's. s.121 is amended by clause 31; asking a notification
    about "121" would find nothing and wrongly read as uncommenced.
    """
    m = re.search(rf"(\d+)\.\s*(?:Omission|Amendment)\s+of\s+section\s+"
                  rf"{re.escape(section)}\b", text, re.I)
    return int(m.group(1)) if m else None


def _clause_for_section(text: str, section: str) -> str | None:
    """The amending Act's clause dealing with this section, if it names one."""
    for m in re.finditer(
            rf"(\d+)\.\s*(?:Omission|Amendment)\s+of\s+section\s+{re.escape(section)}\b",
            text, re.I):
        # Take up to the next numbered clause, so the extract is one operation.
        rest = text[m.start():m.start() + 2500]
        nxt = re.search(r"\.\s+\d+\.\s+(?:Omission|Amendment|Insertion|Substitution)\s+of",
                        rest[10:])
        return (rest[:nxt.start() + 10] if nxt else rest).strip()
    return None


# An omission, bound to the verb that performs it. The quote must be governed by
# "shall be omitted" — taking the longest quoted string in a clause regardless of
# its operation made s.161 read as a CONFLICT, because the longest quote there
# belongs to an INSERTION and is therefore still present in the current text.
_OMISSION_OP = re.compile(
    r"(?:the\s+(?:words?|figures?|brackets?|letters?)"
    r"(?:\s+and\s+(?:words?|figures?|brackets?|letters?))*\s*)"
    r"[\"“\'']([^\"”\'']{3,400})[\"”\'']"
    r"[^\".;]{0,60}?shall\s+be\s+omitted",
    re.I | re.S)

# "in sub-section (2)", "in the second proviso" — the path an operation sits on.
_SUBSEC = re.compile(r"in\s+sub-?section\s*\((\d+[A-Z]?)\)", re.I)


@dataclass
class Omission:
    text: str
    subsection: str
    at: int


def omissions_in(clause: str) -> list[Omission]:
    """Every omission the clause performs, each bound to its own verb.

    Nested items — (i) in sub-section (1),— (a) ... omitted; (b) ... omitted —
    are read individually. The sub-section attributed to an omission is the
    nearest one appearing before it, which is how the drafting reads.
    """
    out: list[Omission] = []
    for m in _OMISSION_OP.finditer(clause):
        subs = [s for s in _SUBSEC.finditer(clause) if s.start() < m.start()]
        out.append(Omission(text=m.group(1).strip(),
                            subsection=subs[-1].group(1) if subs else "(unstated)",
                            at=m.start()))
    return out


def build(offline: bool = False) -> list[Item]:
    from checker.section_index import section_by_number
    cands = batch_candidates(10)
    c = None if offline else Corroborator()
    items: list[Item] = []

    for s in cands:
        rec = section_by_number(s.section)
        html = rec.get("content") or "" if rec else ""
        it = Item(
            section=s.section, subsection="(not isolated)", marker=s.marker,
            operation=s.operation, amending_act=s.instrument or "",
            commencement_date=s.wef or "",
            # India Code's footnote states the w.e.f. date. Whether it came from
            # the Act itself or a separate commencement notification is not
            # recorded there, so the type is not asserted.
            commencement_type="UNKNOWN",
            commencement_source="india-code-footnote",
            india_code_state=(
                "marker present, no bracketed span: text omitted from the "
                "consolidation"),
        )

        if offline or c is None:
            it.status = ABSTAIN
            it.reason = "offline: no witness fetched"
            it.missing_evidence = "amending Act text"
            it.next_source = WITNESS_ACTS.get(it.amending_act, "unknown")
            items.append(it)
            continue

        w = _act_text(c, it.amending_act)
        if w is None:
            it.status = ABSTAIN
            it.reason = f"no copy of {it.amending_act} is held"
            it.missing_evidence = "amending Act text"
            it.next_source = "official Gazette or MCA (MCA currently returns 403)"
            items.append(it)
            continue

        text, url = w
        it.witness_url = url
        clause = _clause_for_section(text, it.section)
        if clause is None:
            it.status = ABSTAIN
            it.reason = (f"{it.amending_act} names no clause for s.{it.section}; "
                         "the omission may have been effected by a Schedule or a "
                         "consequential provision")
            it.missing_evidence = f"clause of {it.amending_act} affecting s.{it.section}"
            it.next_source = "the Act's Schedules"
            it.needs_legal_interpretation = True
            items.append(it)
            continue

        it.witness_clause = clause[:600]
        it.witness_sha256 = _sha(clause)

        if not _OMIT_VERB.search(clause):
            it.status = CONFLICT
            it.reason = ("India Code records an omission; the Act's clause for this "
                         "section does not use omission language")
            it.needs_legal_interpretation = True
            items.append(it)
            continue

        omits = omissions_in(clause)
        if not omits:
            it.status = PARTIAL
            it.reason = ("the Act's clause for this section performs no omission "
                         "whose words it quotes, so the earlier text cannot be "
                         "reproduced")
            it.missing_evidence = "an omission operation with quoted words"
            it.next_source = "the Act as originally enacted (Gazette, 30 Aug 2013)"
            items.append(it)
            continue

        # Determinacy. A marker can be tied to an omission only when the clause
        # leaves no choice: either it performs exactly one omission, or it
        # performs several that omit identical words — which the Act does do, as
        # s.137 omits "within the time specified under section 403" twice.
        markers_here = sum(1 for x in cands if x.section == s.section)
        distinct = {normalise(o.text) for o in omits}
        if len(omits) > 1 and len(distinct) > 1:
            it.status = PARTIAL
            it.reason = (f"the clause performs {len(omits)} distinct omissions "
                         f"({', '.join(sorted(o.subsection for o in omits))}); "
                         "nothing in the record ties this marker to one of them")
            it.missing_evidence = "marker-to-operation mapping"
            it.next_source = "the pre-amendment text, to match each omission to its place"
            it.needs_legal_interpretation = True
            items.append(it)
            continue

        chosen = omits[0]
        it.subsection = chosen.subsection
        if len(omits) > 1:
            it.reason_prefix = (f"the clause omits the same words {len(omits)} times "
                                f"and India Code carries {markers_here} marker(s); ")

        longest = chosen.text
        # The presence test only means something for distinctive wording. s.2's
        # clause omits the single word "and", which naturally still occurs
        # throughout the section — the test reported a CONFLICT between two
        # sources that do not in fact disagree. Below this threshold the check
        # carries no information and must not be run.
        if len(longest.split()) < 4 or len(longest) < 20:
            it.status = PARTIAL
            it.reason = (f"the Act omits {longest!r} from sub-section "
                         f"({chosen.subsection}), but the wording is too short to "
                         "test against the current consolidation: its presence "
                         "there would prove nothing")
            it.missing_evidence = "distinctive wording, or the pre-amendment text"
            it.next_source = "the Act as originally enacted (Gazette, 30 Aug 2013)"
            items.append(it)
            continue

        if normalise(longest) in normalise(html):
            it.status = CONFLICT
            it.reason = ("the Act quotes this text as omitted, but it is still "
                         "present in India Code's current content")
            it.needs_legal_interpretation = True
            items.append(it)
            continue

        if _OPERATIVE.search(longest):
            it.status = PARTIAL
            it.reason = ("the extracted text contains the amending Act's own "
                         "operative language, so it is clause scaffolding rather "
                         "than the omitted provision")
            it.missing_evidence = "the omitted words, isolated from the clause"
            it.next_source = "the clause read against the pre-amendment text"
            it.needs_legal_interpretation = True
            items.append(it)
            continue

        # Strict EXACT requires commencement provenance. The notification lists
        # the AMENDING Act's sections, so the clause number is what to ask about.
        from checker import commencement as cm
        cno = _clause_number(text, it.section)
        prov = cm.check(cno, it.commencement_date) if cno else None
        if prov is not None and prov.notification is not None:
            it.commencement_source = prov.notification.locator
            it.commencement_type = "NOTIFICATION"
        if prov is None or not prov.confirmed:
            it.status = PARTIAL
            it.reconstructed_before = longest
            it.reason = (
                f"text and clause identity are established (amending Act s.{cno}, "
                f"sub-section ({chosen.subsection})), but commencement is not: "
                + (prov.note if prov else "the amending clause number is unknown"))
            it.missing_evidence = (
                f"a notification bringing amending-Act s.{cno} into force")
            it.next_source = "the remaining commencement notifications in the series"
            it.commencement_type = "UNKNOWN" if prov is None or not prov.notification \
                else it.commencement_type
            items.append(it)
            continue

        it.reconstructed_before = longest
        it.reconstructed_after = "(text omitted)"
        it.status = EXACT
        it.reason = (getattr(it, "reason_prefix", "") +
                     f"the Act omits these words from sub-section ({chosen.subsection}) "
                     "of this section; they are absent from the current "
                     f"consolidation as expected; and {prov.note}")
        items.append(it)

    # A section may carry several omissions in one clause. This code locates the
    # clause by section number alone, so it cannot tell which marker corresponds
    # to which omission — and it handed markers 8 and 9 of s.2 the same prior
    # text. Identical text across distinct markers means the mapping is
    # unresolved, and neither may be EXACT.
    seen: dict[tuple[str, str], list[Item]] = {}
    for i in items:
        if i.status == EXACT and i.reconstructed_before:
            seen.setdefault((i.section, normalise(i.reconstructed_before)), []).append(i)
    for (sec, _), group in seen.items():
        if len(group) < 2:
            continue
        for i in group:
            i.status = PARTIAL
            i.reason = (f"{len(group)} markers in s.{sec} resolved to identical text; "
                        "the clause names the section but this code cannot map a "
                        "marker to a specific omission within it")
            i.missing_evidence = "marker-to-omission mapping within the clause"
            i.next_source = "the clause's sub-section and clause references"
            i.needs_legal_interpretation = True
            i.reconstructed_before = None
            i.reconstructed_after = None

    return items


def report(items: list[Item]) -> str:
    from collections import Counter
    st = Counter(i.status for i in items)
    acts = sorted({i.amending_act for i in items})
    lines = [
        "", "=" * 70, "BATCH 1 / 12 — omission spans against held amending Acts",
        "=" * 70, "",
        f"Input spans            : {len(items)}",
        f"EXACT                  : {st[EXACT]}",
        f"PARTIAL                : {st[PARTIAL]}",
        f"ABSTAIN                : {st[ABSTAIN]}",
        f"CONFLICT               : {st[CONFLICT]}",
        f"Human review required  : {len(items)}",
        f"Official Acts used     : {', '.join(acts)}",
        "",
    ]
    for i in items:
        lines.append(f"--- s.{i.section} m{i.marker}  [{i.status}]")
        lines.append(f"    operation        : {i.operation}")
        lines.append(f"    amending Act     : {i.amending_act}")
        lines.append(f"    commencement     : {i.commencement_date} "
                     f"({i.commencement_type}, per {i.commencement_source})")
        if i.witness_url:
            lines.append(f"    witness          : {i.witness_url}")
        if i.witness_sha256:
            lines.append(f"    clause sha256    : {i.witness_sha256[:30]}...")
        if i.status == EXACT:
            lines.append(f"    before           : {(i.reconstructed_before or '')[:150]}")
            lines.append(f"    after            : {i.reconstructed_after}")
        else:
            lines.append(f"    missing evidence : {i.missing_evidence or '-'}")
            lines.append(f"    next source      : {i.next_source or '-'}")
            lines.append(f"    legal interp.    : "
                         f"{'REQUIRED' if i.needs_legal_interpretation else 'no'}")
        lines.append(f"    reason           : {i.reason}")
        lines.append(f"    human_review     : {i.human_review}")
    lines += ["", "Nothing above is promoted. EXACT means the evidence supports the",
              "reconstruction, not that it has been accepted.", ""]
    return "\n".join(lines)


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

    print("batch1_omissions")

    cands = batch_candidates(10)
    check(len(cands) <= 10, f"the batch is at most ten items ({len(cands)})")
    check(all(c.operation == "omitted" for c in cands), "every item is an omission")
    check(all(c.witness_held for c in cands), "every item's amending Act is held")
    check(all(c.witness_eligible for c in cands), "every item passes the inventory gate")
    check(all(c.bucket == "OMISSION_MARKER" for c in cands),
          "no parser-fixed or unclosed span is in the batch")

    items = build(offline=True)
    check(all(i.human_review == "PENDING" for i in items),
          "every item is PENDING review; nothing is promoted")
    check(all(i.status == ABSTAIN for i in items),
          "offline, every item ABSTAINs rather than guessing")
    check(all(i.commencement_type == "UNKNOWN" for i in items),
          "commencement type is not asserted from a w.e.f. date alone")

    # Clause extraction, on real amending-Act language.
    sample = ("14. Amendment of section 26. In section 26 of the principal Act, "
              "sub-section (4) shall be omitted. 15. Omission of section 27. "
              "Section 27 of the principal Act shall be omitted.")
    c26 = _clause_for_section(sample, "26")
    check(c26 is not None and "section 26" in c26.lower(),
          "the clause for a named section is located")
    check(c26 is not None and "Omission of section 27" not in c26,
          "extraction stops at the next numbered clause")
    check(_clause_for_section(sample, "999") is None,
          "a section the Act does not mention yields no clause")
    check(bool(_OMIT_VERB.search(sample)), "omission language is recognised")
    check(not _OMIT_VERB.search("shall be substituted"),
          "substitution language is not read as omission")

    # Regressions for the two defects that produced false EXACTs.
    check(bool(_OPERATIVE.search(
        "shall be omitted; (f) after sub-section (15), the following sub-sections "
        "shall be inserted, namely:-")),
        "clause scaffolding is recognised and cannot be served as omitted text")
    check(not _OPERATIVE.search("within the time as specified, under section 403"),
          "genuine omitted wording is not mistaken for scaffolding")

    # Clause-level binding: the quote must be governed by the omission verb.
    s161 = ('51. Amendment of section 161. In section 161 of the principal Act,- '
            '(i) in sub-section (2), after the words "alternate directorship", the '
            'words "or holding directorship in the same company" shall be inserted; '
            '(ii) in sub-section (4),- (a) the words "In the case of a public '
            'company," shall be omitted;')
    os = omissions_in(s161)
    check(len(os) == 1, f"only the omission is extracted, not the insertion ({len(os)})")
    check(os and os[0].text == "In the case of a public company,",
          "the omitted words are the ones the omission verb governs")
    check(os and os[0].subsection == "4",
          "the omission is attributed to its own sub-section, not the clause's first")
    check(all("holding directorship" not in o.text for o in os),
          "inserted text is never returned as omitted text")

    multi = ('In section 137, (i) in sub-section (1),- (a) the words "A B C D E" '
             'shall be omitted; (b) the words "X Y Z P Q" shall be omitted;')
    check(len(omissions_in(multi)) == 2, "each omission in a nested clause is seen")

    r = report(items)
    check("Human review required  : 10" in r or f"Human review required  : {len(items)}" in r,
          "the report states how many items need review")
    check("Nothing above is promoted" in r,
          "the report says explicitly that nothing is promoted")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    if "--test" in sys.argv:
        _test()
    else:
        its = build(offline="--offline" in sys.argv)
        print(report(its))
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps([asdict(i) for i in its], indent=1) + "\n")
        print(f"written: {OUT}")
