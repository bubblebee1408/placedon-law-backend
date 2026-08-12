"""
The question pipeline: retrieve → route → epistemic gate → generate → enforce.

This wires `epistemic_status.py` to something a user can actually reach. The lattice has existed
for a day and nothing user-facing consumed it; a machine for representing uncertainty that nobody
sees is a machine for nothing.

## The routing decision, which is the substance

Not every question is a question. **"Do I need an Internal Committee?"** is a *deduction* — the
Act sets a condition, the company told us its headcount, and `applicability.py` reads the Act.
Sending that to a language model would be asking a probabilistic system to redo arithmetic that
is already settled, and it is exactly how a wrong answer gets a confident voice.

**"What does section 19 require?"** is genuinely a question about text. That one is worth
generating an explanation for — if, and only if, the text is verified enough to quote.

So the engine routes before it retrieves. Deduction goes to code. Exposition goes to the corpus,
through a gate.

## Three departures from the spec this was built from

**The dependency graph is not hand-authored.** The spec says to inline four edges — s.4→s.26,
s.4→s.19, s.4→s.21, s.2→s.4. `provision_graph.py` already extracts them from the statute's own
cross-references and finds far more, each carrying the sentence that proves it. Four hand-typed
edges would be a regression from a derived graph to somebody's memory of the Act.

**No HIGH/MEDIUM/LOW confidence tiers.** Those were deleted deliberately: calibrating them needs
a labelled validation set we do not have, and at the sample sizes available the target sits below
the resolution of the instrument. The response carries the **epistemic status** instead —
`UNCHECKED`, `INFERRED`, `QUOTED` — which is an ordinal fact about the corpus, not an estimate.

**Abstention names the weakest link, not a list.** "Provisions not verified: [s.4, s.16]" tells a
user nothing they can act on. "s.4 rests on unverified s.16" tells them what would have to change.

Run: python3 checker/ask_engine.py
"""
from __future__ import annotations

import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from checker import retrieval, verifier                      # noqa: E402
from checker import distress, register  # noqa: E402
from checker.path_validity import PathTracer  # noqa: E402
from checker.epistemic_status import EpistemicState, Status  # noqa: E402

# Questions that are deductions, not requests for exposition. These must never reach a model:
# the Act states a condition and the company stated its facts, so the answer is computed.
APPLICABILITY = (
    r"\bdo(?:es)?\s+(?:this|it|posh|the act|any of this)?\s*apply\b",
    r"\bdo\s+(?:i|we)\s+(?:need|have to|require)\b",
    r"\bam\s+i\s+(?:covered|required|liable|compliant)\b",
    r"\bare\s+we\s+(?:covered|required|liable|compliant|exempt)\b",
    r"\bis\s+(?:it|this)\s+(?:mandatory|compulsory|required)\b",
    r"\bwhat\s+(?:do|must)\s+(?:i|we)\s+(?:need|have)\s+to\s+do\b",
)


@dataclass
class Answer:
    """What the caller gets. `answer` is None whenever `abstained` is True — never both."""

    answer: str | None = None
    abstained: bool = True
    reason: str = ""
    route: str = "corpus"                       # "deterministic" | "corpus" | "none"
    status: str = Status.UNSUPPORTED.name       # the lattice, not a confidence tier
    sources: list[dict] = field(default_factory=list)
    epistemic_chain: list[dict] = field(default_factory=list)
    cost_inr: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "abstained": self.abstained,
            "reason": self.reason,
            "route": self.route,
            "status": self.status,
            "sources": self.sources,
            "epistemic_chain": self.epistemic_chain,
            "cost_inr": round(self.cost_inr, 4),
        }


def is_applicability_question(question: str) -> bool:
    q = " ".join(question.lower().split())
    return any(re.search(p, q) for p in APPLICABILITY)


class AskEngine:
    """
    Retrieval, routing, the epistemic gate, generation, and post-hoc enforcement.

    `generate` is injected rather than imported so the tests can drive the enforcement path
    without a model running. Default is the real gateway.
    """

    def __init__(self, *, provisions: list[dict] | None = None,
                 generate: Callable[[str, list[dict], dict], Any] | None = None,
                 top_k: int = 3) -> None:
        self._provisions = provisions
        self._top_k = top_k
        self._generate = generate
        self._state = EpistemicState(provisions)
        self._tracer = PathTracer(provisions)

    # ── the pipeline ─────────────────────────────────────────────────────

    # Questions the register can speak to. Deliberately narrow: the register knows one thing,
    # and applying it to a question it does not govern would be its own kind of fabrication.
    _RETURN_Q = re.compile(r"annual (?:return|report)|file the (?:return|report)|"
                           r"filing deadline|when is .*(?:return|report) due", re.I)

    def _register_note(self, question: str, context: dict) -> tuple[str, dict | None]:
        """District-specific provenance for the annual-return question, or nothing at all."""
        if not self._RETURN_Q.search(question):
            return "", None
        districts = context.get("districts") or []
        if not districts:
            return ("No date is prescribed in the PoSH Rules — the District Officer sets it for "
                    "each district. Tell us your district and we will tell you what yours has "
                    "said, or that we are still waiting."), None
        try:
            sentence, source = register.describe(districts[0])
        except (register.UnknownDistrict, ValueError):
            # Loud in the log, silent to the user: a district we do not hold is not a licence to
            # invent one, and it is not the user's problem to solve.
            logging.warning("register.describe failed for %r", districts[0], exc_info=True)
            return "", None
        return sentence, ({"kind": "district_officer_reply", **source} if source else None)

    def ask(self, question: str, context: dict | None = None) -> Answer:
        context = context or {}

        if not question or len(question.strip()) < 8:
            return Answer(reason="That question was too short for us to work with.", route="none")

        # BEFORE routing, retrieval, the epistemic gate and any model call.
        #
        # If the person asking is the person it happened to, a better citation is the wrong
        # output. This hands over to s.6, her District Officer by name, and SHe-Box — and it
        # runs while verified_by is null, so it works today when everything else abstains.
        # Nothing in it is generated: every sentence is statutory text or a directory entry.
        ref = distress.route(question, (context.get("districts") or [None])[0])
        if ref.triggered:
            sources = [{"section": ref.statutory_route["citation"],
                        "heading": "Constitution and jurisdiction of Local Committee",
                        "text": ref.statutory_route["quote"], "verified_by": None}] \
                if ref.statutory_route else []
            return Answer(
                abstained=True, route="referral", status=Status.QUOTED.name,
                # Contacts first, statute second. The module orders its own contacts so a human
                # comes before a form; that ordering was being silently undone here by putting
                # the s.6 quote at the top. For a compliance answer the citation leads. For a
                # referral the citation is the justification, and the phone number is the answer.
                reason=ref.message, sources=[*ref.contacts, *sources], cost_inr=0.0,
                epistemic_chain=[{"ground": "routed to a human, not answered",
                                  "status": "REFERRAL", "source": ref.matched}],
            )

        # 1. Route. A deduction must not reach a model.
        if is_applicability_question(question):
            return Answer(
                abstained=True, route="deterministic",
                reason=("This is a question our rules engine answers, not our language model. "
                        "Run the free check — it reads the Act and your headcount directly, and "
                        "it does not guess."),
            )

        # 2. Retrieve.
        provisions, stage = self._retrieve(question)
        if not provisions:
            return Answer(reason="No relevant provisions found. We only answer where we hold "
                                 "the text, and nothing in our corpus addresses this.",
                          route="none")

        # 3. The epistemic gate — weakest link across every retrieved provision AND its
        #    dependencies, which provision_graph derives from the statute's cross-references.
        sections = [p["section_number"] for p in provisions]
        citation = provisions[0].get("citation", "")
        claim = self._state.assess(question, sections=sections, citation=citation,
                                   question=question)
        chain = [{"ground": g.reason, "status": g.status.name, "source": g.source}
                 for g in sorted(claim.grounds, key=lambda g: g.status)]
        sources = [{"section": p.get("citation", f"s.{p['section_number']}"),
                    "heading": p.get("heading", ""),
                    "text": " ".join((p.get("text_display") or "").split())[:600],
                    "verified_by": p.get("verified_by")} for p in provisions]

        # Two tests the lattice cannot perform, both from Falkor-IRAC (arXiv 2605.14665).
        #
        # The lattice composes weakest-link across a SET of grounds — it asks whether each one is
        # verified. It cannot ask whether the retrieved sections actually REACH the provision the
        # claim rests on, and it cannot notice two of them contradicting each other, because
        # weakest-link is monotone and a contradiction just resolves to the weaker.
        #
        # A conflict is reported even when the answer would otherwise be given. s.9 grants three
        # months to complain and its proviso extends that to six; an answer quoting one without
        # the other is wrong in the direction that costs a complainant her remedy.
        found = self._tracer.conflicts(sections)
        if found:
            chain = [*chain, *({"ground": c.detail, "status": "CONFLICT",
                                "source": f"s.{c.sections[0]}"} for c in found)]

        # An abstention that names its blocker is better than one that names a status; an
        # abstention that shows the ROUTE to its blocker is better still, because the reader can
        # check it. "We cannot state the penalty" is an assertion. "We cannot state the penalty
        # because s.26(1)(a) attaches it to failing the s.4 duty, and nobody has verified s.4" is
        # a chain of authority, which is how a lawyer would have to justify the same refusal.
        for blocker in self._state.graph.blocked_by(sections[0]) if hasattr(
                self._state, "graph") else self._tracer.graph.blocked_by(sections[0]):
            if blocker in sections:
                continue                          # retrieved already; the chain covers it
            path = self._tracer.trace(sections, blocker)
            if path.reached and path.hops:
                hop = path.hops[-1]
                quote = " ".join((hop.evidence or "").split())[:150]
                chain = [*chain, {
                    "ground": (f"rests on s.{blocker}, reached from s.{hop.frm} via the Act's own "
                               f"words: “{quote}”"),
                    "status": "PATH", "source": f"s.{blocker}"}]

        if not claim.status.answerable:
            weakest = claim.weakest
            reason = (f"We will not answer this yet. {weakest.reason}."
                      if weakest else "We will not answer this yet.")
            # An abstention that shows its work beats one that does not. For the annual-return
            # question specifically, the reason we cannot answer is not our own ignorance — it is
            # that no date is prescribed nationally and the District Officer sets it. Saying that,
            # and saying whether we have asked, is more useful than a bare status and is the one
            # thing no competitor can currently say.
            note, source = self._register_note(question, context)
            if note:
                reason = f"{reason} {note}"
                if source:
                    sources = [*sources, source]
            return Answer(
                abstained=True, route="corpus", status=claim.status.name,
                sources=sources, epistemic_chain=chain, reason=reason,
            )

        # 4. Generate. Only reachable once the chain is verified.
        try:
            result = self._call_model(question, provisions, context)
        except Exception as exc:                              # noqa: BLE001
            return Answer(abstained=True, route="corpus", status=claim.status.name,
                          sources=sources, epistemic_chain=chain,
                          reason=f"We could not draft an answer just now ({type(exc).__name__}).")
        if getattr(result, "degraded", False):
            return Answer(abstained=True, route="corpus", status=claim.status.name,
                          sources=sources, epistemic_chain=chain,
                          reason="The explanation service is unavailable. Nothing was charged.")

        text = (result.text or "").strip()
        cost = float(getattr(result, "cost_inr", 0.0) or 0.0)

        # 5. Post-hoc enforcement. Numbers must appear in source; citations must resolve,
        #    sub-clauses included; advice language and uncited assertions are rejected.
        verdict = verifier.should_abstain(question, provisions, text,
                                          state=str(context.get("state", "")))
        if verdict.abstained:
            detail = []
            if verdict.unsupported_numbers:
                detail.append(f"figures not in the source text: "
                              f"{', '.join(verdict.unsupported_numbers)}")
            if verdict.unresolved_citations:
                detail.append(f"sections we did not retrieve: "
                              f"{', '.join(verdict.unresolved_citations)}")
            return Answer(
                abstained=True, route="corpus", status=claim.status.name,
                sources=sources, epistemic_chain=chain, cost_inr=cost,
                reason=("Our own check rejected the drafted answer before you saw it"
                        + (f" — {'; '.join(detail)}." if detail else f". {verdict.reason}")),
            )

        return Answer(answer=text, abstained=False, route="corpus", status=claim.status.name,
                      reason="", sources=sources, epistemic_chain=chain, cost_inr=cost)

    # ── seams ────────────────────────────────────────────────────────────

    def _retrieve(self, question: str) -> tuple[list[dict], str]:
        if self._provisions is None:
            return retrieval.retrieve(question, top_k=self._top_k)
        by_num = {p["section_number"]: p for p in self._provisions}
        routed = retrieval.keyword_route(question) or ()
        hits = [by_num[n] for n in routed if n in by_num][:self._top_k]
        if hits:
            return hits, "keyword"
        # Same relevance floor as retrieval.retrieve(). Duplicating the threshold would let the
        # injected-corpus path drift from production behaviour, so the constant is imported.
        scored = sorted(((retrieval._score(question, p), p) for p in self._provisions),
                        key=lambda x: x[0], reverse=True)
        hits = [p for s, p in scored[:self._top_k] if s >= retrieval.SCAN_FLOOR]
        return hits, "scan" if hits else "none"

    def _call_model(self, question: str, provisions: list[dict], context: dict):
        if self._generate is not None:
            return self._generate(question, provisions, context)
        from backend.services.llm import explain_provisions   # noqa: PLC0415
        return explain_provisions(question, provisions, context)


# ─────────────────────────────── tests ───────────────────────────────
if __name__ == "__main__":
    import json

    CORPUS = Path(__file__).resolve().parent.parent / "corpus/provisions/posh_act_2013.json"
    raw = json.loads(CORPUS.read_text())["provisions"]
    verified = [{**p, "verified_by": "Adv. Test"} for p in raw]

    failures = 0

    def check(name: str, got, want) -> None:
        global failures
        ok = got == want
        failures += (not ok)
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + ("" if ok else f"  got={got!r}"))

    class Reply:
        def __init__(self, text, cost=0.97, degraded=False):
            self.text, self.cost_inr, self.degraded = text, cost, degraded

    # A4 — routing. The most important test here: a deduction never reaches a model.
    called = []
    router = AskEngine(provisions=verified,
                       generate=lambda q, p, c: called.append(q) or Reply("should not run"))
    for q in ("Do I need an Internal Committee?", "Does PoSH apply to us?",
              "Are we required to have a policy?", "Is it mandatory for a 12-person company?"):
        a = router.ask(q)
        check(f"A4 routed to code, not the model: {q[:38]!r}", a.route, "deterministic")
    check("A4   ...and the model was never called", called, [])

    check("exposition is NOT routed away",
          AskEngine(provisions=verified,
                    generate=lambda q, p, c: Reply("Section 19 requires display [s.19].")
                    ).ask("What does section 19 require?").route, "corpus")

    # A2 — the epistemic gate, on today's real corpus.
    today = AskEngine(provisions=raw, generate=lambda q, p, c: Reply("should not run"))
    a2 = today.ask("What must the employer display at the workplace?")
    check("A2 unverified corpus → abstains", a2.abstained, True)
    check("A2   ...reason names the weakest link",
          "unverified" in a2.reason or "verified our reading" in a2.reason, True)
    check("A2   ...sources are still returned so the user can check us", len(a2.sources) > 0, True)
    check("A2   ...and the chain is exposed", len(a2.epistemic_chain) > 0, True)
    check("A2   ...nothing was spent", a2.cost_inr, 0.0)
    print(f"        → {a2.reason[:96]}")

    # A1 — the clean path.
    good = AskEngine(
        provisions=verified,
        generate=lambda q, p, c: Reply(
            "The employer must display the penal consequences of sexual harassment and the order "
            "constituting the Internal Committee at a conspicuous place [s.19]."))
    a1 = good.ask("What must the employer display at the workplace?")
    check("A1 verified corpus → answers", a1.abstained, False)
    check("A1   ...carries sources", len(a1.sources) > 0, True)
    check("A1   ...status is a lattice value, not a confidence tier",
          a1.status in {s.name for s in Status}, True)
    check("A1   ...cost recorded", a1.cost_inr > 0, True)

    # A3 — citation enforcement.
    liar = AskEngine(provisions=verified,
                     generate=lambda q, p, c: Reply("The employer must display it [s.27]."))
    a3 = liar.ask("What must the employer display at the workplace?")
    check("A3 hallucinated s.27 → abstains", a3.abstained, True)
    check("A3   ...names the section we never retrieved", "s.27" in a3.reason, True)

    numbers = AskEngine(
        provisions=verified,
        generate=lambda q, p, c: Reply("File it by 31 January each year [s.19]."))
    a3b = numbers.ask("What must the employer display at the workplace?")
    check("A3b invented '31 January' → abstains", a3b.abstained, True)
    check("A3b   ...names the figure", "31" in a3b.reason, True)

    # A5 — nothing retrieved.
    a5 = AskEngine(provisions=verified,
                   generate=lambda q, p, c: Reply("x")).ask("What is the GST rate on chocolate?")
    check("A5 empty retrieval → abstains", a5.abstained, True)
    check("A5   ...says so plainly", "No relevant provisions found" in a5.reason, True)

    # Degradation must never become an answer.
    down = AskEngine(provisions=verified,
                     generate=lambda q, p, c: Reply("unavailable", 0.0, degraded=True))
    d = down.ask("What must the employer display at the workplace?")
    check("a degraded model call is not an answer", (d.abstained, d.answer), (True, None))

    boom = AskEngine(provisions=verified,
                     generate=lambda q, p, c: (_ for _ in ()).throw(RuntimeError("boom")))
    check("a raising model call is not an answer", boom.ask("What does s.19 require?").answer,
          None)

    check("answer and abstained are never both set",
          all(x.answer is None for x in (a2, a3, a3b, a5, d)), True)

    print(f"\n{'all passed' if not failures else f'{failures} FAILED'}")
    raise SystemExit(1 if failures else 0)
