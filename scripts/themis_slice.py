#!/usr/bin/env python3
"""The THEMIS V0 vertical slice, end to end, on real data.

    python3 scripts/themis_slice.py            # live: poll the Gazette, create work
    python3 scripts/themis_slice.py --test     # offline self-test
    python3 scripts/themis_slice.py --demo     # the worked G.S.R. 880(E) case, offline

Master build plan §79 (V0 target) and §88 (milestone 9). The slice:

    Gazette event -> observation -> affected obligation -> watchlist
                  -> operation -> routed tasks -> evidence budget -> human review

## What this proves, and what it does not

It proves the chain runs on live data and produces **work**. It does not produce a
legal conclusion anywhere along it, and the operation says so in its own words.

One honest limit sits in the middle of the chain, and the runner shows it rather
than hiding it: **a Gazette listing does not name the instrument it contains.**
Measured live 2026-09-23 — every listed row's subject was either truncated by the
site ("Publication of Notification...") or read "This Gazette may contains Multiple
Subjects". The G.S.R. number is inside the PDF.

So for a real Gazette row the first task is "open this and identify the
instrument", and NO obligation is claimed to be affected. `--demo` shows the other
half of the chain, where the instrument IS known, using G.S.R. 880(E) — an
instrument this repository already holds and has attested.

Exit status: 0 = nothing needing a person, 2 = work was created, 1 = the poll
failed. Same convention as `scripts/watch_gazette.py`.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from checker.feeds.egazette import EGazetteFeed          # noqa: E402
from checker.operations import (CORPORATE_DATA, FINANCIAL_DATA,  # noqa: E402
                                HUMAN_REVIEW, LEGAL_RESEARCH, Watchlist,
                                operation_for_gazette_item, operation_for_instrument)
from checker.provenance import ACCESSIBLE                # noqa: E402

# The watchlist is a demo fixture, not a client list: this repo holds no client
# data (PLAN_07 — client documents are never durable here).
DEMO_WATCHLIST = (("U72200KA2019PTC123456", "Acme Holdings Private Limited"),)

_ORDER = (LEGAL_RESEARCH, CORPORATE_DATA, FINANCIAL_DATA, HUMAN_REVIEW)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def demo_watchlist() -> Watchlist:
    wl = Watchlist()
    for cin, name in DEMO_WATCHLIST:
        wl.add(cin, name)
    return wl


def render(op, *, indent: str = "  ") -> str:
    """One operation as a page a person can act on."""
    b = op.budget()
    out = [f"{indent}OPERATION {op.operation_id}",
           f"{indent}  intent : {op.intent}",
           f"{indent}  trigger: {op.trigger.get('gazette_id') or op.trigger.get('instrument', '?')}"
           f"  {op.trigger.get('ministry', '')}".rstrip(),
           f"{indent}  budget : {b.sentence()}"]
    for spec in _ORDER:
        tasks = op.tasks_for(spec)
        if not tasks:
            continue
        out.append(f"{indent}  {spec} ({len(tasks)})")
        for r in tasks:
            mark = "!" if r.criticality == "BLOCKING" else " "
            out.append(f"{indent}   {mark} {r.question}")
            if r.note:
                out.append(f"{indent}     ({r.note})")
    out.append(f"{indent}  NOTE: {op.what_this_is_not}")
    return "\n".join(out)


def run_live(*, feed=None, watchlist=None) -> tuple[int, list]:
    """Poll the Gazette and create one operation per listed item."""
    feed = feed or EGazetteFeed()
    watchlist = watchlist or demo_watchlist()
    result = feed.fetch()
    obs = feed.parse(result, observed_at=_now())
    if obs.source_behaviour != ACCESSIBLE or not obs.payload.get("items"):
        return 1, []
    ops = [operation_for_gazette_item(item, watchlist=watchlist)
           for item in obs.payload["items"]]
    return (2 if ops else 0), ops


def run_demo(*, watchlist=None) -> list:
    """The other half of the chain: an instrument this repo already holds."""
    watchlist = watchlist or demo_watchlist()
    trigger = {"gazette_id": "CG-DL-E-01122025-268124",
               "ministry": "Ministry of Corporate Affairs",
               "published": "01-12-2025", "instrument": "G.S.R. 880(E)",
               "pdf_url": "https://egazette.gov.in/WriteReadData/2025/268124.pdf"}
    op = operation_for_instrument("880", trigger=trigger, watchlist=watchlist)
    return [op] if op else []


def _test() -> int:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    import hashlib

    from checker.feeds import FetchResult
    from checker.feeds.egazette import SOURCE_ID
    from checker.provenance import BLOCKED

    def page(*rows):
        out = ""
        for n, (ministry, gid, subject) in enumerate(rows):
            out += (f'<span id="rpt_Extra_lbl_MinistryE_{n}">{ministry}</span>'
                    f'<span id="rpt_Extra_lbl_SubjectE_{n}">{subject}</span>'
                    f'<span id="rpt_Extra_lbl_DateE_{n}">23-Sep-2026</span>'
                    f'<span id="rpt_Extra_lbl_UGIDExtra_{n}">{gid}</span>')
        return out.encode()

    class Fake(EGazetteFeed):
        def __init__(self, body):
            super().__init__(); self._body = body

        def fetch(self, entry_url=None):
            if self._body is None:
                return FetchResult(SOURCE_ID, "https://egazette.gov.in/",
                                   hashlib.sha256(b"").hexdigest(), b"", BLOCKED,
                                   note="simulated outage")
            return FetchResult(SOURCE_ID, "https://egazette.gov.in/",
                               hashlib.sha256(self._body).hexdigest(), self._body, ACCESSIBLE)

    # ---- the live shape: a real row, whose instrument is NOT named --------------
    body = page(("Ministry of Corporate Affairs", "CG-DL-E-23092026-276437",
                 "Publication of Notification..."),
                ("Ministry of Labour and Employment", "CG-DL-E-23092026-276435",
                 "In exercise of the powers conferred by claus..."))
    code, ops = run_live(feed=Fake(body))
    check(code == 2 and len(ops) == 2, f"one operation per listed item (code={code}, n={len(ops)})")
    first = ops[0]
    check("identify which instrument" in first.requirements[0].question,
          "the first task on an unidentified row is to identify the instrument")
    check(all(r.obligation_id in ("(unidentified)", "(review)") for r in first.requirements),
          "...and no obligation is claimed affected, because none was matched")
    check(not first.budget().can_close, "...and the operation cannot be closed")

    # ---- a failed poll creates NO work ------------------------------------------
    code, ops = run_live(feed=Fake(None))
    check(code == 1 and ops == [], "a failed poll creates no operations, rather than empty ones")
    code, ops = run_live(feed=Fake(b"<html>error</html>"))
    check(code == 1 and ops == [], "an unreadable page creates no operations either")

    # ---- the demo half: a known instrument reaches the register ------------------
    d = run_demo()
    check(len(d) == 1, "the worked instrument creates one operation")
    op = d[0]
    check(any(r.obligation_id == "CA13-S2-85-SMALL" for r in op.requirements),
          "...and the reverse index names the affected obligation")
    specs = {r.specialist for r in op.requirements}
    check(len(specs) >= 3, f"...routed across at least three specialists ({sorted(specs)})")
    check(any(r.specialist == HUMAN_REVIEW for r in op.requirements),
          "...with a human review as a first-class task")

    # ---- the rendering carries the refusal --------------------------------------
    text = render(op)
    check("what, if anything, follows" in text, "the page shows the human-review task")
    check("not a finding" in text, "the page states the operation is not a finding")
    for word in ("applies to", "is a small company", "has breached", "complies"):
        check(word not in text, f"the page never says {word!r}")

    # ---- the ring boundary -------------------------------------------------------
    from checker import rings
    check(not [v for v in rings.violations() if "operations" in v or "themis_slice" in v],
          "no Ring 0/1 module reaches the operation model")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


def main() -> int:
    if "--test" in sys.argv:
        return _test()
    if "--demo" in sys.argv:
        ops = run_demo()
        print(f"THEMIS slice — worked case, G.S.R. 880(E) ({_now()})\n")
        for op in ops:
            print(render(op))
        return 2 if ops else 0

    code, ops = run_live()
    if code == 1:
        print("POLL FAILED — no operations created. Nothing is marked as seen.")
        return 1
    print(f"THEMIS slice — live Gazette ({_now()}): {len(ops)} operation(s) created\n")
    for op in ops:
        print(render(op)); print()
    if "--json" in sys.argv:
        print(json.dumps([o.to_dict() for o in ops], indent=1))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
