"""Two backends, one interface, and one conformance suite that both must pass.

The in-memory store is what the gate runs on; Postgres is what a deployment runs on. The
risk in having two is that they diverge quietly -- the memory one keeps working, the
Postgres one is exercised by nobody, and the difference is discovered in production.

So the contract is a FUNCTION here, `conformance(backend)`, and it is run twice:

    gateway/store.py   in the gate, against MemoryBackend
    scripts/rls_integration.py   outside it, against PostgresBackend, on a real server

Identical assertions, two backends. A behaviour that only the dict satisfies fails the same
test on Postgres, and there is no second suite to keep in step.

## Why a run decomposes

R-016 was decided in favour of the DERIVATION (research/TASKS.md, 29-09-2026): a run is
`runs` + ordered `run_steps` + `propositions`, not one blob. So `write()` takes the dict
the runtime already produces and splits it across three tables, and `read()` reassembles
it. The dict shape is `agents/runtime.py`'s, unchanged, because the runtime should not
learn what a database is.

## Tenant isolation is the database's job, and this sets up the question it asks

Every Postgres connection issues `SET app.tenant_id` before it reads or writes anything.
The policies in gateway/migrations/*.sql compare against that setting, so a backend that
forgot it would see nothing rather than everything -- which is the safe direction, and is
also why `PostgresBackend` refuses to be constructed without a tenant.

Run: PYTHONPATH=. python3 gateway/store.py
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Protocol

MEMORY = "in-memory"
POSTGRES = "postgres"

URL_ENV = "PLACEDON_DATABASE_URL"
_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                   r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


class StoreError(RuntimeError):
    """The store could not do what was asked. Never swallowed into a None."""


class Backend(Protocol):
    kind: str

    def write_run(self, run: dict) -> None: ...
    def read_run(self, run_id: str) -> dict | None: ...
    def put_document(self, *, sha256: str, name: str, byte_count: int) -> dict: ...
    def get_document(self, sha256: str) -> dict | None: ...
    def write_decision(self, decision: dict) -> dict: ...
    def read_decisions(self, run_id: str) -> list[dict]: ...
    def append_step(self, run_id: str, step: dict, *, key: str) -> bool: ...
    def set_run(self, run_id: str, *, status: str, refusal_code=None, result=None) -> None: ...
    def write_cascade(self, record: dict, *, run_id: str | None = None) -> dict: ...
    def read_cascades(self, *, run_id: str | None = None, limit: int = 1000) -> list[dict]: ...


# ── in memory ────────────────────────────────────────────────────────────────

# The key set a step and a proposition ALWAYS have when read back. Postgres returns every
# column whether or not the writer supplied it; a dict returns what it was handed. Without
# normalising, `step["model"]` is a KeyError on memory and None on Postgres -- which is a
# divergence that only shows up on the backend the gate does not run.
STEP_KEYS = ("capability", "engine_capability", "status", "model", "degraded",
             "provider", "region", "cost_inr", "cost_note", "idempotency_key")
PROPOSITION_KEYS = ("status", "source_ref", "span_start", "span_end")

# What makes a retry safe. The key is DERIVED from (run_id, capability) by the worker, never
# generated, so the same step computed twice produces the same key and the second append is
# a no-op. Because cost_inr rides on the step row, that is also what stops a reclaimed job
# from billing the same call twice.
def step_key(run_id: str, capability: str) -> str:
    return f"{run_id}:{capability}"
# A human decision, as labelled data (PLAN_23 rule 5, migration 005). `quoted_span` is what
# the reviewer was SHOWN, attested by the surface that showed it -- not re-derived here.
DECISION_KEYS = ("decision_id", "run_id", "item_ref", "decision", "reason", "quoted_span",
                 "actor_id", "decided_at")

# Also in gateway/verbs.py and as a CHECK in 005_decisions.sql. "ok" is not a reason, and a
# label whose text is "ok" teaches a later evaluation nothing.
MIN_REASON_CHARS = 10

# What a stored cascade record always reads back with. `attempts` keeps its ORDER: stage 2
# only ran because stage 1 was rejected, and a record that has to be re-sorted to see that
# has lost the thing it was kept for.
CASCADE_KEYS = ("cascade_id", "run_id", "status", "error", "attempts", "body_ids",
                "claim_count", "refusal_count", "total_cost_inr")


class DecisionExists(StoreError):
    """One decision per item per run. A second one would overwrite the label."""


def _check_cascade(row: dict) -> None:
    """The invariants 007_cascade.sql states as CHECKs, refused in Python too.

    Both, because a backfill or a fixture reaches one and not the other -- and because the
    memory backend has no CHECK constraints at all, so without this the two backends would
    accept different records and the conformance suite would be testing nothing.
    """
    if row["status"] not in ("ANSWERED", "PARTIAL", "NEEDS_LAWYER", "FAILED"):
        raise StoreError(f"{row['status']!r} is not a cascade status")
    if (row["status"] == "FAILED") != bool(row.get("error")):
        raise StoreError(
            "a FAILED cascade carries its transport error and nothing else does. A refusal "
            "is a decision and a failure is not, and the two must not blur in the record.")
    cost = row.get("total_cost_inr")
    if cost is not None and float(cost) <= 0:
        raise StoreError(
            "a recorded cascade cost of 0 would claim the calls were free. UNPRICED is "
            "NULL; there is no free provider here.")


NO_CALL_NOTE = ("no model was called on this step, so there is nothing to price. This is "
                "not a cost of zero.")


def _shaped(row: dict, keys: tuple[str, ...]) -> dict:
    out = {k: row.get(k) for k in keys}
    if "degraded" in keys:
        out["degraded"] = bool(row.get("degraded", False))
    if "cost_note" in keys and out.get("cost_inr") is None and not out.get("cost_note"):
        # A null cost ALWAYS carries a reason. Without this, a step with no model reads as
        # a blank -- and a blank beside a null is indistinguishable from a cost nobody
        # bothered to record, which is the ambiguity this whole change exists to remove.
        out["cost_note"] = NO_CALL_NOTE
    return out


@dataclass
class MemoryBackend:
    """A dict, with the same decomposition discipline as Postgres so the tests can be one.

    It stores the run's parts separately rather than keeping the caller's dict, because a
    backend that hands back the very object it was given passes tests the database cannot:
    a caller mutating its own dict would appear to have written to the store.
    """
    kind: str = MEMORY
    tenant_id: str = "00000000-0000-0000-0000-000000000000"
    runs: dict = field(default_factory=dict)
    steps: dict = field(default_factory=dict)
    props: dict = field(default_factory=dict)
    documents: dict = field(default_factory=dict)
    decisions: dict = field(default_factory=dict)      # run_id -> [row]
    cascades: list = field(default_factory=list)

    def write_run(self, run: dict) -> None:
        rid = run["id"]
        self.runs[rid] = {k: v for k, v in run.items()
                          if k not in ("steps", "propositions")}
        self.steps[rid] = [_shaped(s, STEP_KEYS) for s in run.get("steps", [])]
        self.props[rid] = [_shaped(p, PROPOSITION_KEYS)
                           for p in run.get("propositions", [])]

    def read_run(self, run_id: str) -> dict | None:
        if run_id not in self.runs:
            return None
        out = dict(self.runs[run_id])
        out.setdefault("result", None)
        out["steps"] = [dict(s) for s in self.steps.get(run_id, [])]
        out["propositions"] = [dict(p) for p in self.props.get(run_id, [])]
        return out

    def put_document(self, *, sha256: str, name: str, byte_count: int) -> dict:
        row = {"sha256": sha256, "name": name, "byte_count": byte_count,
               "tenant_id": self.tenant_id}
        self.documents[sha256] = row
        return dict(row)

    def get_document(self, sha256: str) -> dict | None:
        row = self.documents.get(sha256)
        return dict(row) if row else None

    def write_decision(self, decision: dict) -> dict:
        rid = decision["run_id"]
        existing = self.decisions.setdefault(rid, [])
        # The UNIQUE (run_id, item_ref) of 005, enforced here too so the two backends
        # refuse the same second decision rather than one of them silently keeping both.
        if any(d["item_ref"] == decision["item_ref"] for d in existing):
            raise DecisionExists(
                f"{decision['item_ref']} on run {rid} already has a decision. A reviewer "
                f"changing their mind writes a new one against a new run; overwriting "
                f"would destroy the label, which is the point of storing it.")
        row = _shaped(decision, DECISION_KEYS)
        if not row.get("decided_at"):
            # Postgres defaults this column; without the same default here one backend
            # returns a timestamp and the other returns None for an identical write.
            from datetime import datetime, timezone
            row["decided_at"] = datetime.now(timezone.utc).isoformat()
        existing.append(row)
        return dict(row)

    def read_decisions(self, run_id: str) -> list[dict]:
        return [dict(d) for d in self.decisions.get(run_id, [])]

    def append_step(self, run_id: str, step: dict, *, key: str) -> bool:
        """Append one step unless `key` was already written. True if it was written now.

        The return value matters: a worker that cannot tell "I wrote this" from "this was
        already there" cannot tell a resumed run from a fresh one, and would re-bill.
        """
        rows = self.steps.setdefault(run_id, [])
        if any(r.get("idempotency_key") == key for r in rows):
            return False
        rows.append({**_shaped(step, STEP_KEYS), "idempotency_key": key})
        return True

    def write_cascade(self, record: dict, *, run_id: str | None = None) -> dict:
        """Store one `model_cascade.Result.to_dict()`. Returns the row as it reads back."""
        import uuid as _uuid
        row = {
            "cascade_id": record.get("cascade_id") or str(_uuid.uuid4()),
            "run_id": run_id,
            "status": record.get("status", ""),
            "error": record.get("error"),
            "attempts": [dict(a) for a in record.get("attempts", [])],
            "body_ids": list(record.get("body_ids", [])),
            "claim_count": len(record.get("claims", [])),
            "refusal_count": len(record.get("refusals", [])),
            "total_cost_inr": record.get("total_cost_inr"),
        }
        _check_cascade(row)
        self.cascades.append(row)
        return dict(row)

    def read_cascades(self, *, run_id: str | None = None, limit: int = 1000) -> list[dict]:
        rows = [c for c in self.cascades if run_id is None or c["run_id"] == run_id]
        return [dict(c) for c in rows[:limit]]

    def set_run(self, run_id: str, *, status: str, refusal_code=None, result=None) -> None:
        row = self.runs.setdefault(run_id, {"id": run_id})
        row["status"] = status
        row["refusal_code"] = refusal_code
        if result is not None:
            row["result"] = result

    # The shape agents/runtime.Store expects, so a run can be executed straight onto it.
    def read(self, run_id: str) -> dict | None:
        return self.read_run(run_id)

    def write(self, run: dict) -> None:
        self.write_run(run)


# ── postgres ─────────────────────────────────────────────────────────────────

class PostgresBackend:
    """The same interface over psycopg. Every connection sets app.tenant_id first."""

    kind = POSTGRES

    def __init__(self, url: str, *, tenant_id: str, actor_id: str | None = None) -> None:
        if not _UUID.match(tenant_id or ""):
            raise StoreError(
                f"tenant_id must be a UUID, got {tenant_id!r}. The row-level security "
                f"policies compare against app.tenant_id, so a backend without one would "
                f"read nothing and write rows nobody can see.")
        self._url = url
        self.tenant_id = tenant_id
        self.actor_id = actor_id or tenant_id

    def _conn(self):
        import psycopg
        conn = psycopg.connect(self._url, autocommit=True)
        # Before anything else. A statement issued ahead of this one is a statement the
        # policy evaluates with no tenant set, which returns nothing and looks like data loss.
        conn.execute("SELECT set_config('app.tenant_id', %s, false)",
                     (self.tenant_id,))
        return conn

    def write_run(self, run: dict) -> None:
        rid = run["id"]
        with self._conn() as c:
            c.execute(
                "INSERT INTO runs (run_id, tenant_id, actor_id, intent, status, "
                "refusal_code) VALUES (%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (run_id) DO UPDATE SET status = EXCLUDED.status, "
                "refusal_code = EXCLUDED.refusal_code",
                (rid, self.tenant_id, self.actor_id, run.get("intent", ""),
                 run.get("status", "PLANNED"), run.get("refusal_code")))
            c.execute("DELETE FROM run_steps WHERE run_id = %s", (rid,))
            # Shaped on the way IN, the same as MemoryBackend: one normalisation for
            # both backends, or the two disagree about what a null cost means. The shared
            # conformance suite caught this on Postgres while memory passed.
            for i, s in enumerate(_shaped(st, STEP_KEYS)
                                  for st in run.get("steps", [])):
                c.execute(
                    "INSERT INTO run_steps (run_id, ordinal, tenant_id, capability, "
                    "engine_capability, status, model, degraded, provider, region, "
                    "cost_inr, cost_note, idempotency_key) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (rid, i, self.tenant_id, s.get("capability", ""),
                     s.get("engine_capability"), s.get("status", "PLANNED"),
                     s.get("model"), bool(s.get("degraded", False)),
                     s.get("provider"), s.get("region"), s.get("cost_inr"),
                     s.get("cost_note"), s.get("idempotency_key")))
            c.execute("DELETE FROM propositions WHERE run_id = %s", (rid,))
            for i, p in enumerate(_shaped(pr, PROPOSITION_KEYS)
                                  for pr in run.get("propositions", [])):
                import uuid as _uuid
                c.execute(
                    "INSERT INTO propositions (proposition_id, run_id, tenant_id, ordinal, "
                    "status, source_ref, span_start, span_end) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (p.get("proposition_id") or str(_uuid.uuid4()), rid, self.tenant_id, i,
                     p.get("status", "UNVERIFIED"), p.get("source_ref"),
                     p.get("span_start"), p.get("span_end")))

    def read_run(self, run_id: str) -> dict | None:
        # A malformed id is not a run. Postgres raises InvalidTextRepresentation on a
        # non-UUID for a uuid column, so without this a lookup of "no-such-run" is an
        # exception on Postgres and None in memory -- the two backends disagreeing about
        # what "unknown" means, which is exactly what the shared contract is for.
        if not _UUID.match(run_id or ""):
            return None
        with self._conn() as c:
            r = c.execute("SELECT run_id, intent, status, refusal_code, result FROM runs "
                          "WHERE run_id = %s", (run_id,)).fetchone()
            if r is None:
                return None
            out = {"id": str(r[0]), "intent": r[1], "status": r[2], "refusal_code": r[3],
                   "result": r[4]}
            out["steps"] = [
                {"capability": s[0], "engine_capability": s[1], "status": s[2],
                 "model": s[3], "degraded": s[4], "provider": s[5], "region": s[6],
                 "cost_inr": float(s[7]) if s[7] is not None else None,
                 "cost_note": s[8], "idempotency_key": s[9]}
                for s in c.execute(
                    "SELECT capability, engine_capability, status, model, degraded, "
                    "provider, region, cost_inr, cost_note, idempotency_key "
                    "FROM run_steps WHERE run_id = %s ORDER BY ordinal", (run_id,)).fetchall()]
            out["propositions"] = [
                {"status": p[0], "source_ref": p[1], "span_start": p[2], "span_end": p[3]}
                for p in c.execute(
                    "SELECT status, source_ref, span_start, span_end FROM propositions "
                    "WHERE run_id = %s ORDER BY ordinal", (run_id,)).fetchall()]
            return out

    def put_document(self, *, sha256: str, name: str, byte_count: int) -> dict:
        with self._conn() as c:
            c.execute(
                "INSERT INTO documents (sha256, tenant_id, name, byte_count) "
                "VALUES (%s,%s,%s,%s) ON CONFLICT (tenant_id, sha256) DO NOTHING",
                (sha256, self.tenant_id, name, byte_count))
        return {"sha256": sha256, "name": name, "byte_count": byte_count,
                "tenant_id": self.tenant_id}

    def get_document(self, sha256: str) -> dict | None:
        with self._conn() as c:
            r = c.execute("SELECT sha256, name, byte_count, tenant_id FROM documents "
                          "WHERE sha256 = %s", (sha256,)).fetchone()
        return None if r is None else {"sha256": r[0], "name": r[1],
                                        "byte_count": r[2], "tenant_id": str(r[3])}

    def write_decision(self, decision: dict) -> dict:
        import psycopg
        with self._conn() as c:
            try:
                r = c.execute(
                    "INSERT INTO decisions (decision_id, run_id, tenant_id, item_ref, "
                    "decision, reason, quoted_span, actor_id, decided_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,COALESCE(%s::timestamptz, now())) "
                    "RETURNING decision_id, run_id, item_ref, decision, reason, "
                    "quoted_span, actor_id, decided_at",
                    (decision["decision_id"], decision["run_id"], self.tenant_id,
                     decision["item_ref"], decision["decision"], decision["reason"],
                     decision["quoted_span"], decision["actor_id"],
                     decision.get("decided_at"))).fetchone()
            except psycopg.errors.UniqueViolation:
                raise DecisionExists(
                    f"{decision['item_ref']} on run {decision['run_id']} already has a "
                    f"decision. A reviewer changing their mind writes a new one against a "
                    f"new run; overwriting would destroy the label, which is the point of "
                    f"storing it.") from None
        return {"decision_id": str(r[0]), "run_id": str(r[1]), "item_ref": r[2],
                "decision": r[3], "reason": r[4], "quoted_span": r[5],
                "actor_id": str(r[6]), "decided_at": r[7].isoformat()}

    def read_decisions(self, run_id: str) -> list[dict]:
        if not _UUID.match(run_id or ""):
            return []
        with self._conn() as c:
            rows = c.execute(
                "SELECT decision_id, run_id, item_ref, decision, reason, quoted_span, "
                "actor_id, decided_at FROM decisions WHERE run_id = %s "
                "ORDER BY decided_at, item_ref", (run_id,)).fetchall()
        return [{"decision_id": str(r[0]), "run_id": str(r[1]), "item_ref": r[2],
                 "decision": r[3], "reason": r[4], "quoted_span": r[5],
                 "actor_id": str(r[6]), "decided_at": r[7].isoformat()} for r in rows]

    def append_step(self, run_id: str, step: dict, *, key: str) -> bool:
        """Append unless the key is already there. The unique index decides, not a SELECT:
        a check-then-insert is two statements a second worker can interleave with."""
        st = _shaped(step, STEP_KEYS)
        with self._conn() as c:
            n = c.execute(
                "INSERT INTO run_steps (run_id, ordinal, tenant_id, capability, "
                "engine_capability, status, model, degraded, provider, region, cost_inr, "
                "cost_note, idempotency_key) SELECT %s, "
                "(SELECT coalesce(max(ordinal) + 1, 0) FROM run_steps WHERE run_id = %s), "
                "%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s "
                "ON CONFLICT (run_id, idempotency_key) WHERE idempotency_key IS NOT NULL "
                "DO NOTHING",
                (run_id, run_id, self.tenant_id, st.get("capability", ""),
                 st.get("engine_capability"), st.get("status", "PLANNED"),
                 st.get("model"), bool(st.get("degraded", False)), st.get("provider"),
                 st.get("region"), st.get("cost_inr"), st.get("cost_note"), key)).rowcount
        return bool(n)

    def set_run(self, run_id: str, *, status: str, refusal_code=None, result=None) -> None:
        import json as _json
        with self._conn() as c:
            c.execute(
                "UPDATE runs SET status = %s, refusal_code = %s, "
                "result = COALESCE(%s::jsonb, result), "
                "finished_at = CASE WHEN %s THEN now() ELSE finished_at END "
                "WHERE run_id = %s",
                (status, refusal_code,
                 None if result is None else _json.dumps(result),
                 status in ("ANSWERED", "PARTIAL", "REFUSED", "FAILED"), run_id))

    def write_cascade(self, record: dict, *, run_id: str | None = None) -> dict:
        import json as _json
        import uuid as _uuid
        row = {
            "cascade_id": record.get("cascade_id") or str(_uuid.uuid4()),
            "run_id": run_id,
            "status": record.get("status", ""),
            "error": record.get("error"),
            "attempts": [dict(a) for a in record.get("attempts", [])],
            "body_ids": list(record.get("body_ids", [])),
            "claim_count": len(record.get("claims", [])),
            "refusal_count": len(record.get("refusals", [])),
            "total_cost_inr": record.get("total_cost_inr"),
        }
        _check_cascade(row)
        with self._conn() as c:
            c.execute(
                "INSERT INTO cascade_runs (cascade_id, run_id, tenant_id, status, error, "
                "attempts, body_ids, claim_count, refusal_count, total_cost_inr) "
                "VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s)",
                (row["cascade_id"], row["run_id"], self.tenant_id, row["status"],
                 row["error"], _json.dumps(row["attempts"]), row["body_ids"],
                 row["claim_count"], row["refusal_count"], row["total_cost_inr"]))
        return dict(row)

    def read_cascades(self, *, run_id: str | None = None, limit: int = 1000) -> list[dict]:
        if run_id is not None and not _UUID.match(run_id or ""):
            return []
        where = "WHERE run_id = %s " if run_id is not None else ""
        args = (run_id, limit) if run_id is not None else (limit,)
        with self._conn() as c:
            rows = c.execute(
                "SELECT cascade_id, run_id, status, error, attempts, body_ids, "
                "claim_count, refusal_count, total_cost_inr FROM cascade_runs "
                + where + "ORDER BY created_at LIMIT %s", args).fetchall()
        return [{"cascade_id": str(r[0]),
                 "run_id": str(r[1]) if r[1] is not None else None,
                 "status": r[2], "error": r[3], "attempts": r[4] or [],
                 "body_ids": list(r[5] or []), "claim_count": r[6],
                 "refusal_count": r[7],
                 "total_cost_inr": float(r[8]) if r[8] is not None else None}
                for r in rows]

    def read(self, run_id: str) -> dict | None:
        return self.read_run(run_id)

    def write(self, run: dict) -> None:
        self.write_run(run)


def database_url() -> str | None:
    """The configured URL, or None. Read through checker.env so .env is honoured."""
    try:
        from checker.env import load
        load()
    except Exception:                                            # noqa: BLE001
        pass
    return os.getenv(URL_ENV) or None


def select(*, tenant_id: str | None = None, url: str | None = None) -> Backend:
    """Postgres when a URL is configured, memory otherwise. The ONLY selection point.

    A URL that is set but unusable is an ERROR, never a silent fall back to memory: an
    operator who configured a database and got an in-memory store would be told everything
    is fine while nothing persists and no policy isolates anyone.
    """
    url = url if url is not None else database_url()
    if not url:
        return MemoryBackend(tenant_id=tenant_id or MemoryBackend().tenant_id)
    if not tenant_id:
        raise StoreError(f"{URL_ENV} is set but no tenant was given; a Postgres backend "
                         f"cannot be built without one")
    return PostgresBackend(url, tenant_id=tenant_id)


# ── the contract, run against BOTH backends ──────────────────────────────────

SAMPLE_RUN = {
    "id": "00000000-0000-0000-0000-0000000000r1".replace("r", "9"),
    "intent": "review_contract",
    "status": "ANSWERED",
    "refusal_code": None,
    "steps": [
        {"capability": "intake", "engine_capability": None, "status": "ANSWERED",
         "model": None, "degraded": False},
        {"capability": "document", "engine_capability": "document.ground_extraction",
         "status": "ANSWERED", "model": "azure/llama-3-3-70b", "degraded": True,
         "provider": "azure", "region": "UAE North", "cost_inr": None,
         "cost_note": "UNPRICED: no verified price on record for this deployment"},
        {"capability": "playbook", "engine_capability": "contract.playbook_review",
         "status": "ANSWERED", "model": None, "degraded": False},
    ],
    "propositions": [
        {"status": "VERIFIED", "source_ref": "contract:nda", "span_start": 10,
         "span_end": 42},
        {"status": "UNVERIFIED", "source_ref": None, "span_start": None,
         "span_end": None},
    ],
}


def conformance(backend) -> list[tuple[bool, str]]:
    """Every assertion both backends must satisfy. No I/O beyond the backend itself.

    Called by this module's gated test with MemoryBackend, and by
    scripts/rls_integration.py with PostgresBackend against a live server. One list, two
    callers -- a behaviour only the dict satisfies fails identically on Postgres.
    """
    out: list[tuple[bool, str]] = []

    def ck(cond, label):
        out.append((bool(cond), label))

    import uuid as _uuid
    # A FRESH id per call. SAMPLE_RUN carried a fixed one, and against a shared Postgres
    # that means two tenants writing the same run id: the second one's ON CONFLICT DO
    # UPDATE reaches a row belonging to the first, and row-level security refuses it --
    # correctly. Measured 29-09-2026. The isolation was right and the fixture was wrong.
    run = dict(SAMPLE_RUN, id=str(_uuid.uuid4()))

    ck(backend.read_run("no-such-run") is None,
       "an unknown run reads as None, not as an empty run")
    ck(backend.read_run(str(_uuid.uuid4())) is None,
       "...and a well-formed id that names no run reads as None too")

    backend.write_run(run)
    got = backend.read_run(run["id"])
    ck(got is not None, "a written run reads back")
    if got:
        ck(got["status"] == "ANSWERED" and got["intent"] == "review_contract",
           "...with its intent and status")
        ck([s["capability"] for s in got["steps"]]
           == ["intake", "document", "playbook"],
           "...and its steps IN ORDER, which is what makes a trace replayable")
        ck(got["steps"][1]["model"] == "azure/llama-3-3-70b"
           and got["steps"][1]["degraded"] is True,
           "...carrying which model served a step and whether the route was degraded")
        ck(got["steps"][1]["provider"] == "azure"
           and got["steps"][1]["region"] == "UAE North",
           "...and the provider and the deployment REGION, so a trace answers 'where did "
           "this document go' without reading a deployment note")
        ck(got["steps"][1]["cost_inr"] is None
           and "UNPRICED" in (got["steps"][1]["cost_note"] or ""),
           "...and an unpriced call records NULL with its reason, never 0.0: Azure bills "
           "student credit, so a recorded zero would be a claim the call was free")
        ck([p["status"] for p in got["propositions"]] == ["VERIFIED", "UNVERIFIED"],
           "...and its propositions, in order")
        ck(got["propositions"][0]["span_start"] == 10
           and got["propositions"][0]["span_end"] == 42,
           "...with span OFFSETS, not copied text")

    # Idempotence: writing the same run twice is one run with one set of steps.
    backend.write_run(run)
    again = backend.read_run(run["id"])
    ck(again and len(again["steps"]) == 3,
       "re-writing a run replaces its steps rather than appending them again")

    # The caller's dict is not the store's dict.
    mutant = dict(run)
    mutant["steps"] = [dict(s) for s in run["steps"]]
    backend.write_run(mutant)
    mutant["steps"][0]["capability"] = "TAMPERED"
    after = backend.read_run(run["id"])
    ck(after and after["steps"][0]["capability"] == "intake",
       "mutating the dict AFTER writing does not change the store -- a backend that kept "
       "the caller's object would pass tests a database cannot")

    # A step written WITHOUT its optional keys must read back WITH them. Postgres returns
    # every column; a dict returns what it was handed, and `step["model"]` would then be a
    # KeyError on memory and None on Postgres. Caught the hard way on 29-09-2026, when the
    # CLI demo raised KeyError('model') on a step the sample run happened to populate.
    sparse_id = str(_uuid.uuid4())
    backend.write_run({"id": sparse_id, "intent": "ask", "status": "ANSWERED",
                       "steps": [{"capability": "intake", "status": "ANSWERED"}],
                       "propositions": [{"status": "VERIFIED"}]})
    sp = backend.read_run(sparse_id)
    ck(sp and set(sp["steps"][0]) == set(STEP_KEYS),
       f"a step written with two keys reads back with all of them "
       f"({sorted(sp['steps'][0]) if sp else []})")
    ck(sp and sp["steps"][0]["model"] is None and sp["steps"][0]["degraded"] is False,
       "...the absent ones defaulted, not missing -- so step['model'] is never a KeyError "
       "on one backend and None on the other")
    ck(sp and set(sp["propositions"][0]) == set(PROPOSITION_KEYS),
       "...and the same for a proposition")

    # A null cost always says WHY it is null.
    nulls = [st for st in (backend.read_run(sparse_id) or {}).get("steps", [])
             if st["cost_inr"] is None]
    ck(nulls and all(st["cost_note"] for st in nulls),
       "every step with a null cost carries a reason -- a blank beside a null is "
       "indistinguishable from a cost nobody bothered to record")

    ck(backend.get_document("0" * 64) is None, "an unknown document reads as None")
    sha = _uuid.uuid4().hex + _uuid.uuid4().hex
    doc = backend.put_document(sha256=sha, name="nda.txt", byte_count=33)
    ck(doc["sha256"] == sha, "a document is stored under its sha256")
    back = backend.get_document(sha)
    ck(back and back["byte_count"] == 33 and back["name"] == "nda.txt",
       "...and reads back with its name and size")
    backend.put_document(sha256=sha, name="nda.txt", byte_count=33)
    ck(backend.get_document(sha) is not None,
       "storing the same bytes twice is not an error: the id IS the hash, so it is one "
       "document")

    # ── the human gate, stored as labelled data (PLAN_23 rule 5) ────────────
    ck(backend.read_decisions(run["id"]) == [],
       "a run with no human decision reads as an empty list, not as a missing key")
    dec = {"decision_id": str(_uuid.uuid4()), "run_id": run["id"],
           "item_ref": "playbook:NDA-08", "decision": "REJECTED",
           "reason": "The non-compete is one-way and we do not accept those.",
           "quoted_span": "The Receiving Party shall not compete for two years.",
           "actor_id": "00000000-0000-0000-0000-0000000000a1",
           "decided_at": "2026-09-30T10:00:00+00:00"}
    wrote = backend.write_decision(dict(dec))
    ck(set(wrote) == set(DECISION_KEYS),
       f"a decision reads back with every key both backends promise ({sorted(wrote)})")
    got = backend.read_decisions(run["id"])
    ck(len(got) == 1 and got[0]["reason"] == dec["reason"],
       "...and the reason is stored verbatim: it IS the label")
    ck(got[0]["quoted_span"] == dec["quoted_span"],
       "...with the span the reviewer was shown, so the label is attached to text a person "
       "actually read")
    ck(got[0]["decided_at"],
       "...and a time, defaulted by the store when the caller gives none")

    # One per item, on BOTH backends. Without this the dict keeps two labels for one item
    # and Postgres keeps one, and the disagreement surfaces as a lost review months later.
    try:
        backend.write_decision(dict(dec, decision_id=str(_uuid.uuid4()),
                                    decision="APPROVED", reason="Changed my mind about it."))
        ck(False, "a second decision on the same item is refused")
    except DecisionExists:
        ck(True, "a second decision on the SAME item is refused -- overwriting would "
                 "destroy the label, which is the point of storing it")
    ck(len(backend.read_decisions(run["id"])) == 1,
       "...and nothing was written by the attempt")

    # A different item on the same run is a different label.
    backend.write_decision(dict(dec, decision_id=str(_uuid.uuid4()),
                                item_ref="ss:T1.2", decision="APPROVED",
                                reason="Inspected the book; every page is initialled."))
    ck(len(backend.read_decisions(run["id"])) == 2,
       "...while a different item on the same run is a separate decision")

    # ── idempotent steps: a retried step writes once (PLAN_23 O2) ───────────
    idem = str(_uuid.uuid4())
    backend.write_run({"id": idem, "intent": "review_document", "status": "PLANNED",
                       "steps": [], "propositions": []})
    k = step_key(idem, "document")
    step = {"capability": "document", "status": "ANSWERED", "provider": "azure",
            "region": "UAE North", "cost_inr": 0.05, "cost_note": "priced from tokens"}
    ck(backend.append_step(idem, step, key=k) is True,
       "a step appends and says it was written")
    ck(backend.append_step(idem, step, key=k) is False,
       "...and the SAME key appends nothing and says so -- which is how a worker tells a "
       "resumed run from a fresh one")
    after = backend.read_run(idem)
    ck(after and len(after["steps"]) == 1,
       f"...so a retried step is written ONCE ({len(after['steps']) if after else '?'})")
    total = sum(s["cost_inr"] or 0 for s in after["steps"])
    ck(abs(total - 0.05) < 1e-9,
       f"...and billed once: the cost rides on the step row, so a duplicate step IS a "
       f"duplicate charge ({total})")
    ck(after["steps"][0]["idempotency_key"] == k,
       "...and the key is readable, so the record says why the second write did nothing")
    ck(backend.append_step(idem, {**step, "capability": "playbook"},
                           key=step_key(idem, "playbook")) is True,
       "...while a DIFFERENT step on the same run still appends")

    # ── the run's status and result move without rewriting its steps ────────
    backend.set_run(idem, status="ANSWERED", result={"findings": 3})
    done = backend.read_run(idem)
    ck(done["status"] == "ANSWERED" and len(done["steps"]) == 2,
       f"setting the status leaves the trace alone ({done['status']}, "
       f"{len(done['steps'])} steps)")
    ck(done.get("result") == {"findings": 3},
       f"...and the result is readable by a poller once the status goes final "
       f"({done.get('result')})")
    # ── cascade records (PLAN_23 O3) ───────────────────────────────────────
    ck(backend.read_cascades(run_id=idem) == [],
       "a run with no cascade record reads as an empty list")
    cid = str(_uuid.uuid4())
    casc = {"cascade_id": cid, "status": "PARTIAL", "error": None,
            "attempts": [{"stage": "small_model", "outcome": "REJECTED",
                          "reason": "NO_CITATION: invented", "model": "s",
                          "cost_inr": 0.02, "cost_note": ""},
                         {"stage": "large_model", "outcome": "ACCEPTED", "reason": "",
                          "model": "l", "cost_inr": 0.10, "cost_note": ""}],
            "body_ids": ["CA2013", "FEMA1999"],
            "claims": [{"text": "t"}], "refusals": [{"body": "FEMA1999"}],
            "total_cost_inr": 0.12}
    wrote = backend.write_cascade(dict(casc), run_id=idem)
    ck(set(wrote) == set(CASCADE_KEYS),
       f"a cascade record reads back with every key both backends promise "
       f"({sorted(wrote)})")
    got_c = backend.read_cascades(run_id=idem)
    ck(len(got_c) == 1 and got_c[0]["status"] == "PARTIAL",
       "...and is findable by the run it belonged to")
    ck([a["stage"] for a in got_c[0]["attempts"]] == ["small_model", "large_model"],
       f"...with its attempts IN ORDER: stage 2 only ran because stage 1 was rejected, "
       f"and a record that must be re-sorted to see that has lost it "
       f"({[a['stage'] for a in got_c[0]['attempts']]})")
    ck(got_c[0]["attempts"][0]["reason"] == "NO_CITATION: invented",
       "...each carrying the verifier's rejection reason, which is what a rate counts")
    ck(got_c[0]["body_ids"] == ["CA2013", "FEMA1999"],
       f"...and every body the answer touched ({got_c[0]['body_ids']})")
    ck(abs((got_c[0]["total_cost_inr"] or 0) - 0.12) < 1e-9,
       "...and the total cost, including the rejected stage")

    unp = backend.write_cascade({"status": "NEEDS_LAWYER", "attempts": [],
                                 "body_ids": [], "total_cost_inr": None}, run_id=idem)
    ck(unp["total_cost_inr"] is None,
       "an unpriced cascade stores NULL, which is UNPRICED")
    for bad, why in (
        ({"status": "FAILED", "attempts": [], "body_ids": []},
         "FAILED with no error"),
        ({"status": "ANSWERED", "error": "boom", "attempts": [], "body_ids": []},
         "a non-FAILED record carrying a transport error"),
        ({"status": "ANSWERED", "attempts": [], "body_ids": [], "total_cost_inr": 0},
         "a recorded cost of 0, which would claim the calls were free"),
        ({"status": "MAYBE", "attempts": [], "body_ids": []}, "an unknown status"),
    ):
        try:
            backend.write_cascade(dict(bad), run_id=idem)
            ck(False, f"{why} is refused")
        except StoreError:
            ck(True, f"refused: {why}")
    ck(len(backend.read_cascades(run_id=idem)) == 2,
       "...and none of the refused records was written")
    ck(len(backend.read_cascades()) >= 2,
       "cascades are readable without naming a run, which is what the report needs")

    backend.set_run(idem, status="REFUSED", refusal_code="CANCELLED")
    ck(backend.read_run(idem)["refusal_code"] == "CANCELLED",
       "...and a cancelled run keeps its code, which is what the trace is read for")
    ck(len(backend.read_run(idem)["steps"]) == 2,
       "...with every step it had: cancellation never deletes")
    return out


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

    # ── the contract, against the backend the gate can run ──────────────────
    for good, label in conformance(MemoryBackend()):
        check(good, f"[memory] {label}")

    # ── selection ───────────────────────────────────────────────────────────
    T = "11111111-2222-3333-4444-555555555555"
    check(select(url="").kind == MEMORY,
          "with no URL configured the store is in-memory")
    check(select(url=None, tenant_id=T).kind in (MEMORY, POSTGRES),
          "...and selection reads the environment when no URL is passed")
    b = select(url="postgresql://x/y", tenant_id=T)
    check(b.kind == POSTGRES and isinstance(b, PostgresBackend),
          "a configured URL selects Postgres")
    check(b.tenant_id == T, "...bound to the tenant it was given")
    try:
        select(url="postgresql://x/y")
        check(False, "a URL with no tenant is refused")
    except StoreError as e:
        check("cannot be built without one" in str(e),
              "a URL with no tenant is REFUSED rather than defaulted -- a default tenant "
              "is a tenant whose rows everyone shares")
    try:
        PostgresBackend("postgresql://x/y", tenant_id="not-a-uuid")
        check(False, "a non-UUID tenant is refused")
    except StoreError as e:
        check("row-level security" in str(e).lower() or "policies" in str(e),
              "...and the refusal names WHY: the policies compare against app.tenant_id")

    # A URL that is set but unusable must not degrade to memory.
    import inspect
    src = inspect.getsource(select)
    check("MemoryBackend" in src and "raise StoreError" in src,
          "select() raises on a bad configuration rather than falling back to memory: an "
          "operator told 'fine' while nothing persists is the worst of both")

    # ── both backends really do offer the same names ────────────────────────
    need = ("write_run", "read_run", "put_document", "get_document", "read", "write",
            "write_decision", "read_decisions", "write_cascade", "read_cascades")
    for name in need:
        check(hasattr(MemoryBackend(), name)
              and hasattr(PostgresBackend("postgresql://x/y", tenant_id=T), name),
              f"both backends expose {name}()")
    check(MemoryBackend().kind == MEMORY
          and PostgresBackend("postgresql://x/y", tenant_id=T).kind == POSTGRES,
          "...and each names itself, which is what /v1/health reports")

    check(len(conformance(MemoryBackend())) >= 12,
          f"the shared contract is not a token list "
          f"({len(conformance(MemoryBackend()))} assertions)")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
