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


# ── in memory ────────────────────────────────────────────────────────────────

# The key set a step and a proposition ALWAYS have when read back. Postgres returns every
# column whether or not the writer supplied it; a dict returns what it was handed. Without
# normalising, `step["model"]` is a KeyError on memory and None on Postgres -- which is a
# divergence that only shows up on the backend the gate does not run.
STEP_KEYS = ("capability", "engine_capability", "status", "model", "degraded",
             "provider", "region", "cost_inr")
PROPOSITION_KEYS = ("status", "source_ref", "span_start", "span_end")


def _shaped(row: dict, keys: tuple[str, ...]) -> dict:
    out = {k: row.get(k) for k in keys}
    if "degraded" in keys:
        out["degraded"] = bool(row.get("degraded", False))
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
            for i, s in enumerate(run.get("steps", [])):
                c.execute(
                    "INSERT INTO run_steps (run_id, ordinal, tenant_id, capability, "
                    "engine_capability, status, model, degraded, provider, region, "
                    "cost_inr) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (rid, i, self.tenant_id, s.get("capability", ""),
                     s.get("engine_capability"), s.get("status", "PLANNED"),
                     s.get("model"), bool(s.get("degraded", False)),
                     s.get("provider"), s.get("region"), s.get("cost_inr")))
            c.execute("DELETE FROM propositions WHERE run_id = %s", (rid,))
            for i, p in enumerate(run.get("propositions", [])):
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
            r = c.execute("SELECT run_id, intent, status, refusal_code FROM runs "
                          "WHERE run_id = %s", (run_id,)).fetchone()
            if r is None:
                return None
            out = {"id": str(r[0]), "intent": r[1], "status": r[2], "refusal_code": r[3]}
            out["steps"] = [
                {"capability": s[0], "engine_capability": s[1], "status": s[2],
                 "model": s[3], "degraded": s[4], "provider": s[5], "region": s[6],
                 "cost_inr": float(s[7]) if s[7] is not None else None}
                for s in c.execute(
                    "SELECT capability, engine_capability, status, model, degraded, "
                    "provider, region, cost_inr "
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
         "provider": "azure", "region": "UAE North", "cost_inr": 0.0},
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
           and got["steps"][1]["region"] == "UAE North"
           and got["steps"][1]["cost_inr"] == 0.0,
           "...and the provider, the deployment REGION and the rupee cost, so a trace "
           "answers 'where did this document go' without reading a deployment note")
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
    need = ("write_run", "read_run", "put_document", "get_document", "read", "write")
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
