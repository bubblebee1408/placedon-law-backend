# Loop Runbook — Week 2.1: acquire the Meetings of Board Rules 2014

**Pattern:** sequential · **Mode:** safe · **Started:** 2026-08-21
**Branch:** `ingest/board-meeting-rules-2014` (base: `feature/ss-defect-scan`)

## Scope — acquisition and provenance only

Obtain the Companies (Meetings of Board and its Powers) Rules, 2014 from India Code, store the
artifact in-repo, hash it, and register a `SourceRecord`. **Provenance is recorded before the text
is parsed**, not after.

**Explicitly OUT of scope.** Do not do these even if they look like the obvious next step:
parsing rule text into records · rule→section linking · applicability rules · effective-date
modelling · a rule index · UI · any write to `corpus/companies_act/`.

## Stop condition (hard) — either outcome ends the loop

**SUCCESS:** the Rules PDF is stored under `corpus/sources/`, hashed into `SHA256SUMS`, registered
in `checker/provenance.py` as an `ACCESSIBLE` source with a retrieval date, and all suites green.

**BLOCKED:** India Code refuses the document (403/timeout/removal). The loop then records a
`SourceRecord` with `accessibility=BLOCKED`, writes the failure to the claims ledger, and **stops**.
BLOCKED is a legitimate terminal state, not a reason to keep trying.

Either way the loop reports and halts. It does not proceed to parsing.

## Prohibited fallbacks — the failure mode this guards

If India Code is unavailable, **do not** substitute `ca2013.com`, `vlex.in`, `taxguru.in`, `thc.nic.in`,
or any other reproduction. They are not permitted sources under `docs/SOURCE_POLICY.md` and their
fidelity to the gazetted text is unestablished. An unofficial copy that is 99% right is worse than
no copy, because it is indistinguishable from the real thing at the point of use.

Do not bypass the WAF, robots restrictions, or access controls (CLAUDE.md). A 403 is an answer.

## Pre-flight (verified 2026-08-21)

- [x] Branch created off clean tree
- [x] 9 suites / 223 checks green via `./scripts/run_tests.sh`
- [x] `ECC_HOOK_PROFILE` unset (hooks active)
- [x] Explicit stop condition, including a defined BLOCKED outcome

## Tasks

### T1 — Locate the official document
India Code serves subordinate legislation from an upload path with `type=rule`. Confirm the URL
resolves and is the 2014 Rules as made, noting any amendment status shown.
**Done when:** a URL returns the document, or every official candidate is exhausted and recorded.

### T2 — Record the source BEFORE parsing
Add a `SourceRecord`: url, retrieval date, accessibility, official=True, local artifact path, and
sha256 of the stored bytes. `human_reviewed` stays False until a human has actually read it —
`can_promote()` will refuse VERIFIED until then, which is correct.
**Done when:** `checker/provenance.py` tests pass with the new record.

### T3 — Store and hash the artifact
Write to `corpus/sources/`, append to `SHA256SUMS`. The Week 1 lesson: an artifact in `/tmp` is not
an artifact.
**Done when:** `artifact_present()` and `artifact_matches_hash()` both hold in the suite.

### T4 — Report and halt
Print outcome, evidence state, and what Week 2.2 may now assume. Do not start 2.2.

## Safety gates per iteration

1. Existing suites stay green — a regression stops the loop rather than being worked around.
2. One task, one commit, conventional message.
3. No scope expansion. New ideas go to the ledger, not into this loop.
4. Read-only fetches. No credentials, no WAF evasion, no unofficial mirrors.
5. If the document's identity is uncertain (wrong year, amendment vs principal rules), stop and
   report rather than guessing which instrument it is.

## Monitor

```bash
cd ~/PlacedOn/placedon-law-backend
git log --oneline ingest/board-meeting-rules-2014 ^feature/ss-defect-scan
./scripts/run_tests.sh
```
