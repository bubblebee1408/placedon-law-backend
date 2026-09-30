# Gateway on Postgres — end to end, 2026-09-29

Build-order step 4, proved on a real server rather than described.

**Server:** PostgreSQL 18.6 (Postgres.app), local socket, database `placedon_dev`.
**Application role:** `placedon_app` — NOSUPERUSER, NOBYPASSRLS.

The role matters more than the server. A superuser bypasses row-level security
unconditionally, so an application connecting as one has no tenant isolation whatever the
migrations say. `PLACEDON_DATABASE_URL` therefore names the non-superuser role, and the
first RLS run — made as the superuser macOS account — proved only that a superuser is a
superuser (see `scripts/rls_integration.py`, and R-017 in `research/TASKS.md`).

## Isolation

`scripts/rls_integration.py --run`: **53 checks, 0 failures**, identical on a second run.

| property | result |
|---|---|
| tenant A sees none of tenant B's rows, all 7 tenant-scoped tables | PASS |
| `pg_class.relforcerowsecurity` set on all 7 | PASS |
| policy dropped → default-deny; A sees **0** rows, not even its own | PASS (fails closed) |
| RLS disabled → B's rows **appear**; restored → hidden again | PASS (the proof can fail) |
| `audit_log` refuses UPDATE and DELETE as the app role | PASS |
| tenant B can neither read nor overwrite tenant A's run | PASS |
| `gateway/store.conformance` — the same assertions the gate runs in memory | PASS (17) |

## Three CLI processes, one database

```
$ placedon review-contract --text "<NDA fixture N02>" --name N02
  run_id 1cbdbc10-…  playbook DRAFT  requires_review true
  clauses_in_contract 9   findings 10
  law_not_held ['CONTRACT1872', 'ARBITRATION1996', 'STAMP']

$ placedon runs-trace --run-id 1cbdbc10-…        # a SECOND process
  intake    ANSWERED
  document  ANSWERED  engine=document.ground_extraction
  playbook  ANSWERED  engine=contract.playbook_review

$ placedon runs-get  --run-id 1cbdbc10-…         # a THIRD process
  intent=review_contract  status=ANSWERED  10 propositions
```

Verified directly against the database afterwards:

    as the CLI's tenant     runs=1 run_steps=3 propositions=10
    as a DIFFERENT tenant   runs=0 run_steps=0 propositions=0

The same three commands on the in-memory store return `NOT_FOUND` at the second one,
because that store dies with the process. That is the difference this job existed to make.

## What is still true

Every proposition is UNVERIFIED, and correctly: the CLI has no model configured, so nothing
was extracted, so nothing could be verified. The playbook remains **DRAFT** — no in-house
lawyer has approved a rule in it — and every finding says so.

The **gate has never seen a tenant.** It runs at 227 suites GREEN on the in-memory backend
with `PLACEDON_DATABASE_URL` set, because `create_app` passes `db_url=""`. This file and
`scripts/rls_integration.py` are the only evidence of isolation, and the script has to be
re-run after any migration change.
