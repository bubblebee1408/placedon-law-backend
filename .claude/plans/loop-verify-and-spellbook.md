# Loop runbook — reproducibility, manifest churn, deeper public competitor read

    pattern : sequential
    mode    : safe
    started : 2026-09-03
    branch  : engine/entailment

## Pre-loop checks

    uncommitted : 1 (corpus/benchmark/manifest.json — see below)
    unpushed    : 3
    suite       : all green
    hooks       : pre-commit active, ran green

## Stop condition

1. The suite no longer dirties a tracked file on every run.
2. A fresh clone of origin/engine/entailment runs the full suite green,
   closing the reproducibility half of Phase 5.
3. Spellbook's public documentation is read beyond the marketing pages, and
   any OPEN marker in SPELLBOOK_INFERRED_ARCHITECTURE that it settles is
   closed with a citation.
4. Everything committed and pushed.

## Boundaries

- Public pages only. No account, no authenticated area, no credential use.
  A vendor's login is an access control, and CLAUDE.md's rule covers it.
- An OPEN marker is closed only by a vendor statement, never by inference.
  If the docs do not say, it stays OPEN.
