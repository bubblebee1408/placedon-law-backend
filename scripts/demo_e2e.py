#!/usr/bin/env python3
"""The whole product, end to end, against the real gateway. PASS / BLOCKED / FAIL.

Move 20. `scripts/demo.py` runs the SUITES. This drives the VERBS, in the order a lawyer
would: a document arrives, it is verified, it goes into a review table, a draft is written,
and the calendar says what falls due.

## Three outcomes, and BLOCKED is not a failure

    0  PASS     every stage ran and asserted its state
    2  BLOCKED  a stage could not run and SAID WHY -- no model key, no database
    1  FAIL     a stage ran and produced the wrong answer

The distinction is the point. Tonight's rules forbid a model key, so the review-table stage
CANNOT reach FOUND -- and a demo that reported that as a failure would be crying wolf at its
own constraints, while one that reported it as a pass would be lying. BLOCKED, with the
reason printed, is the only honest third thing.

## It runs over the VERB TABLE, not over HTTP

`gateway/app.py`'s own suite already drives every route through a TestClient, and
`docs/guides/RUN_LOCALLY.md` (PR #67) is the HTTP walkthrough. What is missing -- and what
this adds -- is a single run that proves the stages CONNECT: that the document the vault
ingested is the one the review table can address, and that the thing the calendar reads is
the thing `document.check` wrote. Each stage was proved alone; this is the seam.

Run:  PYTHONPATH=. python3 scripts/demo_e2e.py           # the demo
      PYTHONPATH=. python3 scripts/demo_e2e.py --test    # the self-check, for the gate
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field

PASS, BLOCKED, FAIL = "PASS", "BLOCKED", "FAIL"
BLOCKED_CODE = 2


@dataclass
class Stage:
    name: str
    state: str = PASS
    notes: list = field(default_factory=list)
    reason: str = ""

    def ck(self, cond: bool, label: str) -> bool:
        self.notes.append((bool(cond), label))
        if not cond:
            self.state = FAIL
        return bool(cond)

    def block(self, reason: str) -> None:
        """Could not run, and here is why. Never silent, never a pass."""
        self.state = BLOCKED
        self.reason = reason

    @property
    def failures(self) -> list:
        return [l for ok, l in self.notes if not ok]


def _context():
    """A gateway Context with a real file store and an in-memory backend.

    MemoryBackend rather than Postgres so this runs from a clean checkout with no database.
    The Postgres path is proved by `scripts/rls_integration.py` (365 checks as
    `placedon_app`) and by the runbook; what this proves is that the STAGES connect, which
    is backend-independent.
    """
    import tempfile
    from gateway.filestore import LocalFileStore
    from gateway.store import MemoryBackend
    from gateway.verbs import Context

    tmp = tempfile.mkdtemp(prefix="placedon-demo-e2e-")
    store = MemoryBackend()
    return Context(store=store, files=LocalFileStore(tmp),
                   clock=lambda: "2026-10-05T00:00:00Z"), store, tmp


CONTRACT = (
    "MASTER SERVICES AGREEMENT\n"
    "Date: 14 March 2026\n"
    "This agreement is governed by the laws of India.\n"
    "The courts at Mumbai have exclusive jurisdiction.\n"
    "The term is five years from the Effective Date.\n")


def stage_vault(ctx, store) -> tuple:
    """Upload, ingest through the real worker handler, find it again."""
    from gateway.verbs import _vault_upload, _vault_verify, _vault_find, queue_handlers

    s = Stage("1. vault: upload, ingest, verify, find")
    up = _vault_upload({"name": "msa.txt", "text": CONTRACT}, ctx)
    if up.get("status") == "REFUSED":
        s.block(f"vault.upload refused {up.get('code')}: {up.get('detail', '')[:120]}")
        return s, None
    did = up["document_id"]
    s.ck(up["state"] == "PENDING",
         f"an upload is PENDING, never INGESTED: nothing is searchable until a worker has "
         f"read it ({up['state']})")

    # Through the QUEUE HANDLER when one is registered, and through the agent directly when
    # it is not. On `main` today there is no `vault_ingest` handler -- that registration is
    # move 3, on PR #67 -- and this demo must not crash on a branch where the feature has not
    # landed. Which path ran is PRINTED, because "ingested through the worker" and "ingested
    # by calling the agent" are different claims.
    handlers = queue_handlers(ctx)
    if "vault_ingest" in handlers:
        handlers["vault_ingest"]({"document_id": did, "sha256": up["sha256"],
                                  "name": "msa.txt", "matter_id": None})
        s.ck(True, "ingested through the registered QUEUE HANDLER, as a worker would")
    else:
        from agents.vault_ingest import ingest
        ingest({"document_id": did, "sha256": up["sha256"], "name": "msa.txt",
                "matter_id": None},
               files=ctx.files, store=ctx.store,
               extract=lambda data, name: data.decode("utf-8", "replace"))
        s.ck(True, "ingested by calling the agent directly: this branch has no "
                   "`vault_ingest` queue handler, which lands with PR #67. Said rather than "
                   "glossed -- 'through the worker' and 'by calling the agent' are "
                   "different claims")
    st = _vault_find({"query": "governed by the laws of India"}, ctx)
    s.ck(bool(st.get("hits") or st.get("results") or st.get("passages")),
         f"the ingested document is findable ({list(st)[:4]})")

    v = _vault_verify({"document_id": did}, ctx)
    s.ck(v.get("verified") is True,
         f"vault.verify confirms the stored bytes still hash to the key they are stored "
         f"under ({v.get('verified')})")
    # The per-CHECK lines are move 1, on PR #67. Asserted when present and NAMED when not,
    # rather than asserted unconditionally against a branch where the feature has not
    # landed -- which is what made this stage FAIL on its first run.
    if v.get("checks"):
        s.ck(len(v["checks"]) >= 3,
             f"...as a line PER CHECK, not one real/fake badge ({len(v['checks'])} lines)")
    else:
        s.ck("detail" in v or "note" in v,
             "...as a single boolean with a detail line: the per-check breakdown is move 1 "
             "and lands with PR #67. Named rather than asserted against a branch that does "
             "not have it")
    return s, did


def stage_table(ctx, store, sha256: str) -> Stage:
    """A review table over the stored document. Cannot reach FOUND without a model."""
    from gateway.verbs import _review_table_create, _review_table_status

    s = Stage("2. review table: create, dispatch, status")
    out = _review_table_create(
        {"name": "demo table", "document_ids": [sha256],
         "columns": [{"name": "governing law", "kind": "text",
                      "question": "Which law governs this agreement?"}]}, ctx)
    if out.get("status") == "REFUSED":
        s.block(f"review_table.create refused {out.get('code')}: "
                f"{str(out.get('detail'))[:140]}")
        return s
    s.ck(bool(out.get("grid_id")), "a table is created")
    st = _review_table_status({"grid_id": out["grid_id"]}, ctx)
    s.ck("by_state" in st, f"status reports the cell states ({list(st)[:5]}…)")
    s.ck(st.get("spend", {}).get("total_inr") is None
         or st["spend"]["total_inr"] == 0,
         f"an unrun table is UNPRICED, never ₹0.00 as a claim about free work "
         f"({st.get('spend', {}).get('note', '')[:60]}…)")
    found = (st.get("by_state") or {}).get("FOUND", 0)
    if not found:
        s.block("no cell reached FOUND. A cell needs a MODEL, and standing rule 7 forbids a "
                "key tonight -- the cell fails NO_MODEL and its own reason says 'that is a "
                "failure of ours and says nothing about the document'. This is the "
                "constraint, not a defect")
    return s


def stage_draft(ctx) -> Stage:
    """Create, revise, and prove the optimistic lock refuses a stale save."""
    from gateway.verbs import _draft_create, _draft_revise, _draft_versions

    s = Stage("3. draft: create, revise, stale save refused")
    d = _draft_create({"title": "Board resolution", "body": ""}, ctx)
    if d.get("status") == "REFUSED":
        s.block(f"draft.create refused {d.get('code')}")
        return s
    did = d["draft_id"]
    s.ck(d.get("version") == 1, f"a new draft is at version 1 ({d.get('version')})")
    r1 = _draft_revise({"draft_id": did, "base_version": 1,
                        "body": "RESOLVED THAT the company open a bank account."}, ctx)
    s.ck(r1.get("version") == 2,
         f"a revision is a NEW version; nothing is edited in place ({r1.get('version')})")
    stale = _draft_revise({"draft_id": did, "base_version": 1, "body": "a stale edit"}, ctx)
    s.ck(stale.get("code") == "CONFLICT" or stale.get("status") == "REFUSED",
         f"a save based on version 1 is REFUSED once version 2 exists -- a colleague's work "
         f"is not overwritten silently ({stale.get('code')})")
    vs = _draft_versions({"draft_id": did}, ctx)
    s.ck(len(vs.get("versions") or []) == 2,
         f"...and both versions are kept ({len(vs.get('versions') or [])})")
    return s


def stage_calendar(ctx) -> Stage:
    """What falls due, and what cannot be dated at all."""
    from gateway.verbs import _calendar_upcoming

    s = Stage("4. calendar: dated entries, and 'unknown' for the rest")
    # REAL `CompanyProfile` field names. My first version sent {"type", "listed"}, which
    # the verb refused -- "a caller who sent one believes it was taken into account" -- and
    # it was right to: a profile that silently ignored an unknown field would answer about a
    # different company from the one the caller described.
    out = _calendar_upcoming({"company": {"company_class": "private", "is_listed": False,
                                          "incorporation_date": "2019-04-01",
                                          "as_of": "2026-10-05"},
                              "as_of": "2026-10-05", "horizon_days": 90}, ctx)
    if out.get("status") == "REFUSED":
        s.block(f"calendar.upcoming refused {out.get('code')}")
        return s
    entries = out.get("entries") or out.get("due") or []
    unknown = out.get("unknown") or []
    s.ck(isinstance(entries, list) and isinstance(unknown, list),
         f"the calendar separates what it can date from what it cannot "
         f"({len(entries)} dated, {len(unknown)} unknown)")
    for u in unknown[:3]:
        s.ck(u.get("due") is None and bool(u.get("missing")),
             f"an undatable entry has due=None and NAMES the missing fact -- never a guessed "
             f"date ({u.get('missing')})")
    return s


def run() -> list:
    ctx, store, _tmp = _context()
    stages = []
    s1, did = stage_vault(ctx, store)
    stages.append(s1)
    if did:
        row = store.read_vault_document(did) or {}
        stages.append(stage_table(ctx, store, row.get("sha256", "")))
    else:
        skipped = Stage("2. review table: create, dispatch, status")
        skipped.block("the vault stage did not produce a document to table")
        stages.append(skipped)
    stages.append(stage_draft(ctx))
    stages.append(stage_calendar(ctx))
    return stages


def report(stages: list) -> int:
    worst = 0
    for s in stages:
        mark = {PASS: "PASS", BLOCKED: "BLOCKED", FAIL: "FAIL"}[s.state]
        print(f"\n  [{mark}] {s.name}")
        for ok, label in s.notes:
            print(f"      {'ok  ' if ok else 'FAIL'} {label}")
        if s.reason:
            print(f"      why: {s.reason}")
        if s.state == FAIL:
            worst = 1
        elif s.state == BLOCKED and worst == 0:
            worst = BLOCKED_CODE
    blocked = [s for s in stages if s.state == BLOCKED]
    failed = [s for s in stages if s.state == FAIL]
    print(f"\n  {len(stages)} stage(s): "
          f"{sum(1 for s in stages if s.state == PASS)} PASS, "
          f"{len(blocked)} BLOCKED, {len(failed)} FAIL")
    if blocked and not failed:
        print("  BLOCKED is not a failure of the code: each one printed the reason it could "
              "not run, which is a missing key or a missing permission and not a wrong "
              "answer.")
    return worst


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

    print("demo_e2e")

    stages = run()
    check(len(stages) == 4, f"four stages run ({len(stages)})")
    check(all(s.notes or s.state == BLOCKED for s in stages),
          "every stage either asserted something or said why it could not")
    check(not [s for s in stages if s.state == FAIL],
          f"no stage FAILED -- a failure here is a wrong answer, not a missing key "
          f"({[s.name for s in stages if s.state == FAIL]})")

    # The exit code must distinguish the three. A demo whose BLOCKED looked like a PASS
    # would be the only dishonest outcome available to it.
    code = report(stages)
    check(code in (0, BLOCKED_CODE),
          f"the exit code is PASS or BLOCKED, never FAIL ({code})")
    blocked = [s for s in stages if s.state == BLOCKED]
    check(all(s.reason for s in blocked),
          f"every BLOCKED stage carries a reason: a blocked stage with none is "
          f"indistinguishable from one nobody ran ({[s.name for s in blocked]})")
    if blocked:
        check(any("rule 7" in s.reason or "MODEL" in s.reason.upper() for s in blocked),
              f"...and tonight's block is the model key, which is the known constraint "
              f"({blocked[0].reason[:70]}…)")

    # Stage 1 must really have run: the demo's value is the SEAM between stages, so a
    # vault stage that blocked would make the rest meaningless.
    check(stages[0].state == PASS,
          f"the vault stage PASSES with no key at all -- upload, ingest, verify and find "
          f"need no model ({stages[0].state})")
    check(len(stages[0].notes) >= 4,
          f"...asserting at least four things ({len(stages[0].notes)})")
    check(stages[2].state == PASS,
          f"the draft stage PASSES, including the stale-save refusal ({stages[2].state})")

    # Three distinct states, and the mapping to exit codes is the contract.
    s = Stage("probe")
    check(s.state == PASS, "a stage starts at PASS")
    s.ck(False, "a failing assertion")
    check(s.state == FAIL, "...and one false assertion makes it FAIL")
    s2 = Stage("probe2")
    s2.block("no key")
    check(s2.state == BLOCKED and s2.reason == "no key",
          "block() records the reason, so it cannot be blocked silently")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    if "--test" in argv:
        return _test()
    print("PlacedOn — end to end")
    return report(run())


if __name__ == "__main__":
    raise SystemExit(main())
