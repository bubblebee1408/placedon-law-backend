#!/usr/bin/env python3
"""Render the Gazette watcher's poll log into a markdown digest a person reads.

    python3 scripts/gazette_digest.py            # reads corpus/.gazette_watch.jsonl,
                                                   # writes reports/gazette_digest.md
    python3 scripts/gazette_digest.py --test      # offline self-test, synthetic log

## Why this exists

`scripts/watch_gazette.py` polls once and prints one poll's result to a
terminal that is gone the moment the shell closes. `corpus/.gazette_watch.jsonl`
already remembers every poll -- one JSON line each, appended, never rewritten --
but a `.jsonl` file is not something a person opens. This script is the
difference: it turns the log that already exists into a dated page a person can
read, without adding a second source of truth. It never fetches eGazette itself.

## What this refuses to be

This is delivery, not judgment. It renders what the watcher observed -- per
poll, which items were new, which needed a person, which serials no listing
showed -- and nothing more. **It never says an obligation changed, moved, or
was affected.** `checker/feeds/egazette.py`'s own rule is inherited whole: a
Ministry of Corporate Affairs notification appearing here is a prompt for a
person to acquire and attest it, never an amendment applied. This module is
not ring-registered (`checker/rings.py` classifies `checker/`, not `scripts/`)
and nothing downstream enforces that boundary for it the way `rings.py`
enforces Ring 0 -- so the discipline here is the only thing holding it, and it
holds it by never importing a decider and never writing a verdict word.

## Why it reads the log, not the live site

Re-fetching eGazette to build a digest would duplicate `watch_gazette.py`'s own
fetch, doubling the request rate against a source `checker/feeds/egazette.py`
already measured shows only the newest few rows on its homepage -- an extra,
uncoordinated poller makes the blindness gap worse, not better. So this script
is a pure function of the log: the same `corpus/.gazette_watch.jsonl` renders
the same digest, every time, offline, which is also what makes `--test`
possible without a network.

## What the log did not carry, and now does

Before this script existed, `poll()`'s log entry named which serials were new
(`new_serials`) and which gazette IDs needed a person
(`new_corporate_affairs`, `new_ministry_unknown`) -- but not their ministry,
kind, or PDF address, and it named no "other" (non-MCA, non-unknown) item at
all. A digest that cannot show what an item IS, only that something happened,
is not delivery. `scripts/watch_gazette.py`'s `poll()` now also logs a
`new_items` record (`gazette_id`, `kind`, `ministry`, `pdf_url`,
`corporate_affairs`) for every new item, and this script is the reason that
field exists -- see the same file's `_test()` for the extension's own checks.

## The ledger signal

CLAUDE.md: the Companies Act amendment ledger this repo holds stops at
2023-10-30. `checker/corpus_currency.py` measures that gap and, by design,
refuses to close it -- closing it means acquiring an instrument, which is
human-attested (see that module's own docstring). A NEW Corporate Affairs
item in this digest is exactly the kind of thing that gap could hide, so
every poll block that shows one also states `corpus_currency.report()`'s own
`newest_wef` and says the ledger MAY be behind -- never that the instrument
amends, applies to, or changes anything, because this script has no way to
know that and CLAUDE.md forbids guessing. `_test()` asserts the signal
appears only alongside an MCA item, and that the rendered page never
contains "amended", "applies", or "changed".
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

LOG = ROOT / "corpus" / ".gazette_watch.jsonl"
OUT = ROOT / "reports" / "gazette_digest.md"

UNSEEN_MEANS = ('published under a number no listing showed -- NOT "does not exist". '
               "A person should look.")


def read_log(path: Path) -> list[dict]:
    """Every poll this machine has recorded, oldest first. No file -> no polls yet.

    A line that will not parse as JSON is not dropped -- CLAUDE.md: preserve
    uncertainty, never silently drop an unresolved marker. It becomes its own
    entry naming the line number, so the digest can say the log itself has a
    problem rather than silently rendering one poll short.
    """
    if not path.is_file():
        return []
    entries: list[dict] = []
    for lineno, raw in enumerate(path.read_text().splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except ValueError as exc:
            entries.append({"observed_at": None, "source_behaviour": "UNREADABLE_LOG_LINE",
                            "_corrupt_line": lineno, "_error": str(exc)})
    return entries


def _bucket(items: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """MCA, ministry-UNKNOWN, other -- the same three groups watch_gazette.py's
    own `_report()` prints to a terminal, rendered here to markdown instead."""
    mca = [i for i in items if i.get("corporate_affairs") is True]
    unknown = [i for i in items if i.get("corporate_affairs") is None]
    other = [i for i in items if i.get("corporate_affairs") is False]
    return mca, unknown, other


def _item_line(i: dict) -> str:
    ministry = i.get("ministry") or "(no ministry named on the listing)"
    return (f"- `{i['gazette_id']}` ({i.get('kind', '?')}) -- {ministry}\n"
            f"  {i.get('pdf_url', '(no PDF address recorded)')}")


def render_poll(e: dict, *, ledger_ends: date | None = None) -> list[str]:
    """One poll's markdown block. States what was observed; concludes nothing.

    `ledger_ends` is `corpus_currency.report().newest_wef`, passed in rather
    than computed here so this function stays a pure function of its
    arguments -- offline-testable with any date, and computed exactly once
    per digest by the caller rather than once per poll block.
    """
    when = e.get("observed_at") or "unknown time"
    L = [f"## Poll -- {when}"]

    if "_corrupt_line" in e:
        L.append(f"- **[log line {e['_corrupt_line']} could not be read as JSON]**: "
                 f"{e.get('_error', '')}")
        return L

    # poll() only sets `high_water` on a readable, non-empty poll (see its own
    # docstring: the mark must never move on a failed or unreadable read). That
    # key's presence, not source_behaviour alone, is the readability signal --
    # a page can answer 200 (ACCESSIBLE) and still parse into nothing.
    readable = "high_water" in e
    behaviour = e.get("source_behaviour", "unknown")
    if not readable:
        L.append(f"- source: {behaviour} -- **FAILED**"
                 + (f" ({e['note']})" if e.get("note") else ""))
        L.append(f"- high-water: held at {e.get('high_water_held_at')}")
        return L

    last, hw = e.get("last_seen"), e["high_water"]
    movement = f"{hw} (unchanged)" if last == hw else f"{last if last is not None else '(first poll)'} -> {hw}"
    L.append(f"- source: {behaviour}")
    L.append(f"- listed: {e.get('listed', 0)}")
    L.append(f"- high-water: {movement}")

    items = e.get("new_items", [])
    mca, unknown, other = _bucket(items)
    if mca:
        L.append("\n**New -- Ministry of Corporate Affairs**")
        L += [_item_line(i) for i in mca]
        if ledger_ends is not None:
            L.append(f"\n  _The Act's amendment ledger we hold ends "
                     f"{ledger_ends.isoformat()}; a new MCA instrument may not be "
                     "reflected -- a person must acquire and attest it._")
    if unknown:
        L.append("\n**New -- ministry UNKNOWN** (a multi-ministry weekly may hold an MCA "
                 "item -- open it; absence of a named ministry is not a no)")
        L += [_item_line(i) for i in unknown]
    if other:
        L.append("\n**New -- other**")
        L += [_item_line(i) for i in other]
    if not items:
        # A log entry written before poll() recorded `new_items` still carries
        # `new_serials`. Rendering that as "nothing new" would turn a missing
        # RECORD into an absence of EVENTS -- the confusion this whole layer
        # exists to refuse. Say which of the two it is.
        serials = e.get("new_serials") or []
        if serials:
            L.append(f"\n**{len(serials)} new serial(s) this poll, with no item record in the log**: "
                     f"{serials}")
            L.append("  _This log entry predates the watcher recording ministry and PDF address "
                     "for each new item. The gazettes were seen; their details were not written "
                     "down. This is NOT 'nothing was published'._")
        else:
            L.append("\n(nothing new this poll)")

    unseen = e.get("unseen_serials") or []
    if unseen:
        L.append(f"\n**UNSEEN serials:** {', '.join(str(s) for s in unseen)} -- {UNSEEN_MEANS}")

    return L


def render_digest(entries: list[dict], *, generated_at: str,
                  ledger_ends: date | None = None) -> str:
    """The whole page. Newest poll first -- a reader opening this wants to know
    what just happened, not to scroll to the bottom of a growing log."""
    L = ["# Gazette digest", "",
         f"Generated {generated_at}. This reports what the eGazette watcher observed; "
         "it draws no legal conclusion -- see `checker/feeds/egazette.py` and "
         "`CLAUDE.md`. A Corporate Affairs item below is a prompt for a person to "
         "acquire and attest the instrument, never a statement that anything changed.",
         ""]
    if not entries:
        L.append("No polls recorded yet. Run `python3 scripts/watch_gazette.py`.")
        return "\n".join(L) + "\n"
    for e in reversed(entries):
        L += render_poll(e, ledger_ends=ledger_ends)
        L.append("")
    return "\n".join(L) + "\n"


def main() -> None:
    from checker.corpus_currency import report as ledger_report

    entries = read_log(LOG)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ledger_ends = ledger_report(date.today()).newest_wef
    digest = render_digest(entries, generated_at=now, ledger_ends=ledger_ends)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(digest)
    print(f"wrote {OUT} ({len(entries)} poll(s) in the log)")


def _test() -> int:
    import tempfile

    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    check(read_log(Path("/nonexistent/does-not-exist.jsonl")) == [],
          "a missing log file is zero polls, not an error")

    empty = render_digest([], generated_at="2026-09-17T00:00:00Z")
    check("No polls recorded yet" in empty, "an empty log says so plainly, not a blank page")

    mca_item = {"gazette_id": "CG-DL-E-17092026-298", "kind": "EXTRAORDINARY",
                "ministry": "Ministry of Corporate Affairs", "corporate_affairs": True,
                "pdf_url": "https://egazette.gov.in/WriteReadData/2026/298.pdf"}
    unknown_item = {"gazette_id": "CG-DL-W-13092026-290", "kind": "WEEKLY",
                    "ministry": "This Gazette may contains Multiple Ministries",
                    "corporate_affairs": None,
                    "pdf_url": "https://egazette.gov.in/WriteReadData/2026/290.pdf"}
    other_item = {"gazette_id": "CG-DL-E-17092026-299", "kind": "EXTRAORDINARY",
                  "ministry": "Ministry of Labour and Employment", "corporate_affairs": False,
                  "pdf_url": "https://egazette.gov.in/WriteReadData/2026/299.pdf"}

    poll1 = {"observed_at": "2026-09-17T10:00:00Z", "source_behaviour": "ACCESSIBLE",
             "listed": 3, "last_seen": 290, "high_water": 299,
             "new_serials": [298, 290, 299], "new_corporate_affairs": [mca_item["gazette_id"]],
             "new_ministry_unknown": [unknown_item["gazette_id"]],
             "unseen_serials": [294, 295, 296],
             "new_items": [mca_item, unknown_item, other_item]}
    poll2 = {"observed_at": "2026-09-17T11:00:00Z", "source_behaviour": "BLOCKED",
             "note": "simulated outage", "last_seen": 299, "high_water_held_at": 299}

    with tempfile.TemporaryDirectory() as d:
        log = Path(d) / "log.jsonl"
        log.write_text(json.dumps(poll1) + "\n" + "{not json\n" + json.dumps(poll2) + "\n")
        entries = read_log(log)
        check(len(entries) == 3, f"every line is read, including the corrupt one ({len(entries)})")
        check(entries[1].get("_corrupt_line") == 2,
              "a corrupt line is preserved as its own entry, not dropped")

        # main() end to end, against temp paths -- module globals patched and
        # restored, the same technique the log/state files themselves use.
        global LOG, OUT
        real_log, real_out = LOG, OUT
        out_path = Path(d) / "digest.md"
        LOG, OUT = log, out_path
        try:
            main()
        finally:
            LOG, OUT = real_log, real_out
        check(out_path.is_file(), "main() writes the digest file")
        written = out_path.read_text()
        check(written.startswith("# Gazette digest"), "...with the expected heading")
        check("2023-10-30" in written and "amendment ledger we hold ends" in written,
              "main() wires the real checker.corpus_currency measurement into the MCA group "
              "(2023-10-30, per CLAUDE.md's Verification status)")

    digest = render_digest(entries, generated_at="2026-09-17T12:00:00Z")

    check("## Poll -- 2026-09-17T11:00:00Z" in digest and "## Poll -- 2026-09-17T10:00:00Z" in digest,
          "both polls render their own dated section")
    check(digest.index("2026-09-17T11:00:00Z") < digest.index("2026-09-17T10:00:00Z"),
          "newest poll first -- a reader wants to know what just happened")
    check("**FAILED**" in digest and "held at 299" in digest,
          "the failed poll is shown as failed, and says the high-water mark held")
    check("New -- Ministry of Corporate Affairs" in digest and mca_item["gazette_id"] in digest
          and mca_item["pdf_url"] in digest,
          "the MCA item is grouped and carries its PDF URL")
    check("New -- ministry UNKNOWN" in digest and unknown_item["gazette_id"] in digest
          and unknown_item["pdf_url"] in digest,
          "a multi-ministry weekly gets its own group, not folded into MCA or dropped")
    check("New -- other" in digest and other_item["gazette_id"] in digest
          and other_item["pdf_url"] in digest,
          "a plain non-MCA item still gets a group, a line, and its PDF URL")
    check("294, 295, 296" in digest, "unseen serials are listed")
    check('NOT "does not exist"' in digest, "...and UNSEEN says what it does not mean")

    forbidden = ("obligation", "amended", "amends", "the law changed", "changed the law")
    lowered = digest.lower()
    check(not any(w in lowered for w in forbidden),
          "the digest states no legal conclusion -- it never says an obligation changed")

    corrupt_only = render_digest([entries[1]], generated_at="2026-09-17T12:00:00Z")
    check("could not be read as JSON" in corrupt_only,
          "a corrupt log line is reported, not silently skipped in the rendered page")

    # ── the ledger signal (checker/corpus_currency.py) ──────────────────────
    digest_ledger = render_digest(entries, generated_at="2026-09-17T12:00:00Z",
                                  ledger_ends=date(2023, 10, 30))
    check("2023-10-30" in digest_ledger and "amendment ledger we hold ends" in digest_ledger,
          "the ledger signal appears, worded as specified, on a poll with an MCA item")

    no_mca = [{**poll1, "new_items": [unknown_item, other_item]}]
    digest_no_mca = render_digest(no_mca, generated_at="2026-09-17T12:00:00Z",
                                  ledger_ends=date(2023, 10, 30))
    check("amendment ledger we hold ends" not in digest_no_mca,
          "...and is absent from a poll with no MCA item, even given the same ledger date")

    ledger_line = next(line for line in digest_ledger.splitlines()
                       if "amendment ledger we hold ends" in line)
    check(not any(w in ledger_line.lower() for w in ("amended", "applies", "changed")),
          "...and the signal's own sentence never says the instrument amended, applies to, "
          f"or changed anything ({ledger_line.strip()!r})")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    if "--test" in sys.argv:
        raise SystemExit(_test())
    main()
