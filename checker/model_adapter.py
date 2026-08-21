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

    decision = d.get("decision")
    if decision not in DECISIONS:
        raise AdapterError(f"decision {decision!r} is not one of {DECISIONS}")

    claims, rejected = [], []
    for i, c in enumerate(d.get("claims") or []):
        cid = c.get("claim_id") or f"c{i + 1}"
        try:
            ctype = c.get("claim_type")
            if ctype not in CLAIM_TYPES:
                raise ClaimError(f"{cid}: unknown claim_type {ctype!r}")
            ids = tuple(c.get("evidence_ids") or ())
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

    return (decision, claims, [str(x) for x in d.get("missing_facts") or []],
            [str(x) for x in d.get("warnings") or []], rejected)


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
    decision, claims, missing, warnings, rejected = _parse(raw, allowed)

    # A model may not claim law applies while the pack says its evidence is insufficient.
    if pack.insufficient_evidence and decision in (APPLIES, DOES_NOT_APPLY):
        warnings = warnings + [
            f"model answered {decision} but the pack reports insufficient evidence; "
            "downgraded to INSUFFICIENT_EVIDENCE"]
        decision = INSUFFICIENT_EVIDENCE

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

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
