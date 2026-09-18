# Themis — execution plan, 17 September 2026

An **executable** plan, not a strategy document. Every step names the exact command,
what must be true before it runs, and how it is verified afterwards.

Standing constraints, from the founder's instruction of 17-09:

| Constraint | How it is honoured here |
|---|---|
| **Keep the machine clean** | Nothing is installed. No new runtime dependency. No background daemons. Standard library first. Any candidate dependency is *evaluated on paper* before it is ever fetched |
| **Verify 2–3× before executing** | Every mutating command has a **VERIFY block** — a read-only command that proves the precondition — and a **ROLLBACK line**. See §1 |
| **Paths checked 3–4×** | §1.3. No path is typed from memory; each is confirmed by `ls` before use |
| **Subagents for investigation** | §6 roster. Investigation and verification are delegated; *decisions* are not |
| **Nothing jumps the human gate** | H-C still gates the product. This plan works on the blocker that makes H-C worth doing |

> **One instruction I could not parse with confidence:** *"make sure that the laptop
> is clean and exposed, so don't use any tools."* I have read this as **install
> nothing, add no dependency, leave no daemons running** — not as "do not use the
> file/search tools", since that would make execution impossible. If the intent was
> different, say so before Phase 1 runs.

---

## 1. The execution discipline

### 1.1 The three-gate rule

No command that writes, deletes, moves, or installs runs until three gates pass:

```
GATE 1  PRECONDITION   a read-only command proves the state the step assumes
GATE 2  DRY RUN        the operation is simulated, or run on a copy, and inspected
GATE 3  ROLLBACK       the undo is written down BEFORE the command runs
```

A step whose rollback cannot be written is not executed; it is escalated.

### 1.2 The gate that judges everything

```bash
cd /Users/nishantsingh/PlacedOn/placedon-law-backend && ./scripts/run_tests.sh
```

Current state, **measured 2026-09-17**: `HARNESS_RESULT suites=163 failed=0 status=GREEN`.

This number is the contract. **Any step that lowers it is reverted, not debugged
forward.** After any change to the harness itself, `scripts/harness_regression.sh`
runs too — it proves a failing suite still turns the runner RED, which is the check
that makes the old masking bug unable to recur.

### 1.3 Path verification protocol

Paths are confirmed, never recalled. Before any step that names a path:

```bash
ls -la <the exact path>          # must exist, and be the expected type and size
```

Canonical roots for this plan, **confirmed 2026-09-17**:

| Purpose | Path |
|---|---|
| Repo | `/Users/nishantsingh/PlacedOn/placedon-law-backend` |
| Broken reader | `checker/pdf_text.py` (296 lines) |
| The census that judges it | `scripts/text_layer_census.py` |
| Its three callers | `scripts/review.py`, `scripts/parse_board_rules.py`, `checker/pdf_text.py:266` |
| Corpus PDFs | `corpus/sources/`, `corpus/testdocs/` |
| Scratch (never the repo) | `/private/tmp/claude-501/.../scratchpad` |

**Never** write scratch output into the repository tree. The 16-09 session lost a
scratchpad and had to move the acceptance runner into the repo to survive it — that
was a correct recovery, not a licence to keep scratch in `checker/`.

---

## 2. Mistakes — recognised and recorded

Requested explicitly. This section exists because `RETRACTIONS.md` already proves
the practice works: a mistake written down once stops being made.

### 2.1 Mistakes made in this session (17-09)

| # | Mistake | How it surfaced | Correction |
|---|---|---|---|
| S1 | **Wrote the Bloomberg feature table from memory** and shipped it marked INFERRED. It was wrong: **Docket Key and Dashboard Legal were missing entirely**, and Litigation Analytics has five dimensions, not four | The source check I scheduled myself | Table rebuilt from Bloomberg's own wording; provenance recorded in PLAN_14 §8 |
| S2 | **Asserted a negative claim without checking it** — "e-Courts does not publish a comparable filing corpus". `CLAUDE.md` binds negative claims: *"could not verify" is not "does not exist"* | Caught on re-read before the loop stopped | Downgraded to PARTIALLY_VERIFIED with the evidence and its limits stated |
| S3 | **Mis-numbered a section** (2.5 inserted before 2.4), leaving three stale cross-references | `grep` over the document's own anchors | Renumbered; all references verified by grep |
| S4 | **Argued against the name after the decision was made** — one round past useful | — | Recorded, overruled, moved on. Objections kept in PLAN_15 §0 so they are not re-litigated |

**The pattern in S1 and S2 is one pattern:** confident recall presented as analysis.
It is the same failure `FAILURE_MODES.md` names about this repository — *"a project
that writes down its weaknesses in high-quality prose gets most of the credit for
fixing them."* Prose quality is not evidence.

### 2.2 Project mistakes already recorded — do not repeat

| Incident | The lesson |
|---|---|
| **G.S.R. 700(E) served as CURRENT for nine months** after supersession | The currency engine must watch its own corpus. **This is D-1, still open** |
| **SD-003** — 42 of 121 "source defects" were our own regex, not the source's | Blame the instrument before the source |
| **L-15** — a Bayesian engine built correctly, then deleted | *"I fixed the arithmetic and kept the fabrication."* Rigour on the mechanism does not launder an ungrounded input |
| **The consolidated-Act retraction** | Never use a current consolidation as pre-amendment ground truth |
| **The masking bug** — 8 modules exited 0 while failing | A green harness is a claim; `harness_regression.sh` is the check |

---

## 3. Architecture: what exists, and the RAG correction

### 3.1 The RAG system is built and measured — it is not greenfield

You asked to "develop the RAG system integrated at the backend." **It is developed.**
Both halves have been measured against a frozen eval, and the result is more
interesting than either answer:

| Component | What it is | Measured |
|---|---|---|
| `structural_chunk.py` | Chunks on the statute's **own** units — section → sub-section → clause → proviso → sub-clause, each carrying its path (`2(85)(i)`) | Beats fixed-window chunking by construction. Zero dependencies |
| `chunk_retrieval.py` | **The shipped ranker.** BM25 over structural chunks | **p@1 0.62** vs 0.15 naive. Zero dependencies |
| `dense_index.py` | Decision B — the embedding experiment, run **to be measured, not adopted** | BM25 **0.71 / 0.91**, dense MiniLM **0.73 / 0.96** on the frozen 70-case eval |
| `fusion.py` | Reciprocal Rank Fusion over both | **The finding below** |
| `reranker.py`, `chunk_fusion.py`, `structural_retrieve.py` | Reranking, fusion plumbing, admission-controlled retrieval | BUILT |

**The finding that governs any further retrieval work**, from `fusion.py`'s own
docstring:

> The two p@1 figures **are not distinguishable at this n**. McNemar on the 11/8
> discordant split = **0.648**; Wilson intervals overlap almost entirely
> ([0.60, 0.81] against [0.61, 0.82]). *"'Dense is the better retriever' is not a
> finding here. It may be true; 70 cases cannot say."*

This is L-15 applied to retrieval, and it is the correct posture. **So the
retrieval work that would actually pay is not a better retriever — it is a bigger
eval.** At n=70 no ranking change can be shown to help. Anyone who "improves" RAG
against this eval will be reading noise.

**Therefore: no new retrieval work is scheduled in this plan.** The honest next
retrieval task is growing the eval, and that is downstream of H-C, because the cases
should come from a practitioner's real questions rather than from us.

### 3.2 The backend shape, for reference

```
 RING 0  LEGAL CORE   statute, obligations, deciders, currency, entailment   [BUILT]
 ─────────────────── FIREWALL (one-way, checker/rings.py) ───────────────────  [NOT BUILT]
 RING 1  BOOKMARK     entity graph (CIN/DIN), registers, event log            [MOSTLY]
 RING 2  FEEDS        observations from named sources -> OBSERVATION          [NOT BUILT]
 RING 3  INFERENCE    ordinal ASSESSMENT; ESTIMATE only if calibrated         [NOT BUILT]
```

No Ring 0 decider may import or receive a value originating in Ring 2 or 3.
`rings.py` enforces it by AST walk. **It must land before the first feed**, or the
firewall gets retrofitted around live code and acquires exceptions.

---

## 4. The execution plan

### Phase 0 — protect what exists *(minutes; do this first)*

**0.1 — commit the loose work.**

```
GATE 1   git -C <repo> status --short
GATE 2   git -C <repo> diff --stat          # expect: accept.mjs +150/-29, plans file
GATE 3   rollback = git reset --soft HEAD~1  (nothing is pushed)
```
`web/assistant/tools/accept.mjs` has ~150 uncommitted lines (the A11Y-4 fix making
citation records reachable via `[data-marker]` buttons rather than tab stops). A
session limit destroyed a scratchpad on 16-09; this work is currently no safer.

**Done when:** `git status --short` is empty except intended untracked files, and
the gate is still 163/GREEN.

### Phase 1 — D-002, the blocker *(the real work)*

**The defect, stated precisely.** `extract_pages()` (`checker/pdf_text.py:196`)
finds pages with `_PAGE.finditer(data)` — a regex over **raw file bytes**. In
PDF 1.5+, page objects and the cross-reference table live inside **zlib-compressed
object streams** (`/Type/ObjStm`) and cross-reference streams (`/Type/XRef`). A byte
regex cannot see inside them. Hence 1 page for a 169-page file, 0 for a 179-page
file, 37 for a 22-page file. The module already has `_inflate`; what is missing is
xref-stream and object-stream parsing plus a proper page-tree walk.

**1.1 — measure both options.** IN FLIGHT: two independent subagents (§6), one
measuring the stdlib fix in lines of code, one evaluating the library path against
the dependency policy and its licence exposure. **Read-only. Nothing installed.**

**1.2 — adversarial verification.** A third agent checks both reports against the
actual files before either informs a decision. Two agents agreeing is not evidence;
the repo's own pattern is designs → judges → red team.

**1.3 — the founder decides D-2.** Stdlib fix or library. This is an architectural
and commercial decision (the README advertises no dependencies; a licence like AGPL
in a served backend is a legal problem for a product sold to Indian corporates), and
it is **not delegated**.

**1.4 — implement, TDD.** RED first: a test asserting page-count agreement with the
independent reader on the corpus, which **must fail** before any fix is written.
One logical change per commit.

**1.5 — prove it.**
```bash
python3 scripts/text_layer_census.py        # confirm exact invocation before running
```
**Done when:** the repo reader agrees with the independent reader on **≥13 of 14**
files, the number is recorded with its date, and the gate is still GREEN.

### Phase 2 — convert the fix into movement

| # | Step | Done when |
|---|---|---|
| 2.1 | Re-extract the Board Rules; regenerate `reports/review_brief.md` | Split-word counts ≈ 0 (today: up to **578** on R15); R15's operative/Annexure boundary set; no heading reads `"in its own na me"` |
| 2.2 | Human review of the 30 queued items — *"a day of human work, not engineering"* | Decisions recorded via `scripts/review.py --next`; instrument `production_usable` set **on evidence** |
| 2.3 | Regenerate the compliance matrix | s.177 stops refusing; the gain stated as a measured number, not a mood |
| 2.4 | Reconcile the 2-vs-4 refusing-obligations contradiction | `FEATURES.md` summary says four; the F2 entry says 2 of 15. One is stale |
| 2.5 | **H-C** — one practising Company Secretary reacts to the pack | Written reactions captured in `docs/research/` |

### Phase 3 — only after H-C

`rings.py` → release chokepoint → `checker/feeds/` → Gazette watcher (closes D-1) →
subscriptions and delivery (F5's stated gap) → deadline arithmetic. Specified in
[PLAN_15](PLAN_15_TERMINAL_BUILD.md) §5. **Not scheduled here**, deliberately.

---

## 5. Closed-room testing and scenario simulation

Requested: *test in a closed room, simulate worldwide by creating different
scenarios, create the testing page, run the program.* The repo already has three of
the four, and naming them prevents rebuilding them.

| Layer | What it is | State |
|---|---|---|
| **Closed room** | `scripts/run_tests.sh` — 163 suites, no network, no API key, no dependency outside stdlib. Genuinely hermetic | **BUILT** |
| **Harness honesty** | `scripts/harness_regression.sh` — three full sweeps proving a failing suite turns the runner RED, including the silent `exit 0` shape | **BUILT** |
| **Adversarial scenarios** | `eval/realrun/` — 18 adversarial cases through the real orchestrator, **scored without a model**. `text_field_probe.py` is a measuring instrument, not a gate | **BUILT** |
| **The testing page** | `web/assistant/` prototype + `tools/accept.mjs` — **185/185 checks across 5 widths** (320/360/768/1024/1440) | **BUILT, uncommitted** |
| **Worldwide simulation** | — | **Not applicable, and should not be built.** Themis is jurisdiction-locked: `checker/scope.py` holds **one** body of law (CA2013) and refuses the other eight *by design*. A multi-jurisdiction simulation would test a product that does not exist and must not be implied to |

**The one real gap:** every scenario uses **synthetic or public documents**. The
20-document test on a buyer's real paper is still the unclosed gate, and no amount
of simulation substitutes for it.

---

## 6. Subagent roster

Delegated: investigation, measurement, adversarial checking. **Not delegated:**
architectural decisions, anything that writes to the repo, anything that installs.

| Agent | Task | Mode | State |
|---|---|---|---|
| **A · stdlib measurement** | Confirm the ObjStm/XRef root cause with per-file evidence; specify exactly what must be written; estimate LOC with confidence; name the rabbit holes | Read-only, stdlib only | **RUNNING** |
| **B · dependency evaluation** | The policy verbatim; what is already present (pdfplumber was used for the census — is it declared?); candidates by licence, with the AGPL commercial trap flagged | Read-only, **installs nothing** | **RUNNING** |
| **C · adversarial verifier** | Check A and B against the actual files. Assume both are wrong until proven | Read-only | Queued behind A and B |

**Why a verifier at all:** `run.py`'s founding argument — *"a detector cannot be
validated by the failure its author imagined."* An agent's estimate is a claim, and
this repository's rule is that a claim carries its evidence.

---

## 7. What this plan does not do

- **It does not decide D-2.** It makes the decision informed, with two numbers
  attached instead of the word "large".
- **It does not touch retrieval.** §3.1: at n=70 no ranking change is measurable.
- **It builds no feed, no ring, no telemetry.** All of it is behind H-C.
- **It installs nothing.** If the decision goes to a library, that is a separate,
  explicit, founder-approved step with its stated reason written down first.
