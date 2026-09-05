# Loop Runbook — Week 2.1 acquisition, provenance-first

**Pattern:** sequential · **Mode:** safe · **Started:** 2026-08-21
**Branch:** `ingest/board-meeting-rules-2014`

## Governing principles

Three, taken as design constraints rather than aspirations:

1. **Provenance-first.** An output stays linked to the artifact, the fetch attempt, and the
   extraction that produced it. A conclusion whose evidence chain cannot be walked backwards is not
   servable.
2. **Claim–evidence separation.** What the system *claims* and what a source *says* are separate
   records. `G.S.R. 240(E) / 31-03-2014` is a third-party claim about the principal Rules, held as
   a lead to be checked against the document, never asserted.
3. **Minimal architecture under uncertainty.** Abstractions follow repeated confirmed cases. With
   zero acquired instruments, a source-ranking engine, agent-mode system or generic retry
   orchestrator would encode guesses. Revisit after three to five real acquisitions.

## Two axes that must never be conflated

This repo already made this mistake once: a WAF 403 was recorded as an outage, and an automated
retry got scheduled against a source that had refused us.

| Source-attempt state | Artifact classification |
|---|---|
| `ACCESSIBLE` · `BLOCKED` · `UNREACHABLE` · `NOT_FOUND` | `VERIFIED_PRINCIPAL` · `REJECTED_AMENDMENT` · `UNCONFIRMED_DOCUMENT` · `CORRUPT_OR_UNREADABLE` |

A blocked website and a wrong document are different failures with different remedies. A source can
be perfectly official and still be the wrong artifact for this task: an amendment notification is
authoritative *for its amendment* and is not the principal Rules.

## Source position — settled, do not re-probe

| Route | Result | Retry? |
|---|---|---|
| `upload.indiacode.nic.in` | ECONNREFUSED — host down | Yes |
| `indiacode.nic.in` `/handle/`, `/simple-search`, `/show-data`, `/ViewFileUploaded` | **403 — WAF** | **No** |
| `indiacode.nic.in` `/bitstream/*.pdf` | 200 | n/a — address unknown |
| `mca.gov.in` | 403 | No |
| `egazette.gov.in` | 200, stateful form | Human |

Four distinct dynamic endpoints return 403. That is settled. **Further probing is prohibited** —
repeatedly testing a source that has refused us is what the block exists to stop, whatever the
intent behind it.

## Stop condition (hard)

The loop ends in exactly one of two states, both terminal:

- **`VERIFIED_PRINCIPAL`** — the principal Rules PDF is in `corpus/sources/`, hashed, its own text
  confirms its identity, and all suites are green.
- **`HUMAN_RETRIEVAL_REQUIRED`** — automation has no compliant path left. **This is a success**,
  not a failure. It is the correct outcome when the alternative is guessing.

`VERIFIED_PRINCIPAL` means *identity confirmed*, not *reviewed*. `human_reviewed` stays False until
a person reads the document; `can_promote()` enforces that separately.

> **A safe stop with precise provenance is a successful outcome. A false acquisition is a failure.**

## What discovery failure does and does not mean

Failure to find the file means **the official path is unresolved right now**. It does not mean the
instrument is absent, withdrawn, or unavailable. Nothing in this repo may record it as missing.

## Out of scope

Source-ranking engine · agent-mode system · generic retry scheduler · multi-source orchestration ·
generalised instrument catalogue · parsing rule text · rule→section linking · applicability rules.

## Monitor

```bash
cd ~/PlacedOn/placedon-law-backend
./scripts/run_tests.sh
python3 -c "import json;d=json.load(open('reports/acquisition_board_rules_2014.json'));print(d.get('terminal_state'))"
```
