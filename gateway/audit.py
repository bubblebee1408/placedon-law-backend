"""Append-only audit, hash-chained. Metadata only — never document or prompt text.

## Why a chain

An audit row that can be edited after the fact is a record of what someone was willing to
say happened. Each record carries the digest of the one before it, so changing any field of
any record changes every digest after it, and `verify()` names the first one that broke.
Deleting a record from the middle breaks the chain at that point; truncating the tail is
caught by `expected_length`, because a chain that is merely shorter still verifies.

The shape is taken from `checker/acquisition_log.py`, which already does this for source
attempts and is proven in the gate. Two properties are copied deliberately:

  * **Canonical serialisation.** Sorted keys, no whitespace, so the digest depends on the
    values and not on how some later writer happened to format the JSON.
  * **`timestamp` is a parameter, not a clock read.** The same event logged twice produces
    the same digest, which is what makes the chain testable at all.

## What the chain does NOT buy, stated before it is relied on

A hash chain is tamper-**evidence**, and only against an actor who cannot recompute it. The
migration owner and any Postgres superuser can rewrite a row and re-chain every successor,
and the result verifies perfectly. So **inside the database this chain is not stronger than
the `REVOKE UPDATE, DELETE, TRUNCATE ON audit_log` that PLAN_18 §3.3 already specifies** --
it is a second lock on the same door, keyed to the same people.

It becomes stronger than that only when the head digest is periodically anchored **outside**
the database: a signed daily `head()` written to immutable storage, or countersigned
externally. Until that exists, this module detects an edit made by someone who did not think
to re-chain, and nothing more.

That is written here rather than discovered later because an unanchored chain is a guard
that cannot fail in the one scenario it exists for -- the exact failure class
`checker/rings.py` and `scripts/harness_regression.sh` were built to refuse. **Decide the
anchor when the schema is decided, or do not ship the chain** (research/TASKS.md R-015).

## Why there is no free-text field

PLAN_18 §2.1 says the audit writer records metadata only, and the founder's instruction is
"no document or prompt text in logs". Neither is enforceable by good intentions, so this
module has **no field a prompt could be put in**: the schema is fixed, every string is
length-bounded, and a value containing a newline is refused outright. Prose has newlines;
a route name, a UUID and an action verb do not.

That is a cheap test and it is not a complete one. It stops the accident -- a handler
passing `body["question"]` into `resource` -- and it would not stop someone determined to
smuggle a single-line secret through a bounded field. The structural guarantee is the fixed
schema; the newline and length checks are the tripwire on top of it.

Run: python3 gateway/audit.py
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass

GENESIS = "0" * 64

# Reused from the MCP policy module so the gateway and the tool surface cannot drift on what
# an action means. ATTEST is deliberately NOT importable into an audit record: PLAN_18 §2.1
# states it is never reachable from the gateway, because declaring a source verified is a
# human act and an HTTP request is not a person.
READ = "READ"
WRITE = "WRITE"
ACTIONS = (READ, WRITE)

_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                   r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

# Bounds chosen to fit an identifier and refuse a paragraph.
MAX_FIELD = 200
_FREE_TEXT = re.compile(r"[\n\r\t]")


class AuditError(ValueError):
    """A record that must not be written. Raised before anything reaches the chain."""


@dataclass(frozen=True)
class AuditRecord:
    seq: int
    timestamp: str
    request_id: str
    tenant_id: str
    actor: str
    action: str
    route: str
    resource: str
    outcome: str
    http_status: int
    prev_hash: str
    entry_hash: str

    def computed_hash(self) -> str:
        d = asdict(self)
        d.pop("entry_hash")
        return digest(d)

    @property
    def intact(self) -> bool:
        return self.entry_hash == self.computed_hash()


def digest(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def head(records: tuple[AuditRecord, ...]) -> str:
    """The digest pinning the whole history. Changing anything changes this value."""
    return records[-1].entry_hash if records else GENESIS


def _clean(name: str, value: str) -> str:
    if not isinstance(value, str) or not value:
        raise AuditError(f"{name} is required and must be a non-empty string")
    if len(value) > MAX_FIELD:
        raise AuditError(
            f"{name} is {len(value)} characters, over the {MAX_FIELD} bound. An audit record "
            f"carries metadata; a value this long is document or prompt text, which must "
            f"never reach a log.")
    if _FREE_TEXT.search(value):
        raise AuditError(
            f"{name} contains a newline or tab. Prose has those; a route, an identifier and "
            f"an action verb do not. This is the tripwire for a handler passing question or "
            f"document text into an audit field.")
    return value


def append(records: tuple[AuditRecord, ...], *, timestamp: str, request_id: str,
           tenant_id: str, actor: str, action: str, route: str, resource: str,
           outcome: str, http_status: int) -> tuple[AuditRecord, ...]:
    """A NEW sequence with one record added. The input is never mutated."""
    if not _TIMESTAMP.match(timestamp):
        raise AuditError(f"{timestamp!r} is not an ISO-8601 UTC timestamp (…T…Z)")
    if action not in ACTIONS:
        raise AuditError(
            f"{action!r} is not a gateway action; one of {ACTIONS}. ATTEST is deliberately "
            f"absent: declaring a source verified is a human act, and an HTTP request is not "
            f"a person (PLAN_18 §2.1).")
    for name in ("tenant_id", "actor"):
        v = {"tenant_id": tenant_id, "actor": actor}[name]
        if not _UUID.match(v or ""):
            raise AuditError(f"{name} must be a UUID, got {v!r}. An audit row that cannot "
                             f"name the tenant it belongs to is not an audit row.")
    if not isinstance(http_status, int) or not 100 <= http_status <= 599:
        raise AuditError(f"http_status must be an HTTP status, got {http_status!r}")

    payload = {
        "seq": len(records),
        "timestamp": timestamp,
        "request_id": _clean("request_id", request_id),
        "tenant_id": tenant_id,
        "actor": actor,
        "action": action,
        "route": _clean("route", route),
        "resource": _clean("resource", resource),
        "outcome": _clean("outcome", outcome),
        "http_status": http_status,
        "prev_hash": head(records),
    }
    return tuple(records) + (AuditRecord(entry_hash=digest(payload), **payload),)


def verify(records: tuple[AuditRecord, ...], *,
           expected_length: int | None = None) -> tuple[bool, str]:
    """(ok, reason). Names the FIRST record that broke, so the fix is not a hunt."""
    if expected_length is not None and len(records) != expected_length:
        return False, (f"chain holds {len(records)} records, expected {expected_length} — "
                       f"a truncated chain still verifies, so length is checked separately")
    prev = GENESIS
    for i, r in enumerate(records):
        if r.seq != i:
            return False, f"record {i} carries seq={r.seq}: the chain has been reordered"
        if r.prev_hash != prev:
            return False, (f"record {i} points at {r.prev_hash[:12]}…, but record {i - 1} "
                           f"hashes to {prev[:12]}…: a record was changed or removed")
        if not r.intact:
            return False, (f"record {i} does not hash to its own contents "
                           f"({r.entry_hash[:12]}… vs {r.computed_hash()[:12]}…): it was edited")
        prev = r.entry_hash
    return True, ""


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

    def attempt(fn):
        try:
            fn()
        except Exception as e:                      # noqa: BLE001 - inspected by the test
            return e
        return None

    print("gateway.audit")
    T1 = "11111111-1111-1111-1111-111111111111"
    T2 = "22222222-2222-2222-2222-222222222222"
    U1 = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

    def row(rs, **kw):
        base = dict(timestamp="2026-09-28T04:00:00Z", request_id="req-1", tenant_id=T1,
                    actor=U1, action=READ, route="GET /v2/matters", resource="matter:7",
                    outcome="ALLOW", http_status=200)
        base.update(kw)
        return append(rs, **base)

    chain = ()
    for i in range(4):
        chain = row(chain, request_id=f"req-{i}")
    ok_, why = verify(chain)
    check(ok_ and len(chain) == 4, f"a four-record chain verifies ({why})")
    check(chain[0].prev_hash == GENESIS, "the first record points at GENESIS")
    check(all(chain[i].prev_hash == chain[i - 1].entry_hash for i in range(1, 4)),
          "each record carries the digest of the one before it")

    # ── tampering ────────────────────────────────────────────────────────────
    import dataclasses as _dc
    edited = chain[:2] + (_dc.replace(chain[2], outcome="DENY"),) + chain[3:]
    ok_, why = verify(edited)
    check(not ok_ and "record 2" in why,
          f"editing a field is detected, and the FIRST broken record is named ({why[:60]})")
    check("does not hash to its own contents" in why,
          "...as a record that no longer hashes to its contents")

    reordered = (chain[0], chain[2], chain[1], chain[3])
    ok_, why = verify(reordered)
    check(not ok_ and "reordered" in why, f"reordering is detected ({why[:50]})")

    truncated = chain[:3]
    ok_, _ = verify(truncated)
    check(ok_, "a truncated chain still verifies on its own -- which is why length is checked")
    ok_, why = verify(truncated, expected_length=4)
    check(not ok_ and "truncated" in why,
          f"...and expected_length is what catches the truncation ({why[:50]})")

    # Re-chaining after an edit verifies. This is the limitation in the module docstring,
    # asserted rather than only described: the chain does not defend against an actor who
    # can recompute it, which is why the head must be anchored outside the database.
    rebuilt = ()
    for r in chain:
        rebuilt = append(rebuilt, timestamp=r.timestamp, request_id=r.request_id,
                         tenant_id=r.tenant_id, actor=r.actor, action=r.action,
                         route=r.route,
                         resource=("matter:CHANGED" if r.seq == 2 else r.resource),
                         outcome=r.outcome, http_status=r.http_status)
    ok_, _ = verify(rebuilt)
    check(ok_ and head(rebuilt) != head(chain),
          "a re-chained forgery VERIFIES -- only the head differs, so the head must be "
          "anchored outside the database or the chain proves nothing against an insider")

    # ── determinism ──────────────────────────────────────────────────────────
    check(head(row((), request_id="x")) == head(row((), request_id="x")),
          "the same event logged twice gives the same digest -- timestamp is a parameter, "
          "not a clock read, which is what makes the chain testable")
    check(head(row((), tenant_id=T1)) != head(row((), tenant_id=T2)),
          "...and a different tenant gives a different digest")

    before = chain
    row(chain)
    check(chain is before and len(chain) == 4, "append does not mutate its input")

    # ── no document or prompt text ───────────────────────────────────────────
    e = attempt(lambda: row((), resource="Is ABC Pvt Ltd a small company?\nIt has..."))
    check(isinstance(e, AuditError) and "newline" in str(e),
          "a value containing a newline is refused -- the tripwire for prompt text")
    e = attempt(lambda: row((), resource="x" * (MAX_FIELD + 1)))
    check(isinstance(e, AuditError) and str(MAX_FIELD) in str(e),
          f"a value over {MAX_FIELD} characters is refused as document text")
    check(set(_dc.asdict(chain[0])) == {
        "seq", "timestamp", "request_id", "tenant_id", "actor", "action", "route",
        "resource", "outcome", "http_status", "prev_hash", "entry_hash"},
        "the schema is fixed: there is no field a prompt could be put in")

    # ── refusals ─────────────────────────────────────────────────────────────
    e = attempt(lambda: row((), action="ATTEST"))
    check(isinstance(e, AuditError) and "human act" in str(e),
          "ATTEST is refused: an HTTP request is not a person (PLAN_18 §2.1)")
    check(isinstance(attempt(lambda: row((), tenant_id="not-a-uuid")), AuditError),
          "a tenant_id that is not a UUID is refused")
    check(isinstance(attempt(lambda: row((), timestamp="2026-09-28")), AuditError),
          "a date without a time is refused -- an audit row needs the moment")
    check(isinstance(attempt(lambda: row((), http_status=999)), AuditError),
          "a status outside 100-599 is refused")

    print(f"\n{ok}/{ok + fail} passed")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(_test())
