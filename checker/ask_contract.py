"""The `placedon.ask/0` validator — what a `/v1/ask` response must be before anyone renders it.

Lives in the package so the route can run it on its own response (`checker/api.py`): a
response that breaks the contract is a server fault and is withheld as a 500, never served as
a 200. `scripts/assistant_contract.py` re-exports it and holds its tests, beside the fixtures
they run against. Contract prose: `web/assistant/contract.md` §7.

No test here: `python3 scripts/assistant_contract.py --test` is this module's suite (in the gate).
"""
from __future__ import annotations

SCHEMA = "placedon.ask/0"
STATES = ("answered", "partial", "out_of_scope")
# checker/orchestrator.py step() names. A stage the engine does not emit is not a stage.
STAGE_NAMES = ("capability", "date", "model", "review", "correction", "abstain")
# C4: no confidence, ever. `coverage` is refused because ClaimVerification.coverage is a float that
# reads as confidence; the document-check coverage frame travels as `scope_frame` instead (K8).
FORBIDDEN_KEYS = ("confidence", "coverage")


# ── validation ────────────────────────────────────────────────────────────────
def _keys(obj, path="$"):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k, f"{path}.{k}"
            yield from _keys(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _keys(v, f"{path}[{i}]")


def _lists(obj, path="$"):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _lists(v, f"{path}.{k}")
    elif isinstance(obj, list):
        yield path, obj
        for i, v in enumerate(obj):
            yield from _lists(v, f"{path}[{i}]")


def validate(r: dict) -> list[str]:
    """Every way this response breaks the contract. Empty means it may be rendered."""
    if not isinstance(r, dict):
        return ["the response is not a JSON object"]
    errs: list[str] = []
    if r.get("schema") != SCHEMA:
        errs.append(f"schema must be {SCHEMA}")
    state = r.get("state")
    if state not in STATES:
        return errs + [f"state {state!r} is not one of {', '.join(STATES)} -- the client never "
                       f"infers one"]
    for k in ("turn_id", "question", "generated_at", "as_of", "context", "uses_model", "scope"):
        if k not in r:
            errs.append(f"missing {k}")
    for k, p in _keys(r):
        if k in FORBIDDEN_KEYS:
            errs.append(f"{p}: a '{k}' field is forbidden (C4)")
    for p, v in _lists(r):
        # A sentence that went through list() arrives as its own characters. It reads as
        # a list to every check that only counts items, and as nothing to a reader.
        if len(v) > 2 and all(isinstance(x, str) and len(x) == 1 for x in v):
            errs.append(f"{p}: {len(v)} single-character items -- this is a string that "
                        f"was split, not a list the engine returned")

    ctx = r.get("context") or {}
    kind = ctx.get("kind")
    if kind not in ("document", "general"):
        errs.append("context.kind must be document or general")
    if kind == "document" and not ctx.get("document_date"):
        errs.append("a document-context turn needs its document_date")
    if "stages" in r:
        if kind != "document":
            errs.append("stages exist only on the document path -- a general turn has none (K9)")
        for s in r.get("stages") or []:
            if not isinstance(s, dict) or s.get("what") not in STAGE_NAMES:
                errs.append(f"stage {s!r} is not one the orchestrator emits")
    if "parent_turn_id" in r and not r["parent_turn_id"]:
        errs.append("a follow-up must name the turn it follows")

    pack = r.get("evidence_pack") or {}
    in_pack = set(pack.get("usable_keys", [])) | set(pack.get("unusable_keys", []))
    for cit in r.get("citations", []):
        if cit.get("ref") not in in_pack:
            errs.append(f"citation {cit.get('ref')} is outside the evidence pack")
        if "effective_from" in cit:
            errs.append(f"citation {cit.get('ref')}: section text carries no in-force date")
        if state == "answered" and not cit.get("usable_for_answering"):
            errs.append(f"answered cites {cit.get('ref')}, which is not usable for answering")
    for fig in r.get("figures", []):
        for k in ("amount", "instrument", "effective_from"):
            if not fig.get(k):
                errs.append(f"figure {fig.get('key')} has no {k}")
    # A turn that shows rows or section text must say what law they were read against. On a
    # document turn, "current" means current consolidation -- not the law at the document date.
    if (state != "out_of_scope"
            and any(r.get(k) for k in ("rows", "confirmed", "superseded", "citations"))
            and not r.get("law_version")):
        errs.append("a turn that renders rows or legal text needs law_version -- what law it "
                    "was checked against")

    if state == "answered":
        if r.get("uses_model") is not False:
            errs.append("answered is only truthful from a deterministic path today "
                        "(claim_verifier never returns SUPPORTED)")
        if not (r.get("figures") or r.get("rows")):
            errs.append("answered needs a figure or an obligation row")
    elif state == "partial":
        if not r.get("not_confirmed"):
            errs.append("partial needs at least one thing not confirmed")
        for item in r.get("confirmed", []):
            if "effective_from" in item:
                errs.append("confirmed section text carries no in-force date -- current "
                            "consolidation is not a point-in-time answer")
            if item.get("ref") and in_pack and item["ref"] not in in_pack:
                errs.append(f"confirmed {item['ref']} is outside the evidence pack")
    else:
        body = r.get("body") or {}
        if body.get("scope_status") in (None, "IN_CORPUS"):
            errs.append("out_of_scope must name a body of law we do not hold")
        if not r.get("reason"):
            errs.append("out_of_scope needs the register's reason")
    return errs
