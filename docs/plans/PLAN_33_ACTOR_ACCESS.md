# Actor identity and matter access

## Status — 19 October 2026

This change is the first security prerequisite for individual matter access. It does
**not** enable confidential multi-lawyer use. Current persistent artifact policies
remain tenant-scoped. A shared frontend passcode still represents one backend actor.

## Reproduced failures

- A second authenticated actor in the same tenant could resolve the first actor's
  temporary uploaded text and filename from the process cache.
- The gateway reused the first actor's PostgreSQL queue when a second actor in the
  same tenant submitted work. The job record could therefore name the wrong actor.
- Job decoding discarded the stored actor identity, and workers used a fixed store
  and handler context. Work could run with the operator's identity.

## First implementation

Affected files: `gateway/document_cache.py`, `gateway/app.py`, `gateway/jobs.py`,
`gateway/worker.py`; regression tests and the counted offline test wrapper.

1. Require tenant and authenticated actor for every temporary-cache view. Partition
   reads, listings, writes and deletes; retain aggregate tenant/global memory limits.
2. Construct the submission queue for the authenticated actor. Ignore actor identity
   in request/job argument objects.
3. Carry persisted tenant/actor fields on decoded jobs. Restore a matching store and
   handlers for each durable job, and recheck active actor/role before invoking it.
4. Refuse missing or mismatched execution identity. Do not invoke a model or handler
   when identity cannot be established. Preserve explicit failure/retry accounting.
5. Retain the shared-workspace warning. No migration, account grant or access claim
   is implied by these fixes.

Verification: reproduce before fixing; run same-tenant cache/HTTP simulations;
exercise two actors through PostgreSQL queue submission and worker execution;
verify disabled actors, spoofed payloads and mismatched execution stores; run the
repository gate and independent code/security review. Use synthetic data only.

## Deployment prerequisite

Queued work now consults the current database actor record. The operator must verify
that the service actor explicitly has the `lawyer` or `admin` role and is not disabled.
An API key labelled `admin` does not override a database `viewer` or revoked actor.
Do not automatically promote existing actors to make a test pass. Provision only the
intended service identity through the existing administrative account workflow.
A worker started with only a tenant may claim that tenant's jobs, but restores the
submitting actor separately for each job. Memory mode remains a synthetic test mode.

## Next migration: complete matter access

Policy: filed artifacts require active matter membership; unfiled artifacts belong
only to their recorded creator. Account administration alone grants no document
access. Unknown historical ownership fails closed. Derived artifacts must not widen
the source's access scope.

- Add matter membership and explicit owners to matters, vault and legacy documents.
- Populate run/conversation/draft/grid ownership and matter scope consistently.
- Apply restrictive actor/matter RLS alongside tenant isolation, with parent-sensitive
  rules on messages, steps, propositions, decisions, chunks, tags, checks, versions,
  review cells and saved evidence. Two permissive policies would OR their conditions
  and are insufficient.
- Scope answer caches, deduplication, search counts and file bytes. Prevent filename
  or existence disclosure through duplicate-upload errors.
- Recheck membership on queued execution and result publication; current actor/role
  rechecks do not establish matter membership or mid-execution revocation protection.
- Audit API, MCP, CLI and binary export paths together. Matter lists alone are not
  the access boundary.
- Inventory and quarantine ownerless historical records; preserve rows and backups.
  Any reassignment needs an explicit audited administrative action.

Acceptance matrix: member/nonmember/revoked member in one tenant plus a second tenant;
read/write/list/search/export/replay/cancel/approve paths; unfiled ownership; pooled
connection context reset; revocation before and during jobs. Test using a PostgreSQL
role with neither superuser nor BYPASSRLS and two independent browser accounts.

## Remaining product milestones

After access control: evaluated full-document summaries with claim-to-evidence mapping;
page-preserving extraction and OCR evaluated on public/synthetic Indian documents;
retention rules for saved excerpts; separately verified live case research and reviewed
Indian drafting templates. Current exact excerpts are not complete summaries or legal
verification, and these hardening tests do not establish provider accuracy.
