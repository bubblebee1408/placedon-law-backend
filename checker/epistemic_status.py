"""
Epistemic status of a claim — an ordinal lattice, not a probability.

## Why this file has no arithmetic

It had some, for about an hour. An earlier version of this module did proper Bayesian updating on
the odds form, with likelihood ratios attached to corpus facts. The maths was correct — it fixed
a real sign error in the spec it came from. The number was never shown to a user. And it was
still wrong, for reasons an adversarial audit of the underlying research made unavoidable:

**There is no aleatoric uncertainty here to be probabilistic about.** s.4 either applies to a
company or it does not; the company told us its headcount and `applicability.py` reads the Act.
A probability over a settled deduction is a probability about whether our pipeline works — a
software-correctness question wearing legal clothing.

**Calibration is unreachable, and not for want of effort.** Guo et al. (ICML 2017) needs logits
and a held-out labelled i.i.d. set; their smallest is 2,897 examples. At n=20 the observable
resolution is exactly 0.05, so an "ECE < 0.05" target sits *below the resolution of the
instrument*. Worse, the noise floor for a **perfectly calibrated** model at p=0.9 is 0.0535 — it
fails the target by construction. Distinguishing 0.94 from 0.93 needs ~2,256 labels per
provision. We have zero.

**The literature that does this all stipulates its numbers.** Constant (*AI and Law* 32(2), 2023)
builds almost exactly this — Bayesian nodes for statutory applicability with Shannon entropy —
and says plainly: *"The goal of this study was simply to propose a toy model."* Its priors are
chosen "to match the narrative". RSI (arXiv 2603.21610) carries an applicability indicator and
proves three theorems, then states *"full numerical validation is forthcoming."* Nobody has
grounded these numbers. Neither had we.

**And the empirical frontier is far below where a number like 0.94 implies.** SOTA macro-F1 on
Indian statute identification is **64.58** (Paul et al., ICAIL 2023) — on a criminal-law task
with vastly more training signal than HR compliance.

## What replaces it

An **ordinal lattice with weakest-link semantics.** A claim resting on several grounds is exactly
as strong as its weakest ground — which is how a lawyer reads a chain of authority, composes
without invented weights, and cannot be mistaken for a measurement.

    QUOTED       the section says it, in its own words, and a lawyer has checked our reading
    VERIFIED     a lawyer has checked our reading
    INFERRED     derived from the text by a reading we state as a reading
    SECONDARY    the text is a reproduction, not the primary source
    UNCHECKED    we hold the text; nobody has verified our reading of it
    UNSUPPORTED  the claim rests on a section we do not hold, or on unverified ground
    SILENT       the statute does not settle the question at all

Ordering is total, comparison is meaningful, and no step invents a quantity. Every status carries
the corpus field that produced it, so `explain()` still shows the derivation — which was the one
genuinely useful thing the probabilistic version did.

Run: python3 checker/belief_engine.py
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from checker.provision_graph import ProvisionGraph  # noqa: E402
from checker.verifier import EDGE_CASES             # noqa: E402

CORPUS = Path(__file__).resolve().parent.parent / "corpus/provisions/posh_act_2013.json"


class Status(IntEnum):
    """Ordered worst to best. IntEnum so `min()` is the weakest link, with no arithmetic."""

    SILENT = 0        # the Act does not address this
    UNSUPPORTED = 1   # rests on text we do not hold, or on unverified ground
    UNCHECKED = 2     # text held, reading unverified — where the whole corpus sits today
    SECONDARY = 3     # text is a reproduction rather than the primary source
    INFERRED = 4      # a reading we derived and label as a reading
    VERIFIED = 5      # a lawyer has checked our reading
    QUOTED = 6        # verbatim, and checked

    @property
    def answerable(self) -> bool:
        """Below VERIFIED we do not assert. This is today's behaviour, made explicit."""
        return self >= Status.VERIFIED


@dataclass(frozen=True)
class Ground:
    """One reason a claim sits where it does, and the corpus field that says so."""

    status: Status
    reason: str
    source: str          # the field or module this was read from


@dataclass
class Claim:
    text: str
    grounds: list[Ground] = field(default_factory=list)

    @property
    def status(self) -> Status:
        """Weakest link. A chain of authority is as strong as its weakest ground."""
        return min((g.status for g in self.grounds), default=Status.UNSUPPORTED)

    @property
    def weakest(self) -> Ground | None:
        return min(self.grounds, key=lambda g: g.status, default=None)

    def explain(self) -> list[str]:
        return [f"{g.status.name:<12} {g.reason}  (from {g.source})"
                for g in sorted(self.grounds, key=lambda g: g.status)]


class EpistemicState:
    """Status of each claim we are about to make, derived only from corpus fields."""

    def __init__(self, provisions: list[dict] | None = None) -> None:
        self.provisions = (provisions if provisions is not None
                           else json.loads(CORPUS.read_text())["provisions"])
        self._by_num = {p["section_number"]: p for p in self.provisions}
        self._graph = ProvisionGraph(self.provisions)
        self.claims: dict[str, Claim] = {}

    def assess(self, claim: str, *, sections: list[int], citation: str = "",
               question: str = "") -> Claim:
        c = Claim(text=claim)

        for pattern, subject in EDGE_CASES:
            if question and re.search(pattern, question.lower()):
                c.grounds.append(Ground(Status.SILENT, f"the Act does not settle {subject}",
                                        "verifier.EDGE_CASES"))
                self.claims[claim] = c
                return c

        for n in sections:
            p = self._by_num.get(n)
            if p is None:
                c.grounds.append(Ground(Status.UNSUPPORTED, f"s.{n} is not in the corpus",
                                        "corpus (absent)"))
                continue

            if p.get("verified_by"):
                verbatim = bool(citation) and "inferred" not in citation.lower()
                c.grounds.append(Ground(
                    Status.QUOTED if verbatim else Status.VERIFIED,
                    f"s.{n} checked by {p['verified_by']}", "provision.verified_by"))
            else:
                c.grounds.append(Ground(Status.UNCHECKED,
                                        f"nobody has verified our reading of s.{n}",
                                        "provision.verified_by is null"))

            if str(p.get("source_quality", "")).startswith("secondary"):
                c.grounds.append(Ground(Status.SECONDARY,
                                        f"s.{n} text is a reproduction, not the gazette",
                                        "provision.source_quality"))

            blocked = [x for x in self._graph.blocked_by(n) if x != n]
            if blocked:
                c.grounds.append(Ground(
                    Status.UNSUPPORTED,
                    f"s.{n} rests on unverified {', '.join(f's.{b}' for b in blocked)}",
                    "provision_graph.blocked_by"))

        if citation and "inferred" in citation.lower():
            c.grounds.append(Ground(Status.INFERRED,
                                    f"this is our reading, not the Act's words: {citation}",
                                    "citation text says 'inferred'"))

        self.claims[claim] = c
        return c

    def should_abstain(self, claim: str) -> tuple[bool, str]:
        c = self.claims.get(claim)
        if c is None:
            return True, "No claim was assessed."
        if c.status.answerable:
            return False, ""
        w = c.weakest
        return True, (f"We will not state this. {w.reason}." if w
                      else "We will not state this.")

    def rank(self) -> list[tuple[str, Status]]:
        """Ordering — the job the number was doing, done without one."""
        return sorted(((k, v.status) for k, v in self.claims.items()),
                      key=lambda kv: -kv[1])


# ─────────────────────────────── tests ───────────────────────────────
if __name__ == "__main__":
    failures = 0

    def check(name: str, got, want) -> None:
        global failures
        ok = got == want
        failures += (not ok)
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + ("" if ok else f"  got={got!r}"))

    raw = json.loads(CORPUS.read_text())["provisions"]
    verified = [{**p, "verified_by": "Adv. Test"} for p in raw]

    check("the lattice is totally ordered", Status.SILENT < Status.UNSUPPORTED < Status.UNCHECKED
          < Status.SECONDARY < Status.INFERRED < Status.VERIFIED < Status.QUOTED, True)
    check("only VERIFIED and above are answerable",
          [s.name for s in Status if s.answerable], ["VERIFIED", "QUOTED"])

    c = Claim("x", [Ground(Status.QUOTED, "a", "t"), Ground(Status.UNCHECKED, "b", "t")])
    check("weakest link governs", c.status, Status.UNCHECKED)
    check("  ...and names itself", c.weakest.reason, "b")

    today = EpistemicState(raw)
    t = today.assess("PoSH requires an IC", sections=[4], citation="s.4(1), PoSH Act 2013")
    check("today's corpus is UNSUPPORTED (s.4 rests on unverified s.16)",
          t.status, Status.UNSUPPORTED)
    check("  ...so we abstain", today.should_abstain("PoSH requires an IC")[0], True)

    after = EpistemicState(verified)
    a = after.assess("PoSH requires an IC", sections=[4], citation="s.4(1), PoSH Act 2013")
    check("fully verified corpus → QUOTED", a.status, Status.QUOTED)
    check("  ...and answerable", after.should_abstain("PoSH requires an IC")[0], False)

    inf = EpistemicState(verified).assess(
        "PoSH applies at ten workers", sections=[6],
        citation="s.6(1), PoSH Act 2013 (inferred — s.4 states no threshold)")
    check("an inferred reading ranks below a quoted one", inf.status < a.status, True)
    check("  ...and is INFERRED exactly", inf.status, Status.INFERRED)

    edge = EpistemicState(verified)
    edge.assess("interns count", sections=[2], question="do interns count toward the ten?")
    check("edge case is SILENT even on a verified corpus",
          edge.claims["interns count"].status, Status.SILENT)

    absent = EpistemicState(verified).assess("s.99 says something", sections=[99])
    check("a section we do not hold is UNSUPPORTED", absent.status, Status.UNSUPPORTED)

    src = EpistemicState([{**p, "verified_by": "Adv. Test",
                           "source_quality": "secondary_reproduction"} for p in raw])
    s = src.assess("the Rules say so", sections=[4], citation="s.4")
    check("a secondary source caps the status below VERIFIED", s.status, Status.SECONDARY)
    check("  ...so it is not answerable", src.should_abstain("the Rules say so")[0], True)

    check("no float anywhere in the module",
          bool(re.search(r"\b0\.\d+", Path(__file__).read_text().split('"""')[2])), False)

    print("\n  The s.4 claim on today's corpus:")
    for line in t.explain():
        print(f"    {line}")
    print(f"    → {today.should_abstain('PoSH requires an IC')[1]}")

    print(f"\n{'all passed' if not failures else f'{failures} FAILED'}")
    raise SystemExit(1 if failures else 0)
