"""
Amendment timeline for a Companies Act section.

The question this answers is the one nothing else answers well for Indian corporate law:
**what changed in this section, when, and by which instrument.** 434 amendment records are parsed
from India Code's own footnotes, 431 of them carrying a w.e.f. date.

What it does NOT do is reconstruct the text as it stood on a past date. `checker/as_of.py` can
attempt that, and it has never been verified against an independent source, so this module reports
the CHANGE HISTORY and refuses to assert prior wording. A timeline is checkable -- the footnote
either says "Subs. by Act 29 of 2020 (w.e.f. 21-12-2020)" or it does not. Reconstructed text is not
checkable without a second source, and claiming it would be the overclaim this repo exists to avoid.

An independent cross-check exists for one instrument: PRS records the Companies (Amendment) Bill
2020 passing the Rajya Sabha on 22 September 2020. Act 29 of 2020 appears 111 times in these
records, which is consistent -- it does not verify any individual date.

Run: python3 checker/timeline.py
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from checker.amendment import parse_footnote
from checker.section_index import lookup

CORPUS = Path(__file__).resolve().parent.parent / "corpus/companies_act"

# The Act received assent on 29 August 2013. A w.e.f. date outside this window is a parse error or
# a source typo, not a fact about the law -- one record in the corpus reads year 5017.
ACT_ASSENT = date(2013, 8, 29)
PLAUSIBLE_MAX = date(2040, 1, 1)

__all__ = ["Change", "Timeline", "timeline_for", "IMPLAUSIBLE"]

IMPLAUSIBLE = "IMPLAUSIBLE_DATE"


@dataclass(frozen=True)
class Change:
    marker: str
    operation: str            # substituted | inserted | omitted
    instrument: str           # "Act 29 of 2020"
    wef: date | None
    flags: tuple[str, ...] = ()

    @property
    def dated(self) -> bool:
        return self.wef is not None and not self.flags

    def line(self) -> str:
        when = self.wef.isoformat() if self.wef else "date not stated"
        flag = f"   [{', '.join(self.flags)}]" if self.flags else ""
        return f"{when}  {self.operation:<12} by {self.instrument}{flag}"


@dataclass(frozen=True)
class Timeline:
    section: str
    title: str
    changes: tuple[Change, ...]
    undated: int
    implausible: int

    @property
    def amended(self) -> bool:
        return bool(self.changes)

    def in_force_window(self) -> tuple[date | None, date | None]:
        """When the CURRENT text of this section took shape: the latest dated change, to today.

        The opening bound is the most recent amendment we can date. It is not a claim that the
        section was untouched before it -- only that this is the last change on record.
        """
        dated = [c.wef for c in self.changes if c.dated]
        return (max(dated) if dated else None, None)

    def render(self) -> str:
        out = [f"AMENDMENT TIMELINE — s.{self.section}  {self.title}", ""]
        if not self.changes:
            out += ["  No amendment recorded in the source footnotes.",
                    "  This is NOT proof the section was never amended — only that India Code's",
                    "  footnotes for it record none."]
            return "\n".join(out)
        for c in sorted(self.changes, key=lambda x: (x.wef or date(1900, 1, 1))):
            out.append("  " + c.line())
        since, _ = self.in_force_window()
        out += ["", f"  {len(self.changes)} change(s) recorded"]
        if since:
            out.append(f"  Current text has stood since at least {since.isoformat()}")
        if self.undated:
            out.append(f"  {self.undated} change(s) carry NO date — the section's history is incomplete")
        if self.implausible:
            out.append(f"  {self.implausible} change(s) carry an implausible date — source or parse defect")
        out += ["",
                "  This is the CHANGE HISTORY, taken from the source's own footnotes.",
                "  It is not the text as it stood on any past date: point-in-time reconstruction",
                "  is unverified against an independent source and is therefore not asserted."]
        return "\n".join(out)


def timeline_for(section_number: str) -> Timeline | None:
    """The amendment history of a section, or None if the section is not in the corpus."""
    e = lookup(section_number)
    if not e or not e.get("section_id"):
        return None
    rec = json.loads((CORPUS / f"{e['section_id']}.json").read_text())
    changes, undated, implausible = [], 0, 0
    for a in parse_footnote(rec.get("footnote") or ""):
        flags = []
        if a.wef is None:
            undated += 1
        elif not (ACT_ASSENT <= a.wef <= PLAUSIBLE_MAX):
            flags.append(IMPLAUSIBLE)
            implausible += 1
        changes.append(Change(str(a.marker), a.operation, str(a.instrument or "not stated"),
                              a.wef, tuple(flags)))
    return Timeline(section_number, e.get("title", ""), tuple(changes), undated, implausible)


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"[PASS] {label}")
        else:
            fail += 1; print(f"[FAIL] {label}")

    t = timeline_for("96")
    check(t is not None and t.amended, "s.96 has a recorded amendment")
    check(any("2018" in str(c.wef) for c in t.changes), "...the 2018 substitution is on it")
    check("not the text as it stood" in t.render(),
          "the rendering refuses to claim past wording")

    t173 = timeline_for("173")
    check(t173 is not None, "s.173 resolves")

    check(timeline_for("9999") is None, "an unknown section returns None, not an empty timeline")
    check(timeline_for("11") is None, "an omitted section returns None")

    # An implausible date must be flagged, not silently carried into a legal answer.
    bad = Change("1", "substituted", "Act X", date(5017, 1, 1), (IMPLAUSIBLE,))
    check(not bad.dated, "an implausibly-dated change does not count as dated")
    check(IMPLAUSIBLE in bad.line(), "...and the flag is visible in the rendering")

    # Sweep the corpus: how much of the Act carries a usable history?
    from checker.section_index import MVP_SECTIONS
    amended = [s for s in MVP_SECTIONS if (tl := timeline_for(s)) and tl.amended]
    check(len(amended) >= 5,
          f"{len(amended)} of {len(MVP_SECTIONS)} MVP sections have a recorded amendment")

    total_impl = sum(tl.implausible for s in MVP_SECTIONS if (tl := timeline_for(s)))
    check(total_impl == 0, f"no MVP section carries an implausible date ({total_impl})")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
