"""
The model adapter: the only place an LLM is allowed to touch this system.

The model is the least trusted component here and is treated that way. It is handed a closed world,
required to cite into it, and its output is parsed into a rigid structure that rejects anything it
cannot audit. Nothing it says becomes an answer until claim_verifier has checked it.

Three refusals happen BEFORE any model call, because a prompt is not a safety mechanism:

  1. A pack not built in MODE_MODEL is refused. MODE_REVIEW packs deliberately contain material a
     human may inspect and a model may not. The pack attests to its own mode, so a caller cannot
     simply assert the wrong one.
  2. A pack with no admissible evidence is answered INSUFFICIENT_EVIDENCE without asking a model.
     There is nothing to reason over, and asking anyway invites the model to reason from memory.
  3. Output citing an evidence id that is not in the pack is rejected, not repaired. A citation to
     something absent is the signature of a fabricated one.

Everything downstream of the model FAILS CLOSED. Malformed output does not raise -- it becomes
INSUFFICIENT_EVIDENCE with a parse-failure warning. An exception here would propagate to whatever
is asking the legal question, and a crash is a worse answer than an abstention: abstention is
correct-and-unhelpful, a crash is neither.

The model here is a callable, and the default is a stub. That is deliberate: the contract should be
provable without spending money or depending on one model's habits, and swapping in a real model is
one argument.

Run: python3 checker/model_adapter.py
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Callable

from checker.claim_schema import (CLAIM_TYPES, Claim, ClaimError, LEGAL_TRIGGER, MISSING_FACT,
                                  SUPPORT_LEVELS)
from checker.evidence_pack import EvidencePack

__all__ = ["ModelTask", "ModelResult", "AdapterError", "run", "build_prompt",
           "StubModel", "APPLIES", "DOES_NOT_APPLY", "INSUFFICIENT_FACTS", "INSUFFICIENT_EVIDENCE"]

APPLIES = "APPLIES"
DOES_NOT_APPLY = "DOES_NOT_APPLY"
INSUFFICIENT_FACTS = "INSUFFICIENT_FACTS"          # law is here; the document does not say enough
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"    # the law itself is not here or not admissible
DECISIONS = (APPLIES, DOES_NOT_APPLY, INSUFFICIENT_FACTS, INSUFFICIENT_EVIDENCE)

PROMPT_VERSION = "closed-world-v1"

# Warning codes. Strings, so they survive JSON round-trips into the audit trail.
NO_ADMISSIBLE_EVIDENCE = "NO_ADMISSIBLE_EVIDENCE"
MODEL_OUTPUT_PARSE_FAILURE = "MODEL_OUTPUT_PARSE_FAILURE"
DECISION_DOWNGRADED = "DECISION_DOWNGRADED"
DECISION_WITHOUT_CLAIMS = "DECISION_WITHOUT_CLAIMS"
DUPLICATE_CLAIM_ID = "DUPLICATE_CLAIM_ID"

INSTRUCTION = """\
You are given the complete admissible evidence for this task. Nothing else is available to you.

1. Use ONLY the evidence below. Your own knowledge of Indian company law is NOT evidence here and
   must not appear in your answer.
2. Every LEGAL_TRIGGER and PROCEDURAL_REQUIREMENT claim must cite one or more evidence ids from
   the pack. An uncited legal statement will be discarded.
3. Write each claim as ONE self-contained proposition. Do not join two propositions with "and
   also", "furthermore", or a second sentence. Split them into separate claims.
4. If the pack lacks the law needed, answer INSUFFICIENT_EVIDENCE. If the law is here but the
   document does not say enough, answer INSUFFICIENT_FACTS. Do not guess between them.
5. Never cite an item listed as withheld or not admitted. It is not available to you as support.
6. State what the document does NOT say as MISSING_FACT claims, with no evidence ids.

Return ONLY JSON:
{"decision": "APPLIES|DOES_NOT_APPLY|INSUFFICIENT_FACTS|INSUFFICIENT_EVIDENCE",
 "claims": [{"claim_id": "c1", "text": "...", "claim_type": "LEGAL_TRIGGER|FACT_INFERENCE|\
PROCEDURAL_REQUIREMENT|MISSING_FACT", "evidence_ids": ["..."], "support": "DIRECT|INFERRED",
 "confidence": "HIGH|MEDIUM|LOW"}],
 "missing_facts": ["..."],
 "warnings": ["..."]}
"""


class AdapterError(ValueError):
    """A refusal that happens before or instead of trusting model output."""


@dataclass(frozen=True)
class ModelTask:
    task_type: str
    question: str
    evidence_pack: EvidencePack
    document_text: str = ""
    as_of: str | None = None


@dataclass(frozen=True)
class ModelResult:
    decision: str
    claims: tuple[Claim, ...] = ()
    missing_facts: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    raw_text: str = ""
    model_name: str = "stub"
    prompt_version: str = PROMPT_VERSION
    rejected_claims: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return dict(decision=self.decision, claims=[c.to_dict() for c in self.claims],
                    missing_facts=list(self.missing_facts), warnings=list(self.warnings),
                    model_name=self.model_name, prompt_version=self.prompt_version,
                    rejected_claims=list(self.rejected_claims))


def evidence_ids(pack: EvidencePack) -> tuple[str, ...]:
    """The ids a model may cite: admissible provisions only."""
    return tuple(p.key for p in pack.usable)


def build_prompt(task: ModelTask) -> str:
    parts = [INSTRUCTION, "", "=== QUESTION ===", task.question]
    if task.document_text:
        parts += ["", "=== DOCUMENT UNDER REVIEW ===", task.document_text.strip()]
    parts += ["", task.evidence_pack.prompt_block()]
    return "\n".join(parts)


def _claim_id(c: dict, i: int) -> str:
    """The id a claim will be known by, including the positional fallback for an unlabelled one.

    Stringified so that 1 and "1" count as ONE id rather than two. They are indistinguishable to a
    reader of the audit trail, and two claims a reader cannot tell apart is the exact condition the
    duplicate rule exists to catch.
    """
    return str(c.get("claim_id") or f"c{i + 1}")


def _parse(raw: str, allowed: tuple[str, ...]) -> tuple[str, list[Claim], list[str], list[str],
                                                        list[str]]:
    """Parse model output. Anything unauditable is REJECTED, never repaired.

    Repairing a malformed claim means inventing the part the model did not supply, which is the
    same failure as the model inventing it -- with the added problem that the trail then shows a
    well-formed claim nobody actually made.
    """
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        raise AdapterError("model returned no JSON object")
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError as e:
        raise AdapterError(f"model returned malformed JSON: {e}")

    if not isinstance(d, dict):
        raise AdapterError(f"model returned a JSON {type(d).__name__}, not an object")

    decision = d.get("decision")
    if decision not in DECISIONS:
        raise AdapterError(f"decision {decision!r} is not one of {DECISIONS}")

    # Types are checked explicitly rather than discovered by exception. Model output is untrusted
    # input; `claims` arriving as a string used to reach `.get()` and throw AttributeError straight
    # past run()'s AdapterError handler and out to whoever asked the legal question -- the exact
    # crash the fail-closed rule exists to prevent. Found by checker/redteam.py (RED-05).
    raw_claims = d.get("claims") or []
    if not isinstance(raw_claims, (list, tuple)):
        raise AdapterError(f"'claims' is a {type(raw_claims).__name__}, expected a list")

    # Which ids are duplicated is decided BEFORE any claim is accepted. A `seen` set cannot express
    # this rule: rejecting the second copy leaves the first standing, so of two claims sharing an id
    # -- "Board approval is required" and "no approval is required" -- the one that becomes the
    # answer is the one the model happened to emit first, not the one better supported by the
    # evidence. That is choosing a legal conclusion by accident. A duplicated id means claim
    # identity is unreliable for EVERY claim carrying it, so every one of them is rejected and the
    # decision falls back to the downgrade rules below.
    id_counts: dict[str, int] = {}
    for i, c in enumerate(raw_claims):
        if isinstance(c, dict):
            cid = _claim_id(c, i)
            id_counts[cid] = id_counts.get(cid, 0) + 1
    duplicated = {cid for cid, n in id_counts.items() if n > 1}

    claims, rejected = [], []
    for i, c in enumerate(raw_claims):
        if not isinstance(c, dict):
            rejected.append(f"c{i + 1}: claim is a {type(c).__name__}, expected an object")
            continue
        cid = _claim_id(c, i)
        try:
            # Checked first, so both copies are rejected for the same stated reason even when one
            # of them is independently malformed -- the rejection text then does not depend on
            # which order the copies arrived in either.
            if cid in duplicated:
                raise ClaimError(
                    f"{cid}: duplicate claim_id -- {id_counts[cid]} claims in this response share "
                    f"this id, so ALL of them are rejected (this is claim {i + 1} of "
                    f"{len(raw_claims)}; the text of each is preserved verbatim in raw_text). "
                    "Keeping one would let emission order rather than evidence decide which "
                    "survives, and verification results would be unattributable, since two "
                    "different claims would share one verdict.")
            ctype = c.get("claim_type")
            if ctype not in CLAIM_TYPES:
                raise ClaimError(f"{cid}: unknown claim_type {ctype!r}")
            raw_ids = c.get("evidence_ids") or ()
            if not isinstance(raw_ids, (list, tuple)):
                raise ClaimError(
                    f"{cid}: 'evidence_ids' is a {type(raw_ids).__name__}, expected a list")
            ids = tuple(str(x) for x in raw_ids)
            unknown = [e for e in ids if e not in allowed]
            if unknown:
                raise ClaimError(
                    f"{cid}: cites evidence not in the pack ({', '.join(unknown)}) -- a citation "
                    "to something absent is the signature of a fabricated one")
            support = c.get("support", "INFERRED")
            if support not in SUPPORT_LEVELS:
                support = "INFERRED"
            claims.append(Claim(cid, str(c.get("text", "")), ctype, ids, support,
                                c.get("confidence", "LOW")))
        except ClaimError as e:
            rejected.append(str(e))

    warnings = [str(x) for x in d.get("warnings") or []]
    if duplicated:
        names = ", ".join(sorted(duplicated))
        warnings.append(
            f"{DUPLICATE_CLAIM_ID}: {names} -- "
            f"{'this id was' if len(duplicated) == 1 else 'these ids were'} used by more than one "
            "claim; every claim carrying a duplicated id was rejected, since a claim id is what a "
            "verification verdict is attributed to")

    return (decision, claims, [str(x) for x in d.get("missing_facts") or []], warnings, rejected)


def run(task: ModelTask, model: Callable[[str], str] | None = None,
        *, model_name: str = "stub") -> ModelResult:
    """Run the task, refusing before the model wherever a refusal is possible."""
    pack = task.evidence_pack

    if pack.mode != "MODEL":
        raise AdapterError(
            f"pack was built in mode {pack.mode!r}; only a MODEL pack may reach a model. "
            "REVIEW packs contain material admitted for human inspection only.")

    allowed = evidence_ids(pack)
    if not allowed:
        # No model call. There is nothing to reason over, and asking anyway invites the model to
        # answer from memory -- which is the one thing this whole layer exists to prevent.
        return ModelResult(
            decision=INSUFFICIENT_EVIDENCE,
            missing_facts=tuple(pack.missing),
            warnings=("no admissible evidence in the pack; no model was consulted",),
            model_name=model_name)

    prompt = build_prompt(task)
    raw = (model or StubModel(pack=pack))(prompt)
    try:
        decision, claims, missing, warnings, rejected = _parse(raw, allowed)
    except AdapterError as e:
        return ModelResult(
            decision=INSUFFICIENT_EVIDENCE,
            warnings=(f"{MODEL_OUTPUT_PARSE_FAILURE}: {e}",),
            raw_text=raw, model_name=model_name)
    except Exception as e:  # noqa: BLE001
        # Defence in depth. The explicit type checks above cover what a model plausibly emits, but
        # "plausibly" is doing real work in that sentence and the contract is absolute: NOTHING a
        # model returns may crash the caller. The exception type is preserved in the warning so a
        # genuine bug in our own code is still diagnosable rather than silently swallowed.
        return ModelResult(
            decision=INSUFFICIENT_EVIDENCE,
            warnings=(f"{MODEL_OUTPUT_PARSE_FAILURE}: unexpected "
                      f"{type(e).__name__} while parsing model output: {e}",),
            raw_text=raw, model_name=model_name)
    except BaseException:
        raise

    # A model may not claim law applies while the pack says its evidence is insufficient.
    if pack.insufficient_evidence and decision in (APPLIES, DOES_NOT_APPLY):
        warnings = warnings + [
            f"{DECISION_DOWNGRADED}: model answered {decision} but the pack reports insufficient "
            "evidence; downgraded to INSUFFICIENT_EVIDENCE"]
        decision = INSUFFICIENT_EVIDENCE

    # A conclusion with no surviving reasoning is not a conclusion. If every claim behind APPLIES
    # or DOES_NOT_APPLY was rejected at parse, the decision has nothing left holding it up.
    substantive = [c for c in claims if c.claim_type != MISSING_FACT]
    if decision in (APPLIES, DOES_NOT_APPLY) and not substantive:
        warnings = warnings + [
            f"{DECISION_WITHOUT_CLAIMS}: {decision} was asserted with no surviving substantive "
            f"claim ({len(rejected)} rejected at parse); downgraded to INSUFFICIENT_EVIDENCE"]
        decision = INSUFFICIENT_EVIDENCE

    # An abstention with no stated reason is unauditable: a reader cannot tell whether the law was
    # absent, withheld, or simply not looked for.
    if decision == INSUFFICIENT_EVIDENCE and not (warnings or missing or pack.missing):
        warnings = warnings + ["INSUFFICIENT_EVIDENCE returned without a stated reason"]

    return ModelResult(decision=decision, claims=tuple(claims), missing_facts=tuple(missing),
                       warnings=tuple(warnings), raw_text=raw, model_name=model_name,
                       rejected_claims=tuple(rejected))


class StubModel:
    """A deterministic stand-in for a real model.

    It exists so the contract can be tested exhaustively without a network call or an API bill, and
    so the parsing and refusal logic is shaped by the SPEC rather than by whatever a particular
    model happens to emit. **It is not a simulation of model quality and must never be scored as
    one.**

    It is given the pack rather than scraping the prompt. An earlier version regexed evidence keys
    out of the prompt text and cited a section that was not in the pack -- the adapter correctly
    rejected it, but the stub was manufacturing exactly the fabricated-citation failure it was
    meant to help detect, which made every downstream number meaningless.

    Its one claim lifts wording from the provision itself, because a compliant model grounds its
    claims in the text it cites. A stub that emits ungrounded prose guarantees a 100% unsupported
    rate and tells you nothing about the harness.
    """

    def __init__(self, script: str | None = None, pack: EvidencePack | None = None) -> None:
        self.script = script
        self.pack = pack

    def __call__(self, prompt: str) -> str:
        if self.script is not None:
            return self.script
        usable = list(self.pack.usable) if self.pack else []
        if not usable:
            return json.dumps({"decision": INSUFFICIENT_EVIDENCE, "claims": [],
                               "missing_facts": ["no provision was supplied"], "warnings": []})
        p = usable[0]
        body = " ".join((p.reading_text or p.raw_text).split())
        # One sentence of the provision, so the claim is grounded in the cited text by construction.
        sentence = re.split(r"(?<=[.;])\s", body)[0][:240].rstrip(" .;") or p.ref.title
        return json.dumps({
            "decision": INSUFFICIENT_FACTS,
            "claims": [
                {"claim_id": "c1", "claim_type": LEGAL_TRIGGER,
                 "text": f"{sentence}.",
                 "evidence_ids": [p.key], "support": "DIRECT", "confidence": "MEDIUM"},
                {"claim_id": "c2", "claim_type": MISSING_FACT,
                 "text": "The document does not state facts sufficient to apply this provision.",
                 "evidence_ids": [], "support": "MISSING", "confidence": "MEDIUM"},
            ],
            "missing_facts": ["facts required by the cited provision"],
            "warnings": [],
        })


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"[PASS] {label}")
        else:
            fail += 1; print(f"[FAIL] {label}")

    from checker.retrieve import MODE_MODEL, MODE_REVIEW, retrieve

    pack, _ = retrieve("s.173", mode=MODE_MODEL)
    task = ModelTask("APPLICABILITY_CHECK", "Does s.173 require a meeting?", pack)

    res = run(task)
    check(res.decision in DECISIONS, f"stub produced a valid decision ({res.decision})")
    check(all(c.evidence_ids or c.claim_type == MISSING_FACT for c in res.claims),
          "every non-missing claim carries a citation")
    check(not res.rejected_claims, f"nothing rejected on a clean run ({res.rejected_claims})")

    # THE boundary: a review pack must never reach a model.
    rpack, _ = retrieve("s.16", mode=MODE_REVIEW)
    try:
        run(ModelTask("APPLICABILITY_CHECK", "q", rpack))
        check(False, "a REVIEW pack must be refused")
    except AdapterError as e:
        check("only a MODEL pack may reach a model" in str(e), "a REVIEW pack is refused")

    # Suspended law: nothing admissible, so no model is consulted at all.
    spack, _ = retrieve("s.16", mode=MODE_MODEL)
    called = []
    res2 = run(ModelTask("APPLICABILITY_CHECK", "q", spack),
               model=lambda p: called.append(p) or "{}")
    check(res2.decision == INSUFFICIENT_EVIDENCE, "an empty pack yields INSUFFICIENT_EVIDENCE")
    check(not called, "...and the model is never called")

    prompt = build_prompt(task)
    for phrase in ("is NOT evidence here", "INSUFFICIENT_EVIDENCE", "ONE self-contained proposition"):
        check(phrase in prompt, f"the prompt states: {phrase!r}")

    allowed = evidence_ids(pack)
    fabricated = json.dumps({"decision": APPLIES, "claims": [
        {"claim_id": "c1", "claim_type": LEGAL_TRIGGER, "text": "Section 999 applies.",
         "evidence_ids": ["ACT:COMPANIES_ACT_2013:S999"], "support": "DIRECT"}]})
    _, claims, _, _, rejected = _parse(fabricated, allowed)
    check(not claims and rejected, "a claim citing evidence outside the pack is rejected")
    check("fabricated" in rejected[0], "...and the rejection says why")

    bundled = json.dumps({"decision": APPLIES, "claims": [
        {"claim_id": "c1", "claim_type": LEGAL_TRIGGER, "evidence_ids": list(allowed[:1]),
         "text": "Section 173 applies. The Board must also meet four times."}]})
    _, claims2, _, _, rej2 = _parse(bundled, allowed)
    check(not claims2 and any("atomic" in r for r in rej2), "a bundled claim is rejected")

    try:
        _parse("no json here", allowed); check(False, "unparseable output must raise")
    except AdapterError:
        check(True, "unparseable model output raises rather than yielding an empty answer")

    try:
        _parse(json.dumps({"decision": "MAYBE"}), allowed); check(False, "bad decision must raise")
    except AdapterError:
        check(True, "an invented decision value is refused")

    # --- fail closed: run() must never propagate a parse failure to the caller ---
    for junk in ("not json at all", "{broken", json.dumps({"decision": "MAYBE"})):
        r = run(task, model=lambda p, j=junk: j)
        check(r.decision == INSUFFICIENT_EVIDENCE,
              f"malformed output {junk[:14]!r} abstains instead of raising")
        check(any(MODEL_OUTPUT_PARSE_FAILURE in w for w in r.warnings),
              "...and the parse failure is named in the warnings")
        check(r.raw_text == junk, "...and the raw output is preserved for diagnosis")

    # --- duplicate claim ids: every copy goes, and emission order decides nothing ---
    # The rule the earlier version got wrong: it kept the FIRST claim under a repeated id, so of
    # two contradictory claims the answer was whichever the model listed first. Both are rejected
    # now, and the pair below is run in both orders to prove it.
    REQUIRED = "Board approval is required."
    NOT_REQUIRED = "No Board approval is required."

    def _dupe_pair(first: str, second: str) -> str:
        return json.dumps({"decision": APPLIES, "claims": [
            {"claim_id": "c1", "claim_type": LEGAL_TRIGGER, "text": t,
             "evidence_ids": list(allowed[:1])} for t in (first, second)]})

    ra = run(task, model=lambda p: _dupe_pair(REQUIRED, NOT_REQUIRED))
    rb = run(task, model=lambda p: _dupe_pair(NOT_REQUIRED, REQUIRED))
    check(ra.claims == () and rb.claims == (),
          "both claims sharing one id are rejected -- not merely the later one")
    check(len(ra.rejected_claims) == 2
          and all("duplicate claim_id" in x for x in ra.rejected_claims),
          "...and each discarded claim is recorded in rejected_claims with a reason")
    # to_dict() carries decision, claims, missing_facts, warnings and rejected_claims -- everything
    # a reader is served. Only raw_text differs, because the two raw responses genuinely differ.
    check(ra.to_dict() == rb.to_dict(),
          "ORDER-INDEPENDENCE: both emission orders produce an identical result")
    check(not any(t in c.text for c in ra.claims + rb.claims for t in (REQUIRED, NOT_REQUIRED)),
          "...so neither side of the contradiction can win by arriving first")
    check(any(DUPLICATE_CLAIM_ID in w and "c1" in w for w in ra.warnings),
          "the warning names the duplicated id")
    check(ra.decision == INSUFFICIENT_EVIDENCE
          and any(DECISION_WITHOUT_CLAIMS in w for w in ra.warnings),
          "APPLIES resting only on duplicated claims is downgraded to INSUFFICIENT_EVIDENCE")

    # A malformed pair must not take good claims down with it.
    mixed = json.dumps({"decision": APPLIES, "claims": [
        {"claim_id": "c1", "claim_type": LEGAL_TRIGGER, "text": REQUIRED,
         "evidence_ids": list(allowed[:1])},
        {"claim_id": "c1", "claim_type": LEGAL_TRIGGER, "text": NOT_REQUIRED,
         "evidence_ids": list(allowed[:1])},
        {"claim_id": "c2", "claim_type": LEGAL_TRIGGER, "text": "The Board shall meet.",
         "evidence_ids": list(allowed[:1])}]})
    rmix = run(task, model=lambda p: mixed)
    check([c.claim_id for c in rmix.claims] == ["c2"],
          "a uniquely-identified claim survives alongside a duplicated pair")
    check(len(rmix.rejected_claims) == 2, "...and exactly the two duplicates are rejected")
    check(rmix.decision == APPLIES,
          "...and the surviving substantive claim still holds the decision up")

    # Three copies, not two: the rule is about the id, not about being the second sighting.
    triple = json.dumps({"decision": INSUFFICIENT_FACTS, "claims": [
        {"claim_id": "c1", "claim_type": LEGAL_TRIGGER, "text": t,
         "evidence_ids": list(allowed[:1])}
        for t in ("The Board shall meet once a year.", "The Board shall meet twice a year.",
                  "The Board shall meet four times a year.")]})
    rt3 = run(task, model=lambda p: triple)
    check(rt3.claims == () and len(rt3.rejected_claims) == 3,
          "three claims sharing one id all go, not two of the three")
    check(any(DUPLICATE_CLAIM_ID in w for w in rt3.warnings),
          "...and the duplicate warning is raised regardless of the decision")

    # The unaffected path: distinct ids draw no duplicate warning at all.
    clean = run(task)
    check(not any(DUPLICATE_CLAIM_ID in w for w in clean.warnings),
          "distinct claim ids raise no duplicate warning")

    # --- a conclusion with no surviving reasoning is not a conclusion ---
    hollow = json.dumps({"decision": APPLIES, "claims": [
        {"claim_id": "c1", "claim_type": LEGAL_TRIGGER, "text": "Section 999 applies.",
         "evidence_ids": ["ACT:COMPANIES_ACT_2013:S999"]}]})
    rh = run(task, model=lambda p: hollow)
    check(rh.decision == INSUFFICIENT_EVIDENCE,
          "APPLIES with every claim rejected is downgraded, not served")
    check(any(DECISION_WITHOUT_CLAIMS in w for w in rh.warnings),
          "...and the downgrade says why")

    only_missing = json.dumps({"decision": APPLIES, "claims": [
        {"claim_id": "c1", "claim_type": MISSING_FACT,
         "text": "The document does not state the date.", "evidence_ids": []}]})
    rm = run(task, model=lambda p: only_missing)
    check(rm.decision == INSUFFICIENT_EVIDENCE,
          "APPLIES supported only by a MISSING_FACT is downgraded")

    # --- an abstention must carry a reason ---
    bare = json.dumps({"decision": INSUFFICIENT_EVIDENCE, "claims": [],
                       "missing_facts": [], "warnings": []})
    rb = run(task, model=lambda p: bare)
    check(rb.warnings or rb.missing_facts, "an abstention without a reason gains one")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
