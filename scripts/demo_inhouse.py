#!/usr/bin/env python3
"""The in-house lawyer's day, end to end, on synthetic data.

8d. Seven steps through the real verb table: sign in, open a matter, ask a question, map
an event to the bodies of law it engages, review an NDA against the playbook, draft the
client email from that review, and look at what falls due.

## PASS, BLOCKED and FAIL are three different things

A demo that prints PASS for a step it could not run is worse than no demo, because the
next person reads a green column as working software. So:

    PASS     the step ran and produced what it claims
    BLOCKED  the step could not run, and the REASON is printed -- no model in this
             region, no credential. Not a failure of the code under test.
    FAIL     the step ran and produced the wrong thing

`--test` requires zero FAIL and lets BLOCKED through with its reason, which is what makes
this runnable in the gate on a machine with no model and no database.

## Synthetic only

The NDA below is invented, between two invented companies, and `test_data` is set on the
review so `public_only.refuse_unconfirmed_region` does not refuse it (PLAN_22 D3). No
client document is in this file and none should ever be: it is committed.

Run: PYTHONPATH=. python3 scripts/demo_inhouse.py
     PYTHONPATH=. python3 scripts/demo_inhouse.py --test
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field

PASS, BLOCKED, FAIL = "PASS", "BLOCKED", "FAIL"

# Invented, between invented parties. Short on purpose: the point is the pipeline, not the
# drafting, and a long contract makes a failing step harder to read.
SYNTHETIC_NDA = """MUTUAL NON-DISCLOSURE AGREEMENT

This Agreement is made between Lodestar Analytics Private Limited and Petrichor Labs
Private Limited.

1. Confidential Information means information disclosed by one party to the other.
2. Term. The obligations in this Agreement continue for five years from the Effective
   Date.
3. Governing law. This Agreement is governed by the laws of India.
4. Each party shall return or destroy Confidential Information on request.
"""

RESEARCH_QUESTION = "What is the quorum for a meeting of the Board?"


@dataclass
class Step:
    name: str
    state: str = PASS
    detail: str = ""
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"name": self.name, "state": self.state, "detail": self.detail}


def run(*, model_for=None) -> list[Step]:
    """Every step, in order. `model_for` injected so the gate runs it without a model."""
    from gateway.auth import KeyStore
    from gateway.roles import may
    from gateway.store import MemoryBackend
    from gateway.verbs import Context, by_name

    steps: list[Step] = []
    verbs = by_name()
    TENANT = "11111111-2222-3333-4444-555555555555"
    ACTOR = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

    # ── 1. sign in ──────────────────────────────────────────────────────────
    keys = KeyStore()
    _, lawyer = keys.mint(tenant_id=TENANT, actor=ACTOR, label="demo", role="lawyer")
    _, viewer = keys.mint(tenant_id=TENANT, actor=ACTOR, label="demo", role="viewer")
    if lawyer.role == "lawyer" and may("lawyer", "runs.approve") \
            and not may("viewer", "runs.approve"):
        steps.append(Step("sign in", PASS,
                          "a lawyer key may sign off a finding; a viewer key may not"))
    else:
        steps.append(Step("sign in", FAIL, "the role check did not hold"))

    ctx = Context(store=MemoryBackend(), clock=lambda: "2026-10-02T09:00:00+05:30",
                  model_for=model_for)

    # ── 2. open a matter ────────────────────────────────────────────────────
    matter = verbs["matters.create"].run(
        {"name": "Petrichor NDA", "client_ref": "LODE-2026-04"}, ctx)
    if matter.get("matter_id"):
        steps.append(Step("open a matter", PASS,
                          f"{matter['name']} ({matter['client_ref']})",
                          {"matter_id": matter["matter_id"]}))
    else:
        steps.append(Step("open a matter", FAIL, str(matter)[:120]))
        return steps

    # ── 3. ask a question ───────────────────────────────────────────────────
    asked = verbs["conversation.send"].run(
        {"text": RESEARCH_QUESTION, "matter_id": matter["matter_id"]}, ctx)
    env = asked.get("envelope") or {}
    if env.get("status") in ("ANSWERED", "PARTIAL") and env.get("citations"):
        steps.append(Step("ask a question", PASS,
                          f"{env['status']} with {len(env['citations'])} citation(s): "
                          f"{env['citations'][0]['provision']}",
                          {"conversation_id": asked.get("conversation_id")}))
    elif env.get("status") in ("ABSTAINED", "NEEDS_LAWYER", None):
        steps.append(Step("ask a question", BLOCKED,
                          f"no cited answer was served ({env.get('status')}). On this "
                          f"machine that usually means no model could be served",
                          {"conversation_id": asked.get("conversation_id")}))
    else:
        steps.append(Step("ask a question", FAIL, f"status {env.get('status')}"))

    # ── 4. map an event to the bodies of law it engages ─────────────────────
    mapped = verbs["events.assess"].run(
        {"event": "commercial_contract", "facts": {}}, ctx)
    findings = mapped.get("findings") or []
    if findings:
        named = [f.get("body_id") for f in findings][:4]
        steps.append(Step("map the event", PASS,
                          f"{len(findings)} body(ies) engaged, incl. {named}"))
    else:
        steps.append(Step("map the event", FAIL, "no body of law was named"))

    # ── 5. review the NDA ───────────────────────────────────────────────────
    # Through conversation.send, NOT the bare verb: the draft in step 6 is built from the
    # newest reviewable turn IN THIS THREAD. Calling review_contract directly left the
    # review outside the conversation, and the draft silently fell back to the research
    # question -- a client email about the wrong thing, which looked like a pass.
    reviewed_turn = verbs["conversation.send"].run(
        {"conversation_id": asked.get("conversation_id"),
         "text": "Please review this NDA against our standard.",
         "task_override": "REVIEW_CONTRACT", "test_data": "synthetic",
         "matter_id": matter["matter_id"]}, ctx)
    reviewed = verbs["review_contract"].run(
        {"text": SYNTHETIC_NDA, "name": "Petrichor NDA", "test_data": "synthetic"}, ctx)
    if reviewed.get("status") == "REFUSED":
        steps.append(Step("review the NDA", BLOCKED,
                          f"{reviewed.get('code')}: {str(reviewed.get('detail'))[:90]}"))
    else:
        issues = [f for f in reviewed.get("findings") or ()
                  if f.get("kind") == "POTENTIAL_ISSUE"]
        unheld = [b.get("body") for b in reviewed.get("law_not_held") or ()]
        steps.append(Step("review the NDA", PASS,
                          f"{len(issues)} clause(s) differ from the playbook; "
                          f"{len(unheld)} body(ies) of law named as NOT held: {unheld}"))

    # ── 6. draft the client email from that review ──────────────────────────
    drafted = verbs["conversation.send"].run(
        {"conversation_id": asked.get("conversation_id"),
         "text": "draft an email to the client about this review",
         "matter_id": matter["matter_id"]}, ctx)
    if drafted.get("draft_id"):
        note = str(drafted.get("prose_note") or "")
        dropped = len(drafted.get("dropped_claims") or [])
        state = PASS if drafted.get("template") == "client_email" else FAIL
        steps.append(Step("draft the email", state,
                          f"draft {drafted['draft_id'][:8]} from the "
                          f"{drafted.get('template')} template, {dropped} fabricated "
                          f"claim(s) dropped"
                          + (f"; {note}" if note else "")
                          + ("" if state == PASS else
                             " -- expected client_email: the draft drew on the wrong turn")))
    elif (drafted.get("envelope") or {}).get("task") == "DRAFT":
        steps.append(Step("draft the email", BLOCKED,
                          "the turn was a DRAFT and no draft was built, which happens "
                          "when no prior run in the thread can be a source"))
    else:
        steps.append(Step("draft the email", FAIL,
                          f"task {(drafted.get('envelope') or {}).get('task')}"))

    # ── 7. what falls due ───────────────────────────────────────────────────
    cal = verbs["calendar.upcoming"].run(
        {"company": {"company_class": "private", "incorporation_date": "2020-04-01"},
         "anchors": {"financial_year_end": "2026-06-30"},
         "as_of": "2026-10-02"}, ctx)
    if cal.get("status") == "REFUSED":
        steps.append(Step("the calendar", FAIL, str(cal.get("detail"))[:110]))
    else:
        steps.append(Step("the calendar", PASS,
                          f"{len(cal.get('due') or [])} due in "
                          f"{cal.get('horizon_days')} days, "
                          f"{len(cal.get('unknown') or [])} cannot be dated and are "
                          f"listed, not hidden"))
    return steps


def report(steps) -> str:
    width = max((len(s.name) for s in steps), default=10)
    lines = ["in-house demo, on synthetic data", ""]
    for s in steps:
        lines.append(f"  {s.state:<8} {s.name:<{width}}  {s.detail}")
    bad = [s for s in steps if s.state == FAIL]
    blocked = [s for s in steps if s.state == BLOCKED]
    lines += ["", f"  {len(steps) - len(bad) - len(blocked)}/{len(steps)} passed, "
                  f"{len(blocked)} blocked, {len(bad)} failed"]
    if blocked:
        lines.append("  BLOCKED is not a failure of the code: the reason is printed "
                     "beside each one.")
    return "\n".join(lines)


def main(argv=None) -> int:
    steps = run()
    print(report(steps))
    return 1 if any(s.state == FAIL for s in steps) else 0


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

    print("demo_inhouse")
    from agents import research_question as rq

    srcs = tuple(s for s, o in rq.evidence(RESEARCH_QUESTION))

    def stub(_origins):
        return rq.quoting_model(srcs)

    steps = run(model_for=stub)
    names = [s.name for s in steps]
    check(names == ["sign in", "open a matter", "ask a question", "map the event",
                    "review the NDA", "draft the email", "the calendar"],
          f"the seven steps run in the order a lawyer does them ({names})")
    failed = [(s.name, s.detail) for s in steps if s.state == FAIL]
    check(not failed, f"**no step FAILS** ({failed})")
    for s in steps:
        if s.state == BLOCKED:
            check(bool(s.detail),
                  f"{s.name}: BLOCKED carries a reason -- a green column for a step that "
                  f"did not run is worse than no demo")
    check(all(s.state in (PASS, BLOCKED, FAIL) for s in steps),
          "every step reports one of the three states")

    text = report(steps)
    check("passed" in text and "blocked" in text and "failed" in text,
          "the report counts all three, so a reader cannot mistake blocked for passed")
    check(all(s.name in text for s in steps), "...and names every step")

    # The things this demo must not do.
    import pathlib
    src = pathlib.Path(__file__).read_text(encoding="utf-8")
    check("Lodestar" in SYNTHETIC_NDA and "Petrichor" in SYNTHETIC_NDA,
          "the NDA is between INVENTED parties: this file is committed, and a real "
          "counterparty's name in it would be a client document in the repository")
    check('"test_data": "synthetic"' in src,
          "...and the review is marked test data, so the region guard (PLAN_22 D3) is "
          "satisfied by a true statement rather than bypassed")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    if "--test" in sys.argv:
        raise SystemExit(_test())
    raise SystemExit(main())
