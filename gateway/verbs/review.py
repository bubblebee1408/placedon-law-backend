"""review.contract and review.document."""
from __future__ import annotations

from gateway.verbs import model_access
from gateway.verbs.core import Context, _affirmed, _refuse
from gateway.verbs.run_records import SS_TEXTS, _persist_run, law_versions_of


def _review_contract(args: dict, ctx: Context) -> dict:
    from pathlib import Path

    from agents import review_contract as rc
    from checker import playbook as pb
    text = args.get("text") or ""
    if not text.strip():
        return _refuse("BAD_REQUEST", "text is required")
    book_path = args.get("playbook") or "playbooks/nda_v1.json"
    root = Path(__file__).resolve().parent.parent.parent
    try:
        book = pb.load(root / book_path)
    except pb.PlaybookError as e:
        return _refuse("BAD_REQUEST", f"playbook: {e}")
    from checker import public_only, router
    name = args.get("name") or "contract"
    # The clearance is made HERE, before a route is chosen, so the served callable is bound
    # to this document and cannot be reused against another one.
    try:
        origin = public_only.clear_matter(
            text, name=name, provider="azure",
            test_data=ctx.synthetic_fixtures and (
                _affirmed(args.get("test_data")) or
                args.get("test_data") in ("fixture", "synthetic")))
    except public_only.NotPublic as e:
        return _refuse("NOT_PERMITTED", str(e))
    # Residency is a decision about the DOCUMENT, so it is taken before a route is sought.
    # Checked only inside the Azure call, a gateway with no credentials refused NO_MODEL
    # instead, and the reader was told "outage" where the answer was "not permitted".
    from checker import azure_model
    try:
        azure_model.refuse_unconfirmed_region(origin)
    except azure_model.ModelRefused as e:
        return _refuse("NOT_PERMITTED", str(e))

    served, refusal = model_access._served_or_refusal(origin, name="review_contract",
                                         purpose=router.EXTRACTION,
                                         consequence=router.HIGH, ctx=ctx)
    if refusal:
        refusal["run_id"] = _persist_run(
            ctx, intent="review_contract", status="REFUSED",
            refusal_code=refusal["code"],
            steps=[{"capability": "intake", "status": "ANSWERED"},
                   {"capability": "document", "status": "REFUSED"}],
            propositions=[])
        return refusal

    try:
        out = rc.review(text, book=book, model=served.call, name=name, origin=origin)
    except Exception as e:                                       # noqa: BLE001
        rid = _persist_run(ctx, intent="review_contract", status="FAILED",
                           steps=[{"capability": "document", "status": "FAILED"}],
                           propositions=[])
        return {"status": "FAILED", "error": f"{type(e).__name__}: the provider request could not finish",
                "run_id": rid}
    d = out.to_dict()

    # The run, as a derivation: the steps agents/plans.py declares for this intent, and one
    # proposition per finding. A finding's status is a PLAYBOOK status (MATCHES, DEVIATES,
    # MISSING, NEEDS_LAWYER) and a proposition's is an L0 verification status, so they are
    # mapped rather than copied -- writing "DEVIATES" into a column that means "VERIFIED"
    # would put a company standard where a legal verdict is read from.
    # VERIFIED requires an EXTRACTION that passed span verification -- not merely a
    # finding. The first version derived it by subtraction ("every clause, minus the
    # unverified ones"), and with no model configured nothing is extracted, nothing is
    # unverified, and all ten findings persisted as VERIFIED. Ten MISSING clauses recorded
    # as verified propositions is a falsehood in the one record that is supposed to be
    # trustworthy. So the set is built from what was actually verified, positively.
    verified_clauses = {e.clause for e in out.extracted if e.verified}
    props = [{"status": "VERIFIED" if f.clause in verified_clauses else "UNVERIFIED",
              "source_ref": f"playbook:{f.rule_id}",
              "span_start": None, "span_end": None}
             for f in out.findings]
    fields = served.step_fields()
    steps = [
        {"capability": "intake", "status": "ANSWERED", "degraded": False},
        {"capability": "document", "engine_capability": "document.ground_extraction",
         "status": "ANSWERED", **fields},
        {"capability": "playbook", "engine_capability": "contract.playbook_review",
         "status": "ANSWERED", "degraded": False},
    ]
    d["run_id"] = _persist_run(ctx, intent="review_contract", status="ANSWERED",
                               steps=steps, propositions=props,
                               law_versions=law_versions_of((book_path,)))
    return d


def _review_document(args: dict, ctx: Context) -> dict:
    """SS-1/SS-2 checks over a filing. No model is called, so nothing leaves the process.

    PLAN_23 O1. The classification happens FIRST and in code -- there is no `doc_type` input,
    because a caller who could declare "this is minutes" could turn every minutes check on a
    notice back on, which is the false-positive source the classifier was added to remove.
    """
    from agents import review_document as rd
    try:
        out = rd.review(
            args.get("text") or "",
            meeting_kind=args.get("meeting_kind") or "board",
            meeting_date=args.get("meeting_date"),
            entry_date=args.get("entry_date"),
        )
    except rd.BadRequest as e:
        return _refuse("BAD_REQUEST", str(e))

    d = out.to_dict()
    # An unclassified document is ANSWERED as a RUN -- the work was done and nothing failed
    # -- while its own status says the document was not identified. Recording the run as
    # REFUSED would say we declined to look, and recording it as a clean result would say
    # we looked and found nothing wrong. Neither happened.
    props = [{"status": "UNVERIFIED" if i["status"] in (rd.NEEDS_BOOK, rd.NOT_APPLICABLE)
                        else "VERIFIED",
              "source_ref": f"ss:{i['rule_id']}",
              "span_start": None, "span_end": None}
             for i in d["findings"]]
    steps = [
        {"capability": "intake", "status": "ANSWERED", "degraded": False},
        {"capability": "document", "engine_capability": "document.ground_extraction",
         "status": "ANSWERED" if out.status == rd.ANSWERED else "REFUSED",
         "degraded": False,
         # Named rather than left blank: UNPRICED with no reason is indistinguishable from
         # a cost nobody recorded, and this one has a good reason -- there was no model.
         "cost_note": "no model is called by this intent; the checks are code"},
        {"capability": "verify", "status": "ANSWERED", "degraded": False,
         "cost_note": "no model is called by this intent; the checks are code"},
    ]
    d["run_id"] = _persist_run(ctx, intent="review_document", status="ANSWERED",
                               steps=steps, propositions=props,
                               law_versions=law_versions_of(SS_TEXTS))
    return d
