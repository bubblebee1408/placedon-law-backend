"""
The provision dependency graph — derived from the statute, not authored by us.

## Why this is not the graph the PLAE spec asked for

The spec models provisions as Bayesian nodes with conditional probability tables:
`P(child=true | parent_states)`. That needs numbers. We hold none — zero labelled outcomes, zero
observed filings, zero users. Every entry in such a table would be invented, and the arithmetic
would then launder the invention into a figure like `posh_applicable: 0.94`, which reads as
measurement. That is the risk-score pattern with better maths on top, and worse, because the
machinery makes it credible.

So the edges here are **deductive and evidenced**, not probabilistic. The statute states its own
dependencies in its own words:

    s.26: "Where the employer fails to— (a) constitute an Internal Committee under
           sub-section (1) of section 4"

That sentence *is* the edge s.4 → s.26, and it is quoted on the edge. Nothing is asserted that
cannot be traced to a span of ingested text. Extraction beats authorship: a hand-drawn graph is
one person's model of the Act; this one is the Act's model of itself, and it is re-derivable
whenever the corpus changes.

## What the graph is for

Two questions the flat corpus cannot answer:

1. **What must hold before a claim can be made?** The ₹50,000 penalty in s.26 is not free-
   standing — it attaches to failing a duty in s.4. If s.4 is unverified, s.26's penalty cannot
   be asserted either, however well-verified s.26 itself is. Verification propagates along
   dependency, and before this module nothing tracked that.

2. **What does a question actually depend on?** `retrieval.py` returns a flat packet. The graph
   returns the chain, so an answer can show its derivation instead of asserting a conclusion.

Run: python3 checker/provision_graph.py
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

CORPUS = Path(__file__).resolve().parent.parent / "corpus/provisions/posh_act_2013.json"

# Cross-references as the Act actually writes them. Deliberately narrow: a loose pattern invents
# edges, and an invented edge is worse than a missing one because it looks derived.
XREF = re.compile(
    r"(?:sub-section\s*\(\d+\)\s*of\s*)?"        # "sub-section (1) of "
    # {1,3}, not {1,2}. The PoSH Act stops at 30 so two digits sufficed and nobody noticed the
    # ceiling. But we already hold Companies Act s.134, the AGM section is s.96, and the labour
    # codes run well past 100 — every cross-reference to a three-digit section would have been
    # silently invisible to the graph, which means blocked_by() would report a claim unblocked
    # when its dependency was simply never seen. Found by a test fixture using s.100.
    r"section\s+(\d{1,3})\b",                    # "section 4", "section 134"
    re.I,
)

# A provision citing itself is not a dependency. Nor is the Act's own short title.
SELF_EVIDENT = {1}


@dataclass(frozen=True)
class Edge:
    """A dependency, with the sentence from the statute that establishes it."""

    parent: int          # the section depended upon
    child: int           # the section that refers to it
    quote: str           # verbatim span from the child's text

    def __str__(self) -> str:
        return f"s.{self.child} → s.{self.parent}"


@dataclass
class Node:
    number: int
    citation: str
    heading: str
    verified: bool
    parents: set[int] = field(default_factory=set)
    children: set[int] = field(default_factory=set)


class ProvisionGraph:
    """
    A DAG over ingested sections. Every edge carries its evidence.

    Cycles are not an error to raise here — a statute can legitimately cross-reference in both
    directions (s.11 mentions s.13, s.13 mentions s.11). What matters is that traversal
    terminates, so walks are depth-bounded and visit-tracked rather than assuming acyclicity.
    """

    def __init__(self, provisions: list[dict] | None = None) -> None:
        raw = provisions if provisions is not None else json.loads(CORPUS.read_text())["provisions"]
        self.nodes: dict[int, Node] = {
            p["section_number"]: Node(
                number=p["section_number"],
                citation=p.get("citation", f"s.{p['section_number']}"),
                heading=p.get("heading", ""),
                verified=bool(p.get("verified_by")),
            )
            for p in raw
        }
        self.edges: list[Edge] = []
        self._extract(raw)

    def _extract(self, raw: list[dict]) -> None:
        for p in raw:
            child = p["section_number"]
            body = " ".join((p.get("text_display") or "").split())
            for m in XREF.finditer(body):
                parent = int(m.group(1))
                if parent == child or parent in SELF_EVIDENT or parent not in self.nodes:
                    continue
                if any(e.parent == parent and e.child == child for e in self.edges):
                    continue
                start = max(0, m.start() - 70)
                self.edges.append(Edge(parent, child,
                                       body[start:m.end() + 30].strip()))
                self.nodes[child].parents.add(parent)
                self.nodes[parent].children.add(child)

    # ── queries ──────────────────────────────────────────────────────────

    def dependencies(self, section: int, *, depth: int = 6) -> list[int]:
        """Everything `section` rests on, transitively. Visit-tracked, so cycles terminate."""
        seen: set[int] = set()
        frontier = [(section, 0)]
        while frontier:
            n, d = frontier.pop()
            if d >= depth:
                continue
            for parent in self.nodes.get(n, Node(n, "", "", False)).parents:
                if parent not in seen:
                    seen.add(parent)
                    frontier.append((parent, d + 1))
        return sorted(seen)

    def blocked_by(self, section: int) -> list[int]:
        """
        Sections that must be verified before a claim citing `section` can be asserted.

        This is the load-bearing query. s.26 verified but s.4 not means the penalty cannot be
        stated — s.26 attaches to failing the s.4 duty, so an unverified s.4 leaves the penalty
        claim resting on unverified ground. Nothing tracked that before.
        """
        unverified = [n for n in self.dependencies(section)
                      if not self.nodes[n].verified]
        if not self.nodes.get(section) or not self.nodes[section].verified:
            unverified.append(section)
        return sorted(set(unverified))

    def evidence_for(self, parent: int, child: int) -> str | None:
        return next((e.quote for e in self.edges if e.parent == parent and e.child == child), None)

    def roots(self) -> list[int]:
        return sorted(n for n, node in self.nodes.items() if not node.parents)


# ─────────────────────────────── tests ───────────────────────────────
if __name__ == "__main__":
    failures = 0

    def check(name: str, got, want) -> None:
        global failures
        ok = got == want
        failures += (not ok)
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + ("" if ok else f"  got={got!r}"))

    g = ProvisionGraph()

    check("graph covers the whole corpus", len(g.nodes), 30)
    check("edges were extracted at all", len(g.edges) > 10, True)

    # The edge the spec hand-authored, here derived from the Act's own words.
    check("s.4 → s.26 exists (penalty depends on the duty)", 26 in g.nodes[4].children, True)
    ev = g.evidence_for(4, 26)
    check("  ...and carries its evidence",
          bool(ev) and "section 4" in (ev or "").lower(), True)
    print(f"        “…{ev[-88:]}”" if ev else "")

    check("s.26 depends on s.4", 4 in g.dependencies(26), True)
    check("every edge quotes real text",
          all(len(e.quote) > 20 for e in g.edges), True)
    check("no self-edges", all(e.parent != e.child for e in g.edges), True)

    # Verification propagation — the reason this module exists.
    check("with nothing verified, s.26 is blocked by itself and s.4",
          set(g.blocked_by(26)) >= {4, 26}, True)

    verified_s26_only = json.loads(CORPUS.read_text())["provisions"]
    for p in verified_s26_only:
        p["verified_by"] = "Adv. Test" if p["section_number"] == 26 else None
    g2 = ProvisionGraph(verified_s26_only)
    check("verifying s.26 alone does NOT unblock the penalty claim",
          4 in g2.blocked_by(26), True)
    check("  ...s.26 itself is no longer the blocker", 26 in g2.blocked_by(26), False)

    all_verified = json.loads(CORPUS.read_text())["provisions"]
    for p in all_verified:
        p["verified_by"] = "Adv. Test"
    check("with everything verified, nothing is blocked",
          ProvisionGraph(all_verified).blocked_by(26), [])

    # Traversal must terminate even though the Act cross-references both ways.
    mutual = [
        {"section_number": 11, "citation": "s.11", "heading": "Inquiry",
         "text_display": "The inquiry shall proceed under section 13.", "verified_by": None},
        {"section_number": 13, "citation": "s.13", "heading": "Report",
         "text_display": "On completion of an inquiry under section 11 the report shall issue.",
         "verified_by": None},
    ]
    gm = ProvisionGraph(mutual)
    check("mutual cross-reference terminates", sorted(gm.dependencies(11)), [11, 13])

    print(f"\n  roots (depend on nothing): {g.roots()[:12]}")
    top = sorted(g.nodes.values(), key=lambda n: -len(n.children))[:4]
    print("  most depended-upon:")
    for n in top:
        print(f"    s.{n.number:<3} {n.heading[:44]:44} {len(n.children)} dependents")

    print(f"\n{'all passed' if not failures else f'{failures} FAILED'}")
    raise SystemExit(1 if failures else 0)
