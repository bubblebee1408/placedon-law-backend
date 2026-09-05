# Loop Runbook — Week 2.1 completion watch

**Pattern:** sequential · **Mode:** safe · **Started:** 2026-08-21
**Branch:** `ingest/board-meeting-rules-2014`

## The loop builds nothing

Acquisition infrastructure is finished and further building is out of scope. The blocking step is a
**human downloading one PDF**. This loop exists only to complete the handoff the moment that
happens, so the result does not wait on someone remembering a command.

**Watch:** `~/Downloads/placedon-review/`
**On a PDF appearing:** run `python3 scripts/acquire_rules.py <file>` and report the classification
verbatim.

## Stop condition (hard)

The loop ends as soon as the verifier produces any one of:

`VERIFIED_PRINCIPAL` · `REJECTED_AMENDMENT` · `UNCONFIRMED_DOCUMENT` · `CORRUPT_OR_UNREADABLE`

All four are terminal. **A refusal is a result, not a failure** — `REJECTED_AMENDMENT` in particular
demonstrates the guard doing the exact job it was built for.

## Prohibited, without exception

- Overriding or weakening a refusal to make a file pass.
- Copying anything into `corpus/` — `VERIFIED_PRINCIPAL` means identity matched, nothing more.
  Storage is a separate, reviewed step.
- Probing the four blocked India Code endpoints (`/handle/`, `/simple-search`, `/show-data`,
  `/ViewFileUploaded`). All return 403. This is settled.
- Brute-forcing URL variants.
- Recording the instrument as missing. Discovery failure ≠ absence.
- Promoting `G.S.R. 240(E)` to verified from secondary references.
- Writing any rule logic from memory.

## Correct test command

```bash
./scripts/run_tests.sh          # 11 suites, 314 checks
```

**Do not use `python3 -m pytest`.** Verified on 2026-08-21: it collects **zero tests and exits 0**.
This repo uses self-testing modules, not pytest files, so pytest reports a clean pass having run
nothing at all. A false green is worse than an error, and this exact class of mistake already
happened once here with `checker/as_of.py`.

## If the result is UNCONFIRMED_DOCUMENT

Do **not** weaken the classifier. The likeliest cause is that the G.S.R. line sits outside the first
three extracted pages — an extraction-window problem, not a wrong document. Diagnose in this order:

1. Show the exact text the classifier saw.
2. Name which identity signals were missing.
3. Decide: principal, amendment, consolidated, or incomplete?
4. Decide: extraction problem or identity problem?
5. Only then, the smallest test-backed change — if any.

## If the result is REJECTED_AMENDMENT

Keep the file and its hash. An amendment is authoritative *for its own amendment* and is real
evidence; it is simply the wrong artifact for this task. Report the triggering language, the hash,
and confirm it was not written into the principal-rules record.

## Monitor

```bash
ls -la ~/Downloads/placedon-review/
cd ~/PlacedOn/placedon-law-backend && ./scripts/run_tests.sh
```
