"""
Belief engine — subjective credence in **our reading**, not probability that the law applies.

## The reframing this module rests on

The spec models `P(posh_applicable)`. But whether PoSH applies to a company with 14 employees is
not uncertain: `applicability.py` decides it deterministically from the Act, and the company told
us its headcount. Putting a probability on a settled deduction is a category error, and it is the
one that produces figures like `posh_applicable: 0.94` — precise, unfalsifiable, and read by a
user as measurement.

What *is* uncertain is **whether our reading of the statute is right**. That uncertainty is real,
it varies by provision, and every input to it is a fact we already hold:

| Input | Where it comes from | Not invented because |
|---|---|---|
| has a lawyer checked this reading | `verified_by` on the provision | it is a field, set or null |
| is this a quote or an inference | `"inferred"` in the citation | `CITE_THRESHOLD` says so in text |
| does the statute settle it at all | `verifier.EDGE_CASES` | the Act is silent on interns |
| primary or secondary source | `source_quality` | recorded at ingestion |
| does it rest on unverified ground | `provision_graph.blocked_by()` | extracted from cross-references |

## Three deliberate departures from the spec

**The prior is 0.5, not 0.6.** The spec's 0.6 is captioned "base rate from population data". We
hold no population data, and our own `RESEARCH_LOG` records the opposite of that figure — Udyam
puts 93.17% of registered MSMEs in the *micro* band. 0.5 is the honest starting credence: maximum
entropy, no claim. It is a stated assumption, not a measurement wearing one's clothes.

**Ambiguity shrinks the likelihood ratio toward 1, not toward 0.** The spec computes
`lr = lr * (1 - ambiguity)`. That drives LR to zero, which is certainty *against* the
proposition. Measured on the spec's own numbers: raising ambiguity from 0.0 to 0.8 on the
"fewer than ten employees" branch moves the posterior from 0.130 to **0.029** — more doubt
producing more confidence. `lr ** (1 - ambiguity)` moves it to 0.486 instead, converging on the
prior, which is what "we are less sure" has to mean.

**The number is never shown to a user.** It orders findings and it triggers abstention. It is
not rendered as "94% confident", because a number used for ranking needs no calibration while a
number shown as a confidence needs a labelled validation set we do not have. `docs/PLAE.md`
carries the full reasoning.

Run: python3 checker/belief_engine.py
"""
from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from checker.provision_graph import ProvisionGraph  # noqa: E402
from checker.verifier import EDGE_CASES             # noqa: E402

CORPUS = Path(__file__).resolve().parent.parent / "corpus/provisions/posh_act_2013.json"

# Maximum-entropy starting credence. Not a population base rate — we hold none.
NEUTRAL_PRIOR = 0.5

# How much each corpus fact moves the odds that our reading holds. These are subjective weights,
# stated as odds ratios so they compose, and every one is attached to a checkable condition.
# They are honest about being judgements; what they are not is dressed as measurements.
LR_LAWYER_VERIFIED = 12.0     # a human who can be named checked this reading
LR_VERBATIM_QUOTE = 4.0       # the claim is the section's own words
LR_INFERRED = 0.45            # a reading we derived; s.4 threshold is the worked example
LR_SECONDARY_SOURCE = 0.6     # text from a reproduction, not the gazette
LR_BLOCKED_DEPENDENCY = 0.3   # rests on a section nobody has verified

# Below this, refuse. Chosen so that today's corpus — nothing verified — lands under it, which
# is the behaviour we already ship and want preserved rather than quietly relaxed.
ABSTAIN_BELOW = 0.62


@dataclass(frozen=True)
class Evidence:
    """One corpus fact and what it does to the odds. `source` is what makes it auditable."""

    variable: str
    value: object
    likelihood_ratio: float
    source: str                       # the field or module this was read from
    ambiguity: float = 0.0            # 0 = the statute settles it, 1 = it does not


@dataclass
class Belief:
    proposition: str
    prior: float = NEUTRAL_PRIOR
    posterior: float = NEUTRAL_PRIOR
    evidence: list[Evidence] = field(default_factory=list)

    @property
    def entropy(self) -> float:
        """Binary Shannon entropy, in bits. 1.0 at p=0.5, 0.0 at certainty."""
        p = self.posterior
        if p <= 0.0 or p >= 1.0:
            return 0.0
        return -(p * math.log2(p) + (1 - p) * math.log2(1 - p))

    def update(self, ev: Evidence) -> None:
        """
        Bayes on the odds form, with ambiguity shrinking the evidence toward uninformative.

        `lr ** (1 - ambiguity)` and not `lr * (1 - ambiguity)`: multiplying pushes the ratio to
        0, which is certainty that the proposition is FALSE. Exponentiating pushes it to 1,
        which is "this evidence tells us nothing" — the actual meaning of ambiguity.
        """
        lr = max(ev.likelihood_ratio, 1e-9) ** (1.0 - min(max(ev.ambiguity, 0.0), 1.0))
        odds = (self.posterior / (1 - self.posterior)) * lr
        self.posterior = min(max(odds / (1 + odds), 1e-6), 1 - 1e-6)
        self.evidence.append(ev)

    def explain(self) -> list[str]:
        """Every step, with the corpus field that caused it. No unexplained movement."""
        out, running = [], self.prior
        for ev in self.evidence:
            lr = max(ev.likelihood_ratio, 1e-9) ** (1.0 - ev.ambiguity)
            odds = (running / (1 - running)) * lr
            nxt = odds / (1 + odds)
            out.append(f"{running:.3f} → {nxt:.3f}   LR {lr:5.2f}   {ev.variable} "
                       f"(from {ev.source})")
            running = nxt
        return out


class BeliefState:
    """Credence in each claim we are about to make, derived from corpus facts."""

    def __init__(self, provisions: list[dict] | None = None) -> None:
        self.provisions = (provisions if provisions is not None
                           else json.loads(CORPUS.read_text())["provisions"])
        self._by_num = {p["section_number"]: p for p in self.provisions}
        self._graph = ProvisionGraph(self.provisions)
        self.beliefs: dict[str, Belief] = {}

    def assess(self, claim: str, *, sections: list[int], citation: str = "",
               question: str = "") -> Belief:
        """
        Credence that a claim citing `sections` holds. Nothing here is hand-entered.
        """
        b = Belief(proposition=claim)

        # The Act is silent on the subject → no amount of verification helps.
        import re                                                  # noqa: PLC0415
        for pattern, subject in EDGE_CASES:
            if question and re.search(pattern, question.lower()):
                b.update(Evidence("statute_is_silent", subject, 0.02,
                                  "verifier.EDGE_CASES", ambiguity=0.0))
                self.beliefs[claim] = b
                return b

        for n in sections:
            p = self._by_num.get(n)
            if p is None:
                b.update(Evidence(f"s.{n}_not_held", None, 0.05, "corpus (absent)"))
                continue

            if p.get("verified_by"):
                b.update(Evidence(f"s.{n}_lawyer_verified", p["verified_by"],
                                  LR_LAWYER_VERIFIED, "provision.verified_by"))
            else:
                b.update(Evidence(f"s.{n}_unverified", None, 1 / LR_LAWYER_VERIFIED,
                                  "provision.verified_by is null"))

            if p.get("source_quality", "").startswith("secondary"):
                b.update(Evidence(f"s.{n}_secondary_source", p["source_quality"],
                                  LR_SECONDARY_SOURCE, "provision.source_quality"))

            blocked = [x for x in self._graph.blocked_by(n) if x != n]
            if blocked:
                b.update(Evidence(f"s.{n}_rests_on_unverified", blocked,
                                  LR_BLOCKED_DEPENDENCY, "provision_graph.blocked_by"))

        if "inferred" in citation.lower():
            b.update(Evidence("claim_is_inferred", citation, LR_INFERRED,
                              "citation text says 'inferred'"))
        elif citation:
            b.update(Evidence("claim_is_verbatim", citation, LR_VERBATIM_QUOTE,
                              "citation resolves to quoted text"))

        self.beliefs[claim] = b
        return b

    # ── consumption ──────────────────────────────────────────────────────

    def should_abstain(self, claim: str) -> tuple[bool, str]:
        b = self.beliefs.get(claim)
        if b is None:
            return True, "No belief was formed for this claim."
        if b.posterior < ABSTAIN_BELOW:
            weakest = min(b.evidence, key=lambda e: e.likelihood_ratio, default=None)
            why = f" The weakest link is {weakest.variable} ({weakest.source})." if weakest else ""
            return True, ("We are not confident enough in our own reading to state this." + why)
        return False, ""

    def rank(self) -> list[tuple[str, float]]:
        """Claims by credence. This is what the number is FOR — ordering, not display."""
        return sorted(((k, v.posterior) for k, v in self.beliefs.items()),
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

    # ── the maths ────────────────────────────────────────────────────
    b = Belief("test")
    b.update(Evidence("x", 1, 10.0, "test"))
    check("prior 0.5 + LR 10 → 0.909", round(b.posterior, 3), 0.909)

    b2 = Belief("test")
    b2.update(Evidence("x", 1, 10.0, "test"))
    b2.update(Evidence("y", 1, 0.1, "test"))
    check("conflicting evidence returns to the prior", round(b2.posterior, 3), 0.5)

    lo, hi = Belief("a"), Belief("b")
    lo.update(Evidence("x", 1, 0.1, "t", ambiguity=0.0))
    hi.update(Evidence("x", 1, 0.1, "t", ambiguity=0.8))
    check("ambiguity moves the posterior TOWARD the prior, not away",
          hi.posterior > lo.posterior, True)
    check("  ...which the spec's `lr * (1-amb)` got backwards",
          round((0.1 * 0.2 * 0.6) / ((0.1 * 0.2 * 0.6) + 0.4), 3) < 0.13, True)
    check("no evidence → maximum entropy", round(Belief("x").entropy, 3), 1.0)
    check("certainty → zero entropy",
          round(Belief("x", posterior=0.999999).entropy, 3), 0.0)

    # ── grounding in the corpus ──────────────────────────────────────
    today = BeliefState(raw)
    t = today.assess("PoSH requires an IC", sections=[4], citation="s.4(1), PoSH Act 2013")
    check("unverified corpus → abstain", today.should_abstain("PoSH requires an IC")[0], True)
    check("  ...and every step names its source",
          all("from " in line for line in t.explain()), True)

    after = BeliefState(verified)
    a = after.assess("PoSH requires an IC", sections=[4], citation="s.4(1), PoSH Act 2013")
    check("lawyer-verified corpus → answerable",
          after.should_abstain("PoSH requires an IC")[0], False)
    check("  ...credence rose", a.posterior > t.posterior, True)

    inferred = BeliefState(verified).assess(
        "PoSH applies at ten workers", sections=[6],
        citation="s.6(1), PoSH Act 2013 (inferred — s.4 states no threshold)")
    check("an inferred reading scores below a verbatim one",
          inferred.posterior < a.posterior, True)

    edge = BeliefState(verified)
    edge.assess("interns count", sections=[2], question="do interns count toward the ten?")
    check("edge case abstains even on a fully verified corpus",
          edge.should_abstain("interns count")[0], True)

    absent = BeliefState(verified).assess("s.99 says something", sections=[99])
    check("a section we do not hold scores near zero", absent.posterior < 0.1, True)

    print("\n  Worked example — the s.4 claim on today's corpus:")
    for line in t.explain():
        print(f"    {line}")
    print(f"    abstain: {today.should_abstain('PoSH requires an IC')[1][:78]}")

    print(f"\n{'all passed' if not failures else f'{failures} FAILED'}")
    raise SystemExit(1 if failures else 0)
