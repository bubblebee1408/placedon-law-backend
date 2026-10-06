# Run the whole thing on a laptop

From a clean clone to an upload that is searchable and a review table that dispatches.
Written 2026-10-05, move 4 of `.claude/plans/loop-overnight-twenty-moves-2026-10-05.md`.

**No external key is needed for any step here.** A model call needs one; nothing below makes
a model call. Where a step would need a key, it says so and refuses by name.

## 1. A FRESH database. Not `placedon_dev`.

```bash
createdb placedon_app_local
PLACEDON_DATABASE_URL="postgresql:///placedon_app_local?host=/tmp" \
  python3 -c '
import pathlib, psycopg, os
url = os.environ["PLACEDON_DATABASE_URL"]
with psycopg.connect(url, autocommit=True) as c:
    for m in sorted(pathlib.Path("gateway/migrations").glob("0*.sql")):
        c.execute(m.read_text())
        print("applied", m.name)
'
```

That applies **001 through 022**. All of them, in order, to an empty database.

### Why not just upgrade the database you already have

`placedon_dev` on this machine is at migration ~007. Every table the console needs arrives
later: `review_grids` (011), `drafts` (012), `matters` (019), `vault_documents` (020),
`jobs.lane` (021), the grid's budget state (022).

**And it cannot be upgraded in place.** `scripts/rls_integration.py`'s own run log records
why: `placedon_dev` holds 64 APPROVED seed rows written before `quote_viewed` existed, and
008's `VALIDATE` refuses them *by design* — "the pre-existing approvals must be looked at by
a person, not defaulted". Those are a test script's synthetic seeds, so the answer is a fresh
database and not a change to 008.

If you try it anyway, 008 fails and you are left part-migrated. Start clean.

## 2. Point the backend at it, without editing `.env`

`checker/env.load()` does not override a variable that is already set, so exporting wins and
your `.env` is untouched:

```bash
export PLACEDON_DATABASE_URL="postgresql:///placedon_app_local?host=/tmp"
export PLACEDON_FILES_DIR="$PWD/.local-vault"
```

`PLACEDON_FILES_DIR` is the vault. Without it `create_app` configures no file store, every
`vault.upload` refuses `NO_VAULT` by name, and `/v1/health` says
`files: {"configured": false, …}` — so you can see it on health rather than discovering it
from a refusal.

## 3. Start the gateway — with a LAWYER key

From the frontend repo (`../placedon-claude-legal-3300`):

```bash
PLACEDON_DATABASE_URL="postgresql:///placedon_app_local?host=/tmp" \
  python3 scripts/local-gateway.py
```

It mints a key into `.env.local` without printing it, and passes the gateway a queue and a
file store.

**The key is minted as `lawyer`, not the `viewer` default.** `KeyStore.mint` defaults to
`viewer`, and `vault.upload`, `review_table.create`, `draft.create` and `draft.revise` all
require `lawyer` (`gateway/roles.REQUIRED`). With a viewer key the first live call is:

```
403 — vault.upload needs the lawyer role; this key has viewer
```

That is the console able to read the app and not use it. `admin` is deliberately not used:
nothing these screens do needs it, and a local key with more authority than the screens
require is a habit worth not forming.

## 4. Start the worker — a SECOND process

```bash
PYTHONPATH=. \
PLACEDON_DATABASE_URL="postgresql:///placedon_app_local?host=/tmp" \
PLACEDON_FILES_DIR="$PWD/.local-vault" \
PLACEDON_WORKER_TENANT_ID="00000000-0000-0000-0000-000000000001" \
  python3 gateway/worker.py --serve
```

**`PLACEDON_WORKER_TENANT_ID` is required on Postgres.** One worker drains ONE tenant's
jobs: every row it reads is behind `FORCE ROW LEVEL SECURITY` on `app.tenant_id`, so there
is no safe default and the worker refuses rather than guess. The id above is the one
`local-gateway.py` fixes for the local console — it prints it on startup. Without it
the worker exits on `StoreError` before claiming anything, and the only symptom is a
document that stays PENDING.

Run it from the repository root. **`PYTHONPATH=.` is required** and this doc shipped without
it: `gateway/worker.py` does `from gateway import jobs`, so without it the worker dies on
`ModuleNotFoundError: No module named 'gateway'` before it claims anything, and the only
symptom at the console is a document that stays PENDING for ever. The gateway does not need
it because `local-gateway.py` sets it itself.

**`--serve` is required.** A bare `python3 gateway/worker.py` runs the worker's own TESTS,
because `scripts/run_tests.sh` invokes it that way; a service-by-default would have the gate
start a worker and block until the timeout on every run.

The gateway does **not** start a worker for you. Two processes, on purpose: a gateway that
drained its own queue would hide the failure the console exists to show. With no worker
running, `review_table.status` says so in words —
`"not dispatched: no worker. N cell(s) are queued and nothing has claimed one"` — rather than
leaving PENDING to be read as progress.

Both processes need the same `PLACEDON_FILES_DIR`, or the worker reads an empty directory and
every ingest refuses.

## 5. Check it works

```bash
curl -s http://127.0.0.1:8000/v1/health | python3 -m json.tool | head -20
```

Expect `store.kind: postgres` and `files.configured: true`. Then, with the key from
`.env.local`:

```bash
KEY=$(grep '^PLACEDON_GATEWAY_KEY=' ../placedon-claude-legal-3300/.env.local | cut -d= -f2)
curl -s -X POST http://127.0.0.1:8000/v2/vault/upload \
  -H "Authorization: Bearer $KEY" -H 'content-type: application/json' \
  -d '{"name":"nda.txt","text":"This Agreement is governed by the laws of India."}'
```

That returns `state: PENDING` with a `job_id`. **PENDING is not INGESTED** — nothing is
searchable until the worker has read it. A second later:

```bash
curl -s -X POST http://127.0.0.1:8000/v2/vault/status \
  -H "Authorization: Bearer $KEY" -H 'content-type: application/json' \
  -d '{"document_id":"<the document_id>"}'
```

`state: INGESTED`. Then `/v2/vault/verify` reports a line per check — the record exists, the
bytes are present, the bytes hash to their key — rather than one real/fake verdict.

## What still needs a key, and what it blocks

| Step | Needs | Without it |
|---|---|---|
| A review table cell reaching FOUND | a model key (Azure today, Bedrock after B1) | the cell is FAILED or NEEDS_LAWYER. It never silently becomes FOUND |
| `conversation.send` answering with prose | the same | the draft is built from templates and records `prose not generated: <reason>` |
| OCR on a scan | Textract (BLOCKED until AWS) | the upload is `CANNOT_READ`, refused rather than stored unsearchable |

A cell that cannot be answered does **not** become FOUND with a stub. Writing a stub answer
into a real `review_grid_cells` row would be a fabricated finding about a real document, and
no local-development convenience is worth that.

## The frontend

```bash
cd ../placedon-claude-legal-3300 && npm run build && npx next start -p 3300
```

`/app/vault`, `/app/tables`, `/app/drafts/<id>` and `/app/calendar` read through
`src/lib/gateway`, server-side only. Its `README.md` under `docs/app-screens` records every way the
live system behaved differently from the mock — read it before trusting a fixture.

## Tearing down

```bash
dropdb placedon_app_local && rm -rf .local-vault
```
