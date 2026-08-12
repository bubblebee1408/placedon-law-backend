"""
Two things the epistemic lattice does not do: trace a path, and notice a contradiction.

Both gaps were found by reading [Falkor-IRAC](https://arxiv.org/abs/2605.14665), which arrived at
this repository's architecture independently and measures two things we did not.

## 1. Path validity

`epistemic_status.assess()` composes weakest-link across a *set* of grounds. It answers "is every
provision this rests on verified?" It does not answer "is there a traceable chain from the
question to the claim?"

Those differ, and the difference is not academic. Retrieval can return s.26 for a penalty question
while the claim actually depends on s.4 — because s.26(1)(a) penalises failure to constitute a
committee *under s.4*. If s.4 was never retrieved, every ground we checked is verified and the
answer still rests on a provision nobody looked at. The lattice reports VERIFIED. The path is
broken.

`trace()` walks the statute's own cross-references and reports whether each edge exists and each
node is answerable. It is the stricter test, and ours was the weaker one.

## 2. Conflict

Weakest-link is monotone: adding a ground can only lower the status, never contradict it. So two
provisions that disagree compose silently into the weaker one, and the disagreement — which is
the thing a reader most needs — disappears.

Statutes disagree constantly, and provisos exist precisely to carve exceptions. s.9 gives three
months to complain and then a proviso extends it to six. An answer that quotes one without the
other is not merely incomplete; it is wrong in the direction that costs a complainant her remedy.

`conflicts()` finds three shapes, all textual and all deterministic:

  * **proviso** — a section containing "Provided that", which by construction qualifies what
    precedes it
  * **override** — "notwithstanding", "save as otherwise", "subject to"
  * **numeric tension** — two retrieved provisions stating different periods for what a reader
    would take to be the same clock

None of this uses a model. All of it is checkable by reading the section.

Run: python3 checker/path_validity.py
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from checker.epistemic_status import Status                   # noqa: E402
from checker.provision_graph import ProvisionGraph            # noqa: E402

# Written-out durations, because statutes spell numbers. "ninety days" not "90 days".
PERIOD = re.compile(
    r"\b(one|two|three|four|five|six|seven|eight|nine|ten|thirty|sixty|ninety|"
    r"\d{1,3})\s+(day|days|month|months|year|years)\b", re.I)

PROVISO = re.compile(r"\bProvided\s+(?:further\s+|also\s+)?that\b", re.I)
OVERRIDE = re.compile(r"\bnotwithstanding\b|\bsave\s+as\s+otherwise\b|\bsubject\s+to\s+the\s+"
                      r"provisions\b", re.I)

_WORD = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
         "eight": 8, "nine": 9, "ten": 10, "thirty": 30, "sixty": 60, "ninety": 90}
_UNIT_DAYS = {"day": 1, "days": 1, "month": 30, "months": 30, "year": 365, "years": 365}


def _days(qty: str, unit: str) -> int:
    n = _WORD.get(qty.lower(), None)
    if n is None:
        n = int(qty)
    return n * _UNIT_DAYS[unit.lower()]


@dataclass(frozen=True)
class Hop:
    """One edge in a reasoning path, and whether it holds."""

    frm: int
    to: int
    evidence: str | None            # the statute's own words creating the link
    status: Status                  # of the destination
    ok: bool


@dataclass
class Path:
    """A traced route from the sections retrieved to the section actually relied on."""

    target: int
    hops: list[Hop] = field(default_factory=list)
    reached: bool = False
    reason: str = ""

    @property
    def valid(self) -> bool:
        """Traceable AND every hop lands on something answerable."""
        return self.reached and bool(self.hops) and all(h.ok for h in self.hops)


@dataclass(frozen=True)
class Conflict:
    """Two provisions a reader must be shown together, and why."""

    kind: str                       # "proviso" | "override" | "numeric_tension"
    sections: tuple[int, int]
    detail: str


class PathTracer:
    """Traces reasoning paths and finds conflicts over the ingested corpus."""

    def __init__(self, provisions: list[dict] | None = None) -> None:
        self.graph = ProvisionGraph(provisions)
        self._prov = {p["section_number"]: p for p in (provisions or self._load())}

    @staticmethod
    def _load() -> list[dict]:
        import json                                            # noqa: PLC0415
        path = ROOT / "corpus/provisions/posh_act_2013.json"
        return json.loads(path.read_text())["provisions"] if path.exists() else []

    def _text(self, section: int) -> str:
        p = self._prov.get(section)
        return " ".join((p.get("text_statutory") or "").split()) if p else ""

    def _status(self, section: int) -> Status:
        """A provision is only answerable once a lawyer has verified our reading of it."""
        p = self._prov.get(section)
        if p is None:
            return Status.UNSUPPORTED
        return Status.VERIFIED if p.get("verified_by") else Status.UNCHECKED

    # ---------------------------------------------------------------- path validity

    def trace(self, retrieved: list[int], target: int, *, depth: int = 6) -> Path:
        """
        Is there a route from something we retrieved to the provision the claim relies on?

        Breadth-first over the statute's cross-references. Every hop records the statute's own
        words that create the link, so a reader can check the path rather than trust it.
        """
        if target in retrieved:
            st = self._status(target)
            return Path(target=target, reached=True,
                        hops=[Hop(target, target, "directly retrieved", st, st.answerable)],
                        reason="")

        seen, frontier = set(retrieved), [(s, []) for s in retrieved]
        for _ in range(depth):
            nxt: list[tuple[int, list[Hop]]] = []
            for node, trail in frontier:
                for child in self.graph.dependencies(node, depth=1):
                    if child in seen and child != target:
                        continue
                    st = self._status(child)
                    # Edge direction: the graph stores (depended-upon, depender), so an edge
                    # for "s.26 rests on s.4" is filed under parent=4, child=26. We are walking
                    # dependencies — node rests on child — so the evidence lives at (child, node).
                    # Passing (node, child) returned None for every hop and the evidence
                    # assertion caught it.
                    hop = Hop(node, child, self.graph.evidence_for(child, node), st,
                              st.answerable)
                    if child == target:
                        return Path(target=target, hops=[*trail, hop], reached=True)
                    seen.add(child)
                    nxt.append((child, [*trail, hop]))
            if not nxt:
                break
            frontier = nxt

        return Path(target=target, reached=False,
                    reason=(f"no cross-reference path from {retrieved} to s.{target}. The claim "
                            f"rests on a provision nothing retrieved reaches — the grounds may "
                            f"all be verified and the reasoning still be unsupported."))

    @staticmethod
    def validity_rate(paths: list[Path]) -> float:
        """Fraction of traced paths that hold end to end. Falkor-IRAC's metric."""
        return round(sum(1 for p in paths if p.valid) / len(paths), 4) if paths else 0.0

    # ---------------------------------------------------------------- conflict

    def conflicts(self, sections: list[int]) -> list[Conflict]:
        """Pairs among the retrieved provisions that a reader must be shown together."""
        out: list[Conflict] = []
        for s in sections:
            t = self._text(s)
            if PROVISO.search(t):
                m = PROVISO.search(t)
                out.append(Conflict(
                    "proviso", (s, s),
                    f"s.{s} carries a proviso that qualifies the rule stated before it: "
                    f"…{t[m.start():m.start() + 130]}…"))
            if OVERRIDE.search(t):
                m = OVERRIDE.search(t)
                out.append(Conflict(
                    "override", (s, s),
                    f"s.{s} is expressed as subject to, or notwithstanding, other provisions: "
                    f"…{t[max(0, m.start() - 30):m.start() + 110]}…"))

        # Two provisions naming different periods, retrieved for the same question, is the shape
        # of s.9: three months in the rule, six months in its proviso. Quoting one is wrong.
        periods: dict[int, set[int]] = {}
        for s in sections:
            found = {_days(q, u) for q, u in PERIOD.findall(self._text(s))}
            if found:
                periods[s] = found
        seen_pairs = set()
        for a in periods:
            for b in periods:
                if a >= b or (a, b) in seen_pairs:
                    continue
                seen_pairs.add((a, b))
                # Two different numbers are only in tension if they plausibly govern the SAME
                # clock. Over the whole Act, a naive pairwise comparison produced 37 "conflicts"
                # — s.4's three-year committee tenure against s.11's ninety-day inquiry, which
                # are simply different things. A metric that fires 37 times on a 30-section Act
                # trains the reader to ignore it, which is worse than not having it.
                #
                # The cheap, checkable proxy for "same clock": the statute itself links them,
                # i.e. one section cross-references the other. Provisos to the same rule are
                # linked by construction, which is the case that matters (s.9's three months and
                # its six-month extension).
                linked = (b in self.graph.dependencies(a, depth=1)
                          or a in self.graph.dependencies(b, depth=1))
                if linked and periods[a] != periods[b] and not (periods[a] & periods[b]):
                    out.append(Conflict(
                        "numeric_tension", (a, b),
                        f"s.{a} states {sorted(periods[a])} day(s); s.{b} states "
                        f"{sorted(periods[b])}. Both were retrieved for one question — an answer "
                        f"quoting one without the other may be wrong in the reader's favour or "
                        f"against it."))
        return out


# --------------------------------------------------------------------------------------------
_pass = _fail = 0


def check(name: str, got, want) -> None:
    global _pass, _fail
    if got == want:
        _pass += 1
        print(f"  PASS  {name}")
    else:
        _fail += 1
        print(f"  FAIL  {name}\n        got  {got!r}\n        want {want!r}")


def _suite() -> int:
    t = PathTracer()

    # ---- path validity
    p = t.trace([26], 26)
    check("a retrieved section traces to itself", p.reached, True)
    check("but is not valid while unverified", p.valid, False)

    p2 = t.trace([26], 4)
    check("s.26 -> s.4 traces (s.26(1)(a) names section 4)", p2.reached, True)
    if p2.reached and p2.hops:
        check("the hop carries the statute's own words",
              bool(p2.hops[-1].evidence), True)

    p3 = t.trace([2], 999)
    check("an unreachable target does not trace", p3.reached, False)
    check("and says why, naming the gap", "rests on a provision" in p3.reason, True)
    check("an untraceable path is not valid", p3.valid, False)

    check("validity_rate over a mixed set", t.validity_rate([p, p3]), 0.0)
    check("validity_rate of nothing is zero, not an error", t.validity_rate([]), 0.0)

    # ---- conflict
    c9 = t.conflicts([9])
    check("s.9's proviso is flagged", any(c.kind == "proviso" for c in c9), True)

    c_pair = t.conflicts([9, 11])
    kinds = {c.kind for c in c_pair}
    check("three months vs ninety days is NOT a false conflict",
          "numeric_tension" in kinds, False)

    c_none = t.conflicts([])
    check("no sections, no conflicts", c_none, [])

    # The check that matters: a real disagreement must surface.
    # Linked by a cross-reference, which is what makes them the same clock. Unlinked sections
    # stating different numbers are not in tension — they are simply about different things, and
    # treating them as conflicts produced 37 false alarms across a 30-section Act.
    fake = [{"section_number": 100, "text_statutory": "The period shall be thirty days.",
             "text_display": "The period shall be thirty days.",
             "citation": "s.100", "verified_by": None},
            {"section_number": 101, "text_statutory": "Notwithstanding anything in section 100, the period shall be ninety days.",
             "text_display": "Notwithstanding anything in section 100, the period shall be ninety days.",
             "citation": "s.101", "verified_by": None}]
    t2 = PathTracer(fake)
    c2 = t2.conflicts([100, 101])
    check("unlinked sections with different numbers are NOT flagged",
          any(c.kind == "numeric_tension" for c in PathTracer([
              {"section_number": 200, "text_statutory": "A term of three years.",
               "text_display": "A term of three years.",
               "citation": "s.200", "verified_by": None},
              {"section_number": 201, "text_statutory": "A period of ninety days.",
               "text_display": "A period of ninety days.",
               "citation": "s.201", "verified_by": None}]).conflicts([200, 201])), False)

    check("linked sections with different numbers ARE flagged",
          any(c.kind == "numeric_tension" for c in c2), True)
    check("and names both sections",
          next(c.sections for c in c2 if c.kind == "numeric_tension"), (100, 101))

    # ---- the wiring TASK 1 asks for: an abstention that names the route to its blocker
    from checker.ask_engine import AskEngine                   # noqa: PLC0415

    a = AskEngine().ask("What is the penalty for not complying?",
                        {"state": "IN-KA", "employees": 40})
    paths = [c for c in a.epistemic_chain if c.get("status") == "PATH"]
    check("an abstention carries the path to what blocks it", bool(paths), True)
    if paths:
        check("and the path quotes the statute's own linking words",
              any("section 4" in (p.get("ground") or "").lower() for p in paths), True)

    print(f"\n  {_pass} passed, {_fail} failed")
    return 1 if _fail else 0


if __name__ == "__main__":
    raise SystemExit(_suite())
