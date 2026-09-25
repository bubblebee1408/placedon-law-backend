# Red team — the operation store and the evidence-submission path

Run 2026-09-25 against `1eeea18`, by the session that wrote the code the day before.
Move 8 of `.claude/plans/loop-ten-moves-2026-09-24.md`. Two delegated agents stalled
without producing anything; this was run directly instead.

**The claim under attack**, taken verbatim from the tool description and the MCP
handshake as they stood:

> *"An agent may satisfy non-blocking work with a named source; only a human may
> close BLOCKING work. Nothing here writes to the corpus or attests anything."*

The second sentence held. The first did not.

## Result

| id | Finding | Severity | Status |
|---|---|---|---|
| RT-10 | `actor_kind` was taken from the caller; sending `"human"` closed every BLOCKING requirement | **FATAL** | FIXED — the tool is gone |
| RT-14 | `operation_store` is tenant-blind; any claimed `_tenant` reached every operation | **FATAL** | MITIGATED by RT-10's fix; closed properly at PLAN_17 M4 |
| RT-11 | Lost update: a second submission erased the first from state | HIGH | FIXED + test |
| RT-12 | `source` checked only for non-emptiness; `"."` accepted | MEDIUM | FIXED + test |
| RT-13 | `tools.py` docstring denied the existence of a tool it registered | LOW | FIXED |
| A4 | Policy boundary: a non-submit tool attempting SUBMIT | — | HELD, no defect |

## RT-10 — an agent closed the terminal human review by saying it was a person

`checker/mcp/tools.py::_submit_evidence` contained:

```python
kind = AGENT if str(args.get("actor_kind", AGENT)).lower() != HUMAN else HUMAN
```

Reproduction, through `server.handle_message` — the real MCP entry point, not a
back door:

```
themis.submit_evidence(operation_id=…, requirement_id=<BLOCKING>,
                       actor="research-agent", actor_kind="human",
                       closed_by="research-agent", note="looks fine",
                       source="I checked it myself")
→ 200 accepted
```

Repeated across all five requirements of a live operation:

```
r_b450c4eb3a BLOCKING  -> 200 accepted
r_b52cf424dd IMPORTANT -> 200 accepted
r_3593cc5964 IMPORTANT -> 200 accepted
r_d185798f15 IMPORTANT -> 200 accepted
r_e254a9a684 BLOCKING  -> 200 accepted     <- the terminal HUMAN_REVIEW sink
can_close: True
"5 of 5 requirements satisfied; nothing blocking."
```

The store's `REFUSAL_AGENT_BLOCKING` never fired, and it was not defective: it was
told by the caller that the caller was a human, and it believed the only thing it
had been given.

**The shape of the mistake.** Not "SUBMIT was too wide". `server.py` and `policy.py`
both already stated, at length, that this surface cannot authenticate anyone and
that `actor` and `tenant` are CLAIMS. The error was letting **one** of those claims
decide a guarantee rather than merely be recorded beside it. Meanwhile the
handshake was telling every connecting client the guarantee was real.

That is the second lying-handshake defect in two days (the first: `initialize` still
saying *"Every tool is read-only"* after `submit_evidence` shipped). Both have the
same cause — a sentence asserting a property of code that no test bound to the code.

**Fix.** Not a stronger check; there is no check available at this layer that makes
an unauthenticated claim true. `themis.submit_evidence` was removed from the MCP
surface entirely, `policy.py` returned to three actions with no write path, and the
handshake now says what is true: *every tool is read-only, because this server
cannot establish who you are.*

This matches **PLAN_17 M6**, written 2026-09-24 and merged 2026-09-25, independently:

> *submit_evidence(requirement_id, evidence) — gateway route only (NOT an MCP tool:
> the MCP surface stays read-only).*

and **PLAN_18 §2.10**: *"'Human' is enforced by the principal type: service and MCP
identities carry no member role for writes."*

The submission path itself is unchanged and still tested — `operation_store.submit_evidence`,
in process — and is reached by the authenticated gateway at M6, where `actor_kind`
comes from a validated Entra token instead of a JSON field.

## RT-14 — the store does not know what a tenant is

`grep -c tenant checker/operation_store.py` → **1**, and that one is a comment.
`save()` / `load()` / `list_open()` are global. Any MCP caller asserting any
`_tenant` reached every stored operation, read or write.

Reads remain possible today (an operation id would have to be guessed or leaked);
the write path is gone with RT-10. Closed properly by PLAN_17 M4's tenanted tables
with row-level security — recorded here so the gap is not rediscovered as a surprise.

## RT-11 — a closure erased from state, while the log said otherwise

`save()` writes a **whole-operation snapshot**. Two callers who each loaded the same
operation and each closed a different requirement:

```
A loads, closes r_3593cc5964, saves      -> state: {r_3593cc5964: SATISFIED}
B loads (same state), closes r_d185798f15, saves
                                          -> state: {r_d185798f15: SATISFIED}
                                             A's closure is gone from state
log.jsonl: 2 evidence_accepted events    <- the log is right; the store is wrong
```

This is the RT-08 family one layer up. The module's docstring claims it copied
`watch_ofac.py`'s durability discipline; it copied the **ordering** half (log first,
then state) and not the **concurrent-write** half.

**Fix.** `submit_evidence` re-reads the stored operation and refuses if any
requirement has moved since the caller's copy (`REFUSAL_STALE`) — refuse, never
overwrite, because the losing write is someone else's judgement. Tested three ways:
the refusal fires, the first closure survives in state, and re-reading then
resubmitting keeps both.

## RT-12 — "." was a source

`if not source.strip()` accepted any non-whitespace string. A requirement was closed
citing one full stop.

**Fix.** `_source_usable()` — at least 8 characters, at least one alphanumeric. It is
a **shape test and says so in its own refusal**: this module cannot dereference a
citation, and it must not imply that it can. It stops a gesture at a source, not a
plausible invented one. That is what tracing and human review are for.

## RT-13 — a file denying the existence of its own tool

`checker/mcp/tools.py`'s "What is deliberately absent" section read *"No
`submit_evidence`, no `attest`, no write of any kind … this module never offers the
tool"* for the entire time the module registered `themis.submit_evidence` in `TOOLS`,
thirty lines below. True again now, and the episode is recorded in place rather than
silently restored.

## What held

- **A4.** `policy.decide` refused SUBMIT on every tool but the named one, and refused
  WRITE and ATTEST on all of them, for every actor, throughout.
- **Budget arithmetic.** `can_close` was never wrong about its own inputs. Every
  false `True` above came from a requirement that had genuinely been flipped, by an
  actor that should not have been able to flip it. The lattice did its job; the
  gate in front of it did not.
- **Refusal wording.** Every refusal that did fire arrived verbatim, quotable, with
  its reason — including through the MCP transport as a 409, not an `isError`.

## The pattern this is the fourth instance of

`docs/FAILURE_MODES.md` N13 and this week's commits: **a green check that cannot
fail, a `hasattr` guard swallowing a missing API, a `.get(default)` turning "missing"
into a plausible value** — and now *a claim from the party the rule constrains,
accepted as the fact that decides the rule*. All four are the same failure: a place
where the system accepts something unverified and renders it as though it were
established.

Every fix above is a test that fails if the behaviour returns.
