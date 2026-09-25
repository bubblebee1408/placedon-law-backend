"""Persisting the Operation Model, and the one path that may close its work.

THEMIS V0 milestones 5 and 6. `checker/operations.py` builds an `Operation` in
memory and hands it back; nothing held it between calls, so
`themis.get_operation` answered every lookup with an honest `501: not
persisted yet` (`checker/mcp/tools.py:_get_operation`). This module is the
store that makes that stop being true -- and, because closing a `Requirement`
is the one place a human's judgement can be silently skipped, it is also where
evidence submission lives, with the refusal rules that make skipping it
impossible rather than merely discouraged.

## Where the durability discipline comes from

`scripts/watch_ofac.py` already paid for two FATAL findings from the 2026-09-18
Ring-2 red team (`docs/research/RED_TEAM_RING2_2026_09_18.md`), and this module
copies its fix rather than re-deriving it:

- **RT-08.** Both watchers used to advance their state file BEFORE writing the
  human-readable log line describing what changed. A kill between the two --
  an ordinary event under any process manager -- left the state pointing past
  an item the log never recorded, so the next run no longer considered it
  new and it was lost, permanently, with no trace. The fix, PROVEN in
  `watch_ofac.py`'s own `_test()`: the log entry is written and fsynced
  **first**; only then does the state file move. `save()` and
  `submit_evidence()` below follow the same order, and `_test()` proves it the
  same way RT-08 was proven -- by monkeypatching `os.replace` to fail at the
  instant the state file would move, and asserting the log already holds the
  truth.
- **RT-09.** Neither watcher's state write was atomic -- a plain
  `Path.write_text` truncates before it writes, so a crash mid-write leaves a
  fragment on disk. `_atomic_write_json` below is `write_state` from
  `watch_ofac.py` copied verbatim in shape: temp file, fsync, `os.replace`
  (atomic on POSIX -- a reader sees the old state or the new one, never a
  fragment), and the temp file is unlinked on any failure so no fragment is
  ever left beside a real state file.
- **The one lesson that predates both:** a corrupt state file is a **hard
  stop**, never a reason to start over. `checker/acquisition_log.py`'s hash
  chain, `watch_ofac.py`'s `StateCorrupt`, and PLAN_08's ring firewall all
  refuse the same shortcut ("no valid state found -> treat as first run") for
  the same reason -- it silently discards whatever was already known.
  `load()` raises `OperationCorrupt` for exactly this, and never returns
  `None` for it: `None` is reserved for the one case that actually is
  "nothing was ever saved here."

## Why evidence submission lives in the same file as the store

An `Operation` has no method that flips a `Requirement` to `SATISFIED` --
deliberately (`checker/operations.py`'s docstring: "this type has no field in
which a legal conclusion could be stored, which is the point"). The moment
persistence exists, though, *something* has to be the place a caller reaches
to actually close a requirement, and whatever that something is becomes the
one gate an agent could talk its way past into declaring work done that
nobody reviewed. Rather than leave that gate implicit -- wherever the first
caller happens to mutate a `Requirement` and call `save()` -- this module
makes it the only path: `submit_evidence()` is the sole way this codebase
flips a status to `SATISFIED`, and the two hard rules live at that one
choke point:

1. **A `BLOCKING` requirement may be closed only by a human reviewer**, naming
   themselves (`closed_by`) and a reason (`note`). An agent that attempts it
   is refused, by kind, not by a check on its name -- see `REFUSAL_AGENT_BLOCKING`
   below for the exact wording, because a refusal nobody can quote is a
   refusal nobody can be held to.
2. **Every submission, `BLOCKING` or not, must name a source.** "A fact with
   no source is the thing this whole repository refuses" is not new here --
   it is `CLAUDE.md`'s own rule, and it applies exactly as hard to a
   `Requirement` closed by an automated actor as to any other claim this
   system makes.

Both rules are enforced before anything is mutated, and both a refusal and an
acceptance are logged -- "a refused submission is logged too; a refusal
nobody can see is a refusal nobody can audit."

## What this module deliberately does NOT add

**No `close_operation()`.** `Operation.budget().can_close` already governs
whether an operation may be considered closed, computed purely from its
requirements' statuses (`checker/operations.py`), and the terminal
`HUMAN_REVIEW` requirement is the sink every other requirement depends on.
Closing every requirement does not, by itself, mean anything happened --
someone still has to close the terminal review requirement, which is itself
a `BLOCKING` requirement and therefore subject to rule 1 above. Adding a
second field or function that means "done" would let the two disagree, which
is exactly the second-notion-of-truth failure this codebase already refuses
elsewhere (`checker/mvp_freeze.py`, `checker/acquisition_log.py`'s hash
chain). `save()` persists whatever `Operation.budget()` already says; nothing
here decides closure a second time.

## Ring

Ring 2, alongside `checker.operations`: it reads operations and writes local
state under `corpus/.operations/`, never touching the statute or the
obligation register. No Ring 0 or Ring 1 decider may import it -- enforced by
`checker/rings.py`, not by convention.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from checker.operations import (BLOCKING, CRITICALITY, OPEN, SATISFIED, SPECIALISTS,
                                Operation, Requirement)

__all__ = ["OperationStoreError", "OperationCorrupt", "SubmissionRefused",
           "HUMAN", "AGENT", "ACTOR_KINDS",
           "save", "load", "list_open", "record", "submit_evidence",
           "DEFAULT_STORE_DIR", "DEFAULT_LOG_PATH"]

STATE_SCHEMA = "operation_store/v1"

# Anchored to the repository root, the same discipline `watch_ofac.py` and
# `watch_gazette.py` use and the same reason: run from anywhere but the root
# and a cwd-relative path would write state somewhere else and silently start
# over with no baseline.
_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STORE_DIR = _ROOT / "corpus/.operations"
DEFAULT_LOG_PATH = DEFAULT_STORE_DIR / "log.jsonl"

HUMAN = "human"
AGENT = "agent"
ACTOR_KINDS = (HUMAN, AGENT)

# Quoted in full in the module docstring and this repository's own commit
# history -- an agent that hits this must get the same sentence every time,
# so anyone auditing a refusal later is reading the actual reason, not a
# paraphrase of it.
REFUSAL_AGENT_BLOCKING = (
    "requirement {rid!r} is BLOCKING: it may be closed only by a human "
    "reviewer, naming themselves and a reason. An agent or other automated "
    "actor may never close a BLOCKING requirement -- attestation and final "
    "judgement in this system are human-gated, and an agent that could close "
    "the blocking work could declare an operation finished that nobody read."
)
REFUSAL_NO_SOURCE = (
    "a submission with no source is refused: a fact with no source is the "
    "thing this whole repository refuses (CLAUDE.md), and that binds an "
    "automated actor exactly as hard as any other claim this system makes."
)


class OperationStoreError(Exception):
    """Base for everything this module raises on its own behalf."""


class OperationCorrupt(OperationStoreError):
    """A state file exists but cannot be trusted. Never a reason to reset it.

    Distinct from `load()` returning `None`: `None` means "nothing was ever
    saved under this id", which is a legitimate, ordinary outcome. This
    exception means a file IS there and is wrong -- unreadable, not JSON, the
    wrong schema, missing a required field, or containing a `Requirement`/
    `Operation` that fails its own validation. A caller that could not tell
    these apart would treat "someone tampered with or half-wrote this file"
    exactly like "this operation was never created", which is the same
    silent-reset mistake `watch_ofac.StateCorrupt` and
    `checker.acquisition_log`'s hash chain both already refuse.
    """


class SubmissionRefused(OperationStoreError):
    """An evidence submission that violates one of the two hard rules.

    Always raised AFTER the refusal is logged (see `submit_evidence`), so a
    caller catching this can trust the log already has the record -- "a
    refused submission is logged too."
    """


def _now(dt: datetime | None = None) -> str:
    return (dt or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")


_SAFE_ID = re.compile(r"^[A-Za-z0-9_\-]+$")


def _validate_operation_id(operation_id: str) -> None:
    if not operation_id or not _SAFE_ID.match(operation_id):
        raise ValueError(f"{operation_id!r} is not a safe operation id "
                         "(expected non-empty, letters/digits/-/_ only)")


def _state_path(operation_id: str, *, store_dir: Path) -> Path:
    _validate_operation_id(operation_id)
    return store_dir / f"{operation_id}.json"


def _to_state(op: Operation) -> dict:
    """Everything needed to reconstruct `op`, as JSON. Built by hand rather
    than trusting `Operation.to_dict()`'s shape not to drift -- that method's
    job is a display shape for an API response (it adds a derived `budget`
    key); this module's job is round-tripping, so it lists exactly the
    dataclass fields `_from_state` reads back.
    """
    return {
        "schema": STATE_SCHEMA,
        "operation_id": op.operation_id,
        "intent": op.intent,
        "trigger": dict(op.trigger),
        "companies": list(op.companies),
        "created_at": op.created_at,
        "what_this_is_not": op.what_this_is_not,
        "requirements": [dict(r.__dict__, depends_on=list(r.depends_on))
                         for r in op.requirements],
    }


def _requirement_from_state(d: dict) -> Requirement:
    return Requirement(
        requirement_id=d["requirement_id"], question=d["question"],
        obligation_id=d["obligation_id"], provision=d["provision"],
        specialist=d["specialist"], criticality=d["criticality"],
        minimum_evidence=d["minimum_evidence"],
        depends_on=tuple(d.get("depends_on") or ()),
        status=d.get("status", OPEN), note=d.get("note", ""),
    )


def _from_state(d: dict) -> Operation:
    reqs = tuple(_requirement_from_state(r) for r in d["requirements"])
    kwargs = dict(operation_id=d["operation_id"], intent=d["intent"],
                 trigger=dict(d["trigger"]), requirements=reqs,
                 created_at=d["created_at"], companies=tuple(d.get("companies") or ()))
    if "what_this_is_not" in d:
        kwargs["what_this_is_not"] = d["what_this_is_not"]
    return Operation(**kwargs)


def _atomic_write_json(path: Path, payload: dict) -> None:
    """Write `payload` to `path` ATOMICALLY: temp file, fsync, `os.replace`.

    RT-09. `os.replace` is atomic on POSIX, so any reader sees the old file or
    the new one, never a fragment. On any failure the temp file is removed --
    no half-written file is ever left beside a real one, waiting to be mistaken
    for it.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    body = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    try:
        with tmp.open("w", encoding="utf-8") as f:
            f.write(body); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


# A default argument binds at DEFINITION time, so `store_dir=DEFAULT_STORE_DIR` in a
# signature captures the path once, at import, and reassigning the module constant
# afterwards changes nothing. That silently defeats any caller trying to redirect the
# store -- a test, or a future per-tenant store. Found 2026-09-25 when a tool test
# pointed the store at a temp directory and the tool kept reading the real one.
# Resolving here, at call time, is the fix.
def _store_dir(p: "Path | None") -> "Path":
    return DEFAULT_STORE_DIR if p is None else p


def _log_path(p: "Path | None") -> "Path":
    return DEFAULT_LOG_PATH if p is None else p


def record(event: dict, *, log_path: Path | None = None,
          now: datetime | None = None) -> None:
    """Append one event to the operation log. FLUSHED AND FSYNCED before
    returning.

    RT-08: this is what makes "log before state" a real ordering guarantee
    rather than an ordering of two buffered writes the OS is free to
    reorder or lose independently. Every caller in this module that changes
    persisted state calls this FIRST, and does not catch what it raises --
    if the log write itself fails, nothing downstream may proceed as if the
    event were recorded, because it was not.
    """
    log_path = _log_path(log_path)
    payload = dict(event)
    payload.setdefault("at", _now(now))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str) + "\n")
        f.flush(); os.fsync(f.fileno())


def save(op: Operation, *, store_dir: Path | None = None,
        log_path: Path | None = None, now: datetime | None = None) -> None:
    """Persist `op`. Log first (RT-08), then an atomic state write (RT-09).

    A crash between the two calls below leaves the log holding a true record
    of the save that was attempted, even if the state file itself never
    moved -- see `_test`'s RT-08 case, which proves this by making
    `os.replace` fail at exactly that instant.
    """
    store_dir = _store_dir(store_dir)
    log_path = _log_path(log_path)
    b = op.budget()
    record({"event": "operation_saved", "operation_id": op.operation_id,
            "requirements": b.total, "satisfied": b.satisfied,
            "blocking_open": list(b.blocking_open), "can_close": b.can_close},
           log_path=log_path, now=now)
    _atomic_write_json(_state_path(op.operation_id, store_dir=store_dir), _to_state(op))


def load(operation_id: str, *, store_dir: Path | None = None) -> Operation | None:
    """The persisted `Operation`, or `None` if nothing was ever saved under
    this id.

    `None` and `OperationCorrupt` are deliberately different types for
    deliberately different situations -- see `OperationCorrupt`'s docstring.
    A caller that wants "does this operation exist" MUST be able to tell
    "no" from "I can't tell, and neither should you until a person looks."
    """
    store_dir = _store_dir(store_dir)
    path = _state_path(operation_id, store_dir=store_dir)
    if not path.exists():
        return None
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        raise OperationCorrupt(f"{path}: could not read ({e})") from e
    try:
        state = json.loads(raw)
    except json.JSONDecodeError as e:
        raise OperationCorrupt(f"{path}: not valid JSON ({e})") from e
    if not isinstance(state, dict) or state.get("schema") != STATE_SCHEMA:
        got = state.get("schema") if isinstance(state, dict) else type(state).__name__
        raise OperationCorrupt(f"{path}: unknown schema {got!r}; expected {STATE_SCHEMA!r}")
    required = ("operation_id", "intent", "trigger", "requirements", "created_at")
    missing = [k for k in required if k not in state]
    if missing:
        raise OperationCorrupt(f"{path}: missing required field(s) {missing}")
    try:
        return _from_state(state)
    except (KeyError, TypeError, ValueError) as e:
        raise OperationCorrupt(f"{path}: state does not reconstruct a valid "
                              f"Operation ({e})") from e


def list_open(*, store_dir: Path | None = None) -> tuple[Operation, ...]:
    """Every persisted operation that cannot yet close.

    "Open" is not a second notion invented here -- it IS
    `Operation.budget().can_close` being `False`, the same governance
    `checker.operations` already defines. A corrupt file among the good ones
    is NOT skipped: `load()` raises, and this function does not catch it,
    because an unreadable store is not an empty store, and a caller getting
    a short list back has no way to tell "everything else is closed" from
    "one operation is sitting there unreadable."
    """
    store_dir = _store_dir(store_dir)
    if not store_dir.is_dir():
        return ()
    out: list[Operation] = []
    for path in sorted(store_dir.glob("*.json")):
        op = load(path.stem, store_dir=store_dir)
        if op is not None and not op.budget().can_close:
            out.append(op)
    return tuple(out)


def submit_evidence(op: Operation, *, requirement_id: str, actor: str, actor_kind: str,
                    source: str = "", note: str = "", closed_by: str = "",
                    store_dir: Path | None = None,
                    log_path: Path | None = None,
                    now: datetime | None = None) -> Operation:
    """Move ONE `Requirement` on `op` from OPEN to SATISFIED -- the only path
    in this codebase that does so.

    `actor_kind` is `HUMAN` or `AGENT`. Two rules, checked before anything is
    mutated, and both a refusal and an acceptance are logged either way:

    1. A `BLOCKING` requirement may be closed only by `actor_kind == HUMAN`,
       naming a reviewer (`closed_by`) and a reason (`note`). An agent is
       refused with `REFUSAL_AGENT_BLOCKING`, not a generic error -- the
       reason names why, every time, in the same words.
    2. Every submission, whatever its criticality, must name a `source`. No
       source, no submission -- `REFUSAL_NO_SOURCE`.

    Returns the new `Operation` (already persisted via `save()`) on success;
    raises `SubmissionRefused` on refusal. The operation passed in is never
    mutated -- `Requirement` and `Operation` are frozen dataclasses, so the
    return value is a distinct object, exactly like `operations.py`'s own
    `_test()` already relies on (`Operation(**{**op.__dict__, ...})`).
    """
    store_dir = _store_dir(store_dir)
    log_path = _log_path(log_path)
    if actor_kind not in ACTOR_KINDS:
        raise ValueError(f"{actor_kind!r} is not an actor kind; one of {ACTOR_KINDS}")
    if not actor.strip():
        raise ValueError("a submission with no actor is not a submission -- "
                         "an unattributed close cannot be reviewed")

    target = next((r for r in op.requirements if r.requirement_id == requirement_id), None)

    def refuse(reason: str) -> None:
        record({"event": "evidence_refused", "operation_id": op.operation_id,
                "requirement_id": requirement_id, "actor": actor, "actor_kind": actor_kind,
                "source": source, "closed_by": closed_by, "note": note, "reason": reason},
               log_path=log_path, now=now)
        raise SubmissionRefused(reason)

    if target is None:
        refuse(f"no requirement {requirement_id!r} on operation {op.operation_id!r}")
    if target.status == SATISFIED:
        refuse(f"requirement {requirement_id!r} is already SATISFIED -- resubmitting "
              "would overwrite a prior closure with no record of what changed")
    if not source.strip():
        refuse(REFUSAL_NO_SOURCE)
    if target.criticality == BLOCKING:
        if actor_kind != HUMAN:
            refuse(REFUSAL_AGENT_BLOCKING.format(rid=requirement_id))
        if not closed_by.strip():
            refuse(f"requirement {requirement_id!r} is BLOCKING: a human reviewer must "
                  "name themselves (closed_by) to close it")
        if not note.strip():
            refuse(f"requirement {requirement_id!r} is BLOCKING: a human reviewer must "
                  "carry a reason (note) to close it")

    new_reqs = tuple(
        Requirement(**{**r.__dict__, "status": SATISFIED})
        if r.requirement_id == requirement_id else r
        for r in op.requirements
    )
    new_op = Operation(**{**op.__dict__, "requirements": new_reqs})

    record({"event": "evidence_accepted", "operation_id": op.operation_id,
            "requirement_id": requirement_id, "actor": actor, "actor_kind": actor_kind,
            "criticality": target.criticality, "source": source, "closed_by": closed_by,
            "note": note}, log_path=log_path, now=now)
    save(new_op, store_dir=store_dir, log_path=log_path, now=now)
    return new_op


def _test() -> None:
    import tempfile

    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    print("operation_store")

    from checker.operations import Watchlist, operation_for_instrument

    trigger = {"gazette_id": "CG-DL-E-01122025-268124", "ministry": "Ministry of Corporate Affairs"}
    wl = Watchlist(); wl.add("U72200KA2019PTC123456", "Acme Holdings Private Limited")

    def fresh_op(nonce: str = "") -> Operation:
        # operation_for_instrument's id is a hash of instrument+trigger+companies (see
        # checker/operations.py) -- deterministic on purpose, but that means calling it
        # twice with identical arguments returns the SAME operation_id. Tests that need
        # a genuinely distinct operation (e.g. one whose save deliberately fails) pass a
        # nonce so the two are not accidentally the same file on disk.
        t = dict(trigger, nonce=nonce) if nonce else trigger
        return operation_for_instrument("880", trigger=t, watchlist=wl)

    def last_event(name: str, *, log_path: Path) -> dict:
        """The most recent log line with `event == name`. `save()` always appends
        its own 'operation_saved' line after `submit_evidence`'s own event, so the
        LAST line in the file is not necessarily the one a caller just logged --
        this searches backward for the one that is."""
        for line in reversed(log_path.read_text().splitlines()):
            rec = json.loads(line)
            if rec.get("event") == name:
                return rec
        raise AssertionError(f"no log line with event={name!r}")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        store_dir, log_path = root / "store", root / "store" / "log.jsonl"

        # ---- load() of an id never saved: None, a legitimate first-run answer ----
        check(load("op_never_saved", store_dir=store_dir) is None,
              "load() of an unsaved id returns None")

        # ---- save() then load(): a full round trip ------------------------------
        op = fresh_op()
        save(op, store_dir=store_dir, log_path=log_path)
        check((store_dir / f"{op.operation_id}.json").is_file(),
              "save() writes one JSON file named by operation_id")
        back = load(op.operation_id, store_dir=store_dir)
        check(back is not None, "load() finds what save() wrote")
        check(back.operation_id == op.operation_id and back.intent == op.intent,
              "...with the same identity and intent")
        check(len(back.requirements) == len(op.requirements),
              "...and every requirement survives the round trip")
        check(all(a.__dict__ == b.__dict__ for a, b in zip(op.requirements, back.requirements)),
              "...field-for-field, not just in count")
        check(back.budget().can_close == op.budget().can_close,
              "...and the budget recomputes the same verdict")
        check(log_path.is_file() and len(log_path.read_text().splitlines()) >= 1,
              "save() appends a log line")
        first_log = json.loads(log_path.read_text().splitlines()[0])
        check(first_log["event"] == "operation_saved" and first_log["operation_id"] == op.operation_id,
              "...naming the event and the operation")

        # ---- no .tmp fragment survives an ordinary save --------------------------
        check(not any(p.suffix == ".tmp" for p in store_dir.glob("*.tmp")),
              "an ordinary save leaves no .tmp fragment behind")

        # ---- RT-09: the temp file is removed on a failed replace -----------------
        orig_replace = os.replace
        op2 = fresh_op(nonce="rt09-rt08-probe")
        check(op2.operation_id != op.operation_id,
              "the fixture used for the crash tests is a genuinely different operation")

        def boom_replace(*_a, **_kw):
            raise OSError("simulated crash: disk full at the instant of replace")

        os.replace = boom_replace
        try:
            try:
                save(op2, store_dir=store_dir, log_path=log_path)
                check(False, "a failing os.replace must propagate, not be swallowed")
            except OSError:
                check(True, "save() propagates the OSError from a failed os.replace")
        finally:
            os.replace = orig_replace
        check(not list(store_dir.glob(f"{op2.operation_id}.json.tmp")),
              "RT-09: the temp file is unlinked, not left as a fragment beside a real state")
        check(not (store_dir / f"{op2.operation_id}.json").exists(),
              "...and no state file was ever created for the operation that failed to save")

        # ---- RT-08: the log already holds the truth even though state never moved
        log_lines_before = log_path.read_text().splitlines()
        check(json.loads(log_lines_before[-1])["operation_id"] == op2.operation_id,
              "RT-08: the log entry for the failed save is present -- it was written "
              "and fsynced BEFORE os.replace ever ran, so the crash lost nothing about "
              "what was attempted, even though the state file itself was never written")

        # ---- a corrupt state file STOPS, never silently resets -------------------
        garbage_id = "op_garbage"
        (store_dir / f"{garbage_id}.json").write_text("{ not json at all", encoding="utf-8")
        try:
            load(garbage_id, store_dir=store_dir)
            check(False, "unparseable JSON must raise OperationCorrupt, not return None")
        except OperationCorrupt as e:
            check("not valid JSON" in str(e), f"...and says why: {e}")

        wrong_schema_id = "op_wrongschema"
        (store_dir / f"{wrong_schema_id}.json").write_text(
            json.dumps({"schema": "something/v0"}), encoding="utf-8")
        try:
            load(wrong_schema_id, store_dir=store_dir)
            check(False, "a wrong schema must raise OperationCorrupt")
        except OperationCorrupt as e:
            check("schema" in str(e), f"...and it does: {e}")

        incomplete_id = "op_incomplete"
        (store_dir / f"{incomplete_id}.json").write_text(
            json.dumps({"schema": STATE_SCHEMA, "operation_id": incomplete_id}),
            encoding="utf-8")
        try:
            load(incomplete_id, store_dir=store_dir)
            check(False, "a state file missing required fields must raise OperationCorrupt")
        except OperationCorrupt as e:
            check("missing required field" in str(e), f"...and it does: {e}")

        bad_requirement_id = "op_badreq"
        bad_state = _to_state(op)
        bad_state["operation_id"] = bad_requirement_id
        bad_state["requirements"][0]["criticality"] = "URGENT!!"   # not a real criticality
        (store_dir / f"{bad_requirement_id}.json").write_text(json.dumps(bad_state), encoding="utf-8")
        try:
            load(bad_requirement_id, store_dir=store_dir)
            check(False, "a Requirement that fails its own validation must raise OperationCorrupt")
        except OperationCorrupt as e:
            check("does not reconstruct" in str(e), f"...and it does: {e}")

        check(load(op.operation_id, store_dir=store_dir) is not None,
              "None vs OperationCorrupt are genuinely distinct outcomes, proven side by "
              "side: the real operation still loads fine while the garbage ones raise")

        # ---- list_open(): an unreadable store is not an empty store --------------
        try:
            list_open(store_dir=store_dir)
            check(False, "list_open() must propagate a corrupt file, not skip it silently")
        except OperationCorrupt:
            check(True, "list_open() refuses to report a short list past a corrupt entry")

        for gid in (garbage_id, wrong_schema_id, incomplete_id, bad_requirement_id):
            (store_dir / f"{gid}.json").unlink()

        opened = list_open(store_dir=store_dir)
        check(op.operation_id in {o.operation_id for o in opened},
              "a fresh, unsatisfied operation is reported as open")
        check(op2.operation_id not in {o.operation_id for o in opened},
              "an operation that failed to save is not reported at all")

        closed_all = tuple(Requirement(**{**r.__dict__, "status": SATISFIED}) for r in op.requirements)
        save(Operation(**{**op.__dict__, "requirements": closed_all}),
             store_dir=store_dir, log_path=log_path)
        opened_after = {o.operation_id for o in list_open(store_dir=store_dir)}
        check(op.operation_id not in opened_after,
              "an operation with every requirement satisfied is no longer 'open'")
        check(not any("closed" in k for state_path in store_dir.glob(f"{op.operation_id}.json")
                     for k in json.loads(state_path.read_text())),
              "the persisted state has no second 'closed'/'done' field -- can_close, "
              "recomputed from requirement status, is the only notion of closure")

        # ---- operation id path safety ---------------------------------------------
        for bad_id in ("../escape", "a/b", "", "  "):
            try:
                load(bad_id, store_dir=store_dir)
                check(False, f"a load() of unsafe id {bad_id!r} must raise")
            except ValueError:
                check(True, f"an unsafe operation id {bad_id!r} is refused before touching disk")

        # ---- record(): the generic append primitive -------------------------------
        record({"event": "probe", "detail": "hello"}, log_path=log_path)
        last = json.loads(log_path.read_text().splitlines()[-1])
        check(last["event"] == "probe" and "at" in last,
              "record() appends an arbitrary event and stamps a timestamp if none given")

    # ==== MOVE 6: evidence submission ==========================================
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        store_dir, log_path = root / "store", root / "store" / "log.jsonl"
        op = fresh_op()
        save(op, store_dir=store_dir, log_path=log_path)

        blocking = next(r for r in op.requirements if r.criticality == BLOCKING)
        important = next((r for r in op.requirements if r.criticality != BLOCKING), None)
        check(important is not None, "the fixture operation has a non-blocking requirement to test")

        # ---- rule 1: an agent may never close a BLOCKING requirement -------------
        try:
            submit_evidence(op, requirement_id=blocking.requirement_id, actor="research_agent",
                            actor_kind=AGENT, source="India Code REST API",
                            store_dir=store_dir, log_path=log_path)
            check(False, "an agent closing a BLOCKING requirement must be refused")
        except SubmissionRefused as e:
            check("may be closed only by a human reviewer" in str(e), f"...and says why: {e}")
            check("agent" in str(e).lower() and "never" in str(e).lower(),
                  "...naming, specifically, that an agent may never do this")
        refusal_log = json.loads(log_path.read_text().splitlines()[-1])
        check(refusal_log["event"] == "evidence_refused" and refusal_log["actor_kind"] == AGENT,
              "the refused attempt is logged, naming who attempted it and how")
        reloaded = load(op.operation_id, store_dir=store_dir)
        still_open = next(r for r in reloaded.requirements if r.requirement_id == blocking.requirement_id)
        check(still_open.status == OPEN,
              "a refused submission never mutates the stored operation")

        # ---- a submission with no source is refused, whatever the criticality ----
        try:
            submit_evidence(op, requirement_id=important.requirement_id, actor="research_agent",
                            actor_kind=AGENT, source="", store_dir=store_dir, log_path=log_path)
            check(False, "a submission with no source must be refused")
        except SubmissionRefused as e:
            check("no source is refused" in str(e), f"...and says why: {e}")
        no_source_log = json.loads(log_path.read_text().splitlines()[-1])
        check(no_source_log["event"] == "evidence_refused" and no_source_log["source"] == "",
              "a sourceless refusal is logged too, with the empty source visible")

        # ---- an agent MAY satisfy a non-blocking requirement, with a named source
        updated = submit_evidence(op, requirement_id=important.requirement_id, actor="corporate_data_agent",
                                  actor_kind=AGENT, source="MCA-21 filing, SRN A12345678",
                                  store_dir=store_dir, log_path=log_path)
        got = next(r for r in updated.requirements if r.requirement_id == important.requirement_id)
        check(got.status == SATISFIED, "a sourced agent submission on a non-blocking requirement is accepted")
        accepted_log = last_event("evidence_accepted", log_path=log_path)
        check(accepted_log["actor_kind"] == AGENT
              and accepted_log["source"] == "MCA-21 filing, SRN A12345678",
              "the acceptance is logged with who, what, and the source")
        check(load(op.operation_id, store_dir=store_dir).requirements ==
              updated.requirements, "the acceptance was actually persisted")

        # ---- resubmitting an already-satisfied requirement is refused ------------
        try:
            submit_evidence(updated, requirement_id=important.requirement_id, actor="another_agent",
                            actor_kind=AGENT, source="a different source",
                            store_dir=store_dir, log_path=log_path)
            check(False, "resubmitting a SATISFIED requirement must be refused")
        except SubmissionRefused as e:
            check("already SATISFIED" in str(e), f"...and says why: {e}")

        # ---- an unknown requirement id is refused, not silently ignored ----------
        try:
            submit_evidence(updated, requirement_id="r_does_not_exist", actor="someone",
                            actor_kind=AGENT, source="x", store_dir=store_dir, log_path=log_path)
            check(False, "an unknown requirement id must be refused")
        except SubmissionRefused as e:
            check("no requirement" in str(e), f"...and says why: {e}")

        # ---- rule 1, positive case: a human reviewer with name+reason succeeds ---
        try:
            submit_evidence(updated, requirement_id=blocking.requirement_id, actor="reviewer",
                            actor_kind=HUMAN, source="the Gazette PDF itself, read and hashed",
                            store_dir=store_dir, log_path=log_path)
            check(False, "a human closing BLOCKING with no closed_by must still be refused")
        except SubmissionRefused as e:
            check("name themselves" in str(e) or "closed_by" in str(e), f"...and says why: {e}")

        try:
            submit_evidence(updated, requirement_id=blocking.requirement_id, actor="reviewer",
                            actor_kind=HUMAN, source="the Gazette PDF itself, read and hashed",
                            closed_by="Nishant Singh", note="",
                            store_dir=store_dir, log_path=log_path)
            check(False, "a human closing BLOCKING with no reason (note) must still be refused")
        except SubmissionRefused as e:
            check("carry a reason" in str(e) or "note" in str(e), f"...and says why: {e}")

        final = submit_evidence(updated, requirement_id=blocking.requirement_id, actor="reviewer",
                                actor_kind=HUMAN, source="the Gazette PDF itself, read and hashed",
                                closed_by="Nishant Singh",
                                note="Confirmed G.S.R. 880(E) changes the paid-up capital threshold "
                                     "effective 15-Sep-2025; text matches the register.",
                                store_dir=store_dir, log_path=log_path)
        won = next(r for r in final.requirements if r.requirement_id == blocking.requirement_id)
        check(won.status == SATISFIED, "a named human reviewer, with a reason and a source, can "
                                       "close a BLOCKING requirement")
        human_log = last_event("evidence_accepted", log_path=log_path)
        check(human_log["closed_by"] == "Nishant Singh" and human_log["actor_kind"] == HUMAN,
              "the human closure is logged with who closed it, not just who submitted it")

        # ---- closing every requirement does NOT itself close the operation -------
        remaining = final
        for r in remaining.requirements:
            if r.status == SATISFIED:
                continue
            kind = HUMAN if r.criticality == BLOCKING else AGENT
            kw = dict(closed_by="Nishant Singh", note="closing out the fixture") if kind == HUMAN else {}
            remaining = submit_evidence(remaining, requirement_id=r.requirement_id,
                                        actor="reviewer" if kind == HUMAN else "sweep_agent",
                                        actor_kind=kind, source="fixture evidence",
                                        store_dir=store_dir, log_path=log_path, **kw)
        check(remaining.budget().can_close, "with every requirement satisfied, budget().can_close "
                                            "is True -- computed, not stored")
        check(not hasattr(remaining, "closed") and not hasattr(remaining, "status"),
              "Operation itself carries no separate 'closed' flag this module could have set")
        persisted_state = json.loads((store_dir / f"{remaining.operation_id}.json").read_text())
        check("closed" not in persisted_state and "status" not in persisted_state,
              "the persisted state invents no second notion of done either")

        # ---- an unattributed submission is refused before anything is checked ----
        try:
            submit_evidence(op, requirement_id=important.requirement_id, actor="  ",
                            actor_kind=AGENT, source="x", store_dir=store_dir, log_path=log_path)
            check(False, "a submission with no actor must raise")
        except ValueError:
            check(True, "an unattributed submission raises before any refusal logic runs")

        try:
            submit_evidence(op, requirement_id=important.requirement_id, actor="x",
                            actor_kind="ROBOT", source="y", store_dir=store_dir, log_path=log_path)
            check(False, "an unknown actor_kind must raise")
        except ValueError:
            check(True, "an unknown actor_kind raises rather than silently defaulting")

    # ---- CRITICALITY/SPECIALISTS sanity, so this file notices if operations.py
    #      ever adds a new criticality this module's rules do not yet cover -----
    check(BLOCKING in CRITICALITY, "BLOCKING is a real criticality this module keys off of")
    check("HUMAN_REVIEW" in SPECIALISTS,
          "the specialist vocabulary is imported from operations.py, not redefined here")

    # ---- the ring boundary -----------------------------------------------------
    from checker import rings
    check(rings.ring_of("checker.operation_store") == rings.RING_2, "this module is Ring 2")
    check(not [v for v in rings.violations() if "operation_store" in v],
          "no Ring 0 or Ring 1 module imports it")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
