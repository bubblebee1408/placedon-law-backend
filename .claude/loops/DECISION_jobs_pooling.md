# Decision: pool the queue's autocommit paths. Do NOT pool `claim()` yet.

**Date** 2026-10-05 · **Move** 19 · **Branch** `claude/overnight-f` · **Supersedes** the
deferral in A-015

## The question A1 left open

`gateway/pool.py` bounds `PostgresBackend` at 10 connections (API) and 4 (worker).
`PostgresQueue._conn` still opens one connection per operation, so **the queue's connections
are outside those caps** — a worker fleet can exhaust `max_connections` through the claim
path while the pool reports itself healthy.

A-015 recorded the risk as "holding a pooled connection across an explicit transaction". That
was the right instinct and it was not yet a decision. This is the decision.

## What I found by reading both files rather than reasoning about them

**1. The pool's connections are the wrong MODE for `claim()`.**
`gateway/pool.py:97` creates every connection with `autocommit=True`. `claim()` needs
`autocommit=False` — it runs `FOR UPDATE SKIP LOCKED` inside a `WITH … UPDATE … RETURNING`
and calls `c.commit()` explicitly. Handing it an autocommit connection would not merely be
unsafe; the lock would be released before the UPDATE it exists to protect.

**2. The pool already handles the exception case correctly.**

> A connection whose transaction state is unknown is not returned to the pool.

On a raise it closes the connection instead of recycling it. That is exactly the right
behaviour and it is already there.

**3. It does NOT handle the success case, because today it does not have to.**
On a clean exit the connection goes back with no commit and no rollback. With
`autocommit=True` there is nothing open, so this is correct. With `autocommit=False` a caller
that returned without committing would hand the next caller an **open transaction and its row
locks** — which is A-015's risk, stated precisely.

**4. The tenant hazard is already solved.** `set_config('app.tenant_id', …, false)` is
session-scoped and survives a checkout, and `connection()` re-sets it on **every** checkout
with a required argument. A1 proved that live, as `placedon_app`, with `max_size=1` so the
connection must be reused.

**5. A latent oddity, found on the way.** `claim()`'s in-flight count
(`gateway/jobs.py:383-387`) opens a connection with `autocommit=False` for a **pure SELECT**
and never commits. Harmless today — the `with` block rolls back and closes — but it is
exactly the shape that would return an idle-in-transaction connection to a pool. It wants
`autocommit=True` whether or not anything is pooled.

## The decision

**Pool the autocommit paths. Leave `claim()` unpooled until the pool owns a transaction
scope.**

Safe to pool now: `enqueue`, `get`, `fail`, `dead`, `claim_counts`, `clear_backoff` — every
operation that is a single statement under autocommit. That is the large majority of the
queue's connection churn, and it brings that churn inside the caps.

Not safe yet: `claim()`. What would make it safe is a **second pool entry point**, not a
flag on the existing one:

```python
@contextmanager
def transaction(self, *, tenant_id: str):
    """A pooled connection with autocommit OFF, committed on clean exit, rolled back
    otherwise, and CLOSED rather than recycled if either fails."""
```

A `pool.connection(autocommit=False)` flag would be the wrong shape: it would make the
caller responsible for a commit the pool depends on, which is the mistake. The pool must own
the boundary it is relying on.

## Why that is not built tonight

Three reasons, in order of weight:

1. **It changes the pool's connection-mode contract**, and the pool is what A1 proved live at
   348 checks as `placedon_app`. Adding a second creation mode means re-proving the tenant
   contract for connections created the new way — `max_size=1`, two tenants, and the peak
   asserted at 1 so the check cannot pass because each caller quietly got its own connection.
   That is a live-database proof, and tonight's rules put a live model key out of reach but
   not a live Postgres; what it needs is an unhurried session, not a tired one.
2. **The gate cannot show it.** A pooled connection returned mid-transaction is a property
   only a real server exhibits — the same reason the pool's own tenant check had to move from
   a fake connection to `placedon_app`, where it promptly revealed that the first version of
   that check had connected as the admin and reported a leak that did not exist.
3. **The partial change is worth having on its own**, and it is strictly safer than today:
   fewer connections, same semantics, no new pool API. Splitting it means the risky half is
   reviewed on its own rather than hidden inside a win.

## Reversal condition

Reverse the "leave `claim()` unpooled" half the moment a deployment runs enough workers that
`max_connections` is reached — at which point the unbounded claim path is no longer a
theoretical risk and the transaction work becomes urgent rather than careful.
`pool.stats()["refusals"]` is the number to watch: it counts connections the cap refused, and
a non-zero value there with the queue still unpooled means the caps are doing their job while
the queue routes around them.

Reverse the whole decision — pool everything with a `transaction()` scope — if the queue is
ever given a second multi-statement path. One explicit transaction is a special case worth
isolating; two is a pattern, and a pattern wants the API.

## What this does NOT change

`PostgresQueue` keeps `_conn` for `claim()`. Nothing is removed, so a deployment that pools
nothing behaves exactly as it does today — which is what makes the partial change safe to
land without a live proof of the half that is not landing.
