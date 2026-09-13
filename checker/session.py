"""The ephemeral session: where a client document lives, and where it does not.

Every legal-AI contract of any size requires zero data retention, and the phrase
has a precise meaning that is easy to miss:

    Storing data during the run and calling a deletion endpoint afterward is not
    zero retention. It is retention followed by deletion.

So this module does not offer a delete. It offers a place where client content
can exist that has **no path to durable storage at all**, and a guard that
inspects anything leaving that place before it is allowed to be written.

## The three rules

1. **Client content lives in memory, keyed to a session, and dies with it.**
   No file, no database, no checkpoint, no cache. `close()` purges; the context
   manager guarantees it even on an exception.

2. **Nothing leaves a session unexamined.** `session.releasable(record)` scans a
   proposed durable record for verbatim fragments of the content the session
   holds, and REFUSES rather than redacting. Redaction invites "we removed the
   bits we found"; refusal makes the caller fix what they are emitting.

3. **A closed session is not a slow session.** Reading from one raises. A stale
   handle returning empty data quietly is how a "purged" session keeps serving.

## What may persist, and what may not

May: the *result* of a check -- obligation ids, verdicts, instrument names, dates,
hashes. All of that is our corpus and our arithmetic, not the client's document.

May not: the document text, an extractor's quoted spans, party names, figures
read out of the file. That is the client's, and it goes home with them.

## An honest limit

The guard catches VERBATIM fragments. It cannot catch a paraphrase, and it is not
meant to: this pipeline is deterministic, so the realistic leak is a span copied
into a result field, not a model retelling the document. A narration layer will
need its own control, and this one should not be mistaken for it.
"""
from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone

# A verbatim run of this many characters escaping a session is treated as a leak.
# Short enough to catch a quoted span, long enough that "private" or a date does
# not trip it. Tuned to the shortest span the extractor is allowed to propose.
LEAK_WINDOW = 40


class SessionClosed(RuntimeError):
    """A closed session was read. It holds nothing, and says so loudly."""


class ContentWouldEscape(RuntimeError):
    """A record proposed for durable storage carries client content."""


@dataclass
class Session:
    """A place for client content to exist that has no path to disk."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    opened_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    _content: dict[str, str] = field(default_factory=dict, repr=False)
    _closed: bool = field(default=False, repr=False)

    # ── holding content ───────────────────────────────────────────────────────
    def put(self, key: str, value: str) -> None:
        if self._closed:
            raise SessionClosed(f"session {self.id} is closed; it holds nothing")
        if not isinstance(value, str):
            raise TypeError("a session holds text; serialise elsewhere and it is "
                            "no longer clear what is client content")
        self._content[key] = value

    def get(self, key: str) -> str:
        if self._closed:
            raise SessionClosed(
                f"session {self.id} is closed. A stale handle returning empty data "
                "quietly is how a purged session keeps serving")
        return self._content[key]

    def keys(self) -> tuple[str, ...]:
        if self._closed:
            raise SessionClosed(f"session {self.id} is closed")
        return tuple(self._content)

    @property
    def closed(self) -> bool:
        return self._closed

    def close(self) -> None:
        """Purge. Idempotent, and the only exit."""
        self._content.clear()
        self._closed = True

    # ── the guard ─────────────────────────────────────────────────────────────
    def _fragments(self) -> list[str]:
        """Sliding windows of everything held, for verbatim leak detection."""
        out: list[str] = []
        for v in self._content.values():
            flat = " ".join(v.split())          # whitespace-insensitive comparison
            for i in range(0, max(1, len(flat) - LEAK_WINDOW + 1)):
                out.append(flat[i:i + LEAK_WINDOW])
        return out

    def releasable(self, record: object) -> object:
        """Return `record` if it carries no client content; otherwise refuse.

        Refuses rather than redacts. A redacting guard teaches callers that
        emitting client content is survivable, and its failures are silent.
        """
        if self._closed:
            return record                        # nothing held; nothing to leak
        blob = " ".join(json.dumps(record, default=str, sort_keys=True).split())
        for frag in self._fragments():
            if frag and frag in blob:
                raise ContentWouldEscape(
                    f"session {self.id}: the record carries a verbatim fragment of "
                    f"held client content — {frag[:60]!r}… Emit ids, verdicts, "
                    f"instruments, dates and hashes; the document goes home with "
                    f"the client.")
        return record


@contextmanager
def session(**kw):
    """Open a session and guarantee it is purged, exception or not."""
    s = Session(**kw)
    try:
        yield s
    finally:
        s.close()


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [PASS] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    print("session")
    DOC = ("CERTIFIED TRUE COPY of a resolution passed at the meeting of the Board "
           "of Directors of Acme Widgets Private Limited held on the 1st day of "
           "June, 2024. Its paid up share capital is Rs. 6,00,00,000 and its "
           "turnover for the financial year 2024-25 was Rs. 55 crore.")

    # ── holds, then purges ───────────────────────────────────────────────────
    with session() as s:
        s.put("document", DOC)
        check(s.get("document") == DOC, "a session holds what was put in it")
        check(s.keys() == ("document",), "...and reports what it holds")
        sid = s.id
    check(s.closed, "leaving the block purges the session")
    try:
        s.get("document")
        check(False, "a closed session refuses reads")
    except SessionClosed as e:
        check("purged session keeps serving" in str(e),
              "a closed session refuses reads, loudly, rather than returning empty")

    # purged even when the block raises
    try:
        with session() as s2:
            s2.put("document", DOC)
            raise ValueError("boom")
    except ValueError:
        pass
    check(s2.closed, "a session is purged even when the block raises")

    # ── the guard ────────────────────────────────────────────────────────────
    with session() as s3:
        s3.put("document", DOC)

        clean = {"obligation_id": "CA13-S2-85-SMALL", "state": "CANNOT_DETERMINE",
                 "instrument": "G.S.R. 880(E)", "as_of": "2026-09-10",
                 "sha256": "sha256:44faa58c"}
        check(s3.releasable(clean) is clean,
              "a result of ids, verdicts, instruments and dates is releasable")

        leaky = dict(clean, basis="the document states: " + DOC[:120])
        try:
            s3.releasable(leaky)
            check(False, "a record carrying a document fragment is refused")
        except ContentWouldEscape as e:
            check("verbatim fragment" in str(e),
                  "a record carrying a document fragment is refused")
            check("goes home with the client" in str(e),
                  "...and the refusal says what may be emitted instead")

        # whitespace does not defeat it
        reflowed = dict(clean, note="  ".join(DOC[:90].split()))
        try:
            s3.releasable(reflowed)
            check(False, "reflowed whitespace does not defeat the guard")
        except ContentWouldEscape:
            check(True, "reflowed whitespace does not defeat the guard")

        # nested and non-string fields are still scanned
        nested = dict(clean, rows=[{"detail": DOC[20:80]}])
        try:
            s3.releasable(nested)
            check(False, "a fragment nested inside a list is still caught")
        except ContentWouldEscape:
            check(True, "a fragment nested inside a list is still caught")

        # a short common phrase must NOT trip it, or the guard is unusable
        check(s3.releasable(dict(clean, note="private company")) is not None,
              "a short common phrase does not trip the guard")

    # ── the real test: a full check inside a session writes nothing durable ──
    import os
    from pathlib import Path

    def snapshot() -> dict:
        out = {}
        for root, dirs, files in os.walk("."):
            dirs[:] = [d for d in dirs if d not in
                       (".git", "__pycache__", ".pytest_cache", ".venv")]
            for f in files:
                p = Path(root) / f
                try:
                    out[str(p)] = p.stat().st_mtime_ns, p.stat().st_size
                except OSError:
                    pass
        return out

    from checker.document_extract import ground
    from checker.api import handle

    before = snapshot()
    with session() as s4:
        s4.put("document", DOC)
        g = ground(s4.get("document"), {
            "document_date": {"value": "2024-06-01", "span": "1st day of June, 2024"},
            "company_class": {"value": "private", "span": "Widgets Private Limited"},
            "paid_up_capital_rupees": {"value": 60000000, "span": "Rs. 6,00,00,000"},
            "financial_year": {"value": "2024-25", "span": "financial year 2024-25"},
            "turnover_rupees": {"value": 550000000, "span": "Rs. 55 crore"},
        }, source_id="board-resolution")
        st, result = handle("POST", "/v1/document-check",
                            {**g.to_payload(), "incorporation_date": "2015-04-01",
                             "as_of": "2026-09-10"},
                            generated_at="2026-09-10T00:00:00Z")
        check(st == 200, f"a full document check runs inside a session ({st}) "
                         f"{result.get('detail','')}")
        released = s4.releasable(result)
        check(released is result,
              "...and its result passes the guard — it carries no document text")
    after = snapshot()

    created = set(after) - set(before)
    changed = {k for k in set(after) & set(before) if after[k] != before[k]}
    check(not created, f"the run created no files ({sorted(created)[:3]})")
    check(not changed, f"...and modified none ({sorted(changed)[:3]})")

    # MUTATION. The two checks above are the entire evidence for "we do not
    # persist client data", so they must be shown to bite. Write a file the way a
    # careless cache or checkpoint would, and confirm the snapshot catches it.
    probe = Path("./.session_leak_probe.tmp")
    b2 = snapshot()
    probe.write_text(DOC)
    a2 = snapshot()
    caught = (set(a2) - set(b2)) or {k for k in set(a2) & set(b2) if a2[k] != b2[k]}
    probe.unlink()
    check(bool(caught),
          "the filesystem check catches a durable write — it is evidence, not decoration")
    check(str(probe) in str(caught), f"...and names the file that appeared ({caught})")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
