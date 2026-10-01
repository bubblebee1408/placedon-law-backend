# Running the worker

The worker drains `gateway/jobs.py`'s queue: it claims a job, runs it through
`gateway/verbs.queue_handlers`, writes the run's steps and result, and marks the job done.
Without one running, every queued task sits at `envelope: null` for ever — which is not a
failure anyone sees, because a pending run looks exactly like a slow one.

## Run it by hand

```bash
PYTHONPATH=. python3 -m gateway.worker --serve
```

**`--serve` is required, and bare invocation runs the tests.** That looks backwards and is
deliberate: `scripts/run_tests.sh` invokes this file as `gateway/worker.py` with no flag, so
making the service the default would have the gate start a worker and block until the
timeout, on every run, for ever.

With `PLACEDON_DATABASE_URL` set (via `.env`, read by `checker/env.py`) it uses the Postgres
queue and wakes on `NOTIFY placedon_jobs`. Without one it says so and uses an in-memory
queue that keeps nothing across a restart — allowed for a smoke test, and said out loud,
because "it ran and did nothing" and "there was nothing to run" look identical in a log.

## Run it under launchd on this Mac

```bash
cp ops/com.placedon.worker.plist ~/Library/LaunchAgents/
launchctl load   ~/Library/LaunchAgents/com.placedon.worker.plist
launchctl list | grep placedon          # PID and last exit status
tail -f ops/worker.log
launchctl unload ~/Library/LaunchAgents/com.placedon.worker.plist
```

The plist carries **no credential**: `PLACEDON_DATABASE_URL` is read from the repo's `.env`,
which is why the file can be committed. `KeepAlive` restarts it on any exit, with
`ThrottleInterval 10` so a crash loop does not spin.

## Shutdown is graceful, and the boundary is the point

`launchctl unload` sends SIGTERM, then SIGKILL after `ExitTimeOut` (30s). On SIGTERM the
worker sets a flag; `serve()` reads it **between jobs and never inside one**.

A worker that dropped a job half-finished would leave a run `RUNNING` with steps written and
no outcome — and the next worker to pick it up cannot tell that from a crash. Finishing the
job in hand costs at most one job's time, which `run_one` already caps at
`STEP_TIMEOUT_SECONDS`.

## If it is killed anyway

`kill -9` is survivable, by design, and nothing is lost:

1. the job stays `LEASED` with an expired lease,
2. a restarted worker claims it again — the lease expiry is what makes a killed worker
   recoverable rather than a lost job,
3. the run reaches a terminal state **exactly once**, and each step is written **once**,
   because the idempotency key is derived from `(run_id, capability)` and the replay is a
   no-op.

All three are asserted in `gateway/worker.py --test`, and **measured once against a real
server** (2026-10-02, PostgreSQL 18.6, throwaway database): a worker was started on a job
whose handler sleeps 30s, `SIGKILL`ed while the job was `LEASED` and the run `RUNNING`, the
lease expired, and a second worker was started.

```
job status before kill: LEASED
worker killed mid-job (SIGKILL)
after kill, job: LEASED     after kill, run: RUNNING
RESULT  run: ANSWERED  |  job: ('DONE', attempts=2)  |  run_steps rows: 1
```

`attempts=2` is the retry, and `run_steps rows: 1` is the point: the work was attempted
twice and recorded once.

## Is it alive?

```bash
curl -s localhost:8000/v1/health | python3 -m json.tool
```

`queue` appears when the app was built with one (`create_app(queue=...)`):

```json
"queue": {"depth": 3, "oldest_pending_seconds": 2.1, "note": "3 job(s) waiting, the oldest for 2s"}
```

**Read both numbers or neither.** Depth alone cannot tell a busy worker from a dead one: a
queue of 3 is healthy if the oldest is 2 seconds old and an outage if it is 40 minutes old.
`oldest_pending_seconds` is `null` for an empty queue, never `0` — zero would read as "a job
is waiting and it just arrived", which is the opposite of the truth on exactly the number a
pager rule would threshold.

`/v1/health` is served without a key, so the queue block carries counts only: no question
text, no run ids, no tenant content. A depth read under RLS is scoped to the tenant the
injected queue was built for, which is right for a single-tenant deployment and wrong for a
shared gateway — wiring it on a shared gateway is a decision, not a default.

## Did the critic run?

Every run records `critic_enabled` (016) and `runs.trace` reports it. The critic's success
case is invisible: *"the critic found nothing"* and *"the critic was off"* produce the same
clean answer, and without that column nothing tells them apart afterwards. `null` means not
recorded — every run from before 016 — and is never reported as `false`.
