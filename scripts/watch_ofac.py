#!/usr/bin/env python3
"""Poll OFAC's SDN list and report what CHANGED since the last trustworthy poll.

    python3 scripts/watch_ofac.py            # one poll; exit 0/1/2 -- see below
    python3 scripts/watch_ofac.py --test      # fully offline self-test

## Why a watcher, and why it is this careful about its own baseline

`checker/feeds/ofac_sdn.py` can read one snapshot. Nobody looks at a 29 MB XML file
by eye to notice that uid 4243 dropped off the list between Tuesday and Thursday --
that comparison only exists if something holds Tuesday's read and diffs it against
Thursday's. This script is that something, and the entire design question is what
happens the day a poll goes wrong, because a watcher that quietly moves its own
baseline on a bad read is worse than no watcher: it reports "nothing changed"
while actually meaning "I could not tell", and those two look identical downstream
unless the baseline logic itself refuses to conflate them.

Three ways a poll can go wrong, each handled differently on purpose:

1. **The fetch itself fails** (network, robots, WAF -- anything
   `checker.feeds.common.fetch` reports as not ACCESSIBLE). Nothing was read, so
   there is nothing to compare. Baseline HELD.
2. **The fetch succeeds but the parse does not add up.** OFAC's file states its
   own `Record_Count`; if the number of `<sdnEntry>` elements actually parsed does
   not equal it, the read is not trustworthy enough to diff against -- a partial or
   corrupted body could look like "3 uids removed" when actually the download just
   got cut short. Baseline HELD, same as a network failure, and for the same
   reason: an untrustworthy read must never look like a trustworthy empty diff.
3. **The watcher's OWN state file is unreadable.** This is the one that matters
   most: if `corpus/.ofac_watch.json` is corrupt, the tempting shortcut is "no
   valid baseline found -> treat as first run". That SILENTLY discards whatever
   baseline existed and reports the next real change as if it were the first ever
   seen -- exactly the failure mode PLAN_08's ring firewall and this repo's other
   state files (`checker/acquisition_log.py`'s hash chain) all refuse for the same
   reason. A corrupt state file STOPS the run. It is not touched, and no fetch is
   even attempted, because a human has to look at it before anything is trusted
   again.

Only a poll that is BOTH ACCESSIBLE and fully-parsed-to-the-stated-count is
"successful": only that kind advances the baseline, and only that kind is
compared against the prior baseline to produce a delta.

## What "the delta" actually is

`checker/feeds/ofac_sdn.py.entries()` yields the whole `<sdnEntry>` (name, akas,
programs, ids, vesselInfo) because `screen()` and `vessels()` both need those
fields. A watcher comparing two 19,385-entry snapshots does not: it needs enough
to say "this uid is new", "this uid is gone", "this uid's name or programs
changed", nothing else survives from either snapshot in memory -- see
`_summarise()`. Both prior and current summaries exist in memory only long
enough to compute one `Delta`, then are discarded rather than folded into the
persisted state (see below).

## Why the artifact, not a copy of the summary, is what gets persisted

`corpus/.ofac_watch.json` records ONLY a pointer -- source_id, the cached
artifact's path and sha256, the file's own stated publish date and record count.
It does not carry a copy of the 19,385-entry uid map. The next poll re-derives
last time's uid map by loading the cached artifact bytes back through
`checker.feeds.common.cache.load()` (which itself refuses to hand back content
whose hash no longer matches its filename) and re-running `entries()` over them --
so the state file stays small, and the thing the diff is actually computed against
is the exact bytes that were fetched, not a summary of a summary.

## Exit codes

  0  poll succeeded, nothing changed since the last baseline (or this was the
     first poll ever -- there is no prior baseline to diff against, so NO delta
     is reported; inventing one would be exactly the "no obligation found reads
     as silence" mistake CLAUDE.md names for the legal side of this repository)
  1  the poll did not produce a trustworthy result -- fetch failure, a
     stated/parsed count mismatch, a corrupt cache entry, or a corrupt state
     file. The baseline is held in every one of these cases.
  2  poll succeeded AND something changed -- a person should look

## What REMOVED means, stated once here because it is easy to get backwards

A uid present in the previous snapshot and absent from this one means it is
**no longer on the SDN list as published on this file's stated date**. It does
not mean the person or vessel was cleared, delisted with prejudice, or is safe --
OFAC's own list is a snapshot (see `checker/feeds/ofac_sdn.py`'s BLINDNESS=EITHER),
and this watcher inherits that same blindness. Every REMOVED line says so.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from checker.feeds.common.cache import (CacheEntry, CacheError,  # noqa: E402
                                        load as cache_load, store as cache_store)
from checker.feeds.ofac_sdn import (ENTRY_URL, OfacSdnFeed,  # noqa: E402
                                    _publish_info, entries as sdn_entries)
from checker.provenance import ACCESSIBLE  # noqa: E402

STATE_SCHEMA = "ofac_watch/v1"

# Anchored to the repository root, as scripts/watch_gazette.py is. These were once
# cwd-relative: run from anywhere but the root, the watcher would have written its
# state somewhere else and silently started over from a first run -- losing the
# baseline and every delta against it.
_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STATE_PATH = _ROOT / "corpus/.ofac_watch.json"
DEFAULT_LOG_PATH = _ROOT / "corpus/.ofac_watch.jsonl"
DEFAULT_CACHE_ROOT = _ROOT / "corpus/.feeds_cache"   # 29 MB per artifact -- git-ignored

EXIT_UNCHANGED = 0
EXIT_POLL_NOT_TRUSTWORTHY = 1
EXIT_CHANGED = 2


class StateCorrupt(ValueError):
    """The state file exists but cannot be trusted. Never a reason to reset it."""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _summarise(content: bytes) -> tuple[dict[str, dict], int]:
    """uid -> {"name", "sdn_type", "programs"}, plus the TRUE parsed count.

    The count is taken from a running counter over every `<sdnEntry>` seen, not
    from `len()` of the returned dict -- if the source ever carried a duplicate
    uid, `len(dict)` would silently under-count and could mask exactly the kind
    of mismatch `poll()` exists to catch. Nothing from `entries()` beyond these
    three fields is kept per record: akas, ids and vesselInfo are all read and
    discarded immediately, the same discipline `checker/feeds/ofac_sdn.py`'s own
    `entries()` uses to keep memory flat on a 29 MB file.
    """
    summary: dict[str, dict] = {}
    parsed = 0
    for e in sdn_entries(content):
        parsed += 1
        summary[e["uid"]] = {"name": e["name"], "sdn_type": e["sdn_type"],
                             "programs": e["programs"]}
    return summary, parsed


@dataclass(frozen=True)
class Delta:
    """uids added, removed, or changed between two summaries. Frozen: a delta
    handed to a caller does not change identity if the dicts it was built from
    are later mutated."""
    added: tuple[str, ...]
    removed: tuple[str, ...]
    changed: tuple[str, ...]  # present on both sides; name and/or programs differ

    def is_empty(self) -> bool:
        return not (self.added or self.removed or self.changed)


def diff(old: dict[str, dict], new: dict[str, dict]) -> Delta:
    old_uids, new_uids = set(old), set(new)
    added = tuple(sorted(new_uids - old_uids))
    removed = tuple(sorted(old_uids - new_uids))
    changed = tuple(sorted(u for u in (old_uids & new_uids) if old[u] != new[u]))
    return Delta(added=added, removed=removed, changed=changed)


def load_state(path: Path) -> dict | None:
    """None means "no baseline yet" -- a legitimate first-run state. Anything
    that exists but cannot be trusted raises StateCorrupt instead of also
    returning None, so a caller cannot accidentally treat "unreadable" the same
    way as "absent"."""
    if not path.exists():
        return None
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        raise StateCorrupt(f"{path}: could not read ({e})") from e
    try:
        state = json.loads(raw)
    except json.JSONDecodeError as e:
        raise StateCorrupt(f"{path}: not valid JSON ({e})") from e
    if not isinstance(state, dict) or state.get("schema") != STATE_SCHEMA:
        raise StateCorrupt(
            f"{path}: unknown schema {state.get('schema') if isinstance(state, dict) else type(state).__name__!r}; "
            f"expected {STATE_SCHEMA!r}")
    required = ("artifact_path", "artifact_meta_path", "sha256", "publish_date",
               "record_count", "observed_at")
    missing = [k for k in required if k not in state]
    if missing:
        raise StateCorrupt(f"{path}: missing required field(s) {missing}")
    return state


def write_state(path: Path, state: dict) -> None:
    """Write the baseline ATOMICALLY (temp file, fsync, rename).

    RT-09: a plain write_text truncates first, so a crash mid-write leaves a
    half-written baseline. The next run refuses loudly rather than silently
    resetting, which is the right direction -- but it needs a human. os.replace is
    atomic on POSIX, so the file a reader sees is either the old baseline or the new
    one, never a fragment.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    body = json.dumps(state, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    try:
        with tmp.open("w", encoding="utf-8") as f:
            f.write(body); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
    except OSError:
        tmp.unlink(missing_ok=True)   # leave no fragment beside the real baseline
        raise


def append_log(path: Path, record: dict) -> None:
    """Append one poll record, FLUSHED AND FSYNCED before returning.

    RT-08: every caller that advances the baseline must have this record on disk
    first. An fsync here is what makes "log before state" a real ordering rather
    than an ordering of two buffered writes the OS may reorder.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
        f.flush(); os.fsync(f.fileno())


def _report(delta: Delta, old: dict[str, dict], new: dict[str, dict], published: str) -> None:
    if delta.added:
        print(f"\nADDED ({len(delta.added)}):")
        for uid in delta.added:
            e = new[uid]
            print(f"  + {uid}  {e['name']}  [{e['sdn_type']}]  "
                  f"programs={','.join(e['programs']) or '(none)'}")
    if delta.removed:
        print(f"\nREMOVED ({len(delta.removed)}) -- no longer on the SDN list as "
              f"published {published or '(date unknown)'}. This is NOT 'cleared' "
              f"and NOT 'not sanctioned' -- see BLINDNESS=EITHER.")
        for uid in delta.removed:
            e = old[uid]
            print(f"  - {uid}  {e['name']}  [{e['sdn_type']}]")
    if delta.changed:
        print(f"\nCHANGED ({len(delta.changed)}):")
        for uid in delta.changed:
            o, n = old[uid], new[uid]
            if o["name"] != n["name"]:
                print(f"  * {uid}  name: {o['name']!r} -> {n['name']!r}")
            if o["programs"] != n["programs"]:
                print(f"  * {uid}  programs: {o['programs']} -> {n['programs']}")


def poll(feed: OfacSdnFeed, *, cache_root: Path, state_path: Path, log_path: Path,
        observed_at: str | None = None) -> int:
    """One poll. Returns the process exit code -- see module docstring."""
    observed_at = observed_at or _now()

    try:
        prev_state = load_state(state_path)
    except StateCorrupt as e:
        append_log(log_path, {"at": observed_at, "result": "state_corrupt", "detail": str(e)})
        print(f"STATE CORRUPT: {e}", file=sys.stderr)
        print("refusing to run -- this is NOT treated as \"no baseline\"; fix or "
              "remove the state file by hand, then re-run", file=sys.stderr)
        return EXIT_POLL_NOT_TRUSTWORTHY

    result = feed.fetch(ENTRY_URL)
    if result.source_behaviour != ACCESSIBLE:
        append_log(log_path, {"at": observed_at, "result": "held", "reason": "fetch_failed",
                              "source_behaviour": result.source_behaviour,
                              "detail": result.note or f"http_status={result.http_status}"})
        print(f"POLL FAILED ({result.source_behaviour}): {result.note or result.http_status} "
              f"-- baseline held", file=sys.stderr)
        return EXIT_POLL_NOT_TRUSTWORTHY

    published, stated = _publish_info(result.content)
    new_summary, parsed = _summarise(result.content)

    if stated is None or stated != parsed:
        append_log(log_path, {"at": observed_at, "result": "held", "reason": "count_mismatch",
                              "stated": stated, "parsed": parsed, "publish_date": published})
        print(f"POLL HELD: parsed {parsed} entries but the file states "
              f"Record_Count={stated} -- baseline held, no delta reported", file=sys.stderr)
        return EXIT_POLL_NOT_TRUSTWORTHY

    # A trustworthy read. The artifact is evidence either way, whether or not
    # anything about the list actually changed -- cache it before deciding that.
    entry = cache_store(cache_root, result, observed_at=observed_at)
    new_state = {
        "schema": STATE_SCHEMA,
        "source_id": result.source_id,
        "artifact_path": str(entry.path),
        "artifact_meta_path": str(entry.meta_path),
        "sha256": entry.sha256,
        "publish_date": published,
        "record_count": parsed,
        "observed_at": observed_at,
    }

    if prev_state is None:
        # RT-08: the record lands on disk BEFORE the baseline advances. A crash
        # between the two used to lose the poll entirely -- the next run would diff
        # against a baseline nothing had ever reported.
        append_log(log_path, {"at": observed_at, "result": "baseline", "publish_date": published,
                              "record_count": parsed, "sha256": entry.sha256})
        write_state(state_path, new_state)
        print(f"BASELINE ESTABLISHED: {parsed} records, published {published}. "
              f"No prior baseline existed -- no delta reported.")
        return EXIT_UNCHANGED

    prev_entry = CacheEntry(path=Path(prev_state["artifact_path"]),
                            meta_path=Path(prev_state["artifact_meta_path"]),
                            sha256=prev_state["sha256"])
    try:
        prev_content, _prev_meta = cache_load(prev_entry)
    except CacheError as e:
        # The same discipline as a corrupt state file: the cache is our own
        # record of what "last time" looked like, and if IT cannot be trusted,
        # silently starting a fresh baseline would hide that just as badly.
        append_log(log_path, {"at": observed_at, "result": "cache_corrupt", "detail": str(e)})
        print(f"CACHE CORRUPT: {e} -- refusing to run", file=sys.stderr)
        return EXIT_POLL_NOT_TRUSTWORTHY

    old_summary, _old_parsed = _summarise(prev_content)
    delta = diff(old_summary, new_summary)

    # RT-08, the flagship finding: the delta is WRITTEN DOWN before the baseline
    # moves. Previously state advanced first, so a kill between the two lines --
    # an ordinary event under cron, systemd or a container -- consumed a newly
    # sanctioned entity permanently: the next poll diffed against the new baseline
    # and saw nothing, and no log line ever named it.
    if delta.is_empty():
        append_log(log_path, {"at": observed_at, "result": "unchanged", "publish_date": published,
                              "record_count": parsed, "sha256": entry.sha256})
        write_state(state_path, new_state)
        print(f"no change ({parsed} records, published {published})")
        return EXIT_UNCHANGED

    append_log(log_path, {"at": observed_at, "result": "changed", "publish_date": published,
                          "record_count": parsed, "sha256": entry.sha256,
                          "added": list(delta.added), "removed": list(delta.removed),
                          "changed": list(delta.changed)})
    write_state(state_path, new_state)
    _report(delta, old_summary, new_summary, published)
    return EXIT_CHANGED


def _test() -> None:
    import tempfile
    import urllib.error

    from checker.feeds.common.fetch import _FakeResponse
    from checker.feeds.ofac_sdn import _NS_SEEN
    from checker.robots import parse as parse_robots

    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    print("watch_ofac")

    def snapshot(entries_xml: str, stated: int, published: str = "09/16/2026") -> bytes:
        return f"""<?xml version="1.0" standalone="yes"?>
<sdnList xmlns="{_NS_SEEN}">
  <publshInformation><Publish_Date>{published}</Publish_Date><Record_Count>{stated}</Record_Count></publshInformation>
{entries_xml}
</sdnList>""".encode()

    def entry(uid: str, name: str, programs: list[str], sdn_type: str = "Entity") -> str:
        progs = "".join(f"<program>{p}</program>" for p in programs)
        return (f'  <sdnEntry><uid>{uid}</uid><lastName>{name}</lastName>'
               f'<sdnType>{sdn_type}</sdnType><programList>{progs}</programList></sdnEntry>')

    e100 = entry("100", "ACME HOLDINGS", ["CUBA"])
    e200 = entry("200", "JOHN DOE", ["SDGT"], sdn_type="Individual")
    e300 = entry("300", "NEW ENTRY", ["CUBA"])
    e300_changed = entry("300", "NEW ENTRY", ["CUBA", "SDGT"])

    snap_a = snapshot(e100 + "\n" + e200, stated=2)             # baseline: {100, 200}
    snap_b = snapshot(e100 + "\n" + e200 + "\n" + e300, stated=3)  # +300
    snap_c = snapshot(e100 + "\n" + e300, stated=2)              # -200
    snap_d = snapshot(e100 + "\n" + e300_changed, stated=2)      # 300's programs changed

    allow_all = parse_robots("")
    deny_all = parse_robots("User-agent: *\nDisallow: /\n")

    def opener_for(body: bytes):
        def opener(url, *, timeout):
            return _FakeResponse(200, body)
        return opener

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        cache_root, state_path, log_path = root / "cache", root / "state.json", root / "log.jsonl"

        def feed_for(body: bytes) -> OfacSdnFeed:
            return OfacSdnFeed(rules=allow_all, opener=opener_for(body))

        # ---- stage 1: first run -- baseline only, no delta possible -----------
        rc = poll(feed_for(snap_a), cache_root=cache_root, state_path=state_path,
                 log_path=log_path, observed_at="2026-09-01")
        check(rc == EXIT_UNCHANGED, f"first run exits UNCHANGED, not CHANGED ({rc})")
        check(state_path.is_file(), "a baseline state file is written on first run")
        state1 = json.loads(state_path.read_text())
        check(state1["record_count"] == 2, "baseline records the parsed count")
        log_lines_after_1 = log_path.read_text().splitlines()
        check(len(log_lines_after_1) == 1 and
             json.loads(log_lines_after_1[0])["result"] == "baseline",
             "the log records this as a baseline event, not a diff")

        # ---- stage 2: same content again -- unchanged, but baseline still advances
        rc = poll(feed_for(snap_a), cache_root=cache_root, state_path=state_path,
                 log_path=log_path, observed_at="2026-09-02")
        check(rc == EXIT_UNCHANGED, f"an identical re-poll is UNCHANGED ({rc})")

        # ---- stage 3: an entry is ADDED ----------------------------------------
        rc = poll(feed_for(snap_b), cache_root=cache_root, state_path=state_path,
                 log_path=log_path, observed_at="2026-09-03")
        check(rc == EXIT_CHANGED, f"an added uid is reported as CHANGED ({rc})")
        added_log = json.loads(log_path.read_text().splitlines()[-1])
        check(added_log["added"] == ["300"] and added_log["removed"] == [] and
             added_log["changed"] == [], "the log names exactly the uid that was added")
        state3 = json.loads(state_path.read_text())
        check(state3["record_count"] == 3, "the baseline advances to the new record count")

        # ---- stage 4: an entry is REMOVED --------------------------------------
        rc = poll(feed_for(snap_c), cache_root=cache_root, state_path=state_path,
                 log_path=log_path, observed_at="2026-09-04")
        check(rc == EXIT_CHANGED, f"a removed uid is reported as CHANGED ({rc})")
        removed_log = json.loads(log_path.read_text().splitlines()[-1])
        check(removed_log["removed"] == ["200"], "the log names exactly the uid that was removed")

        # ---- stage 5: an entry's programs CHANGE -------------------------------
        rc = poll(feed_for(snap_d), cache_root=cache_root, state_path=state_path,
                 log_path=log_path, observed_at="2026-09-05")
        check(rc == EXIT_CHANGED, f"a changed uid is reported as CHANGED ({rc})")
        changed_log = json.loads(log_path.read_text().splitlines()[-1])
        check(changed_log["changed"] == ["300"], "the log names exactly the uid whose fields changed")
        state5 = json.loads(state_path.read_text())

        # ---- stage 6: a FAILED poll holds the baseline -------------------------
        blocked_feed = OfacSdnFeed(rules=deny_all, opener=opener_for(snap_a))
        rc = poll(blocked_feed, cache_root=cache_root, state_path=state_path,
                 log_path=log_path, observed_at="2026-09-06")
        check(rc == EXIT_POLL_NOT_TRUSTWORTHY, f"a robots-refused fetch is POLL_NOT_TRUSTWORTHY ({rc})")
        check(json.loads(state_path.read_text()) == state5,
             "a failed poll leaves the baseline BYTE-FOR-BYTE unchanged, not reset")
        held_log = json.loads(log_path.read_text().splitlines()[-1])
        check(held_log["result"] == "held" and held_log["reason"] == "fetch_failed",
             "the log records a held poll, distinctly from a real diff")

        # ---- stage 7: a COUNT MISMATCH holds the baseline ----------------------
        bad_count = snapshot(e100 + "\n" + e300_changed, stated=99)  # file lies about its own count
        rc = poll(feed_for(bad_count), cache_root=cache_root, state_path=state_path,
                 log_path=log_path, observed_at="2026-09-07")
        check(rc == EXIT_POLL_NOT_TRUSTWORTHY, f"a stated/parsed mismatch is POLL_NOT_TRUSTWORTHY ({rc})")
        check(json.loads(state_path.read_text()) == state5,
             "a count-mismatched poll ALSO leaves the baseline unchanged")
        mismatch_log = json.loads(log_path.read_text().splitlines()[-1])
        check(mismatch_log["reason"] == "count_mismatch" and mismatch_log["stated"] == 99,
             "the log distinguishes a count mismatch from a fetch failure, and names the bad count")

        # ---- stage 8: a CORRUPT state file stops the run, not resets it -------
        state_path.write_text("{ not json ", encoding="utf-8")
        rc = poll(feed_for(snap_d), cache_root=cache_root, state_path=state_path,
                 log_path=log_path, observed_at="2026-09-08")
        check(rc == EXIT_POLL_NOT_TRUSTWORTHY, f"a corrupt state file is POLL_NOT_TRUSTWORTHY ({rc})")
        check(state_path.read_text() == "{ not json ",
             "the corrupt state file is left EXACTLY as it was -- never silently reset "
             "to a fresh baseline")
        corrupt_log = json.loads(log_path.read_text().splitlines()[-1])
        check(corrupt_log["result"] == "state_corrupt",
             "the log records why the run stopped, distinctly from a held poll")

    # ---- diff() and _summarise() in isolation, independent of poll() ----------
    old = {"1": {"name": "A", "sdn_type": "Entity", "programs": ["X"]},
          "2": {"name": "B", "sdn_type": "Entity", "programs": ["X"]}}
    new = {"1": {"name": "A", "sdn_type": "Entity", "programs": ["X", "Y"]},
          "3": {"name": "C", "sdn_type": "Entity", "programs": ["X"]}}
    d = diff(old, new)
    check(d.added == ("3",) and d.removed == ("2",) and d.changed == ("1",),
         "diff() finds exactly one add, one remove, one change from a hand-built pair")
    check(not d.is_empty(), "a non-trivial delta is not empty")
    check(diff(old, old).is_empty(), "diffing a summary against itself is empty")

    summary, parsed = _summarise(snap_a)
    check(parsed == 2 and set(summary) == {"100", "200"},
         "_summarise() returns both the uid map and the true parsed count")
    check(summary["200"]["sdn_type"] == "Individual", "sdn_type survives into the summary")

    # ---- load_state: absent vs corrupt are different outcomes -----------------
    with tempfile.TemporaryDirectory() as tmp:
        missing = Path(tmp) / "no_such_state.json"
        check(load_state(missing) is None, "a state file that does not exist is a legitimate 'no baseline'")

        garbage = Path(tmp) / "garbage.json"
        garbage.write_text("not json at all")
        try:
            load_state(garbage)
            check(False, "unparseable JSON must raise StateCorrupt, not return None")
        except StateCorrupt as e:
            check("not valid JSON" in str(e), f"...and says why: {e}")

        wrong_schema = Path(tmp) / "wrong_schema.json"
        wrong_schema.write_text(json.dumps({"schema": "something/v0"}))
        try:
            load_state(wrong_schema)
            check(False, "a wrong schema must raise StateCorrupt")
        except StateCorrupt as e:
            check("schema" in str(e), f"...and it does: {e}")

        incomplete = Path(tmp) / "incomplete.json"
        incomplete.write_text(json.dumps({"schema": STATE_SCHEMA, "sha256": "x"}))
        try:
            load_state(incomplete)
            check(False, "a state file missing required fields must raise StateCorrupt")
        except StateCorrupt as e:
            check("missing required field" in str(e), f"...and it does: {e}")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--test":
        _test()
        return 0
    feed = OfacSdnFeed()
    return poll(feed, cache_root=DEFAULT_CACHE_ROOT, state_path=DEFAULT_STATE_PATH,
               log_path=DEFAULT_LOG_PATH)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
