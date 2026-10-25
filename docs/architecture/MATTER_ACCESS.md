# Per-matter access (028)

Status: implemented on branch `claude/matter-access-control-20261025`. Enforced twice, by
the database (`gateway/migrations/028_matter_access.sql`) and by one shared check in the
application (`gateway/access.py`).

## The rule

| Row | Read | Write |
|---|---|---|
| Filed (`matter_id` set) | any active grant on the matter | grant role `owner` or `member` |
| Unfiled, with an owner | the owner (`actor_id`, or a document's `uploaded_by`) | the owner |
| Unfiled document shared firm-wide | everyone in the firm | the uploader |
| Unfiled, no recorded owner (pre-028) | nobody, until an admin runs `access.reassign` | nobody |

Grants live in `matter_memberships`: explicit, append-only (a revoke sets `revoked_at` and
nothing is deleted), and each has a granted-by and a reason. Nothing is inferred from tenant
membership. Firm admins see matter metadata (names and members) so they can administer
access. They do not see a matter's contents unless they hold a grant.

Identity is taken only from the authenticated principal. `app.py` builds `Context(actor,
role)` from the session or API key, and each DB connection sets `app.tenant_id`,
`app.actor_id` and `app.actor_scope` on every checkout (`gateway/pool.py:set_identity`).
Those settings are reset to empty when absent, so a pooled connection never inherits the
previous caller's actor. Inaccessible and nonexistent matters return the same refusal
(`access.NOT_AVAILABLE`).

Instead of one broad service scope, there are three narrow scopes. Each is named only in
the policies it needs, and `set_identity` refuses any other value:

| Scope | Set by | Reaches | Never reaches |
|---|---|---|---|
| `queue` | `jobs.py` (every queue connection) | `jobs` (the only scope that reads them); in `runs`, only a PLANNED/RUNNING run whose job is DEAD, to set it FAILED | finished runs (answers), run steps, propositions, decisions, cascades, conversations, messages, vault documents/chunks/tags, drafts, grids, cache, matters, grants |
| `grant_bootstrap` | `store.write_matter`, transaction-local | INSERT into `matter_memberships`, only as a self-grant of `owner` (`actor_id = granted_by = app.actor_id`) | any read, any other grant |
| `reassign` | `store.list_unowned` / `reassign_work`, transaction-local, behind ADMIN verbs | the metadata row of ORPHANED work (unfiled, no owner): conversations, drafts, review tables, vault documents. The row it changes stays visible only in the transaction that recorded the change in `access_events` | filed rows, anyone's own unfiled work, chunks, tags, messages, draft versions, grid cells, runs, jobs, cache, matters |

The worker uses no scope. A job whose access was revoked is dead-lettered through the
queue's existing reconcile.

Child tables (messages, run steps, propositions, decisions, cascades, draft versions, grid
columns and cells, chunks, tags, document checks) check their parent's matter and owner
explicitly. They never ask only "is the parent visible?", because that would hand them
every scope the parent admits. `tests/test_matter_access_postgres.py` seeds every one of
them as another actor (filed, unfiled and orphaned) and counts each under each scope.

The answer cache is partitioned the same way: an entry is reused only inside the matter it
was asked in, or by the one actor who asked it unfiled (`verbs._cache_partition`, and
`answer_cache.actor_id`/`matter_id` under the same policy). A hit never carries the
original ask's `run_id`.

## Inventory: verbs that touch matter data

| Verb | Reads / writes | Check |
|---|---|---|
| `conversation.send` | conversation, messages, run, vault docs, queued job | `require_matter(WRITE)`; existing thread `row_allowed`; each file `document_allowed`; run tagged with the matter |
| `conversation.get` / `conversation.list` / `citation.get` | conversation, messages | `row_allowed` / `require_matter(READ)` |
| `matters.create` / `matters.list` | matters, first grant | creator becomes owner; list = own grants (admin: all metadata); existing ids refused with one sentence |
| `matters.grant` / `revoke` / `members` / `access_report` | grants, unowned-work list | ADMIN role and DB policy (`membership_insert`) |
| `vault.upload` | vault doc, blob, ingest run and job | `require_matter(WRITE)`; uploader recorded from the session |
| `vault.list` / `status` / `verify` / `summarize` / `compile` / `delete` | vault docs, chunks, tags | `require_matter` / `document_allowed` (delete: WRITE) |
| `vault.find` / `vault.research` | chunks (search index) | index built only from readable documents. **Was firm-wide.** |
| `vault.share` | doc share flag, `access_events` | uploader only |
| `access.reassign` | owner or matter of unfiled work, `access_events` | ADMIN; `reassign` scope; unfiled work only, never filed work |
| `document.verify` / `document.check` | vault doc, chunks, `document_checks` | `document_allowed` |
| `runs.get` / `trace` / `approve` / `reject` | run, steps, decisions | `row_allowed` (approve/reject: WRITE) |
| `runs.cancel` | job (via the queue) | run `row_allowed(WRITE)` first. **Previously any lawyer could cancel any run.** |
| `runs.submit` | run, job | `args_allowed` on the payload's matter, conversation and documents |
| `review_table.*` | grid, cells, blob by hash | `row_allowed`; each hash must be the caller's own cache entry or a readable document. **Previously any known hash read any file.** |
| `draft.*` | draft, versions | owner-private (drafts are never filed) |
| `jobs.dead` | dead jobs (args may hold questions) | own jobs; admin sees all |

These verbs do not touch matter data: `ask`, `research.*`, `sources.*`, `forecast.summary`,
`events.assess`, `company_facts.extract`, `intake.classify`, `calendar.upcoming`,
`usage.status`, `runs.preview`, `auth.*`, `invites.*`. `documents.upload` uses the per-actor
process cache.

## Inventory: background-job paths

| Intent | Re-checked | What is checked |
|---|---|---|
| all | `worker.run_one` on job start and again before publishing the result | `access.job_allowed`: run writable by the job's actor; args' matter, conversation and grid writable; documents (uuid or content hash) readable |
| `vault_ingest`, `document_summary`, `review_grid_cell` | also inside the handler | writes go through the actor's store, so RLS blocks them after revocation |

On revocation the job goes DEAD and the run is FAILED with `worker.ACCESS_REVOKED`. No
result is written.

## Known limits (not fixed here)

- Matter names are unique per firm (`matters_tenant_name_idx`), so creating a matter whose
  name is already taken reveals that a matter with that name exists.
- `documents` (001, the legacy hash registry) remains tenant-scoped.
- Runs created before 028 carry no matter, so colleagues who are later granted the matter
  cannot open those old runs. The owner still can, and the conversation's stored answer
  stays readable.
- Only orphans are reassigned. Unfiled work owned by someone who has since been disabled
  stays theirs, and so is unreachable, until that is decided separately.

## Applying 028 to a populated database

The app role cannot back up rows that row-level security hides, so `--apply` refuses on a
database with data unless a backup role is named. That role is a superuser or BYPASSRLS role
on the same database, and it is used only for `pg_dump`. The migrations still run as the
app role:

    scripts/migrate.py --plan  --url "$APP_URL"
    scripts/migrate.py --apply --url "$APP_URL" --backup-url "$BACKUP_URL" --backup-dir <dir>

`--apply` checks that the backup URL reaches the same database. It reads the archive back
with `pg_restore --list`, and requires a data section for every table, before applying
anything. It never overwrites or deletes an earlier backup.
`tests/test_matter_access_upgrade_postgres.py` runs this procedure on a populated
pre-028 database, then runs the admin regain path.
