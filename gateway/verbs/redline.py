"""redline — positional playbook review with edit generation.

Wire: extraction (agents/review_contract.py) → position ladder (checker/positions.py)
→ edit generation (checker/redline.py).

The endpoint takes a contract text and a positions playbook path, extracts clause
values, resolves each against the Starting/Fallback/Dealbreaker ladder, and returns
concrete text edits the Word add-in can apply as tracked changes.

Run: PYTHONPATH=. python3 gateway/verbs/redline.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from gateway.verbs.core import Context, _refuse


def _redline(args: dict, ctx: Context) -> dict:
    from agents import review_contract as rc
    from checker import playbook as pb
    from checker import positions as pos
    from checker import public_only, redline, router

    text = args.get("text") or ""
    if not text.strip():
        return _refuse("BAD_REQUEST", "text is required")

    root = Path(__file__).resolve().parent.parent.parent
    book_path = args.get("playbook") or "playbooks/nda_positions_v1.json"
    full_path = root / book_path

    if not full_path.exists():
        return _refuse("BAD_REQUEST", f"playbook not found: {book_path}")

    try:
        raw = json.loads(full_path.read_text())
    except (ValueError, OSError) as e:
        return _refuse("BAD_REQUEST", f"playbook: {e}")

    # Build position rules from the JSON
    rules = []
    for r in raw.get("rules", []):
        fallbacks = tuple(
            pos.Position(f["text"], f.get("value"))
            for f in r.get("fallbacks", [])
        )
        db = r.get("dealbreaker")
        dealbreaker = pos.Position(db["text"], db.get("value")) if db else None
        starting = pos.Position(r["starting"]["text"], r["starting"].get("value"))

        rules.append(pos.PositionRule(
            id=r["id"], clause=r["clause"],
            starting=starting, fallbacks=fallbacks,
            dealbreaker=dealbreaker,
            priority=r.get("priority", pos.MANDATORY),
            comparator=r.get("comparator", "equals"),
            applicability=r.get("applicability"),
        ))

    playbook = pos.PositionPlaybook(
        id=raw.get("id", "unknown"),
        version=raw.get("version", "0"),
        rules=tuple(rules),
    )

    # Also load the basic playbook for the extraction model
    # The basic playbook path is derived: nda_positions_v1.json → nda_v1.json
    basic_path_str = book_path.replace("_positions_", "_")
    basic_full = root / basic_path_str
    if basic_full.exists():
        try:
            basic_book = pb.load(basic_full)
        except pb.PlaybookError:
            basic_book = None
    else:
        basic_book = None

    # Extract clause values using the model (or fixture for testing)
    wanted = [r.clause for r in rules]
    model = None
    route = None
    proposed = ()
    extracted_map: dict[str, tuple[str, str]] = {}

    # Try to get a model for extraction
    from gateway.verbs import model_access
    name = args.get("name") or "contract"
    try:
        origin = public_only.clear_matter(
            text, name=name, provider="azure",
            test_data=ctx.synthetic_fixtures and args.get("test_data") in ("fixture", "synthetic"))
    except public_only.NotPublic as e:
        return _refuse("NOT_PERMITTED", str(e))

    from checker import azure_model
    try:
        azure_model.refuse_unconfirmed_region(origin)
    except azure_model.ModelRefused as e:
        return _refuse("NOT_PERMITTED", str(e))

    served, refusal = model_access._served_or_refusal(
        origin, name="redline", purpose=router.EXTRACTION,
        consequence=router.HIGH, ctx=ctx)
    if refusal:
        return refusal

    # Extract
    prompt = rc.extract_prompt(text, wanted)
    proposed = rc.parse_reply(served.call(prompt))

    for p in proposed:
        ext, _why = rc.verify(p, text)
        if ext.verified:
            extracted_map[ext.clause] = (ext.span, ext.value)

    # Resolve positions
    clause_values = {clause: val for clause, (_span, val) in extracted_map.items()}
    results = pos.resolve_all(playbook, clause_values)

    # Generate edits
    edits = redline.generate_edits(results, playbook.rules, extracted_map)

    return {
        "playbook_id": playbook.id,
        "playbook_status": raw.get("status", "DRAFT"),
        "scope": args.get("scope", "full"),
        "edits": [e.to_dict() for e in edits],
        "law_not_held": [{"body": k, "refusal": r} for k, r in rc.law_notes()],
    }


# ── self-test ──────────────────────────────────────────────────────────────

def _self_test() -> None:
    """Offline test: load a positions playbook, build rules, resolve, generate edits."""
    passed = failed = 0

    def check(name: str, cond: bool) -> None:
        nonlocal passed, failed
        if cond:
            print(f"  [PASS] {name}")
            passed += 1
        else:
            print(f"  [FAIL] {name}")
            failed += 1

    root = Path(__file__).resolve().parent.parent.parent

    # Load the NDA positions playbook
    from checker import positions as pos, redline

    p = root / "playbooks" / "nda_positions_v1.json"
    raw = json.loads(p.read_text())
    check("nda positions playbook loads", bool(raw.get("rules")))

    rules = []
    for r in raw["rules"]:
        fallbacks = tuple(
            pos.Position(f["text"], f.get("value"))
            for f in r.get("fallbacks", [])
        )
        db = r.get("dealbreaker")
        dealbreaker = pos.Position(db["text"], db.get("value")) if db else None
        starting = pos.Position(r["starting"]["text"], r["starting"].get("value"))
        rules.append(pos.PositionRule(
            id=r["id"], clause=r["clause"],
            starting=starting, fallbacks=fallbacks,
            dealbreaker=dealbreaker,
            priority=r.get("priority", pos.MANDATORY),
            comparator=r.get("comparator", "equals"),
            applicability=r.get("applicability"),
        ))

    playbook = pos.PositionPlaybook(id=raw["id"], version=raw["version"], rules=tuple(rules))
    check("playbook built", len(playbook.rules) == len(raw["rules"]))

    # Simulate: a contract with 3yr term (fallback), Indian law (starting), London seat (not acceptable)
    extracted = {
        "term": ("three years", "three years"),
        "survival_period": ("two years", "two years"),
        "governing_law": ("India", "India"),
        "arbitration_seat": ("London", "London"),
        "liability_cap": ("Rs 50,00,000", "Rs 50,00,000"),
    }
    clause_values = {c: v for c, (_s, v) in extracted.items()}
    results = pos.resolve_all(playbook, clause_values)
    check("resolve_all returns results", len(results) == len(rules))

    edits = redline.generate_edits(results, playbook.rules, extracted)
    check("edits generated for all rules", len(edits) == len(rules))

    # term is 3yr, max_years starting is 2yr → STARTING (3 <= not applicable, it's max_years so 3 > 2 → ?)
    # Wait — NDA term uses max_years with starting 2yr. 3yr > 2yr → NOT starting.
    # Fallback is 3yr. 3yr <= 3yr → FALLBACK.
    term_edit = next(e for e in edits if e.clause == "term")
    check("term 3yr is FALLBACK", term_edit.status == pos.FALLBACK)
    check("term edit is REWRITE", term_edit.kind == redline.REWRITE)

    gov_edit = next(e for e in edits if e.clause == "governing_law")
    check("governing_law India is STARTING", gov_edit.status == pos.STARTING)
    check("governing_law is NO_EDIT", gov_edit.kind == redline.NO_EDIT)

    seat_edit = next(e for e in edits if e.clause == "arbitration_seat")
    check("London seat is NOT_ACCEPTABLE", seat_edit.status == pos.NOT_ACCEPTABLE)
    check("seat edit is REWRITE", seat_edit.kind == redline.REWRITE)

    cap_edit = next(e for e in edits if e.clause == "liability_cap")
    check("50L cap is STARTING", cap_edit.status == pos.STARTING)

    # notice_period is not extracted → NEEDS_LAWYER
    notice = next((e for e in edits if e.clause == "notice_period"), None)
    if notice:
        check("missing notice_period is NEEDS_LAWYER", notice.status == pos.NEEDS_LAWYER)

    # SHA playbook loads too
    sp = root / "playbooks" / "sha_positions_v1.json"
    raw2 = json.loads(sp.read_text())
    check("sha positions playbook loads", len(raw2.get("rules", [])) == 10)

    # all edits serialize
    for e in edits:
        d = e.to_dict()
        check(f"{e.clause} serializes", isinstance(d, dict) and "kind" in d)

    print(f"\n{passed + failed} tests, {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    _self_test()
