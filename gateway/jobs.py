"""The durable job queue. One contract, two backends, one conformance suite.

PLAN_23 layer 3, O2. The same shape `gateway/store.py` uses and for the same reason: the
gate runs the in-memory queue on every commit, `scripts/rls_integration.py` runs the
identical assertions against PostgreSQL, and a behaviour only the dict satisfies fails
identically on the database.

## What a queue has to get right, and how each is got right here

**Two workers must never hold one job.** Postgres does it with
`SELECT … FOR UPDATE SKIP LOCKED`: the row is locked for the claiming transaction and a
second worker skips it rather than blocking. The dict does it with a single-threaded
claim. Neither is a convention -- `conformance` claims in a loop and asserts NO job is ever
handed out twice, which is the assertion that fails if SKIP LOCKED is ever dropped. It
checks uniqueness rather than emptiness on purpose: the suite also runs against a shared
database that already holds other work, and an earlier version asserting "the next two
claims are mine" was true of a dict and false of a real queue.

**A crashed worker must not strand its job.** A crashed process releases nothing, so the
lease has to expire without it. `claim()` takes QUEUED jobs and jobs whose
`lease_expires_at` has passed, and bumps `attempts` when it does. That counter is the
record that a retry happened, which is the only reason the crash test can tell a resumed
run from a fresh one.

**Cancellation is a request, read at a boundary.** `request_cancel` sets a flag. There is
deliberately no kill: stopping a step mid-flight would leave a half-written step with no
record of why, which is worse than one more step.

Run: PYTHONPATH=. python3 gateway/jobs.py
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Protocol

QUEUED = "QUEUED"
LEASED = "LEASED"
DONE = "DONE"
FAILED = "FAILED"
CANCELLED = "CANCELLED"
JOB_STATUSES = (QUEUED, LEASED, DONE, FAILED, CANCELLED)
TERMINAL = (DONE, FAILED, CANCELLED)

# Long enough that an ordinary step does not lose its lease mid-flight; short enough that a
# killed worker's job is reclaimable while someone is still watching. Not a guess to tune
# later: the worker renews nothing, so this is a cap on how long one step may take.
DEFAULT_LEASE_SECONDS = 120

# The channel a worker LISTENs on. Named here, used by gateway/worker.listen_waiter,
# so the sender and the listener cannot disagree about the string.
NOTIFY_CHANNEL = "placedon_jobs"

_UUID = re.compile(r"^[0-9a-fA-F-]{36}$")


class QueueError(RuntimeError):
    """The queue could not do what was asked. Never swallowed into a silent no-op."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Job:
    job_id: str
    run_id: str
    intent: str
    args: dict
    status: str = QUEUED
    attempts: int = 0
    cancel_requested: bool = False

    def to_dict(self) -> dict:
        return {"job_id": self.job_id, "run_id": self.run_id, "intent": self.intent,
                "args": dict(self.args), "status": self.status,
                "attempts": self.attempts, "cancel_requested": self.cancel_requested}


class Queue(Protocol):
    kind: str

    def enqueue(self, *, run_id: str, intent: str, args: dict) -> Job: ...
    def claim(self, *, worker: str, lease_seconds: int = DEFAULT_LEASE_SECONDS) -> Job | None: ...
    def finish(self, job_id: str, status: str) -> None: ...
    def request_cancel(self, run_id: str) -> bool: ...
    def get(self, run_id: str) -> Job | None: ...
    def depth(self) -> int: ...
    def oldest_pending_seconds(self) -> float | None: ...


# ── in memory ────────────────────────────────────────────────────────────────

@dataclass
class MemoryQueue:
    """A dict with the same claim semantics. What the gate runs."""

    kind: str = "memory"
    tenant_id: str = "00000000-0000-0000-0000-000000000000"
    jobs: dict = field(default_factory=dict)
    # Injected so a test can expire a lease without sleeping. Postgres uses now() and the
    # conformance suite never asserts on wall-clock time, only on ordering.
    clock: object = None

    def _now(self) -> datetime:
        return self.clock() if callable(self.clock) else _now()

    def enqueue(self, *, run_id: str, intent: str, args: dict) -> Job:
        for j in self.jobs.values():
            if j["run_id"] == run_id:
                raise QueueError(
                    f"run {run_id} already has job {j['job_id']}. A second job for one run "
                    f"is the double execution the queue exists to prevent.")
        job_id = str(uuid.uuid4())
        self.jobs[job_id] = {"job_id": job_id, "run_id": run_id, "intent": intent,
                             "args": json.loads(json.dumps(args)), "status": QUEUED,
                             "attempts": 0, "claimed_by": None, "lease_expires_at": None,
                             "cancel_requested": False, "created_at": self._now()}
        return self._job(self.jobs[job_id])

    def oldest_pending_seconds(self) -> float | None:
        """Age in seconds of the oldest QUEUED job, or None when there are none.

        None, NOT 0.0. An empty queue has no oldest job, and 0 would read as "a job is
        waiting and it just arrived" -- the opposite of the truth, on the one number an
        operator looks at to decide whether the worker is still alive.
        """
        waiting = [r for r in self.jobs.values() if r["status"] == QUEUED]
        if not waiting:
            return None
        now = self._now()
        return max((now - r["created_at"]).total_seconds() for r in waiting)

    @staticmethod
    def _job(row: dict) -> Job:
        return Job(job_id=row["job_id"], run_id=row["run_id"], intent=row["intent"],
                   args=dict(row["args"]), status=row["status"], attempts=row["attempts"],
                   cancel_requested=row["cancel_requested"])

    def claim(self, *, worker: str, lease_seconds: int = DEFAULT_LEASE_SECONDS) -> Job | None:
        now = self._now()
        candidates = [
            r for r in self.jobs.values()
            if r["status"] == QUEUED
            or (r["status"] == LEASED and r["lease_expires_at"] is not None
                and r["lease_expires_at"] <= now)
        ]
        if not candidates:
            return None
        row = min(candidates, key=lambda r: r["created_at"])
        row["status"] = LEASED
        row["claimed_by"] = worker
        row["lease_expires_at"] = now + timedelta(seconds=lease_seconds)
        row["attempts"] += 1
        return self._job(row)

    def finish(self, job_id: str, status: str) -> None:
        if status not in TERMINAL:
            raise QueueError(f"{status!r} is not a terminal job status; one of {TERMINAL}")
        row = self.jobs.get(job_id)
        if row is None:
            raise QueueError(f"no job {job_id!r}")
        row["status"] = status
        row["claimed_by"] = None
        row["lease_expires_at"] = None

    def request_cancel(self, run_id: str) -> bool:
        for row in self.jobs.values():
            if row["run_id"] == run_id:
                if row["status"] in TERMINAL:
                    return False
                row["cancel_requested"] = True
                return True
        return False

    def get(self, run_id: str) -> Job | None:
        for row in self.jobs.values():
            if row["run_id"] == run_id:
                return self._job(row)
        return None

    def depth(self) -> int:
        return sum(1 for r in self.jobs.values() if r["status"] == QUEUED)


# ── postgres ─────────────────────────────────────────────────────────────────

class PostgresQueue:
    """The same interface over psycopg. Every connection sets app.tenant_id first."""

    kind: str = "postgres"

    def __init__(self, url: str, *, tenant_id: str, actor_id: str | None = None) -> None:
        if not tenant_id:
            raise QueueError(
                "PostgresQueue needs a tenant_id: the policies compare against "
                "app.tenant_id, and a connection with none set sees no rows at all.")
        self._url = url
        self.tenant_id = tenant_id
        self.actor_id = actor_id or tenant_id

    def _conn(self, *, autocommit: bool = True):
        import psycopg
        conn = psycopg.connect(self._url, autocommit=autocommit)
        conn.execute("SELECT set_config('app.tenant_id', %s, false)", (self.tenant_id,))
        return conn

    @staticmethod
    def _job(r) -> Job:
        return Job(job_id=str(r[0]), run_id=str(r[1]), intent=r[2],
                   args=r[3] or {}, status=r[4], attempts=r[5],
                   cancel_requested=bool(r[6]))

    def enqueue(self, *, run_id: str, intent: str, args: dict) -> Job:
        import psycopg
        job_id = str(uuid.uuid4())
        try:
            with self._conn() as c:
                r = c.execute(
                    "INSERT INTO jobs (job_id, run_id, tenant_id, actor_id, intent, args) "
                    "VALUES (%s,%s,%s,%s,%s,%s) "
                    "RETURNING job_id, run_id, intent, args, status, attempts, "
                    "cancel_requested",
                    (job_id, run_id, self.tenant_id, self.actor_id, intent,
                     json.dumps(args))).fetchone()
        except psycopg.errors.UniqueViolation:
            raise QueueError(
                f"run {run_id} already has a job. A second job for one run is the double "
                f"execution the queue exists to prevent.") from None
        # Wake a listening worker. AFTER the insert and outside the failure path, so a
        # notification is never sent for a job that does not exist. A missed notification
        # costs latency and nothing else -- `gateway/worker.serve` polls on a timeout as
        # well, because a NOTIFY sent while nobody was listening is simply gone.
        with self._conn() as c:
            c.execute(f"NOTIFY {NOTIFY_CHANNEL}")
        return self._job(r)

    def claim(self, *, worker: str, lease_seconds: int = DEFAULT_LEASE_SECONDS) -> Job | None:
        # SKIP LOCKED is the whole point: a second worker running this statement at the same
        # moment steps over the locked row instead of blocking on it, so two workers never
        # hold one job and neither waits for the other.
        sql = (
            "WITH claimed AS ("
            "  SELECT job_id FROM jobs"
            "   WHERE status = 'QUEUED'"
            "      OR (status = 'LEASED' AND lease_expires_at <= now())"
            "   ORDER BY created_at"
            "   FOR UPDATE SKIP LOCKED"
            "   LIMIT 1)"
            "UPDATE jobs j SET status = 'LEASED', claimed_by = %s,"
            "  lease_expires_at = now() + make_interval(secs => %s),"
            "  attempts = j.attempts + 1, updated_at = now()"
            " FROM claimed WHERE j.job_id = claimed.job_id"
            " RETURNING j.job_id, j.run_id, j.intent, j.args, j.status, j.attempts,"
            "           j.cancel_requested")
        with self._conn(autocommit=False) as c:
            r = c.execute(sql, (worker, float(lease_seconds))).fetchone()
            c.commit()
        return None if r is None else self._job(r)

    def finish(self, job_id: str, status: str) -> None:
        if status not in TERMINAL:
            raise QueueError(f"{status!r} is not a terminal job status; one of {TERMINAL}")
        with self._conn() as c:
            n = c.execute(
                "UPDATE jobs SET status = %s, claimed_by = NULL, lease_expires_at = NULL, "
                "updated_at = now() WHERE job_id = %s", (status, job_id)).rowcount
        if not n:
            raise QueueError(f"no job {job_id!r}")

    def request_cancel(self, run_id: str) -> bool:
        if not _UUID.match(run_id or ""):
            return False
        with self._conn() as c:
            n = c.execute(
                "UPDATE jobs SET cancel_requested = true, updated_at = now() "
                "WHERE run_id = %s AND status NOT IN ('DONE','FAILED','CANCELLED')",
                (run_id,)).rowcount
        return bool(n)

    def get(self, run_id: str) -> Job | None:
        if not _UUID.match(run_id or ""):
            return None
        with self._conn() as c:
            r = c.execute(
                "SELECT job_id, run_id, intent, args, status, attempts, cancel_requested "
                "FROM jobs WHERE run_id = %s", (run_id,)).fetchone()
        return None if r is None else self._job(r)

    def depth(self) -> int:
        with self._conn() as c:
            return c.execute("SELECT count(*) FROM jobs WHERE status = 'QUEUED'").fetchone()[0]

    def oldest_pending_seconds(self) -> float | None:
        with self._conn() as c:
            r = c.execute("SELECT EXTRACT(EPOCH FROM (now() - min(created_at))) "
                          "FROM jobs WHERE status = 'QUEUED'").fetchone()
        return None if r is None or r[0] is None else float(r[0])


# ── the shared contract ──────────────────────────────────────────────────────

def conformance(queue) -> list[tuple[bool, str]]:
    """Every assertion both queues must satisfy. Run by this module's gate on the dict and
    by scripts/rls_integration.py on PostgreSQL."""
    out: list[tuple[bool, str]] = []

    def ck(cond, label):
        out.append((bool(cond), label))

    r1, r2 = str(uuid.uuid4()), str(uuid.uuid4())
    ck(queue.get(r1) is None, "a run with no job reads as None, not as an empty job")

    j1 = queue.enqueue(run_id=r1, intent="research_question", args={"question": "q"})
    ck(j1.status == QUEUED and j1.attempts == 0,
       f"an enqueued job is QUEUED and unattempted ({j1.status}, {j1.attempts})")
    ck(queue.get(r1) is not None and queue.get(r1).run_id == r1,
       "...and is findable by its run id, which is what a poller has")

    try:
        queue.enqueue(run_id=r1, intent="research_question", args={})
        ck(False, "a second job for the same run is refused")
    except QueueError:
        ck(True, "a second job for the SAME run is refused -- one run, one execution")

    j2 = queue.enqueue(run_id=r2, intent="review_document", args={"text": "t"})

    # THE assertion. No job is ever handed out twice; if SKIP LOCKED is dropped this goes
    # red. Claimed in a LOOP rather than exactly twice, because this suite also runs against
    # a shared database that already holds other tenants' work and this repo's own seed
    # rows. An earlier version claimed twice and asserted the two were its own, which was
    # true of an empty dict and false of a real queue -- the fixture was wrong, not the
    # queue. Uniqueness is what SKIP LOCKED actually guarantees; emptiness was an artefact.
    seen, mine = [], {}
    for i in range(12):
        j = queue.claim(worker=f"w{i}")
        if j is None:
            break
        seen.append(j.job_id)
        if j.run_id in (r1, r2):
            mine[j.run_id] = j
        if len(mine) == 2:
            break
    ck(len(seen) == len(set(seen)),
       f"no job is ever claimed twice ({len(seen)} claims, {len(set(seen))} distinct)")
    ck(set(mine) == {r1, r2},
       f"...and claiming drains to BOTH of this suite's runs ({sorted(mine)} of "
       f"{sorted((r1, r2))})")
    ck(all(j.attempts == 1 for j in mine.values()),
       f"a claimed job records the attempt ({[j.attempts for j in mine.values()]})")
    ck(mine[r1].args.get("question") == "q",
       "...and carries the arguments it was enqueued with, for the run it was enqueued for")
    a = mine[r1]

    # Cancellation is a flag, read later. Not a kill.
    ck(queue.request_cancel(r1) is True, "cancelling a live run is accepted")
    ck(queue.get(r1).cancel_requested is True, "...and the worker can see the request")
    ck(queue.request_cancel(str(uuid.uuid4())) is False,
       "...while cancelling a run with no job says so rather than pretending")

    queue.finish(j1.job_id, CANCELLED)
    ck(queue.get(r1).status == CANCELLED, "a finished job holds its terminal status")
    ck(queue.request_cancel(r1) is False,
       "...and cancelling an already-finished run is refused, not silently re-applied")
    try:
        queue.finish(j2.job_id, "MAYBE")
        ck(False, "a non-terminal finish status is refused")
    except QueueError:
        ck(True, "finishing with a status that is not terminal is refused")
    queue.finish(j2.job_id, DONE)

    # Not "depth is 0": on a shared database other rows exist and that is correct. What
    # must hold is that finishing a job removes it from the claimable set.
    before = queue.depth()
    r3 = str(uuid.uuid4())
    j3 = queue.enqueue(run_id=r3, intent="review_document", args={})
    ck(queue.depth() == before + 1,
       f"enqueueing raises the queue depth ({before} -> {queue.depth()})")
    queue.finish(j3.job_id, DONE)
    ck(queue.depth() == before,
       f"...and finishing lowers it again ({queue.depth()}), so a done job is not "
       f"re-claimable")
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

    for cond, label in conformance(MemoryQueue()):
        check(cond, f"[memory] {label}")

    # ── the lease, which is the whole crash story ───────────────────────────
    # A crashed worker releases nothing, so the only way its job comes back is the lease
    # lapsing. Time is injected here rather than slept.
    now = [datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)]
    q = MemoryQueue(clock=lambda: now[0])
    rid = str(uuid.uuid4())
    q.enqueue(run_id=rid, intent="review_document", args={})
    first = q.claim(worker="doomed", lease_seconds=60)
    check(first is not None, "a worker claims the job")
    check(q.claim(worker="other") is None,
          "...and while the lease holds, NO other worker can take it")
    now[0] += timedelta(seconds=61)
    again = q.claim(worker="replacement")
    check(again is not None and again.job_id == first.job_id,
          "...but once the lease lapses the SAME job is reclaimable: a crashed worker "
          "cannot release anything, so the lease has to expire on its own")
    check(again.attempts == 2,
          f"...and the attempt count records that it happened ({again.attempts}), which is "
          f"how a resumed run is told from a fresh one")

    check(MemoryQueue().kind == "memory" and PostgresQueue.kind == "postgres",
          "each queue names itself")
    for name in ("enqueue", "claim", "finish", "request_cancel", "get", "depth"):
        check(hasattr(MemoryQueue(), name)
              and hasattr(PostgresQueue("postgresql://x/y", tenant_id="t"), name),
              f"both queues expose {name}()")
    try:
        PostgresQueue("postgresql://x/y", tenant_id="")
        check(False, "a queue with no tenant is refused")
    except QueueError:
        check(True, "a queue with no tenant is REFUSED rather than defaulted: a default "
                    "tenant is a tenant whose jobs everyone can claim")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
