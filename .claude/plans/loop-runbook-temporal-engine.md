# Loop Runbook — Companies Act Temporal Engine

**Pattern:** sequential · **Mode:** safe · **Started:** 2026-08-17
**Branch:** `engine/companies-act-temporal` (base: `main`)

## Scope — core engine only

Build India Code ingestion, the amendment-footnote parser, and point-in-time
reconstruction for the Companies Act 2013.

**Explicitly OUT of scope for this loop.** Do not build any of these, even if they seem next:
UI · drafting · matter workspaces · compliance tracking · team features · dashboard ·
payments · vector search · Neo4j · OCR · a second statute · anything touching RBI as a source.

## Stop condition (hard)

> `section_as_of(section, date)` reconstructs **s.2** and **s.96** correctly at **three past
> dates each**, hand-verified against the amending instruments, with all existing tests still green.

When that holds, the loop stops and reports. It does not continue to the next idea.

## Pre-flight (verified 2026-08-17)

- [x] Branch created off clean `main`
- [x] `checker/verifier.py` — 16/16 passed
- [x] `checker/test_unlock.py` — all passed
- [x] `applicability.py` — 10/10 passed
- [x] `ECC_HOOK_PROFILE` unset (hooks active)
- [x] Explicit stop condition above

## Tasks, in dependency order

Each task ends with tests green and a commit. No task starts before the previous one's
done-condition holds.

### T1 — Section enumeration
The one genuine unknown. A single fetch of the act page yields only ~44 of ~470 section links;
the pagination parameter is unverified. IDs are **not** guessable (s.1→184, s.2→185, but
s.3A→48973, s.10A→49492) — parse anchors, never iterate integers.

- Act page: `/handle/123456789/2114`
- `actid=AC_CEN_22_29_00008_201318_1517807327856`
- **Done when:** all ~470 sections enumerate reproducibly across two runs with matching output.

### T2 — `scripts/ingest_companies_act.py`
Template is the existing `ingest_posh.py`. Source is the JSON endpoint:
`/SectionPageContent?actid=<actid>&sectionID=<id>` → `{"footnote":…, "content":…}`

Store per section: content, footnote, sha256, source URL, fetch timestamp. Same JSON shape as
`corpus/provisions/posh_act_2013.json` so downstream code is untouched.

Text is born-digital — **no OCR**. If falling back to the PDF, normalise spurious intra-word
spaces (`"an d preserve"`, `"sub -section"`).

- **Done when:** s.2 and s.96 ingest with stable hashes; `check_transcription.py` passes.

### T3 — `checker/amendment.py` — footnote parser
The component that does not exist anywhere else. Grammar:

```
{Subs.|Ins.|omitted} by Act <n> of <year>, s. <sec> (w.e.f. <DD-M-YYYY>)
Ins. by S.O. <num>(E), dated <date>
ibid.                                  # back-ref to preceding citation
```

Pair each footnote marker with its inline `1 [ … ]` span in `content`.
Emit `(marker_id, span_start, span_end, operation, instrument, wef_date)`.

- **Done when:** s.2 parses (16+ markers including the `S.O. 1894(E)` gazette insert) and 20
  hand-checked sections round-trip.

### T4 — `section_as_of(section, date)`
Apply/revert marker spans against their `w.e.f.` dates. Return reconstructed text **plus** the
instruments in force at that date.

- **Done when:** the stop condition above is met.

### T5 — Change detection
`Last Updated` on India Code is stale and unusable — it reads 22-04-2019 while s.2 carries an
amendment `w.e.f. 22-1-2021`. Diff `SectionPageContent` responses by hash instead.

- **Done when:** a hash change is detected and reported on a re-fetch.

### T6 — `DerivedDate` in the verifier
Per `docs/TECHNICAL_PLAN_CORPORATE.md` §0. Verify the **interval**, not the result.
`interval_text` must appear verbatim in the cited provision; the result is derived, never
retrieved or generated.

- **Done when:** a correct AGM deadline passes the verifier and a fabricated figure still dies.
  Existing 16/16 stays green.

## Legal constraints binding every task

- **s.52(1)(q)(ii):** Act text may only ever be served **together with original matter**. Never
  emit bare statutory text. **Never build a clean-statute browser or Act download.**
- **Gazette matter is clean** under (q)(i) — prefer the gazetted instrument where one exists.
- Attribute Indian Kanoon prominently if used as a fallback source.

## Safety gates per iteration

1. Existing tests stay green — a regression stops the loop, it does not get worked around.
2. One task, one commit, conventional message.
3. No scope expansion. New ideas go to `BACKLOG.md`, not into this loop.
4. No network writes; read-only fetches from India Code only.
5. If T1's pagination parameter cannot be found after reasonable effort, **stop and report** —
   do not fall back to integer iteration, which silently misses inserted sections.

## Monitor

```bash
cd ~/PlacedOn/placedon-law-backend
git log --oneline engine/companies-act-temporal ^main
python3 checker/verifier.py && python3 checker/test_unlock.py && python3 applicability.py
```

## Out-of-loop, human-gated

These are not the loop's work and it must not attempt them:
30 validation interviews (10 CS, 10 corporate lawyers, 10 CAs) · Indian Kanoon free-tier
application · counsel question on whether machine-generated commentary satisfies s.52(1)(q)(ii) ·
ICSI query for the Certificate-of-Practice count.
