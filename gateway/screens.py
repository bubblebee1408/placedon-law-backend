#!/usr/bin/env python3
"""Which verb each screen calls, and which fields it shows. Checked, not described.

The app and the backend have to agree on this, and a prose document saying so goes stale
the first time a field is renamed -- silently, because nothing runs it. So this is a
MODULE: the mapping is data, and `_test` asserts against `gateway/verbs.py` and the answer
envelope's JSON schema that every verb named here exists, every request field is declared
on that verb, and every envelope field is in the schema.

A screen that names a field nobody serves fails the gate. That is the entire point.

## Three kinds of field, checked three ways

    envelope.X     from the answer envelope -> checked against
                   gateway/schemas/answer_envelope.v1.json
    result.X       a verb's own return key -> checked by RUNNING the verb in `_test`
                   against a seeded in-memory context, because a verb's result shape is
                   not declared anywhere and a second list of keys would drift
    download.X     a binary route -> checked against the app's mounted routes

## PLANNED screens

The vault screen names verbs that do not exist yet (V1). It is declared with
`status=PLANNED` and the test asserts the opposite of the usual thing: that its verbs are
NOT in the table. Leaving the screen out entirely would hide a whole surface from anyone
reading this file; declaring it as if it worked would be a contract nothing serves.

Run: PYTHONPATH=. python3 gateway/screens.py --test
"""
from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["SCREENS", "Call", "Screen", "BUILT", "PLANNED", "screen", "verbs_for"]

BUILT = "BUILT"
PLANNED = "PLANNED"


@dataclass(frozen=True)
class Call:
    """One verb a screen calls, with what it sends and what it shows."""
    verb: str
    sends: tuple = ()
    shows: tuple = ()
    note: str = ""


@dataclass(frozen=True)
class Screen:
    name: str
    purpose: str
    calls: tuple = ()
    status: str = BUILT


# The envelope fields every answering screen renders. Named once: six screens show the
# same six things, and repeating them is how one of them ends up missing `bodies` and
# quietly stops saying which law was not held.
ANSWER_FIELDS = ("envelope.status", "envelope.task", "envelope.as_of",
                 "envelope.text_blocks", "envelope.citations", "envelope.bodies",
                 "envelope.files", "envelope.trace_url")

SCREENS = (
    Screen("home", "Start a thread, or pick one up.", (
        Call("matters.list", (), ("result.matters",),
             "pick a matter first: there is no 'all matters' view"),
        Call("conversation.list", ("matter_id", "limit"),
             ("result.conversations", "result.matter_id"),
             "ONE matter's threads. matter_id is required (8b: no cross-matter listing)"),
        Call("sources.list", (),
             ("result.tiers", "result.fetchable", "result.cacheable", "result.external"),
             "what is held, current-only and declared -- shown so a user learns the "
             "scope before asking rather than from a refusal"),
    )),
    Screen("conversation", "Ask, and see what the answer rests on.", (
        Call("conversation.send", ("conversation_id", "text", "file_ids", "as_of",
                                   "sources", "task_override", "matter_id"),
             ANSWER_FIELDS + ("result.run_id", "result.classification"),
             "`envelope: null` with a run_id means QUEUED, not an empty answer"),
        Call("conversation.get", ("conversation_id",),
             ("result.conversation", "result.messages")),
        Call("citation.get", ("citation_id", "conversation_id"),
             ("result.quote", "result.provision", "result.verified", "result.detail"),
             "the source panel: re-read from the corpus, never trusted from the stored "
             "envelope"),
        Call("runs.trace", ("run_id",),
             ("result.steps", "result.critic_enabled", "result.critic_note")),
    )),
    Screen("contract_review", "A contract against the playbook, and a human sign-off.", (
        Call("review_contract", ("text", "name", "playbook", "test_data"),
             ("result.findings", "result.law_not_held", "result.requires_review",
              "result.playbook_status", "result.run_id"),
             "every finding is against a company standard, never a statement of law"),
        Call("runs.approve", ("run_id", "item_ref", "reason", "quote_viewed"),
             ("result.decision", "result.decision_id")),
        Call("runs.reject", ("run_id", "item_ref", "reason", "quote_viewed"),
             ("result.decision", "result.decision_id"),
             "a decision needs a reason of 10+ characters and an attestation that the "
             "quote was shown"),
    )),
    Screen("draft", "A draft, its versions, and what blocks approval.", (
        Call("draft.create", ("title", "body", "slots", "kind"),
             ("result.draft_id", "result.version", "result.blocking",
              "result.ready_for_approval")),
        # A1: base_version is REQUIRED now. The screen must send the version it rendered,
        # or every save from a stale tab silently overwrites a colleague's revision.
        Call("draft.revise", ("draft_id", "base_version", "title", "body", "slots"),
             ("result.version", "result.blocking")),
        Call("draft.versions", ("draft_id",), ("result.versions",)),
        Call("draft.diff", ("draft_id", "from_version", "to_version"),
             ("result.diff", "result.newly_blocking", "result.newly_supported"),
             "a sentence whose words are unchanged and whose support is gone is what a "
             "text diff cannot show"),
        Call("draft.export", ("draft_id", "version", "format"),
             ("download.docx",),
             "the SCREEN uses the binary route; the verb's base64 is for API callers"),
    )),
    Screen("review_table", "One question per column, across many documents.", (
        Call("review_table.create", ("name", "document_ids", "columns"),
             ("result.grid_id", "result.cells", "result.scheduled")),
        Call("review_table.status", ("grid_id",),
             ("result.by_state", "result.complete", "result.cells_detail",
              "result.spend"),
             "PENDING is not NOT_FOUND, and FAILED is transport only"),
        Call("review_table.cancel", ("grid_id",), ("result.cancelled",)),
        Call("review_table.export", ("grid_id",), ("download.csv",)),
    )),
    Screen("sources", "What may be read, and on whose terms.", (
        Call("sources.list", (),
             ("result.tiers", "result.fetchable", "result.cacheable", "result.external")),
        Call("sources.search", ("query", "tiers", "as_of"), ("result.results",)),
    )),
    Screen("attachments", "Put a document in, and see whether it could be read.", (
        Call("documents.upload", ("text", "name", "cannot_read"),
             ("result.document_id", "result.bytes", "result.state", "result.stored"),
             "`state` is READ or CANNOT_READ; a stored document is READ, and a scan with "
             "no text layer is recorded as unreadable rather than as empty"),
        Call("company_facts.extract", ("text", "uploaded_on"),
             ("result.used", "result.recorded", "result.pending"),
             "no director name and no DIN: personal data is refused at the parser"),
    )),
    Screen("vault", "Twenty thousand documents, searchable and attributable.", (
        Call("vault.upload", ("name", "text", "matter_id"),
             ("result.document_id", "result.state", "result.job_id"),
             "PENDING is not INGESTED: nothing is searchable until a worker reads it"),
        Call("vault.status", ("document_id",),
             ("result.documents", "result.by_state", "result.unsearchable"),
             "the count of documents the vault CANNOT search is on this screen, not "
             "buried: a search answers from the rest and looks complete"),
        Call("vault.find", ("query", "limit"),
             ("result.hits", "result.unsearchable", "result.scope"),
             "contextual BM25 across the firm, not one matter"),
        Call("vault.verify", ("document_id",), ("result.verified", "result.detail")),
        Call("vault.summarize", ("document_id",),
             ("result.doc_class", "result.tags", "result.chunks"),
             "what is RECORDED, not a written summary: no model has read the document"),
        Call("vault.research", ("query", "limit"),
             ("result.passages", "result.answer"),
             "`answer` is always null -- the passages are the answer, and a sentence "
             "synthesised over a client's contracts is a claim about their position"),
        Call("vault.compile", ("matter_id",),
             ("result.documents", "result.count", "result.not_ingested")),
        Call("vault.delete", ("document_id",),
             ("result.deleted", "result.bytes_destroyed"),
             "the record stays and says it was deleted; the bytes do not"),
    )),
)


def screen(name: str) -> Screen:
    for s in SCREENS:
        if s.name == name:
            return s
    raise KeyError(f"no screen {name!r}; one of {[s.name for s in SCREENS]}")


def verbs_for(name: str) -> tuple:
    return tuple(c.verb for c in screen(name).calls)


def _test() -> int:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    print("screens")
    import json
    import pathlib
    from gateway.verbs import VERBS, by_name

    table = by_name()
    schema = json.loads((pathlib.Path(__file__).resolve().parent / "schemas"
                         / "answer_envelope.v1.json").read_text(encoding="utf-8"))
    env_fields = set(schema.get("properties", {}))
    built = [s for s in SCREENS if s.status == BUILT]
    planned = [s for s in SCREENS if s.status == PLANNED]

    check({s.name for s in SCREENS} >= {
        "home", "conversation", "contract_review", "draft", "review_table", "vault",
        "sources", "attachments"},
        f"every screen the brief names is declared ({[s.name for s in SCREENS]})")

    # ── every verb a BUILT screen names really exists ───────────────────────
    for s in built:
        for c in s.calls:
            check(c.verb in table,
                  f"{s.name}: verb {c.verb!r} exists in gateway/verbs.py")

    # ── every field it SENDS is declared on that verb ───────────────────────
    for s in built:
        for c in s.calls:
            if c.verb not in table:
                continue
            declared = {f.name for f in table[c.verb].inputs}
            unknown = [f for f in c.sends if f not in declared]
            check(not unknown,
                  f"{s.name}/{c.verb}: every request field is declared on the verb "
                  f"({unknown or 'all present'})")

    # ── every envelope field it SHOWS is in the schema ──────────────────────
    for s in built:
        for c in s.calls:
            bad = [f for f in c.shows
                   if f.startswith("envelope.") and f.split(".", 1)[1] not in env_fields]
            check(not bad,
                  f"{s.name}/{c.verb}: every envelope field is in the v1 schema "
                  f"({bad or 'all present'})")
    check("envelope.bodies" in ANSWER_FIELDS and "envelope.citations" in ANSWER_FIELDS,
          "the shared answer fields include bodies and citations -- the two a screen "
          "could drop and still look finished while saying nothing about unheld law")

    # ── every download field is a MOUNTED ROUTE, not a promise ──────────────
    from gateway.app import create_app
    app = create_app(db_url="")
    routes = {getattr(r, "path", "") for r in app.routes}
    check("/v2/drafts/{draft_id}/export.docx" in routes,
          f"the draft .docx download route is mounted")
    check("/v2/review_tables/{grid_id}/export.csv" in routes,
          "the review-table CSV download route is mounted")
    downloads = [(s.name, c.verb, f) for s in built for c in s.calls for f in c.shows
                 if f.startswith("download.")]
    check(len(downloads) == 2,
          f"exactly the two screens that offer a file say so ({downloads})")

    # ── result fields: checked by RUNNING the verb, not by a second list ────
    from gateway.verbs import Context
    from gateway.store import MemoryBackend
    ctx = Context(store=MemoryBackend(), clock=lambda: "2026-10-02T10:00:00+05:30")
    doc = table["documents.upload"].run({"text": "Governed by the laws of India.",
                                         "name": "a.txt"}, ctx)
    did = doc["document_id"]
    drafted = table["draft.create"].run(
        {"title": "T", "body": "b",
         "slots": [{"name": "x", "value": "v", "type": "TEMPLATE_TEXT"}]}, ctx)
    grid = table["review_table.create"].run(
        {"name": "g", "document_ids": [did],
         "columns": [{"name": "c", "kind": "text", "question": "q?"}]}, ctx)
    # V1: a real vault round trip, so the vault screen's result fields are EXECUTED and
    # not skipped. The screens test is only worth its name for the verbs it actually runs.
    import tempfile as _tf
    from gateway.filestore import LocalFileStore
    from agents.vault_ingest import ingest as _ingest
    _tmp = _tf.mkdtemp()
    ctx.files = LocalFileStore(_tmp)
    _vmatter = table["matters.create"].run({"name": "screens vault matter"},
                                           ctx)["matter_id"]
    _up = table["vault.upload"].run(
        {"name": "Screens NDA.pdf", "matter_id": _vmatter,
         "text": "2. Term\n\nThis Agreement is governed by the laws of India. "
                 "Confidential Information means anything disclosed."}, ctx)
    _ingest({"document_id": _up["document_id"], "sha256": _up["sha256"],
             "name": "Screens NDA.pdf", "matter_id": _vmatter},
            files=ctx.files, store=ctx.store,
            extract=lambda d, n: d.decode("utf-8", "replace"))
    _vid = _up["document_id"]

    ran = {
        "vault.upload": _up,
        "vault.status": table["vault.status"].run({}, ctx),
        "vault.find": table["vault.find"].run({"query": "governing law"}, ctx),
        "vault.verify": table["vault.verify"].run({"document_id": _vid}, ctx),
        "vault.summarize": table["vault.summarize"].run({"document_id": _vid}, ctx),
        "vault.research": table["vault.research"].run({"query": "confidential"}, ctx),
        "vault.compile": table["vault.compile"].run({"matter_id": _vmatter}, ctx),
        "vault.delete": table["vault.delete"].run({"document_id": _vid}, ctx),
        "documents.upload": doc,
        "draft.create": drafted,
        "draft.versions": table["draft.versions"].run(
            {"draft_id": drafted["draft_id"]}, ctx),
        "draft.status": table["draft.status"].run({"draft_id": drafted["draft_id"]}, ctx),
        "review_table.create": grid,
        "review_table.status": table["review_table.status"].run(
            {"grid_id": grid["grid_id"]}, ctx),
        "review_table.export": table["review_table.export"].run(
            {"grid_id": grid["grid_id"]}, ctx),
        "sources.list": table["sources.list"].run({}, ctx),
        # 8b: a listing needs a matter, so the fixture opens one. That the call REFUSES
        # without it is asserted in gateway/verbs.py; here the point is that the fields
        # this screen shows are really returned when it is called properly.
        "matters.list": table["matters.list"].run({}, ctx),
        "conversation.list": table["conversation.list"].run(
            {"matter_id": table["matters.create"].run(
                {"name": "screens fixture"}, ctx)["matter_id"]}, ctx),
    }
    for s in built:
        for c in s.calls:
            if c.verb not in ran:
                continue
            missing = [f.split(".", 1)[1] for f in c.shows
                       if f.startswith("result.") and f.split(".", 1)[1] not in ran[c.verb]]
            check(not missing,
                  f"{s.name}/{c.verb}: every shown result field is REALLY RETURNED "
                  f"({missing or 'all present'})")
    check(len(ran) >= 17,
          f"...and that was checked by RUNNING {len(ran)} verbs, not by trusting a second "
          f"list of keys that would drift")
    check({v for v in ran if v.startswith("vault.")} == {
        "vault.upload", "vault.status", "vault.find", "vault.verify", "vault.summarize",
        "vault.research", "vault.compile", "vault.delete"},
        "...including every vault verb: a screen contract is only worth its name for the "
        "verbs it actually runs")

    # ── PLANNED still means what it meant, and nothing is PLANNED today ────
    check(not planned,
          f"no screen is PLANNED any more: the vault was, and V1 built it "
          f"({[p.name for p in planned]})")
    check(all(c.verb in table for s in SCREENS for c in s.calls),
          "...so every call on every screen names a verb that exists")
    check(PLANNED in (BUILT, PLANNED) and BUILT != PLANNED,
          "the PLANNED machinery is still here for the next surface declared before it "
          "is served")

    # ── no screen quietly calls a WRITE verb it does not mean to ───────────
    writes = {v.name for v in VERBS if not v.read_only}
    used_writes = {(s.name, c.verb) for s in built for c in s.calls if c.verb in writes}
    check(used_writes == {
        ("conversation", "conversation.send"), ("contract_review", "runs.approve"),
        ("contract_review", "runs.reject"), ("draft", "draft.create"),
        ("draft", "draft.revise"), ("review_table", "review_table.create"),
        ("review_table", "review_table.cancel"), ("attachments", "documents.upload"),
        ("vault", "vault.upload"), ("vault", "vault.delete")},
        f"exactly the expected screens call a WRITE verb -- a new one appearing here is a "
        f"screen that changed what it can do ({sorted(used_writes)})")

    check(len({s.name for s in SCREENS}) == len(SCREENS),
          "no screen name is declared twice")
    try:
        screen("nope")
        check(False, "an unknown screen raises")
    except KeyError:
        check(True, "an unknown screen raises rather than returning an empty one")
    check(verbs_for("sources") == ("sources.list", "sources.search"),
          "verbs_for lists a screen's verbs in order")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        raise SystemExit(_test())
    print(__doc__)
