"""review_contract, end to end: a contract against a company playbook, and what it will not say.

The second intent in `agents/plans.py` that actually runs. The pieces existed; what is
added here is the order, and the two rules that decide what a reader is shown.

    checker/clauses.py       the contract, split by CODE, with offsets
    checker/router.py        which model, and whether the route is a draft
    checker/public_only.py   a customer contract may reach Azure, never the free tier
    checker/quoted_span.py   a span is in the document, or it is not evidence
    checker/playbook.py      the company standard, evaluated by pure functions
    checker/scope.py         the named refusal for law we do not hold

## Rule one: a value that cannot be re-derived from its span is UNVERIFIED

The model is asked for a clause type, a VERBATIM span, and the value read from that span.
Two things are then checked by code, in this order:

    1. the span occurs in the contract, byte for byte
    2. the value occurs in the SPAN

Both, because either alone is satisfiable by a model that is half-right in the dangerous
direction. A real span with an invented value ("term: 3 years", quoting a clause that says
five) passes (1) and fails (2), and that is the failure that would otherwise become a
confident MATCHES against a playbook maximum. An unverified value is never graded --
`playbook.evaluate` refuses it and returns NEEDS_LAWYER.

## Rule two: this reviews against a PLAYBOOK, which is not law

Every finding is a POTENTIAL_ISSUE against a company standard. The Indian Contract Act,
the Stamp Act and the Arbitration Act are DECLARED and unheld (checker/scope.py), so any
question of validity, enforceability, stamping or arbitration gets that body's named
refusal, attached to the report rather than left out of it. Silence would read as "nothing
to say about enforceability", which is the exact failure DECLARED exists to prevent.

Run: PYTHONPATH=. python3 agents/review_contract.py
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from checker import clauses as clause_split
from checker import playbook as pb
from checker import public_only, router, scope

UNVERIFIED = "UNVERIFIED"
SPAN_NOT_IN_CONTRACT = "SPAN_NOT_IN_CONTRACT"
VALUE_NOT_IN_SPAN = "VALUE_NOT_IN_SPAN"

# The bodies a contract review reaches and this corpus does not hold. Named, not implied.
UNHELD_FOR_CONTRACTS = ("CONTRACT1872", "ARBITRATION1996", "STAMP")

EXTRACT_PROMPT = (
    "You are shown a commercial contract and a list of clause types.\n"
    "For each clause type that is PRESENT, return:\n"
    "  span  - the exact words from the contract, copied verbatim\n"
    "  value - the specific term those words state (a duration, a place, an amount, a "
    "law), copied from within the span\n"
    "Omit any clause type that is absent. Do not guess and do not paraphrase.\n"
    "Answer as one JSON object mapping clause type to {{\"span\": ..., \"value\": ...}}, "
    "and nothing else.\n\nCLAUSE TYPES:\n{clauses}\n\nCONTRACT:\n{contract}\n"
)


@dataclass(frozen=True)
class Proposed:
    clause: str
    span: str
    value: str


@dataclass(frozen=True)
class Review:
    findings: tuple[pb.Finding, ...]
    extracted: tuple[pb.Extracted, ...]
    unverified: tuple[tuple[str, str], ...]        # (clause, why)
    law_notes: tuple[tuple[str, str], ...]         # (body key, its refusal)
    playbook_status: str
    route: router.Route | None = None
    clause_count: int = 0

    @property
    def requires_review(self) -> bool:
        """True whenever a person must read this before it is relied on."""
        return bool(self.route and self.route.requires_review) or \
            self.playbook_status != pb.APPROVED

    def to_dict(self) -> dict:
        return {
            "playbook_status": self.playbook_status,
            "requires_review": self.requires_review,
            "model": f"{self.route.provider}/{self.route.model}" if self.route else None,
            "clauses_in_contract": self.clause_count,
            # `standard_text` and `rationale` are what the reader is shown beside a
            # finding; without them the standard column renders blank, which is what it
            # did until 29-09-2026. `why` is deliberately NOT sent: it is the engineering
            # note on the rule's shape -- NDA-02's is a changelog about a false-alarm rate
            # -- and a lawyer's column is the wrong place for it. Both sentences are DRAFT,
            # marked by the `playbook_status` this same dict carries.
            "findings": [{"rule_id": f.rule_id, "clause": f.clause, "status": f.status,
                          "kind": f.kind, "detail": f.detail,
                          "standard_text": f.standard_text, "rationale": f.rationale}
                         for f in self.findings],
            "unverified": [{"clause": c, "why": w} for c, w in self.unverified],
            "law_not_held": [{"body": k, "refusal": r} for k, r in self.law_notes],
        }


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def parse_reply(raw: str) -> tuple[Proposed, ...]:
    """The JSON object in a reply. A reply we cannot read proposes nothing."""
    m = re.search(r"\{.*\}", raw or "", re.DOTALL)
    if not m:
        return ()
    try:
        obj = json.loads(m.group(0))
    except (ValueError, TypeError):
        return ()
    if not isinstance(obj, dict):
        return ()
    out = []
    for clause, body in obj.items():
        if isinstance(body, dict):
            span, value = body.get("span"), body.get("value")
        elif isinstance(body, str):
            span, value = body, body
        else:
            continue
        if isinstance(span, str) and span.strip():
            out.append(Proposed(str(clause), span, str(value if value is not None else "")))
    return tuple(out)


def verify(p: Proposed, contract: str) -> tuple[pb.Extracted, str | None]:
    """(extracted, why_unverified). Both checks, in order, neither sufficient alone."""
    if _norm(p.span) not in _norm(contract):
        return pb.Extracted(p.clause, p.span, p.value, verified=False), SPAN_NOT_IN_CONTRACT
    if not _norm(p.value):
        return pb.Extracted(p.clause, p.span, p.value, verified=False), VALUE_NOT_IN_SPAN
    if _norm(p.value) not in _norm(p.span):
        # The dangerous half-right case: a real quotation with an invented figure beside it.
        return pb.Extracted(p.clause, p.span, p.value, verified=False), VALUE_NOT_IN_SPAN
    return pb.Extracted(p.clause, p.span, p.value, verified=True), None


def law_notes(keys=UNHELD_FOR_CONTRACTS) -> tuple[tuple[str, str], ...]:
    """The named refusal for every body a contract reaches and we do not hold."""
    out = []
    for k in keys:
        try:
            b = scope.body(k)
        except LookupError:
            continue
        if not b.answerable:
            out.append((k, scope.refusal_for(k)))
    return tuple(out)


def extract_prompt(contract: str, clause_names, *, wrap=None) -> str:
    """The prompt, with the contract wrapped as untrusted evidence."""
    if wrap is None:
        from checker.prompt_safety import wrap_untrusted as wrap
    return EXTRACT_PROMPT.format(clauses="\n".join(f"- {c}" for c in clause_names),
                                 contract=wrap(contract, "contract"))


def review(contract: str, *, book: pb.Playbook, model=None, name: str = "contract",
           provider: str = "azure", available: tuple[str, ...] = ("azure",),
           origin=None) -> Review:
    """One contract, one playbook. `model` is a Callable[[str], str] or None.

    `origin` lets a caller pass a PUBLIC one (a specimen, a benchmark contract). Left None,
    the contract is treated as a customer document and cleared through `clear_matter`,
    which refuses any provider PLAN_22 D3 does not permit -- before a prompt is built.
    """
    split = clause_split.split(contract)
    wanted = [r.clause for r in book.rules]

    route = None
    proposed: tuple[Proposed, ...] = ()
    if model is not None:
        route = router.route(
            router.Task("review_contract", router.TEXT, router.HIGH,
                        purpose=router.EXTRACTION),
            available=available)
        if origin is None:
            origin = public_only.clear_matter(contract, name=name, provider=provider)
        proposed = parse_reply(model(extract_prompt(contract, wanted)))

    extracted, unverified = [], []
    for p in proposed:
        e, why = verify(p, contract)
        extracted.append(e)
        if why:
            unverified.append((p.clause, why))

    return Review(findings=pb.review(book, extracted),
                  extracted=tuple(extracted),
                  unverified=tuple(unverified),
                  law_notes=law_notes(),
                  playbook_status=book.status,
                  route=route,
                  clause_count=len(split))


# ── ten NDA fixtures, each with the findings it should produce ───────────────
# `proposed` is what a MODEL THAT READ THE DOCUMENT CORRECTLY would return. The offline
# test therefore measures this pipeline -- span verification, playbook grading, refusals --
# and not a model's reading. What a real model actually returns is measured separately, on
# Azure, because those are two different questions and a fixture that mixes them can only
# tell you that something went wrong.

_BASE = """MUTUAL NON-DISCLOSURE AGREEMENT

This Agreement is made on 1 April 2026 between Acme Private Limited and Beta Limited.

1. Definition of Confidential Information
"Confidential Information" means any information disclosed by one party to the other,
whether orally or in writing, that is marked confidential or would reasonably be
understood to be confidential.

2. Confidentiality Obligation
Each party shall keep the other's Confidential Information secret and shall not disclose
it to any third party without prior written consent.

3. Permitted Disclosure
A party may disclose Confidential Information to the extent required by law or by an
order of a court of competent jurisdiction.

4. Return or Destruction
On termination each party shall return or destroy all Confidential Information in its
possession.

5. Term
{term}

6. Limitation of Liability
The total liability of either party under this Agreement shall not exceed {cap}.

7. Governing Law
This Agreement is governed by the laws of {law}.

8. Jurisdiction
The courts at {seat} shall have exclusive jurisdiction.
{extra}"""


@dataclass(frozen=True)
class Fixture:
    id: str
    text: str
    proposed: dict
    expect: dict


def _nda(term="This Agreement continues for three years from the date above.",
         cap="Rs 50,00,000", law="India", seat="Mumbai", extra="") -> str:
    return _BASE.format(term=term, cap=cap, law=law, seat=seat, extra=extra)


def _without(text: str, heading: str) -> str:
    """The contract with one numbered clause cut out, heading and body together."""
    lines, out, dropping = text.splitlines(keepends=True), [], False
    for line in lines:
        if line.startswith(heading):
            dropping = True
            continue
        if dropping and re.match(r"^\d+\. ", line):
            dropping = False
        if not dropping:
            out.append(line)
    return "".join(out)


def _std(term="three years", cap="Rs 50,00,000", law="India", seat="Mumbai") -> dict:
    return {
        "Definition of Confidential Information":
            {"span": '"Confidential Information" means any information disclosed by one '
                     'party to the other', "value": "any information disclosed"},
        "Confidentiality Obligation":
            {"span": "Each party shall keep the other's Confidential Information secret",
             "value": "keep the other's Confidential Information secret"},
        "Permitted Disclosure":
            {"span": "A party may disclose Confidential Information to the extent required "
                     "by law", "value": "required by law"},
        "Return or Destruction":
            {"span": "each party shall return or destroy all Confidential Information",
             "value": "return or destroy"},
        "Term": {"span": f"continues for {term} from the date above", "value": term},
        "Limitation of Liability": {"span": f"shall not exceed {cap}", "value": cap},
        "Governing Law": {"span": f"governed by the laws of {law}", "value": law},
        "Jurisdiction": {"span": f"The courts at {seat} shall have exclusive jurisdiction",
                         "value": seat},
    }


_ALL_PRESENT = {"NDA-01": pb.MATCHES, "NDA-02": pb.MATCHES, "NDA-03": pb.MATCHES,
                "NDA-04": pb.MATCHES, "NDA-05": pb.MATCHES, "NDA-06": pb.MATCHES,
                "NDA-07": pb.MATCHES, "NDA-08": pb.MATCHES, "NDA-09": pb.MATCHES,
                "NDA-10": pb.MATCHES}


def fixtures() -> tuple[Fixture, ...]:
    drop = lambda d, *ks: {k: v for k, v in d.items() if k not in ks}   # noqa: E731
    nc = "\n9. Non-Compete\nThe Receiving Party shall not compete with the Disclosing " \
         "Party for two years.\n"
    return (
        Fixture("N01", _nda(), _std(), dict(_ALL_PRESENT)),
        Fixture("N02", _nda(term="This Agreement continues for five years from the date "
                                 "above."), _std(term="five years"),
                {**_ALL_PRESENT, "NDA-01": pb.DEVIATES}),
        Fixture("N03", _nda(law="Singapore"), _std(law="Singapore"),
                {**_ALL_PRESENT, "NDA-02": pb.DEVIATES}),
        Fixture("N04", _nda(seat="London"), _std(seat="London"),
                {**_ALL_PRESENT, "NDA-03": pb.DEVIATES}),
        # The clause is removed from the TEXT, not merely from the proposal. An earlier
        # version dropped it from `proposed` only, so the fixture asserted MISSING while
        # the document still contained the clause -- and a live model that read the
        # document correctly found it and "disagreed". The fixture was wrong, not the model.
        Fixture("N05", _without(_nda(), "1. Definition of Confidential Information"),
                drop(_std(), "Definition of Confidential Information"),
                {**_ALL_PRESENT, "NDA-04": pb.MISSING}),
        Fixture("N06", _nda(extra=nc),
                {**_std(), "Non-Compete": {"span": "shall not compete with the Disclosing "
                                                   "Party for two years",
                                           "value": "two years"}},
                {**_ALL_PRESENT, "NDA-08": pb.NEEDS_LAWYER}),
        Fixture("N07", _nda(cap="5 crore"), _std(cap="5 crore"),
                {**_ALL_PRESENT, "NDA-10": pb.DEVIATES}),
        Fixture("N08", _without(_nda(), "4. Return or Destruction"),
                drop(_std(), "Return or Destruction"),
                {**_ALL_PRESENT, "NDA-07": pb.MISSING}),
        Fixture("N09", "MUTUAL NON-DISCLOSURE AGREEMENT\n\nThe parties agree to keep "
                       "things quiet.\n", {},
                {**{k: pb.MISSING for k in _ALL_PRESENT},
                 "NDA-08": pb.MATCHES, "NDA-09": pb.MATCHES}),
        Fixture("N10", _nda(term="This Agreement continues for 36 months from the date "
                                 "above."), _std(term="36 months"), dict(_ALL_PRESENT)),
    )


def fixture_model(fx: Fixture):
    """A model that returns exactly what a correct reading of `fx` would return."""
    def _m(prompt: str) -> str:
        return json.dumps(fx.proposed)
    return _m


def run_fixtures(book: pb.Playbook, *, model_for=None) -> list[tuple[Fixture, Review]]:
    model_for = model_for or fixture_model
    out = []
    for fx in fixtures():
        pub = public_only.Origin(public_only.MATTER, f"matter:{fx.id}", "0" * 64,
                                 text=fx.text)
        out.append((fx, review(fx.text, book=book, model=model_for(fx), origin=pub)))
    return out


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

    book = pb.load(Path(__file__).resolve().parent.parent / "playbooks" / "nda_v1.json")

    # ── rule one: both halves of verification, and neither alone ────────────
    contract = "The term is three years from the Effective Date."
    e, why = verify(Proposed("Term", "term is three years", "three years"), contract)
    check(e.verified and why is None, "a real span with a value read from it verifies")
    e, why = verify(Proposed("Term", "term is ninety years", "ninety years"), contract)
    check(not e.verified and why == SPAN_NOT_IN_CONTRACT,
          "a span that is not in the contract is UNVERIFIED")
    e, why = verify(Proposed("Term", "term is three years", "five years"), contract)
    check(not e.verified and why == VALUE_NOT_IN_SPAN,
          "a REAL span with an invented value is UNVERIFIED -- the half-right case, and "
          "the one that would otherwise become a confident MATCHES against a maximum")
    check(not verify(Proposed("Term", "term is three years", ""), contract)[0].verified,
          "...and an empty value verifies nothing")

    graded = pb.evaluate(book.rules[0], verify(
        Proposed("Term", "term is three years", "five years"), contract)[0])
    check(graded.status == pb.NEEDS_LAWYER,
          "...and an unverified value is never GRADED: the playbook returns NEEDS_LAWYER "
          "rather than a deviation computed from a number the model may have invented")

    # ── rule two: the law we do not hold is named, not omitted ──────────────
    notes = dict(law_notes())
    check(set(notes) == set(UNHELD_FOR_CONTRACTS),
          f"every unheld body a contract reaches is named ({sorted(notes)})")
    for k in UNHELD_FOR_CONTRACTS:
        check(len(notes[k]) > 80 and "scope" not in notes[k][:10].lower(),
              f"...{k} carries scope.py's own refusal, at length, not a shrug")
    check(all(not scope.body(k).answerable for k in UNHELD_FOR_CONTRACTS),
          "...and none of them is answerable, which is why they are refusals")

    # ── the ten fixtures ────────────────────────────────────────────────────
    results = run_fixtures(book)
    check(len(results) == 10, f"ten NDA fixtures ({len(results)})")
    wrong = []
    for fx, rv in results:
        got = {f.rule_id: f.status for f in rv.findings}
        for rule_id, want in fx.expect.items():
            if got.get(rule_id) != want:
                wrong.append((fx.id, rule_id, want, got.get(rule_id)))
    check(not wrong, f"every fixture produces its expected finding per rule ({wrong[:4]})")

    statuses = {f.status for _fx, rv in results for f in rv.findings}
    check({pb.MATCHES, pb.DEVIATES, pb.MISSING, pb.NEEDS_LAWYER} <= statuses,
          f"...and all four statuses are reached across the set ({sorted(statuses)}) -- a "
          f"fixture set that only ever MATCHES measures nothing")

    # A MISSING expectation must mean the clause is missing from the DOCUMENT, or the
    # fixture is asserting that the model failed to read rather than that the clause is
    # absent -- and a live model reading correctly then "disagrees" with a wrong fixture.
    for fid, heading, rule in (("N05", "Definition of Confidential Information", "NDA-04"),
                               ("N08", "Return or Destruction", "NDA-07")):
        fx = next(f for f in fixtures() if f.id == fid)
        check(heading not in fx.text,
              f"{fid} is missing {heading!r} from its TEXT, not merely from its proposal")
        check(fx.expect[rule] == pb.MISSING,
              f"...which is why {rule} expects MISSING there")
    check("Definition of Confidential Information" in fixtures()[0].text,
          "...while the baseline fixture still contains it, so _without() cut one clause "
          "and not the document")

    n09 = next(rv for fx, rv in results if fx.id == "N09")
    check(all(f.status in (pb.MISSING, pb.MATCHES) for f in n09.findings),
          "a bare contract is MISSING on the clauses it lacks")
    check(any(f.rule_id == "NDA-08" and f.status == pb.MATCHES for f in n09.findings),
          "...while must_be_absent_or_approved MATCHES on it: absence IS the standard")

    n06 = next(rv for fx, rv in results if fx.id == "N06")
    check(any(f.rule_id == "NDA-08" and f.status == pb.NEEDS_LAWYER for f in n06.findings),
          "a contract carrying a non-compete is NEEDS_LAWYER, not a verdict")

    # ── the report never reads as legal advice, and says it is a draft ──────
    rv = results[0][1]
    check(all(f.kind == pb.POTENTIAL_ISSUE for f in rv.findings),
          "every finding is a POTENTIAL_ISSUE")
    check(rv.playbook_status == pb.DRAFT and rv.requires_review,
          "a DRAFT playbook makes the whole review requires_review, whatever the model was")
    d = rv.to_dict()
    check(set(d) >= {"findings", "unverified", "law_not_held", "requires_review"},
          "the report carries findings, what could not be verified, and the law not held")

    # ── the standard travels with the finding ──────────────────────────────
    # It did not until 29-09-2026: to_dict dropped it, so a live review rendered ten rows
    # with a blank standard column and the only text a reader had for the company position
    # was the comparison detail. A finding whose standard is not on the wire cannot be
    # judged by the person it is shown to.
    check(all(f["standard_text"].strip() and f["rationale"].strip() for f in d["findings"]),
          "every finding on the wire carries the standard it was judged against and the "
          "reason for it")
    check(all(f["standard_text"] != f["detail"] for f in d["findings"]),
          "...and the standard is not the comparison detail: one is the company position, "
          "the other is what this document said against it")
    check("why" not in set().union(*(set(f) for f in d["findings"])),
          "...and the engineering note is NOT sent: NDA-02's `why` is a changelog about a "
          "false-alarm rate, which is not what a lawyer's column is for")
    check(d["playbook_status"] == pb.DRAFT,
          "...and both sentences are marked DRAFT by the playbook_status on the same "
          "report -- there is no second status for them to fall out of step with")
    check(len(d["law_not_held"]) == len(UNHELD_FOR_CONTRACTS),
          "...and the unheld law travels WITH the report rather than being left out of it")

    # ── a model that invents is caught by the pipeline, not by a reviewer ───
    def liar(fx):
        return lambda prompt: json.dumps(
            {"Term": {"span": "a sentence that is nowhere in this contract",
                      "value": "ten years"}})

    bad = run_fixtures(book, model_for=liar)[0][1]
    check(bad.unverified and bad.unverified[0][1] == SPAN_NOT_IN_CONTRACT,
          "an invented span is recorded as UNVERIFIED with its reason")
    check(next(f for f in bad.findings if f.rule_id == "NDA-01").status == pb.NEEDS_LAWYER,
          "...and grades as NEEDS_LAWYER, never as a ten-year term deviating from three")

    # ── the firewall: a customer contract cannot reach the free tier ────────
    try:
        review("Some customer contract text.", book=book, model=lambda p: "{}",
               provider="gemini")
        check(False, "a customer contract is refused to gemini")
    except public_only.NotPublic as e:
        check("may not receive a matter document" in str(e),
              "a customer contract is REFUSED to the free tier before a prompt is built "
              "(PLAN_22 D3)")

    called = []
    try:
        review("Some customer contract text.", book=book,
               model=lambda p: called.append(1) or "{}", provider="ollama")
        check(False, "...and to the laptop")
    except public_only.NotPublic:
        check(not called, "...and to any provider not named, with nothing sent")

    # ── routing: the model the bake-off chose, flagged as a draft ───────────
    r = review(_nda(), book=book, model=fixture_model(fixtures()[0]),
               origin=public_only.Origin(public_only.MATTER, "matter:x", "0" * 64,
                                         text=_nda()))
    check(r.route is not None and r.route.provider == "azure"
          and r.route.model == "llama-3-3-70b",
          f"extraction routes to the bake-off's fallback model "
          f"({r.route.provider}/{r.route.model})")
    check(r.route.requires_review,
          "...and the route is flagged requires_review: a contract review by a rented "
          "model nobody has read is a draft")
    check(r.clause_count > 5,
          f"...and the contract was split by CODE before the model saw it "
          f"({r.clause_count} clauses)")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
