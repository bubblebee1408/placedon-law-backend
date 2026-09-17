#!/usr/bin/env python3
"""Run the Gazette watcher once: what did the Gazette publish since we last looked?

    python3 scripts/watch_gazette.py            # one poll, live
    python3 scripts/watch_gazette.py --test     # offline self-test

State lives in `corpus/.gazette_watch.json` (the high-water serial) and every poll
is appended to `corpus/.gazette_watch.jsonl`. Both are git-ignored, like
`corpus/.budget.json`: they are this machine's record of what it has seen.

## The rule that matters

**The high-water mark advances only after a successful, non-empty read.** A failed
poll -- blocked, unreachable, or a page that parsed into nothing -- must not move
it, or the instruments published during the outage would be marked as already seen
and never reported. A watcher that silently skips what it missed is worse than no
watcher, because it produces a clean-looking record.

Exit status: 0 = poll succeeded, nothing needing a person; 2 = something needs a
person (a new Corporate Affairs instrument, a new ministry-UNKNOWN gazette, or
UNSEEN serials); 1 = the poll itself failed.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from checker.feeds.egazette import EGazetteFeed  # noqa: E402
from checker.provenance import ACCESSIBLE         # noqa: E402

STATE = ROOT / "corpus/.gazette_watch.json"
LOG = ROOT / "corpus/.gazette_watch.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_high_water(state: Path) -> int | None:
    if not state.is_file():
        return None
    try:
        v = json.loads(state.read_text()).get("high_water")
    except (ValueError, OSError) as exc:
        # A corrupt state file is not "never polled": say so and stop, rather than
        # resetting to a first run that would hide every gap.
        raise SystemExit(f"watch_gazette: state file {state} is unreadable ({exc}); "
                         "fix or remove it deliberately") from exc
    return int(v) if isinstance(v, int) else None


def poll(feed, state: Path, log: Path, *, now: str) -> tuple[int, dict]:
    last = load_high_water(state)
    result = feed.fetch()
    obs = feed.parse(result, observed_at=now, last_seen_serial=last)
    p = obs.payload
    entry = {"observed_at": now, "source_behaviour": obs.source_behaviour,
             "sha256": obs.content_sha256, "last_seen": last, "note": result.note}

    readable = obs.source_behaviour == ACCESSIBLE and p.get("listed", 0) > 0
    if readable:
        entry.update({k: p[k] for k in ("listed", "high_water", "new_serials",
                                         "new_corporate_affairs", "new_ministry_unknown",
                                         "unseen_serials")})
        # The log previously carried only gazette_id and serial for a new item --
        # enough to say a poll SAW something new, not enough to say what it was.
        # scripts/gazette_digest.py reads only this log (never re-fetches the
        # site), so it needs ministry, kind and pdf_url here or it cannot render
        # them. Minimal and additive: one field, the new items' own record, never
        # replacing what was already logged.
        new_set = set(p["new_serials"])
        entry["new_items"] = [
            {k: it[k] for k in ("gazette_id", "kind", "ministry", "pdf_url",
                                 "corporate_affairs")}
            for it in p["items"] if it["serial"] in new_set
        ]
    # RT-07: a listing whose highest serial is BELOW the recorded mark is not a
    # quiet day -- it is a degraded or stale read (a cached page, a partial render,
    # a mirror). The gap check `range(last+1, top+1)` is EMPTY when top < last, so
    # such a poll used to report as perfectly clean. It is now a failed poll: the
    # mark is held and the regression is named.
    regressed = (readable and last is not None and p["high_water"] is not None
                 and p["high_water"] < last)
    if regressed:
        readable = False
        entry["regressed_to"] = p["high_water"]
        entry["note"] = (f"listing regressed: highest serial {p['high_water']} is below the "
                         f"recorded mark {last} -- stale or partial read, not a quiet day")

    if not readable:
        entry["high_water_held_at"] = last   # the rule above, recorded

    # RT-08, the flagship finding: the record is on disk, FSYNCED, BEFORE the mark
    # advances. Previously the mark moved first, so an ordinary kill between the two
    # writes -- cron, systemd, a container stop -- consumed the alert permanently:
    # the next poll saw nothing new and no log line ever named what was missed.
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a") as fh:
        fh.write(json.dumps(entry) + "\n")
        fh.flush(); os.fsync(fh.fileno())

    if readable and p["high_water"] is not None and (last is None or p["high_water"] > last):
        # RT-09: atomic (temp + fsync + rename), so a crash mid-write cannot leave a
        # half-written mark for the next run to choke on.
        state.parent.mkdir(parents=True, exist_ok=True)
        tmp = state.with_suffix(state.suffix + ".tmp")
        try:
            with tmp.open("w") as fh:
                fh.write(json.dumps({"high_water": p["high_water"], "updated_at": now}) + "\n")
                fh.flush(); os.fsync(fh.fileno())
            os.replace(tmp, state)
        except OSError:
            # Leave no fragment behind: a stale .tmp is confusing evidence next to a
            # state file, and a future reader should never have to guess which is real.
            tmp.unlink(missing_ok=True)
            raise

    if not readable:
        return 1, entry
    needs_person = bool(p["new_corporate_affairs"] or p["new_ministry_unknown"]
                        or p["unseen_serials"])
    return (2 if needs_person else 0), {**entry, "items": p["items"]}


def _report(code: int, e: dict) -> None:
    if code == 1:
        print(f"POLL FAILED ({e['source_behaviour']}): {e.get('note') or 'page unreadable'}")
        if "regressed_to" in e:
            print("  the listing went BACKWARDS -- treated as a stale read, not as a quiet day")
        print(f"  high-water mark held at {e.get('high_water_held_at')} -- nothing marked seen")
        return
    print(f"eGazette polled {e['observed_at']}: {e['listed']} listed, "
          f"high-water {e['last_seen']} -> {e['high_water']}")
    new = {i["serial"]: i for i in e["items"] if i["serial"] in set(e["new_serials"])}
    for s in sorted(new, reverse=True):
        i = new[s]
        tag = {True: "MCA", None: "???", False: "   "}[i["corporate_affairs"]]
        print(f"  NEW {tag} {i['gazette_id']:28} {i['kind']:13} {i['ministry'][:50]}")
        print(f"            {i['pdf_url']}")
    if e["unseen_serials"]:
        s = e["unseen_serials"]
        shown = s if len(s) <= 12 else s[:6] + ["…"] + s[-3:]
        print(f"  UNSEEN serials ({len(s)}): {shown}")
        print("    published under a number no listing showed -- NOT 'does not exist'. Look.")
    if code == 2:
        print("  -> needs a person: MCA = Corporate Affairs; ??? = multi-ministry, may hold MCA items")
    else:
        print("  nothing needing a person")


def _test() -> int:
    import tempfile

    from checker.feeds import FetchResult
    from checker.feeds.egazette import SOURCE_ID
    from checker.provenance import BLOCKED

    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    def page(*rows):
        out = ""
        for n, (ministry, gid) in enumerate(rows):
            out += (f'<span id="rpt_Extra_lbl_MinistryE_{n}">{ministry}</span>'
                    f'<span id="rpt_Extra_lbl_SubjectE_{n}">...</span>'
                    f'<span id="rpt_Extra_lbl_DateE_{n}">17-Sep-2026</span>'
                    f'<span id="rpt_Extra_lbl_UGIDExtra_{n}">{gid}</span>')
        return out.encode()

    import hashlib

    class Fake(EGazetteFeed):
        def __init__(self, body: bytes | None):
            super().__init__()
            self._body = body

        def fetch(self, entry_url=None):
            if self._body is None:
                return FetchResult(SOURCE_ID, "https://egazette.gov.in/", hashlib.sha256(b"").hexdigest(),
                                   b"", BLOCKED, note="simulated outage")
            return FetchResult(SOURCE_ID, "https://egazette.gov.in/",
                               hashlib.sha256(self._body).hexdigest(), self._body, ACCESSIBLE)

    with tempfile.TemporaryDirectory() as d:
        st, lg = Path(d) / "s.json", Path(d) / "l.jsonl"

        c, e = poll(Fake(page(("Ministry of Labour", "CG-DL-E-17092026-100"))), st, lg, now=_now())
        check(c == 0 and load_high_water(st) == 100, "first poll: baseline set, no gaps invented")

        c, e = poll(Fake(None), st, lg, now=_now())
        check(c == 1, "an outage is a FAILED poll")
        check(load_high_water(st) == 100, "...and the high-water mark does NOT move during an outage")
        check("new_items" not in e, "...and a failed poll logs no item records -- there are none to log")

        c, e = poll(Fake(b"<html>error</html>"), st, lg, now=_now())
        check(c == 1 and load_high_water(st) == 100, "an unreadable page also holds the mark")

        body = page(("Ministry of Corporate Affairs", "CG-DL-E-18092026-104"),
                    ("Ministry of Labour", "CG-DL-E-18092026-101"))
        c, e = poll(Fake(body), st, lg, now=_now())
        check(c == 2, "a new MCA instrument needs a person (exit 2)")
        check(e["new_corporate_affairs"] == ["CG-DL-E-18092026-104"], "the MCA instrument is named")
        check(e["unseen_serials"] == [102, 103],
              "serials published DURING the outage are reported UNSEEN, not lost")
        check(load_high_water(st) == 104, "the mark advances after a good read")

        check(len(e["new_items"]) == 2,
              f"the log entry carries a full record for every new item, not just the MCA one "
              f"({len(e['new_items'])})")
        mca_item = next(i for i in e["new_items"] if i["gazette_id"] == "CG-DL-E-18092026-104")
        check(mca_item["ministry"] == "Ministry of Corporate Affairs"
              and mca_item["corporate_affairs"] is True
              and mca_item["pdf_url"].endswith("104.pdf")
              and mca_item["kind"] == "EXTRAORDINARY",
              "...with ministry, corporate_affairs, kind and pdf_url -- gazette_digest.py needs "
              "all four and the log previously carried none of them")
        check(any(i["gazette_id"] == "CG-DL-E-18092026-101" and i["corporate_affairs"] is False
                  for i in e["new_items"]),
              "...and a plain new item is recorded too, not only the ones needing a person")

        c, e = poll(Fake(body), st, lg, now=_now())
        check(c == 0 and e["new_serials"] == [], "re-polling the same page reports nothing new")

        # ---- RT-07: a listing that goes BACKWARDS is a stale read, not a quiet day ----
        back = page(("Ministry of Labour", "CG-DL-E-18092026-99"))   # 99 < mark 104
        c, e = poll(Fake(back), st, lg, now=_now())
        check(c == 1, "a listing whose top serial is below the mark is a FAILED poll")
        check(e.get("regressed_to") == 99 and "regressed" in (e.get("note") or ""),
              "...and the regression is named, not silently reported as clean")
        check(load_high_water(st) == 104, "...and the mark is held, never lowered")

        # ---- RT-08: the log is durable BEFORE the mark moves ----
        # Simulate a crash at the instant the mark is written: the poll dies, but the
        # record of what it saw must already be on disk, or the alert is lost forever.
        import os as _os
        real_replace = _os.replace
        def boom(*a, **k):
            raise OSError("simulated crash between log and state")
        before = len(lg.read_text().splitlines())
        _os.replace = boom
        try:
            poll(Fake(page(("Ministry of Corporate Affairs", "CG-DL-E-19092026-200"))), st, lg, now=_now())
            crashed = False
        except OSError:
            crashed = True
        finally:
            _os.replace = real_replace
        after = lg.read_text().splitlines()
        check(crashed, "the simulated crash happened where the mark is written")
        check(len(after) == before + 1, "...and the poll's record was already written")
        check("CG-DL-E-19092026-200" in after[-1],
              "...naming the MCA instrument, so the next run can still surface it")
        check(load_high_water(st) == 104, "...and the mark did not advance through the crash")
        check(not list(st.parent.glob("*.tmp")), "RT-09: no half-written temp state is left behind")

        lines = lg.read_text().strip().splitlines()
        check(len(lines) == 7, f"every poll, failed or not, is logged ({len(lines)} lines)")
        check(json.loads(lines[1])["high_water_held_at"] == 100, "the log records the held mark")

        st.write_text("{not json")
        try:
            load_high_water(st); check(False, "a corrupt state file must stop the run")
        except SystemExit:
            check(True, "a corrupt state file stops the run rather than silently resetting")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    if "--test" in sys.argv:
        raise SystemExit(_test())
    code, entry = poll(EGazetteFeed(), STATE, LOG, now=_now())
    _report(code, entry)
    raise SystemExit(code)
