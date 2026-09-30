"""Append-only, bitemporal store for `ontology.Observed`. Nothing is ever rewritten.

Ring 1. PLAN_19 G1.2, built to `docs/plan19/decisions/M11_OBSERVATION_STORE.md`.

## The property this exists to provide

*"What did Themis tell this client on 31 March, and on what basis?"* — answerable years
later, because a correction is a NEW observation with a later `known_at`, never an edit.
`event_log.py`'s docstring already says `known_at` cannot answer that until a store
exists. This is that store.

## Why there is no index

The obvious design keeps a `{entity, prop} -> offsets` map so queries do not scan. That
map is the only thing in an append-only store that CAN be lost.

`RT-11` (`docs/research/RED_TEAM_OPERATION_STORE_2026_09_25.md`): `operation_store.save`
writes a whole-object snapshot, so two callers who each read the same operation and closed
a different requirement produced a file holding only the second one's work. An append-only
log has no in-place row write, so no ROW can be lost that way — but an index is a mutable
whole-file structure, and rebuilding it after two concurrent appends is RT-11 again, one
layer down.

So: **no index.** `as_of` and `history` scan the log. O(n), microseconds at beta n, and
PLAN_19 §3 already moves this to the PLAN_18 Postgres `observations` table at M4 where the
index is the database's problem and transactional. The benefit is that **no derived
structure can disagree with the log, because the log is the state** — the strongest
available form of "nothing is updated in place". If the scan is ever measurably too slow,
the honest fix is the Postgres move, not a cache; a cache re-introduces RT-11 for a speed
nobody has yet measured a need for.

A consequence worth stating, because it makes one of PLAN_19's own gate tests vacuous:
**there is no state file to move, so there is no `os.replace` here and no RT-08
log-then-state ordering to prove.** RT-08 exists because two writes can be reordered; with
one write there is no ordering. `_test` asserts the absence rather than inventing a crash
test for a code path that does not exist.

## Identity is recorded, never consulted

`actor` and `actor_kind` are stored so a reader can see who claimed what. **No function
here behaves differently according to them.** RT-10: the MCP submit tool took `actor_kind`
from its caller, an agent sent `"human"`, and it closed the terminal human-review
requirement of a live operation. *A permission is only as strong as the identity it is
granted against.* An append-only store needs no such gate, because nothing it does is
destructive.

## The guards, and the family they come from

Four defects in two days: a `hasattr` swallowing a missing API, a `.get(default)` turning
missing into plausible, a `source` check that tested non-emptiness, a fragment check that
did the same.

> **A guard that tests for PRESENCE is not a guard that tests for CONTENT.**

`ontology.Observed` already refuses `None`, a non-`STATES` evidence word and an empty
licence. Added here: a retraction reason must carry actual content (`"."` closed a
requirement three days ago), and a `known_at` in the future is refused, because a
transaction time we have not reached cannot be a time we recorded something.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path

from checker.ontology import UNKNOWN, Observed, SourceRef, Unknown, Validity
from checker.provenance import RETRACTED, STATES

__all__ = ["ObservationStoreError", "ObservationRefused", "ObsId",
           "append", "as_of", "history", "retract", "rows",
           "DEFAULT_LOG_PATH", "REASON_MIN"]

ObsId = str

_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOG_PATH = _ROOT / "corpus/.observations/log.jsonl"

# A retraction reason must be chaseable, not merely non-empty. RT-12's shape: `"."`
# satisfied a non-empty check and closed a requirement. This checks SHAPE, not truth --
# it cannot tell a real reason from a plausible invented one, and says so.
REASON_MIN = 12


class ObservationStoreError(Exception):
    """Base for what this module raises on its own behalf."""


class ObservationRefused(ObservationStoreError):
    """An append or retraction was refused, with the reason in the message."""


def _log_path(p: Path | None = None) -> Path:
    # Resolved at CALL time. A default argument binds at definition time, so
    # `p=DEFAULT_LOG_PATH` in the signature would capture the path once at import and
    # silently ignore any later reassignment -- the exact trap operation_store recorded.
    return p or DEFAULT_LOG_PATH


def _canonical(payload: dict) -> str:
    """The one serialisation. Both the id and the stored line come from this."""
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)


def _obs_id(payload: dict) -> ObsId:
    """Content-addressed, so a reader can recompute it and detect a row edited in place.

    A counter would need a mutable "next id" -- the same lost-update shape as an index.
    Collision on identical content is not a bug: the same observation appended twice IS
    the same observation.
    """
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()[:16]


def _encode(obs: Observed) -> dict:
    """`Observed` -> a plain dict. UNKNOWN is tagged, never flattened to null.

    Writing `None` for UNKNOWN would make a recorded ignorance indistinguishable from an
    absent key on the way back in -- which is the distinction `ontology.Observed` refuses
    `None` to preserve. It would be lost here if the encoder were careless.
    """
    return {
        "value": {"__unknown__": True} if isinstance(obs.value, Unknown) else obs.value,
        "source": asdict(obs.source),
        "valid": {"effective_from": obs.valid.effective_from.isoformat(),
                  "effective_to": (obs.valid.effective_to.isoformat()
                                   if obs.valid.effective_to else None)},
        "known_at": obs.known_at.isoformat(),
        "evidence": obs.evidence,
        "licence": sorted(obs.licence),
    }


def _decode(d: dict) -> Observed:
    v = d["value"]
    valid = d["valid"]
    return Observed(
        value=UNKNOWN if isinstance(v, dict) and v.get("__unknown__") else v,
        source=SourceRef(**d["source"]),
        valid=Validity(date.fromisoformat(valid["effective_from"]),
                       date.fromisoformat(valid["effective_to"])
                       if valid["effective_to"] else None),
        known_at=datetime.fromisoformat(d["known_at"]),
        evidence=d["evidence"],
        licence=frozenset(d["licence"]))


def rows(*, log_path: Path | None = None) -> tuple[dict, ...]:
    """Every line, in order. A malformed line RAISES -- it is never skipped.

    A skipped line is a silently smaller history, and every query above it would answer
    from an incomplete record while looking complete.
    """
    p = _log_path(log_path)
    if not p.exists():
        return ()
    out = []
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError as exc:
            raise ObservationStoreError(f"{p}:{i}: {exc}") from exc
    return tuple(out)


def append(obs: Observed, *, entity: str, prop: str, actor: str, actor_kind: str,
           log_path: Path | None = None, now: datetime | None = None) -> ObsId:
    """Append one observation. Returns its content-addressed id.

    `actor` and `actor_kind` are RECORDED, never consulted -- see the module docstring on
    RT-10. Appending the same observation twice returns the same id and writes a second
    line; the log is a record of what happened, and "it was observed again" is a fact.
    """
    p = _log_path(log_path)
    if not entity.strip() or not prop.strip():
        raise ObservationRefused("an observation with no entity or property cannot be "
                                 "queried, so it cannot be stored")
    if not actor.strip():
        raise ObservationRefused("an unattributed observation cannot be reviewed")
    clock = now or datetime.now(timezone.utc)
    # A transaction time we have not reached cannot be a time we recorded something.
    if obs.known_at.replace(tzinfo=None) > clock.replace(tzinfo=None):
        raise ObservationRefused(
            f"known_at {obs.known_at.isoformat()} is in the future (now "
            f"{clock.isoformat()}): a transaction time is when WE recorded a fact, and "
            "we have not got there yet")

    body = _encode(obs)
    payload = {"entity": entity, "prop": prop, "actor": actor, "actor_kind": actor_kind,
               "kind": "observed", **body}
    oid = _obs_id(payload)
    payload["obs_id"] = oid
    p.parent.mkdir(parents=True, exist_ok=True)
    # Append, flush, fsync. The ONLY write in this module.
    with p.open("a", encoding="utf-8") as f:
        f.write(_canonical(payload) + "\n")
        f.flush(); os.fsync(f.fileno())
    return oid


def retract(obs_id: ObsId, *, reason: str, actor: str, actor_kind: str,
            log_path: Path | None = None, now: datetime | None = None) -> ObsId:
    """Append a RETRACTION of `obs_id`. Nothing is deleted and nothing is rewritten.

    The retraction is itself an observation with its own `known_at`, so a query about a
    moment BEFORE it still sees the original. That is the whole point.
    """
    p = _log_path(log_path)
    if len(reason.strip()) < REASON_MIN or not any(c.isalnum() for c in reason):
        raise ObservationRefused(
            f"reason {reason.strip()!r} is too thin to audit: a retraction nobody can "
            f"explain is a retraction nobody can check. At least {REASON_MIN} characters "
            "with a word in them. This checks SHAPE, not truth -- it cannot tell a real "
            "reason from a plausible invented one")
    if not actor.strip():
        raise ObservationRefused("an unattributed retraction cannot be reviewed")
    target = [r for r in rows(log_path=p) if r.get("obs_id") == obs_id
              and r.get("kind") == "observed"]
    if not target:
        raise ObservationRefused(f"no observation {obs_id!r} to retract")
    clock = now or datetime.now(timezone.utc)
    payload = {"entity": target[-1]["entity"], "prop": target[-1]["prop"],
               "actor": actor, "actor_kind": actor_kind, "kind": "retraction",
               "retracts": obs_id, "reason": reason.strip(),
               "evidence": RETRACTED, "known_at": clock.isoformat()}
    rid = _obs_id(payload)
    payload["obs_id"] = rid
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(_canonical(payload) + "\n")
        f.flush(); os.fsync(f.fileno())
    return rid


def history(entity: str, prop: str, *, log_path: Path | None = None) -> tuple[dict, ...]:
    """Every version ever recorded, never collapsed, retractions included."""
    return tuple(r for r in rows(log_path=log_path)
                 if r.get("entity") == entity and r.get("prop") == prop)


def as_of(entity: str, prop: str, *, valid_at: date, known_at: datetime,
          log_path: Path | None = None) -> tuple[Observed, ...]:
    """What we would have said about `entity.prop` on `known_at`, for `valid_at`.

    Bitemporal, and both halves matter:

    * `known_at` -- only rows recorded AT OR BEFORE it are visible. A retraction appended
      afterwards is INVISIBLE, which is what makes an old answer reproducible rather than
      merely remembered.
    * `valid_at` -- only observations whose `Validity` covers that date.
    """
    seen = [r for r in history(entity, prop, log_path=log_path)
            if datetime.fromisoformat(r["known_at"]).replace(tzinfo=None)
            <= known_at.replace(tzinfo=None)]
    retracted = {r["retracts"] for r in seen if r.get("kind") == "retraction"}
    out = []
    for r in seen:
        if r.get("kind") != "observed" or r["obs_id"] in retracted:
            continue
        obs = _decode(r)
        if obs.valid.covers(valid_at):
            out.append(obs)
    return tuple(out)


def _test() -> None:
    import ast
    import tempfile

    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"  [ok]   {label}")
        else:
            fail += 1; print(f"  [FAIL] {label}")

    print("observation_store")

    SRC = SourceRef(source_id="T", source_title="t", source_url="https://x/y",
                    official=True, accessibility="ACCESSIBLE", retrieved_on="2026-09-26")
    T0 = datetime(2026, 3, 1, 9, 0, 0)
    T1 = datetime(2026, 3, 31, 9, 0, 0)
    T2 = datetime(2026, 9, 26, 9, 0, 0)

    def obs(value=1, known=T0, vfrom=date(2025, 12, 1), vto=None, ev="CORROBORATED"):
        return Observed(value=value, source=SRC, valid=Validity(vfrom, vto),
                        known_at=known, evidence=ev, licence=frozenset({"SERVE"}))

    # ---- GATE 1: Theorem 6 -- replay is byte-identical across a later retraction ----
    with tempfile.TemporaryDirectory() as d:
        log = Path(d) / "o.jsonl"
        oid = append(obs(), entity="CIN1", prop="paid_up_capital", actor="ns",
                     actor_kind="human", log_path=log, now=T0)
        before = as_of("CIN1", "paid_up_capital", valid_at=date(2026, 3, 31),
                       known_at=T1, log_path=log)
        check(len(before) == 1 and before[0].value == 1,
              "an appended observation is visible to a later as_of")

        retract(oid, reason="superseded by the audited figure", actor="ns",
                actor_kind="human", log_path=log, now=T2)

        after = as_of("CIN1", "paid_up_capital", valid_at=date(2026, 3, 31),
                      known_at=T1, log_path=log)
        check(after == before,
              "THEOREM 6: a query at a known_at BEFORE the retraction is BYTE-IDENTICAL "
              "afterwards -- the old answer is reproducible, not merely remembered")
        now_view = as_of("CIN1", "paid_up_capital", valid_at=date(2026, 3, 31),
                         known_at=T2, log_path=log)
        check(now_view == (),
              "...while a query at a known_at AFTER it sees the retraction and returns "
              "nothing")
        check(len(history("CIN1", "paid_up_capital", log_path=log)) == 2,
              "history never collapses: the observation AND its retraction both remain")
        check(all(r.get("obs_id") for r in rows(log_path=log)),
              "every row carries its own content-addressed id")

    # ---- GATE 2: nothing is rewritten or deleted, PROVED by an AST walk -------------
    src = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    prod = [n for n in tree.body if not (isinstance(n, ast.FunctionDef) and n.name == "_test")]
    modes, destructive = [], []
    for node in prod:
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                fn = sub.func
                name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
                if name == "open":
                    for a in list(sub.args) + [k.value for k in sub.keywords
                                               if k.arg == "mode"]:
                        if isinstance(a, ast.Constant) and isinstance(a.value, str) \
                                and any(c in a.value for c in "wx+"):
                            modes.append(a.value)
                # The RECEIVER matters. A first version of this scan flagged every
                # method called `replace`, which caught `datetime.replace(tzinfo=None)`
                # -- pure, and used twice above -- alongside `os.replace`. A scan that
                # cannot tell those apart reports a defect that is not there, and would
                # have been "fixed" by deleting a correct line.
                recv = getattr(fn.value, "id", "") if isinstance(fn, ast.Attribute) else ""
                if name in ("unlink", "rmtree", "truncate"):
                    destructive.append(name)
                elif name in ("remove", "replace", "rename") and recv in ("os", "shutil"):
                    destructive.append(f"{recv}.{name}")
    check(not modes,
          f"no production path opens a file in a truncating or updating mode ({modes})")
    check(not destructive,
          f"no production path unlinks, truncates, replaces or renames ({destructive})")

    # ---- GATE 3: the one PLAN_19 asked for, and why it is VACUOUS here --------------
    # §3 asks for a crash-injection test monkeypatching os.replace at the instant the
    # state file would move (the RT-08 proof shape). There IS no state file: the log is
    # the state, so there is no second write to order against the first. RT-08 exists
    # because two writes can be reordered; with one write there is no ordering. The
    # honest test is the ABSENCE, asserted above and named here rather than faked.
    check(not destructive and "os.replace(" not in src.split("def _test")[0],
          "RT-08 is VACUOUS here, not satisfied: there is no state file to move, so no "
          "log-then-state ordering exists to prove. Asserted as absence, not faked")

    # ---- content, not presence -------------------------------------------------------
    with tempfile.TemporaryDirectory() as d:
        log = Path(d) / "o.jsonl"
        oid = append(obs(), entity="C", prop="p", actor="ns", actor_kind="human",
                     log_path=log, now=T0)
        for thin in (".", "  ", "x", "wrong", "n/a"):
            try:
                retract(oid, reason=thin, actor="ns", actor_kind="human",
                        log_path=log, now=T2)
                check(False, f"a retraction reason {thin!r} was accepted")
                break
            except ObservationRefused:
                pass
        else:
            check(True, "a thin retraction reason is refused -- 'non-empty' is not "
                        "'auditable' (RT-12's shape)")
        try:
            append(obs(known=datetime(2030, 1, 1)), entity="C", prop="p", actor="ns",
                   actor_kind="human", log_path=log, now=T2)
            check(False, "a future known_at was accepted")
        except ObservationRefused as e:
            check("have not got there yet" in str(e),
                  "a known_at in the future is refused: a transaction time is when WE "
                  "recorded a fact")
        try:
            append(obs(), entity="", prop="p", actor="ns", actor_kind="human",
                   log_path=log, now=T0)
            check(False, "an observation with no entity was accepted")
        except ObservationRefused:
            check(True, "an observation with no entity cannot be queried, so it is refused")

        # UNKNOWN must survive the round trip as UNKNOWN, never as null.
        u = append(obs(value=UNKNOWN), entity="C", prop="q", actor="ns",
                   actor_kind="human", log_path=log, now=T0)
        back = as_of("C", "q", valid_at=date(2026, 1, 1), known_at=T1, log_path=log)
        check(len(back) == 1 and back[0].value is UNKNOWN and back[0].known is False,
              "UNKNOWN round-trips as UNKNOWN, not as null -- otherwise a recorded "
              "ignorance would come back indistinguishable from an absent key")
        check(u != oid, "different content yields a different id")
        check(_obs_id({"a": 1}) == _obs_id({"a": 1}),
              "the id is a pure function of content, so a row edited in place is detectable")

        # valid_at is enforced independently of known_at.
        append(obs(value=9, vfrom=date(2027, 1, 1)), entity="C", prop="r", actor="ns",
               actor_kind="human", log_path=log, now=T0)
        check(as_of("C", "r", valid_at=date(2026, 1, 1), known_at=T1, log_path=log) == (),
              "an observation not yet valid is invisible even though it is known")
        check(len(as_of("C", "r", valid_at=date(2027, 6, 1), known_at=T1,
                        log_path=log)) == 1,
              "...and visible once valid_at reaches it")

        # A malformed line must raise, never be skipped.
        log.write_text(log.read_text() + "{not json\n")
        try:
            rows(log_path=log)
            check(False, "a malformed line was skipped")
        except ObservationStoreError:
            check(True, "a malformed line RAISES: a skipped line is a silently smaller "
                        "history that still looks complete")

    check(RETRACTED in STATES, "RETRACTED is provenance's own state, not a new word here")

    from checker import rings
    check(rings.ring_of("checker.observation_store") == rings.RING_1,
          "this module is Ring 1")
    check(not [v for v in rings.violations() if "observation_store" in v],
          "...and introduces no ring violation")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
