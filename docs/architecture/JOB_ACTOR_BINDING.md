# Authenticated actor binding for queued work

Implemented 19 October 2026 as a prerequisite for individual matter permissions.

## Failure reproduced

The HTTP gateway reused a configured PostgreSQL queue whenever its tenant matched the
request. Two lawyers in the same firm therefore submitted jobs under the first queue's
actor. The database stored `jobs.actor_id`, but the Python `Job` projection dropped it.
The production worker also reused one handler context for every claimed job, with
`Context.actor` and `Context.tenant` left at their default values.

## Execution contract

- Gateway queue selection uses both authenticated tenant and actor; it does not accept
  identity from request arguments.
- `Job` retains tenant and actor from the stored queue columns. Arguments remain data.
- A PostgreSQL worker claims within one configured tenant, then constructs a fresh store,
  queue and handler context for the claimed actor. It validates identity before reading or
  changing a run or invoking the handler.
- Immediately before execution, the actor must still exist, be enabled, and hold lawyer
  or admin role. All current queued entry points require lawyer-level submission. Missing,
  disabled or demoted actors result in a failed run and nonretryable dead-letter job.
- A mismatched or missing identity is dead-lettered without writing a possibly wrong
  actor's store. PostgreSQL reconciles a terminal DEAD job with its pending run in the
  same transaction, joining persisted run ID, tenant and actor. It never uses caller
  arguments or the fixed worker actor. Completed runs and mismatched owners are untouched.
- A failure restoring context or checking the actor is retried through existing bounded
  queue policy. Error messages do not include connection details.
- Unbound memory queues retain their existing single-tenant test behavior. They do not
  establish multi-actor access control.

## Deployment preflight (behavior change)

Before restarting a durable worker, an operator must inspect the intended service actor's
stored `actors.role` and `disabled_at` within its tenant. A lawyer/admin API key alone is
insufficient when that actor's stored role remains `viewer` (the old migration default).
Explicitly provision the intended service actor as lawyer/admin through the existing
account administration process, or keep that worker stopped. Never automatically promote
all actors, infer a role from queued payloads, or override a disabled actor. This change
does not modify existing roles or apply production migrations. Synthetic integration
fixtures explicitly create lawyer actors.

If context restoration repeatedly fails, the PostgreSQL job eventually becomes DEAD
under the existing retry limit and its matching pending run becomes FAILED atomically.
Dead-job inspection is required for recovery. Actor lookup outages after a successful
binding record a failed run when the store is writable and retain bounded retries. If the
queue database itself is unavailable, no terminal state can be persisted until recovery.
Memory queues cannot reconcile a run without a store; they are test-only and can retain a
pending run after a binding failure.

The existing queue API has no lease fencing token: a worker exceeding its lease can still
attempt a late fail. This change does not claim to solve that separate race. Reconciliation
preserves all already-terminal runs; comprehensive lease-owner fencing remains follow-up.

## What this does not enforce

This is identity propagation, not a matter access-control implementation. Existing
PostgreSQL data policies remain tenant-scoped. Read routes, legacy vault ownership,
revocation during a running handler, and nested resource authorization require the
separate matter-grant milestone. Revoking a session or API key alone does not cancel an
already accepted job; disabling or demoting its actor prevents new execution. Historical
jobs attributed to the wrong actor cannot be repaired reliably from caller arguments.
A human operator must reconcile or cancel those jobs rather than trust payload identities.

## Verification

`tests/test_worker_actor_identity.py` covers missing, mismatched and cross-tenant identity,
payload spoofing, disabled/demoted/deleted actors, transient binding failures and memory
compatibility. The new behavior was simulated before implementation (six failures, one
existing memory success).

`tests/test_worker_actor_postgres.py` is opt-in, restricted to `placedon_throwaway_*`
databases with a non-superuser, non-BYPASSRLS application role. It exercises real HTTP
upload by a second same-tenant actor, two actors executed by one production binding
factory, persisted job identities, and disabling an actor between submission and execution.
No provider calls or confidential documents are required.
