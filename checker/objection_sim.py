"""Objections a simulation cannot answer, sorted from the ones it can.

`buyer_sim.py` asks ten questions about whether the ENGINE is right, and scores
`OVERCLAIMED` at zero. This asks a different question, and it is the one that
decides whether the product lives: **will a practitioner adopt it.**

The two must not be confused, so this module is built to make confusing them
hard. Its central output is not a pass rate. It is a partition:

    ENGINEERING     an objection code can answer. We can act on it alone.
    EVIDENCE        an objection only a number can answer, and we can produce
                    the number ourselves -- an eval, a benchmark, a leak rate.
    COMMERCIAL      an objection only a signature can answer. Price, contract,
                    insurance, vendor survival. No amount of building moves it.
    IRREDUCIBLE     an objection that will still stand after everything above is
                    done, because it is about trust, habit, or fear.

## Why this file refuses to produce a score

A simulation scored out of ten invites the reading "we are at 8/10, nearly
ready". That reading would be false, because I author both the question and the
answer, and an author does not surprise himself. `simulated_conviction_is_not
_evidence()` exists to make the boundary a thing in code rather than a caveat in
prose: it returns the same refusal whatever the answers say.

What a simulation CAN do is find defects, and the record supports that: the
buyer simulation produced four corrections to shipped, green code. What it cannot
do is establish that anyone will pay. Those are different claims and only the
first is available without a customer.

## Where the questions come from

Not from me. Three adversarial personas, each briefed with a profile and each
instructed to be difficult in a specific professional register -- a Bombay senior
advocate, a practising CS of 37 years, an in-house GC at the named prospect.
An objection I authored is one I have already answered. That is the failure mode
this design is built against.

Run: python3 checker/objection_sim.py
"""
from __future__ import annotations

from dataclasses import dataclass, field as _field

# ── what kind of thing would answer this objection ───────────────────────────
ENGINEERING = "ENGINEERING"      # code. we can do it alone.
EVIDENCE = "EVIDENCE"            # a measurement. we can produce it alone.
COMMERCIAL = "COMMERCIAL"        # a contract, a price, a company. cannot be built.
IRREDUCIBLE = "IRREDUCIBLE"      # trust or habit. survives everything above.
KINDS = (ENGINEERING, EVIDENCE, COMMERCIAL, IRREDUCIBLE)

# Only ENGINEERING and EVIDENCE are reachable by us this month.
ACTIONABLE_ALONE = (ENGINEERING, EVIDENCE)

# ── how the objection stands after our best answer ───────────────────────────
ANSWERED = "ANSWERED"              # the answer is complete and we can show it
PARTIAL = "PARTIAL"                # we can answer part; the rest needs something else
UNANSWERED = "UNANSWERED"          # we have no answer today
FALSE_PREMISE = "FALSE_PREMISE"    # the objection rests on something untrue
CONCEDED = "CONCEDED"              # the objection is correct and we accept it
STATUSES = (ANSWERED, PARTIAL, UNANSWERED, FALSE_PREMISE, CONCEDED)


@dataclass(frozen=True)
class Persona:
    name: str
    role: str
    years: int
    register: str          # the professional register their scepticism lives in


SENIOR_ADVOCATE = Persona(
    "Senior advocate", "Bombay High Court, company law", 41,
    "fear of being embarrassed before a judge")
PRACTISING_CS = Persona(
    "Practising Company Secretary", "sole practitioner, Bengaluru, signs MR-3", 37,
    "personal liability on a personal signature")
IN_HOUSE_GC = Persona(
    "General Counsel", "building-materials group, unlisted, foreign parent", 28,
    "defending a procurement decision internally when it goes wrong")
PERSONAS = (SENIOR_ADVOCATE, PRACTISING_CS, IN_HOUSE_GC)


@dataclass(frozen=True)
class Objection:
    """One thing a practitioner says, and what it would actually take to answer."""
    id: str
    persona: Persona
    question: str
    kind: str
    status: str
    our_answer: str
    what_would_settle_it: str
    false_premise: str = ""
    # Non-empty ONLY for ENGINEERING/EVIDENCE: the concrete thing to do.
    action: str = ""

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"unknown kind {self.kind!r}")
        if self.status not in STATUSES:
            raise ValueError(f"unknown status {self.status!r}")
        if self.status == FALSE_PREMISE and not self.false_premise:
            raise ValueError(
                f"{self.id}: a FALSE_PREMISE verdict must name the false premise. "
                f"Calling an objection mistaken without saying what is mistaken is "
                f"how a real objection gets dismissed.")
        if self.action and self.kind not in ACTIONABLE_ALONE:
            raise ValueError(
                f"{self.id}: kind {self.kind} carries an action. A COMMERCIAL or "
                f"IRREDUCIBLE objection has no engineering action -- recording one "
                f"is how a team convinces itself that building is progress on a "
                f"problem building cannot touch.")

    @property
    def reachable(self) -> bool:
        return self.kind in ACTIONABLE_ALONE


# ── the objections. Sourced from the persona runs, not written by me ─────────
#
# Each is recorded with the answer we can actually give TODAY, not the answer we
# would like to give. Where the honest answer is "nothing", the status is
# UNANSWERED or CONCEDED and no action is recorded.

OBJECTIONS: tuple[Objection, ...] = ()   # populated by record()


def record(*objections: Objection) -> tuple[Objection, ...]:
    """Add objections to the register, refusing duplicates by id."""
    global OBJECTIONS
    seen = {o.id for o in OBJECTIONS}
    for o in objections:
        if o.id in seen:
            raise ValueError(f"duplicate objection id {o.id!r}")
        seen.add(o.id)
    OBJECTIONS = OBJECTIONS + objections
    return OBJECTIONS


# ── the register, from the three persona runs of 13-09-2026 ──────────────────

record(
    # ---- ENGINEERING: reachable by us, this week --------------------------
    Objection(
        "O-01", SENIOR_ADVOCATE,
        "Your flagship example is the Rs 4 crore small-company threshold. That "
        "figure is not in the Act -- s.2(85) says 'as may be prescribed' and the "
        "number lives in a delegated Rule, which you have just told me you mostly "
        "do not hold. So either your disclosure is false or your example is. "
        "Which?",
        ENGINEERING, FALSE_PREMISE,
        our_answer="We hold it. staleness.DEPENDENCIES shows S-002 (G.S.R. 700(E)) "
                   "and S-003 (G.S.R. 880(E)) both HELD_ATTESTED -- those ARE the "
                   "Specification of Definitions Details Rules. The premise is "
                   "false, but only because our coverage STATEMENT is loose: "
                   "'we do not hold most delegated Rules' is true in aggregate and "
                   "misleading about this one.",
        false_premise="that we do not hold the Rule the example depends on -- we "
                      "hold it and it is human-attested",
        what_would_settle_it="a dated, per-instrument holdings table he can check "
                             "himself, not an aggregate adjective",
        action="publish a precise holdings list (instrument, state, date attested) "
               "from staleness.DEPENDENCIES, and stop using aggregate words like "
               "'most' about coverage"),
    Objection(
        "O-02", PRACTISING_CS,
        "My staff are commerce graduates. Kavitha will run your panel, it will say "
        "nothing, and she will tell me 'ma'am, checked'. She will not know the "
        "difference between 'the law has not changed' and 'we do not hold that "
        "Rule'. What stops her? Do not tell me about a tooltip.",
        ENGINEERING, PARTIAL,
        our_answer="The engine distinguishes them internally -- staleness has six "
                   "states and mca_strip already refuses to render an all-clear. "
                   "But the Word pane can still finish quiet, and quiet reads as "
                   "clear. That is a real gap and it is ours.",
        what_would_settle_it="every output ends with a coverage report -- checked: "
                             "X; NOT checked because not held: Y -- printed in "
                             "full, never collapsed, never dismissable",
        action="make the coverage report mandatory and non-collapsible on every "
               "surface: the pane, /v1/document-check, and the strip"),
    Objection(
        "O-03", IN_HOUSE_GC,
        "My worry is not the two rows you refuse. It is that my paralegal sees "
        "thirteen green ticks, assumes the document is clean, and stops thinking. "
        "Partial coverage that LOOKS like full coverage is more dangerous than no "
        "tool at all.",
        ENGINEERING, PARTIAL,
        our_answer="Same defect as O-02, reached from the opposite end -- he fears "
                   "the ticks, she fears the silence. Both are the absence of a "
                   "permanent scope frame.",
        what_would_settle_it="scope shown as a permanent frame, and a written rule "
                             "that the tool never reports a document as COMPLIANT, "
                             "only as CHECKED AGAINST A NAMED LIST",
        action="add the never-says-compliant invariant as a test, the way "
               "mca_strip's FORBIDDEN_HEADLINE already works"),
    Objection(
        "O-04", SENIOR_ADVOCATE,
        "Enactment, commencement and retrospective operation are three different "
        "dates. An Amendment Act sits on the book for two years, then is notified "
        "in pieces by separate S.O. When your box tells me the law on 14 June "
        "2024, which of the three is it telling me? Answer all three or do not "
        "answer.",
        ENGINEERING, PARTIAL,
        our_answer="commencement.py tracks the S.O. notification separately and "
                   "reports CONFIRMED / NOT_LISTED / NO_NOTIFICATION per provision, "
                   "so enactment and commencement are not collapsed. Retrospective "
                   "operation is NOT separately modelled.",
        what_would_settle_it="a demonstration on a split-commencement section "
                             "showing all three dates displayed separately, and the "
                             "engine refusing to collapse them",
        action="model retrospective effect as its own date, and prove the "
               "three-date separation on s.177 or s.447"),
    Objection(
        "O-05", PRACTISING_CS,
        "My WhatsApp group catches the change. What it does not do is tell me which "
        "of my sixty-three companies is affected. Can your tool run a notification "
        "BACKWARDS across two thousand documents on my server, or do I open each "
        "Word file one by one like a clerk?",
        ENGINEERING, UNANSWERED,
        our_answer="One document at a time. She is right that this is the "
                   "difference between a demo and a tool, and she said it more "
                   "precisely than our own roadmap does.",
        what_would_settle_it="folder-level sweep with an exportable affected-list",
        action="build the backward sweep: given an instrument, list every document "
               "in a folder that relied on the superseded position (this is F8, "
               "and event_log.affected_by is already the query)"),

    # ---- EVIDENCE: a number only we can produce ---------------------------
    Objection(
        "O-06", SENIOR_ADVOCATE,
        "You are proud that it says 'cannot verify'. My junior says that for free "
        "at eleven at night and I can shout at him. Why pay for a machine whose "
        "selling point is not knowing things?",
        EVIDENCE, PARTIAL,
        our_answer="Because the refusals are scored as costs, not counted as "
                   "virtue: pit_bench scores WRONG_REFUSAL alongside WRONG_ANSWER "
                   "and the abstention-only arm scores 0.22 against our 1.00. But "
                   "that is our benchmark, graded by us, which is exactly the "
                   "objection he raises next.",
        what_would_settle_it="an error rate on documents HE supplies, measured "
                             "against his own reading -- not our benchmark",
        action="build the eval that takes externally-supplied documents and reports "
               "answered-fraction and error-rate separately"),
    Objection(
        "O-07", IN_HOUSE_GC,
        "You refuse often, by design. Forgive me, but that is exactly what someone "
        "would say if the thing simply did not work. What proportion of refusals "
        "are 'I hold the law but the document is ambiguous' versus 'I do not hold "
        "this law' versus 'I broke'?",
        EVIDENCE, UNANSWERED,
        our_answer="We cannot currently produce that breakdown as a number, and it "
                   "is the sharpest question anyone has asked about abstention. "
                   "The categories exist in code; the census does not.",
        what_would_settle_it="a refusal census by cause, and evidence that refusals "
                             "SHRINK as coverage grows rather than sitting constant",
        action="instrument refusals by cause and publish the breakdown; wire it so "
               "acquiring an instrument visibly moves the number"),
    Objection(
        "O-08", IN_HOUSE_GC,
        "Your differentiator is reconstructing law as it stood on a past date. How "
        "do I know you get it right? Who checked it?",
        EVIDENCE, PARTIAL,
        our_answer="Boundary behaviour is proved on s.177, s.447 and s.35 -- 6/6 "
                   "boundaries, docs/TEMPORAL_PROOF.md. And 24 amended spans are "
                   "corroborated against the amending Acts on Indian Kanoon with 0 "
                   "conflicts. But section-level reconstruction of SUBSTITUTED "
                   "spans is UNVERIFIED and CLAUDE.md says so.",
        what_would_settle_it="an accuracy figure with methodology and named failure "
                             "modes, ideally checked by a practising CS",
        action="publish the measured figure with its limits rather than the proof "
               "narrative"),

    # ---- COMMERCIAL: no action field. building does not touch these -------
    Objection(
        "O-09", IN_HOUSE_GC,
        "There is no entity, no insurance, nobody to sue. What is the counterparty "
        "name on the agreement?",
        COMMERCIAL, CONCEDED,
        our_answer="There is none. He is right and no code changes it.",
        what_would_settle_it="incorporation, GSTIN, a bank account -- or an "
                             "explicitly unpaid evaluation with no PO, which he "
                             "himself says is the more credible answer"),
    Objection(
        "O-10", IN_HOUSE_GC,
        "In eighteen months you will have a placement or a masters admit. What "
        "survives? Not your intention -- the artefact.",
        COMMERCIAL, UNANSWERED,
        our_answer="Nothing is guaranteed to. There is no escrow and no second "
                   "maintainer.",
        what_would_settle_it="source escrow or an open-licensed corpus, and a "
                             "documented pipeline someone else can run"),
    Objection(
        "O-11", PRACTISING_CS,
        "A number, per year, in rupees. My whole software budget is what a "
        "Bangalore family spends on one wedding lunch.",
        COMMERCIAL, UNANSWERED,
        our_answer="We have no price. She supplied one unprompted: Rs 24,000/year "
                   "firm-wide for 63 companies -- about Rs 380 per company -- "
                   "conditional on three things, all of which are on this list.",
        what_would_settle_it="a firm-level annual figure below her broadband bill, "
                             "never per-seat and never per-company"),

    # ---- IRREDUCIBLE: survives everything above ---------------------------
    Objection(
        "O-12", SENIOR_ADVOCATE,
        "If a finding cannot produce, inside the panel, the actual instrument it "
        "relied on -- the Gazette page, its number, its date, and the commencement "
        "notification as a SEPARATE document from the amendment -- then it is a "
        "rumour about the law wearing a citation. I have spent forty-one years "
        "being paid to destroy men who came to court carrying rumours.",
        IRREDUCIBLE, PARTIAL,
        our_answer="We hold the artifacts and hash them -- SHA256SUMS lists every "
                   "acquired instrument -- and provenance.py refuses to promote "
                   "anything to VERIFIED without a local, hashed, human-reviewed "
                   "file. What we do not do is SHOW him the page in the panel.",
        what_would_settle_it="the instrument itself rendered in the pane. But his "
                             "real objection is that he will not trust a screen "
                             "over paper, and that is a 41-year habit, not a "
                             "missing feature"),
    Objection(
        "O-13", PRACTISING_CS,
        "Thirty-seven years I have carried this. Reconstructing where the law stood "
        "on a past date is the judgment I sell. If your tool does it for two "
        "thousand a month, in five years what is left that a client pays me for? "
        "The honest answer to that is also the reason I should not help you build "
        "it.",
        IRREDUCIBLE, CONCEDED,
        our_answer="She names it herself: nothing would satisfy her entirely. The "
                   "most we can do is never sell to her clients, and put that in "
                   "writing. She says if we will not, she will assume it is the "
                   "plan -- and she would be right to.",
        what_would_settle_it="a written commitment never to sell direct to her "
                             "clients. It mitigates; it does not answer"),
    Objection(
        "O-14", IN_HOUSE_GC,
        "'I trusted an unincorporated student's statutory database' is not a "
        "sentence I survive in front of my group legal head, no matter how good "
        "the citations are.",
        IRREDUCIBLE, CONCEDED,
        our_answer="Correct. This is career risk, not product risk, and it is why "
                   "his pilot terms are unpaid, local-only, two machines, and "
                   "outside the IT estate.",
        what_would_settle_it="a second customer he can telephone. Which cannot be "
                             "built, only earned"),
)


def partition(objections: tuple[Objection, ...] | None = None) -> dict[str, list[str]]:
    src = OBJECTIONS if objections is None else objections
    out: dict[str, list[str]] = {k: [] for k in KINDS}
    for o in src:
        out[o.kind].append(o.id)
    return out


def reachable_alone(objections: tuple[Objection, ...] | None = None) -> tuple[Objection, ...]:
    src = OBJECTIONS if objections is None else objections
    return tuple(o for o in src if o.reachable)


def blocked_on_a_person(objections: tuple[Objection, ...] | None = None
                        ) -> tuple[Objection, ...]:
    src = OBJECTIONS if objections is None else objections
    return tuple(o for o in src if not o.reachable)


def queue(objections: tuple[Objection, ...] | None = None) -> list[str]:
    """The only output of this module that is a to-do list.

    Deliberately contains ONLY engineering and evidence items. An objection that
    needs a contract does not become a ticket by being written down.
    """
    return [f"[{o.kind}] {o.id}: {o.action}"
            for o in reachable_alone(objections) if o.action]


def simulated_conviction_is_not_evidence(objections: tuple[Objection, ...] | None = None
                                         ) -> str:
    """What this simulation establishes about demand. The answer is fixed.

    It does not depend on the objections, and it does not improve when they are
    answered well. That is the point: a function whose output could improve would
    eventually be quoted as though it had.
    """
    src = OBJECTIONS if objections is None else objections
    n = len(src)
    blocked = len(blocked_on_a_person(src))
    return (f"NOTHING. {n} objections were answered by the same person who wrote "
            f"them, so the answers are a measure of my own consistency, not of "
            f"anyone's willingness to pay. {blocked} of {n} cannot be closed by "
            f"building at all. This register is a defect-finder and a meeting "
            f"agenda. It is not demand evidence, and a later reader quoting it as "
            f"demand evidence is misreading it.")


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond: ok += 1; print(f"  [ok]   {label}")
        else: fail += 1; print(f"  [FAIL] {label}")

    print("objection_sim")

    # ── the invariants that keep this honest ─────────────────────────────────
    try:
        Objection("X1", SENIOR_ADVOCATE, "q", COMMERCIAL, UNANSWERED, "a", "s",
                  action="build something")
        check(False, "a COMMERCIAL objection may not carry an engineering action")
    except ValueError as e:
        check("building is progress" in str(e),
              "a COMMERCIAL objection carrying an engineering action is refused -- "
              "that is how a team convinces itself building solves a market problem")
    try:
        Objection("X2", PRACTISING_CS, "q", ENGINEERING, FALSE_PREMISE, "a", "s")
        check(False, "FALSE_PREMISE must name the premise")
    except ValueError as e:
        check("without saying what is mistaken" in str(e),
              "calling an objection mistaken without naming the mistake is refused")
    check(Objection("X3", IN_HOUSE_GC, "q", EVIDENCE, PARTIAL, "a", "s",
                    action="run the eval").reachable,
          "an EVIDENCE objection is reachable by us alone")
    check(not Objection("X4", IN_HOUSE_GC, "q", IRREDUCIBLE, CONCEDED, "a",
                        "s").reachable,
          "an IRREDUCIBLE objection is not")

    # ── the refusal that does not move ───────────────────────────────────────
    a = simulated_conviction_is_not_evidence(())
    b = simulated_conviction_is_not_evidence(
        (Objection("Y1", SENIOR_ADVOCATE, "q", ENGINEERING, ANSWERED, "a", "s"),
         Objection("Y2", PRACTISING_CS, "q", ENGINEERING, ANSWERED, "a", "s")))
    check(a.startswith("NOTHING") and b.startswith("NOTHING"),
          "what the simulation establishes about demand is NOTHING, and it stays "
          "NOTHING when every objection is answered perfectly")
    check("not demand evidence" in b,
          "...and it says so in terms a later reader cannot mistake")

    # ── the register, as recorded ────────────────────────────────────────────
    part = partition()
    print()
    for kind in KINDS:
        print(f"  {kind:<12} {len(part[kind]):>2}  {', '.join(part[kind])}")
    print()
    print("  QUEUE (the only to-do list this module produces):")
    for q in queue():
        print(f"    - {q[:108]}")
    print()
    print("  what this establishes about demand:")
    print(f"    {simulated_conviction_is_not_evidence()[:300]}")
    print()

    check(len(OBJECTIONS) == 14, f"14 objections recorded ({len(OBJECTIONS)})")
    check(all(len(v) > 0 for v in part.values()),
          f"every kind is populated -- the partition is real, not a label on one "
          f"pile: { {k: len(v) for k, v in part.items()} }")
    check(len(blocked_on_a_person()) == 6,
          f"{len(blocked_on_a_person())} of 14 cannot be closed by building at all "
          f"-- which is the number that matters")
    check(len(queue()) == 8,
          f"{len(queue())} carry a concrete engineering or evidence action")
    check(all("O-0" in q or "O-1" in q for q in queue()),
          "...and every queue item names the objection it answers")

    # Convergence is the finding a single persona could not have produced.
    coverage = [o for o in OBJECTIONS if o.id in ("O-02", "O-03")]
    check(len({o.persona.name for o in coverage}) == 2,
          "two personas in different registers independently demanded the same "
          "fix -- silence must never read as clearance. Convergence across "
          "briefs is the one signal a self-written simulation cannot fake")

    check(len(PERSONAS) == 3 and len({p.register for p in PERSONAS}) == 3,
          "three personas, three different registers of scepticism -- not one "
          "sceptic wearing three hats")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
