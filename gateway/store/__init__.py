"""Two backends, one interface, and one conformance suite that both must pass.

The in-memory store is what the gate runs on; Postgres is what a deployment runs on. The
risk in having two is that they diverge quietly -- the memory one keeps working, the
Postgres one is exercised by nobody, and the difference is discovered in production.

So the contract is a FUNCTION here, `conformance(backend)`, and it is run twice:

    gateway/store/     in the gate, against MemoryBackend
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

Run: PYTHONPATH=. python3 gateway/store/__main__.py   (or: python3 -m gateway.store)

## Layout

    core          the errors, the `Backend` protocol, row shapes and row checks, helpers
    memory        MemoryBackend, what the gate runs on
    postgres      PostgresBackend, what a deployment runs on
    conformance   conformance(backend): the one contract both backends must pass
    auth_lookup   database_url() and select() (which backend), and AuthLookup
    selftest      `_test()`, the gate suite

Each module imports what it uses from the others. This `__init__` re-exports every public
name and the private ones other code imports, so `from gateway.store import X` works as it
did when this was one file. Patch a name where it is looked up (`gateway.store.postgres.X`),
not this re-export.
"""
from __future__ import annotations

from gateway.store.core import (Backend, CACHE_KEYS, CACHE_STATS, CASCADE_KEYS,
    CONVERSATION_KEYS, DECISION_KEYS, DRAFT_VERSION_KEYS, DecisionExists,
    DuplicateVaultDocument, GRID_CELL_KEYS, MATTER_ROLES, MEMORY, MESSAGE_KEYS,
    MIN_REASON_CHARS, MessageShape, NO_CALL_NOTE, POSTGRES, PROPOSITION_KEYS,
    READABLE_VAULT_STATES, REASSIGNABLE, ROLES, RetryConflict, STEP_KEYS, StoreError,
    TurnConflict, UNOWNED_ONLY, URL_ENV, VAULT_ACCESS_ACTIONS, VAULT_OCR_STATES, VAULT_STATES,
    _insert_draft_version, failure_tag, step_key)
from gateway.store.memory import MemoryBackend
from gateway.store.postgres import PostgresBackend
from gateway.store.conformance import SAMPLE_RUN, conformance
from gateway.store.auth_lookup import AuthLookup, database_url, select

# What this package re-exports (so linters and type checkers see the imports above
# as re-exports, not as unused).
__all__ = ["AuthLookup", "Backend", "CACHE_KEYS", "CACHE_STATS", "CASCADE_KEYS",
    "CONVERSATION_KEYS", "DECISION_KEYS", "DRAFT_VERSION_KEYS", "DecisionExists",
    "DuplicateVaultDocument", "GRID_CELL_KEYS", "MATTER_ROLES", "MEMORY", "MESSAGE_KEYS",
    "MIN_REASON_CHARS", "MemoryBackend", "MessageShape", "NO_CALL_NOTE", "POSTGRES",
    "PROPOSITION_KEYS", "PostgresBackend", "READABLE_VAULT_STATES", "REASSIGNABLE", "ROLES",
    "RetryConflict", "SAMPLE_RUN", "STEP_KEYS", "StoreError", "TurnConflict", "UNOWNED_ONLY",
    "URL_ENV", "VAULT_ACCESS_ACTIONS", "VAULT_OCR_STATES", "VAULT_STATES",
    "_insert_draft_version", "conformance", "database_url", "failure_tag", "select",
    "step_key"]
