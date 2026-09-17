# D-002 — closure report, and what it did *not* fix

**Date:** 2026-09-17 · **Branch:** `loop/bookmark-godseye-v0` · **Status: CLOSED, MEASURED**

Every number below was produced on this machine today and is tagged. Tags follow
[PLAN_00_INDEX](PLAN_00_INDEX.md): **MEASURED** (produced here, reproducible) ·
**SOURCED** (primary source, recorded) · **INFERRED** (reasoning) ·
**UNVERIFIED** (believed, unchecked) · **BLOCKED**.

> **Read §5 before celebrating.** D-002 is genuinely closed. The thing it was
> expected to unblock — the Board Rules re-extraction — **was not unblocked**, and
> the reason is a separate defect in the source document itself. That finding is
> worth more than the fix.

---

## 1. Result in one table

| Measure | Before | After | Tag |
|---|---|---|---|
| Census agreement with the independent oracle | **0 of 14** | **14 of 14** | MEASURED |
| Repo reader page labels | `{NO_TEXT_EXTRACTED: 133, TEXT: 2}` | `{NO_TEXT_EXTRACTED: 2, SUSPECT: 18, TEXT: 494}` | MEASURED |
| Oracle page labels (unchanged control) | `{NO_TEXT_EXTRACTED: 2, SUSPECT: 18, TEXT: 494}` | identical | MEASURED |
| Documents the reader failed on entirely | 4 | **none** | MEASURED |
| Test gate | 163 suites, 0 failed, GREEN | **164 suites, 0 failed, GREEN** | MEASURED |
| New suite `checker/pdf_pages.py` | — | **13/13 passed** | MEASURED |

**The repo reader's labels now match the oracle's exactly, field for field.** That
is a stronger result than the ≥13/14 target in the execution plan.

### 1.1 Per-document, the four that were worst

| Document | True pages | Old reader | New reader | Tag |
|---|---|---|---|---|
| `icsi_gn_board.pdf` | 169 | **1** | **169** | MEASURED |
| `icsi_gn_general.pdf` | 179 | **0** | **179** | MEASURED |
| `route_agm_2024.pdf` | 22 | **37** | **22** | MEASURED |
| `sonata_agm_notice_29th_2024.pdf` | 18 | 18 pages, **0 with text** | 18 pages, **18 with text** | MEASURED |

---

## 2. There were two defects, not one

**Defect 1 — compressed object streams.** `pdf_text.extract_pages` located pages by
running a regex over **raw file bytes** for `/Type/Page`. In PDF 1.5+ the page
objects and the cross-reference table live inside zlib-deflated object streams
(`/Type/ObjStm`) and cross-reference streams (`/Type/XRef`). A byte regex cannot see
inside a deflate stream. **MEASURED**: of 27 PDFs surveyed, those with `ObjStm=True`
undercounted to 0 or 1; `route_agm_2024.pdf` *over*counted to 37 because it carries
**4 `%%EOF` markers** — stale page objects from earlier incremental revisions are
still physically in the file, and a byte regex counts all of them.

**Defect 2 — the `/Contents` look-ahead window.** Independent of the first, and not
anticipated. `pdf_text.py:217` searched for `/Contents` only in the **400 bytes
following** the `/Type/Page` match. Many writers emit `/Contents` *before*
`/Type/Page` in the same dictionary. **MEASURED**:

| Document | Pages | `/Contents` inside the forward window | Only behind (missed) |
|---|---|---|---|
| `titan_agm_2026.pdf` | 15 | 2 | **12** |
| `sonata_agm_notice_29th_2024.pdf` | 18 | **0** | **17** |

Both those files have **no object streams at all**. So Defect 2 would have survived
a perfect fix for Defect 1 — the standard-library path was two parsers, not one.

### 2.1 Why this survived 163 green suites

**MEASURED, and it is the most transferable finding here.** `pdf_text.py`'s only
wired-in fixture was `companies_meetings_board_powers_rules_2014.pdf` — **PDF 1.4,
`ObjStm=False`**. The single test guarding the reader used the one corpus file that
is structurally immune to the bug.

This is the same disease as the old masking incident recorded in
`harness_regression.sh`: a green check that cannot fail. A test whose fixture cannot
exhibit the defect is not evidence, and the harness cannot tell the difference.

---

## 3. The decision, and the reasoning that is not obvious

**D-2, decided by the founder 2026-09-17: adopt `pypdf`, offline paths only.**

| Option | Measured cost | Outcome |
|---|---|---|
| Fix in the standard library | **~400–450 LOC**, medium confidence — xref streams with variable `/W` widths, `/Prev` chain walking with loop guards, ObjStm inflation, a balanced-bracket dict parser, page-tree DFS with cycle guards, **plus** Defect 2. Pure-Python AES a live risk on the first encrypted gazette | Rejected — that is a PDF parser, and every line can be quietly wrong about the source text of the law |
| **`pypdf` 6.16.1** | **BSD-3-Clause, pure Python, zero mandatory transitive dependencies**. Already importable; **nothing was installed** | **ADOPTED** |
| PyMuPDF / fitz | **AGPL-3.0 or paid Artifex commercial licence** (SOURCED, from installed package metadata) | **Rejected on licence.** AGPL §13 extends copyleft to network use; in a served backend sold to Indian corporates it would compel disclosure of the whole product |
| pdfplumber 0.11.10 | Already declared in `requirements-dev.txt`, so nominally free | **Rejected for a subtler reason — §3.1** |

### 3.1 Why not pdfplumber, which was already there

`scripts/text_layer_census.py` uses **pdfplumber as the independent oracle that
judges this repository's reader**. Adopting it as the production reader would make
the census compare pdfplumber against pdfplumber, and the verification instrument
would stop being evidence.

`pypdf` is its own parser; `pdfplumber` wraps `pdfminer.six`. **Two engines, so the
two-reader census stays honest.** That, not dependency count, is the argument.

### 3.2 The boundary that keeps the README true

The README claims *"no dependencies outside the standard library."* **MEASURED**:
`checker/api.py` and everything under `backend/` contain **zero** references to
`pdf_text`, `pdf_pages`, `pypdf`, `pdfplumber` or `fitz`. Every consumer of page
extraction is offline tooling — `checker/sweep.py` and five scripts.

`requirements.txt` (runtime) is **untouched**. `pypdf` belongs in
`requirements-dev.txt`. `checker/pdf_pages.py::_test()` **asserts** this boundary
rather than trusting it, in the same spirit as `api.py`'s existing assertion that
the API imports no model library.

---

## 4. What changed

| File | Change | Tag |
|---|---|---|
| `checker/pdf_pages.py` | **NEW** — pypdf-backed reader, offline only. Raises `PdfUnreadable` rather than returning `[]`; handles encryption by trying the empty password and raising otherwise | MEASURED 13/13 |
| `scripts/run_tests.sh` | Registered the new suite after `checker/pdf_text.py` | 163 → 164 |
| `scripts/text_layer_census.py` | Repo-reader import switched; **oracle left as pdfplumber** | MEASURED |
| `scripts/parse_board_rules.py` | Import switched; `"extractor"` metadata updated | MEASURED |
| `scripts/review.py` | Import switched; two column titles updated | MEASURED |
| `checker/pdf_text.py` | **Untouched.** `extract_text` / `has_extractable_text` work on all 14 and remain stdlib | — |
| `requirements.txt` | **Untouched** | — |

**`requirements-dev.txt`** now declares `pypdf==6.16.1` (N1, done — the pin matches
the installed version exactly, verified). Before that declaration the suites passed
only because the package happened to be on this laptop; a fresh clone or CI runner
would have failed. The declaration carries its reasoning inline, including why
pdfplumber above it is retained as the oracle.

---

## 5. What the fix did NOT fix — the finding that matters

The execution plan predicted this fix would unblock the Board Rules re-extraction
(the 30 queued review items, some carrying **578 split words**). **It does not.**

**MEASURED**, split words in `companies_meetings_board_powers_rules_2014.pdf`:

| Reader | Whole document | Pages 13–22 (the rules) | Pages 1–12 |
|---|---|---|---|
| stdlib (old) | 1,499 | — | — |
| **pypdf (new)** | **1,474** | **1,458** | 16 |
| **pdfplumber (oracle)** | **1,367** | **1,350** | 16 |

Three independent engines agree within **8%**. The splits are **not** in the Hindi
pages (16 on every reader) — they are concentrated in the **English rule text**, on
exactly the pages under review.

**Conclusion (INFERRED from three agreeing measurements): the gazette's own English
text layer has broken word spacing.** No reader fixes it, because it is a property
of the source. Under `CLAUDE.md` — *"Never repair a defective government source.
Flag it, preserve it verbatim"* — it must not be silently rejoined.

**A second, softer correction.** An earlier claim of mine — that a reviewer facing
this text would be "doing OCR correction, not legal review" — was **too strong**.
`scripts/review.py` presents the parsed rule's `text_raw` beside the gazette page
text in two columns, so splits appear in *both* and the structural questions
(boundary, heading fidelity, page bounds) remain answerable. The brief's fourth
question — *"Is the extracted text usable for legal reasoning?"* — is precisely the
judgement being asked of the human, and it is a legitimate one to ask.

**And for this specific file the switch is roughly neutral.** MEASURED on pages
13–22: stdlib 6,051 words, pypdf 5,852, oracle 5,532; all three find
*"Meetings of Board through video conferencing"*, *"Contract or arrangement with a
related party"* and *"vigil mechanism"*. The old reader was never broken on *this*
document. **The value of the fix is entirely on the other thirteen.**

---

## 6. Next execution plan

| # | Task | Done when | Gate |
|---|---|---|---|
| **N1** | **Declare `pypdf==6.16.1` in `requirements-dev.txt`.** Today the suites pass only because it happens to be installed on this laptop | A fresh-clone simulation (`python3 -c "import pypdf"` under a clean env, or the declaration reviewed) confirms the gate is reproducible elsewhere | **DO FIRST** |
| **N2** | **Commit.** `pdf_pages.py`, the 4 switched files, the run_tests registration — plus the still-uncommitted `accept.mjs` (+150/−29) and 5 new docs | `git status` clean; gate 164 GREEN | Founder approval outstanding |
| **N3** | **Decide the split-word question.** Three options: (a) accept as a source defect, record in `SOURCE_DEFECTS.md`, let the reviewer judge; (b) acquire a cleaner rendering of the same instrument; (c) reject (c)-style automated rejoining as source repair | A decision written down with its reason | **Founder — this now gates the 30 items, not D-002** |
| **N4** | **Regenerate `reports/review_brief.md`** once N3 is decided | Brief reflects the current reader and the agreed split-word treatment | After N3 |
| **N5** | **Human review of the 30 items** | Decisions recorded via `scripts/review.py --next` | After N4 |
| **N6** | **Retire or fence `pdf_text.extract_pages`** so the broken path cannot be reached again | Either deleted, or raising with a pointer to `pdf_pages` | Low risk, high value |
| **N7** | **Add an ObjStm fixture to any future reader test** | No reader suite relies solely on a PDF 1.4 fixture | Generalises §2.1 |
| **N8** | **H-C** — one practising Company Secretary reacts to the pack | Written reactions in `docs/research/` | **Still the product gate** |

---

## 7. Mistakes recorded this session

| # | Mistake | Correction |
|---|---|---|
| S5 | **Predicted the fix would unblock the Board Rules.** It did not; the splits are a source defect | §5. Measured against three readers before claiming it |
| S6 | **Overstated the review blocker** — said mangled text made human review impossible without reading how `review.py` presents it | §5. It shows two columns; the structural checks survive |
| S7 | **Nearly shipped the fix without checking text quality**, having seen page counts agree 14/14 | Caught by comparing word counts and split counts before regenerating anything |

The pattern across S5–S7: **page-count agreement is not text-quality agreement.**
The census measures the first. It was never designed to measure the second, and I
briefly read it as if it did.

---

## 8. Unverified, and deliberately not claimed

- **Behaviour outside the 27-file corpus is UNVERIFIED**, particularly whether
  future India Code / eGazette acquisitions are encrypted. None currently are.
- **pypdf's Devanagari handling is poor and UNMEASURED as a defect.** It emits raw
  glyph names (`/g7079/uni092A`) where the oracle emits CID codes
  (`(cid:14)`). Both are unusable; neither was scored. It inflates character counts
  ~3× on Hindi pages, which could distort any future heuristic that reads document
  length. **Flagged, not fixed.**
- **The 17 OCR-over-scan pages remain flagged and unrepaired**, exactly as before.
- **No accuracy claim** for the engine follows from any of this. No practising
  lawyer has reviewed any output, and there is still no real-document benchmark.

---

## 9. Addendum — execution run, 2026-09-17 afternoon

### 9.1 Committed

| Commit | Contents |
|---|---|
| `4b719f7` | `feat:` the new reader, its suite registration, the `pypdf` declaration |
| *(pending)* | `fix:` retirement of the broken reader, four caller switches, regenerated census, **SD-005** |
| *(pending)* | `docs:` the five planning documents |

**Scoped deliberately.** A concurrent session is committing in this repository —
HEAD moved from `ea627b7` to `95cbb08` (six commits) during this run, and
`gsr700e_2022_egazette.pdf` / `gsr700e_registration.json` / `SHA256SUMS` were
modified at 15:18 by that session. **None of its files were staged.** Verified
before each commit with an explicit `grep` guard over the staged set.

### 9.2 SD-005 recorded

The split-word finding is now a numbered source defect in
[SOURCE_DEFECTS.md](SOURCE_DEFECTS.md), with the three-engine table and the
explicit refusal to rejoin. **This, not D-002, is what now gates the 30 review
items.**

### 9.3 A cost this fix introduced — MEASURED

`core.hooksPath` is `.githooks`, and `.githooks/pre-commit` runs
`scripts/verify_green.sh` **synchronously** on every commit. Adding
`checker/pdf_pages.py` to the suite list therefore lengthened **every future
commit**, not just the gate: the new suite reads a 169-page and a 179-page
document, adding roughly 40 seconds.

**INFERRED, worth deciding later:** if commit latency becomes a problem, the two
large fixtures could move behind an env flag that CI always sets, so local commits
stay fast while the evidence still runs somewhere. Not done — a fast gate that
skips the regression is how this defect survived in the first place.

> **A mistake made during this run.** The first commit appeared to hang and I
> killed it at ~2 minutes. It was not hung; it was the pre-commit gate doing
> exactly its job. I had checked `.git/hooks/` and found nothing, without checking
> `core.hooksPath`. **Recorded as S8:** absence of evidence in the default location
> is not evidence of absence when the config can relocate it.

### 9.4 H-C is not blocked on preparation — MEASURED

`H001_FIND_A_CS.md` (118 lines) and `H001_OUTREACH.md` are **complete**: a
ten-candidate funnel, copy-paste LinkedIn post, search strings, the order to show
things in, and `scripts/record_interview.py` to capture per-row verdicts rather
than sentiment.

The outreach leads on a specific claim, and that claim was **re-verified today**
via `scripts/scan_testdocs.py`:

> *"ICSI's specimen AGM notice IS stale: it carries the s.139(1) ratification
> wording repealed by the Companies (Amendment) Act 2017, and 'service tax'."*

A practising CS can check that from memory in under a minute. **The hook works,
the materials exist, and nothing technical remains.** H-C is blocked on one
message being sent by a human — which is the founder's act, not an engineering
task, and no further autonomous work can advance it.

### 9.5 The next execution plan

| # | Task | Owner | Gate |
|---|---|---|---|
| **X1** | **Send the outreach.** Post the LinkedIn text in `H001_FIND_A_CS.md` §1, unedited except the name. Ten messages; expect three or four replies and one yes | **Founder — today** | Nothing blocks it |
| **X2** | Decide SD-005: accept and let the reviewer judge, or acquire a cleaner rendering of G.S.R. 240(E) from India Code | Founder | Gates X3 |
| **X3** | Regenerate `reports/review_brief.md`; human-review the 30 items via `scripts/review.py --next` | Founder + engine | After X2 |
| **X4** | Reconcile the 2-vs-4 refusing-obligations contradiction between `FEATURES.md`'s summary and its F2 entry | Engineering | Independent |
| **X5** | Add an ObjStm-bearing fixture to any future reader suite; generalise §2.1 into a rule | Engineering | Independent |
| **X6** | **H-C interview**, captured with `record_interview.py` — per-row verdicts, not "they liked it" | Founder | After X1 |

**Everything in PLAN_15 Phase 1 — rings, feeds, the Gazette watcher, delivery —
stays behind X6.** That ordering is unchanged and deliberate.
