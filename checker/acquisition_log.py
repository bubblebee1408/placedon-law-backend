"""
Append-only log of attempts to acquire a source.

`provenance.py` records what we ended up holding. This records what we did to get it, including
every attempt that produced nothing. Failed attempts are the part that gets lost, and losing them
costs twice: the next run repeats a request whose answer is already known, and -- worse -- a gap in
the history reads later as "nobody tried", which is how an unacquired instrument turns into an
assumed-absent one.

Append-only is not a naming convention here. Records are frozen, the sequence is a tuple, and
`append()` returns a new sequence rather than touching the old one, so a rewrite has to be
deliberate. What makes rewriting *detectable* is the hash chain: each record commits to the digest
of the one before it, so editing any past field invalidates every digest after it, and the log's
declared head and length pin the tail so that dropping the last records is caught too. An audit log
that can be quietly edited is not evidence of anything.

Timestamps are arguments; nothing here reads the clock. A function that reads the clock cannot be
tested for the same input twice, and this file's whole claim is that identical inputs produce
identical digests. A test enforces the absence.

The terminal state that matters most is HUMAN_RETRIEVAL_REQUIRED. It is a SUCCESS: it means the
automation established that no permitted automated route exists and stopped instead of grinding
against a WAF. See docs/ACQUISITION_POLICY.md.

Run:  python3 checker/acquisition_log.py
Emit: python3 checker/acquisition_log.py --emit
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from checker.provenance import (ACCESSIBILITY_STATES, ACCESSIBLE, BLOCKED, NOT_FOUND, UNREACHABLE,
                                is_retryable)

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "reports" / "acquisition_board_rules_2014.json"
SCHEMA = "acquisition_log/v1"

# Where an acquisition sequence came to rest.
IN_PROGRESS = "IN_PROGRESS"
ACQUIRED = "ACQUIRED"
HUMAN_RETRIEVAL_REQUIRED = "HUMAN_RETRIEVAL_REQUIRED"
TERMINAL_STATES = (IN_PROGRESS, ACQUIRED, HUMAN_RETRIEVAL_REQUIRED)

# Both of these are successful stops. Handing a 5-minute browser task to a human is a correct
# outcome; only IN_PROGRESS is unfinished business.
SUCCESSFUL_STOP = (ACQUIRED, HUMAN_RETRIEVAL_REQUIRED)

# What a pile of failed attempts says about whether the instrument exists.
EXISTENCE_UNDETERMINED = "EXISTENCE_UNDETERMINED"
EXISTENCE_NOTE = (
    "Failure to DISCOVER an instrument is not evidence that the instrument does not exist. Every "
    "outcome below is a fact about a host or an address -- a refusal, an outage, a wrong path -- "
    "and none of them is a fact about the law. Disproving existence would require reading a source "
    "that would list the instrument if it existed; no such source was read. Existence stays "
    "undetermined, and nothing downstream may treat absence-from-corpus as absence-from-law."
)

GENESIS = "0" * 64  # what the first record chains to, so record 0 is not a special case

# Date, or date with a UTC time. Coarse is allowed on purpose: recording a minute we did not
# actually record would be inventing precision.
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2}Z)?$")

# Everything the chain commits to. entry_hash is absent because it IS the commitment.
_PAYLOAD_FIELDS = ("seq", "timestamp", "instrument_id", "url", "host", "method", "outcome",
                   "http_status", "error", "note", "artifact_sha256", "prev_hash")


class AcquisitionLogError(ValueError):
    """Raised on an inconsistent log. Never downgraded to a warning -- see ProvenanceError."""


@dataclass(frozen=True)
class AttemptRecord:
    """One request we made, and what came back. Frozen: history is not a mutable object."""
    seq: int
    timestamp: str
    instrument_id: str
    url: str
    host: str
    method: str
    outcome: str                       # one of provenance.ACCESSIBILITY_STATES
    http_status: int | None = None     # what the server said, if it said anything
    error: str | None = None           # what the socket said, if the server did not
    note: str = ""
    # Set only when the attempt obtained bytes OF THE TARGET INSTRUMENT. A probe that fetched
    # something else -- a control, a redirect, an error page -- leaves this None, or "acquired"
    # stops meaning anything.
    artifact_sha256: str | None = None
    prev_hash: str = GENESIS
    entry_hash: str = ""

    def payload(self) -> dict:
        return {f: getattr(self, f) for f in _PAYLOAD_FIELDS}

    def computed_hash(self) -> str:
        return digest(self.payload())

    def intact(self) -> bool:
        return self.entry_hash == self.computed_hash()


def digest(payload: dict) -> str:
    """Digest of one record's payload.

    Serialised with sorted keys and no whitespace so the digest depends on the values and not on
    how some later writer happened to format the JSON.
    """
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def head(records: tuple[AttemptRecord, ...]) -> str:
    """The digest that pins the whole history. Changing anything at all changes this value."""
    return records[-1].entry_hash if records else GENESIS


def append(records: tuple[AttemptRecord, ...], *, timestamp: str, instrument_id: str, url: str,
           host: str, method: str, outcome: str, http_status: int | None = None,
           error: str | None = None, note: str = "",
           artifact_sha256: str | None = None) -> tuple[AttemptRecord, ...]:
    """Return a NEW sequence with one record added. The input sequence is not touched.

    `timestamp` is a parameter rather than a clock read so that the same attempt logged twice
    produces the same digest, which is what makes the chain testable at all.
    """
    if outcome not in ACCESSIBILITY_STATES:
        raise AcquisitionLogError(
            f"{outcome!r} is not an accessibility state; one of {ACCESSIBILITY_STATES}")
    if not _TIMESTAMP.match(timestamp):
        raise AcquisitionLogError(f"{timestamp!r} is not an ISO-8601 date or UTC datetime")
    if not (instrument_id and url and host and method):
        raise AcquisitionLogError("instrument_id, url, host and method are all required")
    # An outcome that names a status must carry one, and vice versa: "403" with no status recorded
    # is exactly the kind of half-record that later gets re-read as an outage.
    if outcome in (BLOCKED, NOT_FOUND, ACCESSIBLE) and http_status is None:
        raise AcquisitionLogError(f"{outcome} means the server answered; record its status")
    if outcome == UNREACHABLE and not error:
        raise AcquisitionLogError("UNREACHABLE means no answer; record the transport error")

    payload = {
        "seq": len(records),
        "timestamp": timestamp,
        "instrument_id": instrument_id,
        "url": url,
        "host": host,
        "method": method,
        "outcome": outcome,
        "http_status": http_status,
        "error": error,
        "note": note,
        "artifact_sha256": artifact_sha256,
        "prev_hash": head(records),
    }
    return tuple(records) + (AttemptRecord(entry_hash=digest(payload), **payload),)


def verify(records: tuple[AttemptRecord, ...], *, expected_length: int | None = None,
           expected_head: str | None = None) -> tuple[bool, str]:
    """Whether this history is the history that was written.

    Three separate failures, because they are three separate lies:
      * a changed field       -> the record's own digest no longer matches its contents
      * a removed or reordered record -> the next record's prev_hash points at nothing present
      * a truncated tail      -> the chain is still internally valid, so only the declared length
                                 and head catch it. Pass them, or tail-trimming is invisible.
    """
    prev = GENESIS
    for i, r in enumerate(records):
        if r.seq != i:
            return False, f"record {i}: seq is {r.seq}; records were reordered or one was removed"
        if r.prev_hash != prev:
            return False, f"record {i} ({r.url}): prev_hash does not follow record {i - 1}"
        if not r.intact():
            return False, f"record {i} ({r.url}): contents were altered after it was written"
        prev = r.entry_hash
    if expected_length is not None and len(records) != expected_length:
        return False, f"history holds {len(records)} records; {expected_length} were declared"
    if expected_head is not None and head(records) != expected_head:
        return False, "chain head does not match the declared head"
    return True, ""


@dataclass(frozen=True)
class AcquisitionLog:
    instrument_id: str
    title: str
    terminal_state: str
    records: tuple[AttemptRecord, ...] = ()
    handoff: str = ""

    def __post_init__(self) -> None:
        if self.terminal_state not in TERMINAL_STATES:
            raise AcquisitionLogError(
                f"{self.terminal_state!r} is not a terminal state; one of {TERMINAL_STATES}")
        # ACQUIRED has to point at bytes. Otherwise a log can declare a success it cannot show,
        # which is the single failure mode an acquisition log exists to make impossible.
        if self.terminal_state == ACQUIRED and not any(r.artifact_sha256 for r in self.records):
            raise AcquisitionLogError(
                f"{self.instrument_id}: ACQUIRED but no attempt recorded an artifact hash")

    def head(self) -> str:
        return head(self.records)

    def verify(self) -> tuple[bool, str]:
        return verify(self.records)

    def human_retrieval_required(self) -> bool:
        return self.terminal_state == HUMAN_RETRIEVAL_REQUIRED

    def stopped_successfully(self) -> bool:
        return self.terminal_state in SUCCESSFUL_STOP


def summary(log: AcquisitionLog) -> dict:
    """What a reviewer needs to decide what happens next, derived from the records themselves."""
    by_outcome: dict[str, int] = {}
    for r in log.records:
        by_outcome[r.outcome] = by_outcome.get(r.outcome, 0) + 1
    return {
        "instrument_id": log.instrument_id,
        "title": log.title,
        "attempts": len(log.records),
        "hosts_tried": sorted({r.host for r in log.records}),
        "by_outcome": dict(sorted(by_outcome.items())),
        "terminal_state": log.terminal_state,
        "terminal_state_is_success": log.stopped_successfully(),
        "human_retrieval_required": log.human_retrieval_required(),
        "automated_retry_permitted": sorted({r.url for r in log.records
                                             if is_retryable(r.outcome)}),
        "never_retry_automatically": sorted({r.url for r in log.records
                                             if not is_retryable(r.outcome)
                                             and r.outcome != ACCESSIBLE}),
        "instrument_existence": EXISTENCE_UNDETERMINED,
        "existence_note": EXISTENCE_NOTE,
        "chain": {"length": len(log.records), "head": log.head()},
    }


def to_dict(log: AcquisitionLog) -> dict:
    return {
        "schema": SCHEMA,
        "instrument_id": log.instrument_id,
        "title": log.title,
        "terminal_state": log.terminal_state,
        "handoff": log.handoff,
        "summary": summary(log),
        "records": [{**r.payload(), "entry_hash": r.entry_hash} for r in log.records],
    }


def from_dict(data: dict) -> AcquisitionLog:
    if data.get("schema") != SCHEMA:
        raise AcquisitionLogError(f"unknown schema {data.get('schema')!r}; expected {SCHEMA!r}")
    records = tuple(AttemptRecord(**r) for r in data["records"])
    return AcquisitionLog(
        instrument_id=data["instrument_id"],
        title=data["title"],
        terminal_state=data["terminal_state"],
        records=records,
        handoff=data.get("handoff", ""),
    )


def load(path: Path) -> AcquisitionLog:
    """Read a log and refuse to hand back one whose chain does not check out."""
    data = json.loads(path.read_text(encoding="utf-8"))
    log = from_dict(data)
    declared = data.get("summary", {}).get("chain", {})
    good, why = verify(log.records, expected_length=declared.get("length"),
                       expected_head=declared.get("head"))
    if not good:
        raise AcquisitionLogError(f"{path.name}: {why}")
    return log


def write(log: AcquisitionLog, path: Path) -> None:
    path.write_text(json.dumps(to_dict(log), indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")


# --- the actual attempt history for the Board Meetings Rules, 2014 -----------------------------
#
# All of it observed on 2026-08-21 and recorded here verbatim. Timestamps are date-only because
# date-only is what was recorded; ordering is carried by seq, not by an invented clock time.
# Nothing below was re-probed to build this file: re-running requests against a source that has
# already refused us is precisely what CLAUDE.md forbids, and the answers are not in doubt.

BOARD_RULES_ID = "INDIACODE_MEETINGS_BOARD_RULES_2014"
_D = "2026-08-21"


def _board_rules_records() -> tuple[AttemptRecord, ...]:
    rs: tuple[AttemptRecord, ...] = ()
    add = lambda **kw: append(rs, timestamp=_D, instrument_id=BOARD_RULES_ID, **kw)  # noqa: E731

    rs = add(
        url=("https://upload.indiacode.nic.in/showfile?actid=AC_CEN_22_29_00008_201318_"
             "1517807327856&type=rule&filename=The%20Companies%20(Meetings%20and%20Powers%20"
             "of%20Board)%20.pdf"),
        host="upload.indiacode.nic.in", method="GET", outcome=UNREACHABLE,
        error="ECONNREFUSED",
        note="Refused instantly rather than timing out, which is a host that is down and not a "
             "network in between. Retryable: it may come back.")
    rs = add(
        url="http://164.100.94.56/", host="164.100.94.56", method="GET", outcome=UNREACHABLE,
        error="ECONNREFUSED",
        note="The address upload.indiacode.nic.in resolves to. Probed to separate a DNS problem "
             "from a dead service; the service is dead.")
    rs = add(
        url="https://www.indiacode.nic.in/handle/123456789/1362", host="www.indiacode.nic.in",
        method="GET", outcome=BLOCKED, http_status=403,
        note="Browse by handle. Dynamic path.")
    rs = add(
        url="https://www.indiacode.nic.in/simple-search?searchradio=rules",
        host="www.indiacode.nic.in", method="GET", outcome=BLOCKED, http_status=403,
        note="Rules search -- the one route that would have yielded the file's static address.")
    rs = add(
        url="https://www.indiacode.nic.in/show-data", host="www.indiacode.nic.in", method="GET",
        outcome=BLOCKED, http_status=403,
        note="Section/rule view. Same endpoint family as INDIACODE_SECTION_VIEW in provenance.py.")
    rs = add(
        url="https://www.indiacode.nic.in/ViewFileUploaded", host="www.indiacode.nic.in",
        method="GET", outcome=BLOCKED, http_status=403,
        note="File-serving endpoint reached through the dynamic pages.")
    rs = add(
        url="https://www.indiacode.nic.in/bitstream/123456789/2114/5/A2013-18.pdf",
        host="www.indiacode.nic.in", method="GET", outcome=ACCESSIBLE, http_status=200,
        note="CONTROL, and deliberately carries no artifact hash: the bytes it returns are the "
             "Companies Act (INDIACODE_CA2013_PDF in checker/provenance.py), not the Rules. It "
             "matters because it is the same host as the four 403s above: the host is up "
             "and serving, so those are a deliberate block and not an outage. Without this probe "
             "the whole host looks down and gets a retry schedule it must not have.")
    rs = add(
        url="https://www.mca.gov.in/", host="www.mca.gov.in", method="GET", outcome=BLOCKED,
        http_status=403,
        note="Second official publisher. Refused. Not bypassed -- see CLAUDE.md.")
    rs = add(
        url="https://egazette.gov.in/", host="egazette.gov.in", method="GET", outcome=ACCESSIBLE,
        http_status=200,
        note="Reachable, and the right archive, but retrieval runs through a stateful search form "
             "that a human drives. Reachable is not the same as automatable.")
    return rs


BOARD_RULES_2014 = AcquisitionLog(
    instrument_id=BOARD_RULES_ID,
    title="The Companies (Meetings of Board and its Powers) Rules, 2014 — principal Rules",
    terminal_state=HUMAN_RETRIEVAL_REQUIRED,
    records=_board_rules_records(),
    handoff=(
        "Every permitted automated route is exhausted: the one host that serves the file directly "
        "is down, and the only route that could discover the file's static address is behind a "
        "WAF that has refused us and must not be re-probed. A browser session is not subject to "
        "that block, so this is a five-minute human task -- see "
        "docs/ACQUISITION_HANDOFF_board_rules_2014.md, then run scripts/acquire_rules.py on the "
        "downloaded PDF. Third-party sources give a notification number and date for these Rules; "
        "those are LEADS for finding the file and must be read off the acquired document before "
        "they are recorded anywhere (see PRINCIPAL_RULES_LEAD in checker/provenance.py). "
        "Do not backfill them."
    ),
)


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"[PASS] {label}")
        else:
            fail += 1; print(f"[FAIL] {label}")

    log = BOARD_RULES_2014
    good, why = log.verify()
    check(good, f"the recorded Board Rules history verifies ({why})")
    check(len(log.records) == 9, f"nine attempts recorded, got {len(log.records)}")
    check(len(summary(log)["hosts_tried"]) == 5, "five distinct hosts were tried")

    # Append-only, structurally. The old sequence must be unchanged and reusable.
    before = log.records
    grown = append(before, timestamp="2026-08-22", instrument_id=BOARD_RULES_ID,
                   url="https://example.invalid/x", host="example.invalid", method="GET",
                   outcome=UNREACHABLE, error="ETIMEDOUT")
    check(len(before) == 9 and len(grown) == 10, "append returns a new sequence, does not mutate")
    check(all(a is b for a, b in zip(before, grown)), "existing records are the same objects")
    check(grown[-1].prev_hash == before[-1].entry_hash, "the new record chains to the old head")
    check(verify(grown)[0], "the grown chain still verifies")

    # Determinism. This is what "pass the timestamp in" buys.
    again = append(before, timestamp="2026-08-22", instrument_id=BOARD_RULES_ID,
                   url="https://example.invalid/x", host="example.invalid", method="GET",
                   outcome=UNREACHABLE, error="ETIMEDOUT")
    check(again[-1].entry_hash == grown[-1].entry_hash, "identical input gives an identical digest")
    # Read the production half only: the needles below appear in this test by necessity.
    src = Path(__file__).read_text(encoding="utf-8").split("def _test(")[0]
    check(not any(n in src for n in ("datetime.now", "time.time", "utcnow", "date.today")),
          "no clock is read anywhere in the code under test")

    # Tampering with a PAST record must be caught. This is the whole point of the file.
    tampered = tuple(
        AttemptRecord(**{**r.__dict__, "outcome": UNREACHABLE, "http_status": None,
                         "error": "ECONNREFUSED"}) if r.seq == 3 else r
        for r in log.records)
    bad, why2 = verify(tampered)
    check(not bad, "rewriting a past record is detected")
    check("record 3" in why2 and "altered" in why2, f"and the altered record is named: {why2}")

    # The specific rewrite this repo actually made once: a 403 recorded as an outage.
    check(tampered[3].outcome == UNREACHABLE and not tampered[3].intact(),
          "a 403 relabelled as an outage cannot be smuggled past the chain")

    # Truncation. The chain alone stays valid, so the declared length and head have to catch it.
    trimmed = log.records[:-2]
    check(verify(trimmed)[0], "a truncated chain is still internally consistent (why the anchor)")
    cut, why3 = verify(trimmed, expected_length=9, expected_head=log.head())
    check(not cut and "declared" in why3, f"truncation is caught by the declared anchor: {why3}")

    # Removing a record from the middle breaks the links regardless of any anchor.
    gapped = log.records[:4] + log.records[5:]
    check(not verify(gapped)[0], "removing a middle record is detected")
    reordered = log.records[:3] + (log.records[4], log.records[3]) + log.records[5:]
    check(not verify(reordered)[0], "reordering records is detected")

    # Terminal state.
    check(log.terminal_state == HUMAN_RETRIEVAL_REQUIRED, "terminal state is HUMAN_RETRIEVAL_REQUIRED")
    check(log.stopped_successfully(), "HUMAN_RETRIEVAL_REQUIRED is a SUCCESSFUL stop, not a failure")
    check(log.human_retrieval_required(), "summary says a human must retrieve the file")
    try:
        AcquisitionLog(BOARD_RULES_ID, "x", ACQUIRED, log.records)
        check(False, "ACQUIRED with no artifact hash must raise")
    except AcquisitionLogError as e:
        check("no attempt recorded an artifact hash" in str(e),
              "ACQUIRED must point at bytes it can show")
    got = append(log.records, timestamp="2026-09-01", instrument_id=BOARD_RULES_ID,
                 url="https://www.indiacode.nic.in/bitstream/123456789/0/0/rules.pdf",
                 host="www.indiacode.nic.in", method="GET", outcome=ACCESSIBLE, http_status=200,
                 artifact_sha256="a" * 64, note="Hypothetical, for the invariant only.")
    check(AcquisitionLog(BOARD_RULES_ID, "x", ACQUIRED, got).stopped_successfully(),
          "ACQUIRED is allowed once an attempt shows the target's bytes")
    try:
        AcquisitionLog(BOARD_RULES_ID, "x", "PROBABLY_DONE")
        check(False, "invented terminal state must raise")
    except AcquisitionLogError:
        check(True, "invented terminal state rejected")

    # Retry policy, read straight off the outcomes.
    s = summary(log)
    check(all("upload.indiacode.nic.in" in u or "164.100.94.56" in u
              for u in s["automated_retry_permitted"]),
          "only the downed host is offered for automated retry")
    check(any("simple-search" in u for u in s["never_retry_automatically"]),
          "the 403 discovery route is on the never-retry list")
    check(not any("bitstream" in u for u in s["never_retry_automatically"]),
          "a working static path is not on the never-retry list")

    # Existence. No accumulation of failures may be read as absence from the law.
    check(s["instrument_existence"] == EXISTENCE_UNDETERMINED,
          "discovery failure leaves existence undetermined")
    all_failed = AcquisitionLog(
        "X", "x", HUMAN_RETRIEVAL_REQUIRED,
        append((), timestamp=_D, instrument_id="X", url="https://h.invalid/a", host="h.invalid",
               method="GET", outcome=NOT_FOUND, http_status=404))
    check(summary(all_failed)["instrument_existence"] == EXISTENCE_UNDETERMINED,
          "even an all-404 history does not disprove existence")
    check(not summary(all_failed)["automated_retry_permitted"],
          "a 404 is not scheduled for automated retry")

    # No 404 was observed for these Rules; the state exists, but inventing an instance of it here
    # would be inventing a network result.
    check(NOT_FOUND not in s["by_outcome"], "no 404 is claimed that was never observed")

    # Field discipline: an outcome that names a status must carry one.
    for kwargs, label in (
        ({"outcome": BLOCKED}, "BLOCKED without an http_status is rejected"),
        ({"outcome": UNREACHABLE, "http_status": None}, "UNREACHABLE without an error is rejected"),
        ({"outcome": "TEAPOT", "http_status": 418}, "invented outcome is rejected"),
    ):
        try:
            append((), timestamp=_D, instrument_id="X", url="u", host="h", method="GET", **kwargs)
            check(False, label)
        except AcquisitionLogError:
            check(True, label)
    try:
        append((), timestamp="21-08-2026", instrument_id="X", url="u", host="h", method="GET",
               outcome=BLOCKED, http_status=403)
        check(False, "a non-ISO timestamp is rejected")
    except AcquisitionLogError:
        check(True, "a non-ISO timestamp is rejected")

    # The committed report must be the log, byte for byte. A hand-edit of reports/ is a rewrite of
    # history by another name.
    check(REPORT.is_file(), f"{REPORT.relative_to(ROOT)} exists")
    if REPORT.is_file():
        on_disk = json.loads(REPORT.read_text(encoding="utf-8"))
        check(on_disk == to_dict(log), "the committed report matches the recorded history exactly")
        loaded = load(REPORT)
        check(loaded.head() == log.head(), "the report round-trips to the same chain head")
        check(loaded.terminal_state == HUMAN_RETRIEVAL_REQUIRED,
              "the report's terminal state survives the round trip")
        doctored = {**on_disk, "records": [{**r} for r in on_disk["records"]]}
        doctored["records"][2]["http_status"] = 200
        # Written outside the repo: a test must not leave a file in reports/ if it is killed.
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump(doctored, fh)
            tmp = Path(fh.name)
        try:
            load(tmp)
            check(False, "loading a doctored report must raise")
        except AcquisitionLogError as e:
            check("altered" in str(e), f"a doctored report is refused at load: {e}")
        finally:
            tmp.unlink(missing_ok=True)

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    if "--emit" in sys.argv:
        write(BOARD_RULES_2014, REPORT)
        print(f"wrote {REPORT.relative_to(ROOT)} (head {BOARD_RULES_2014.head()[:12]}…)")
    else:
        _test()
