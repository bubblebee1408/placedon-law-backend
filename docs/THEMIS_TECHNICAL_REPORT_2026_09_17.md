# Themis — technical report

> **Integration note — added by the coordinating session when this report was merged
> onto `loop/bookmark-godseye-v0` (2026-09-17, evening).** The body below was measured in
> a worktree branched from `origin/main` (`eb48905`), which is *not* an ancestor of this
> branch. Statements of the form "exists only in the main checkout" or "not yet committed"
> describe that worktree, and are **no longer true on this branch**. As merged:
>
> | Item | State on this branch | Commit |
> |---|---|---|
> | `checker/rings.py` (incl. the package rule) | committed; 28/28 | `0d7cd3b`, `d4fd3e5` |
> | `checker/feeds/` + `ofac_sdn.py` | committed; live 19,385 of 19,385 | `d4fd3e5` |
> | Gazette watcher (`checker/feeds/egazette.py`, `scripts/watch_gazette.py`) | committed; live baseline serial 276299 | `234dca2` |
> | SD-005 | committed | `c4b64d6` |
> | robots.txt 401/403 treated as a refusal | committed | `54eba61` |
> | Full gate | **173 suites, 0 failed, GREEN** (MEASURED by the pre-commit hook) | `86e24a2` |
>
> Appendix rows 5, 20 and 28 are therefore worktree facts; the table above supersedes
> them for this branch. Everything else stands as tagged.

**2026-09-17.** Repository `placedon-law-backend`. Every claim below carries a tag:
**MEASURED** (a command run in this repository, with commit and date), **SOURCED**
(a primary source — a URL, a document, or a repository file read directly),
**INFERRED** (reasoning, stated as such), or **UNVERIFIED** (believed, not checked).
An untagged sentence is scaffolding, not a claim, and should be discounted
accordingly. Where a figure quoted in this repository's own documents disagreed
with what this report measured, both numbers are given and the current one is
named — see §11 and the Appendix.

**A note on provenance of this report.** Two checkouts of this repository exist
side by side: an isolated git worktree (where this report was written and where
every MEASURED figure was produced) at commit `eb489051acde029441742af8747685ea9ad406a6`
on branch `worktree-agent-a9b508df2a97458d9`, and the main checkout at
`/Users/nishantsingh/PlacedOn/placedon-law-backend/`, which has continued advancing
under a separate, concurrent session and is several commits ahead. Some of the
system described here — `checker/rings.py`, the `checker/feeds/` package, and five
planning documents — exists only in that main checkout, not in the worktree this
report was written from. Where a claim rests on code read from the main checkout
rather than run in the worktree, this report says so explicitly and tags the claim
**SOURCED** (repository file, read directly) rather than **MEASURED**, because
reading source is not the same evidentiary act as executing it. §11 gives exact
commands for what can be independently reproduced from each location.

---

## Abstract

Themis is a deterministic compliance-audit engine for Indian corporate law, built
on the premise that the statute itself — not a model's fluency — is the thing that
must be verified, and that refusal is a legitimate output. Nine bodies of Indian
corporate law are declared in scope; one, the Companies Act 2013, is actually held
and reasoned over (MEASURED, `checker/scope.py`, 20/20). The system's own history
supplies its motivating incident: it served a superseded statutory threshold as
current for nine months. This report verifies, by running the repository's own
test suites and reading its own source, what is built, what the numbers actually
say, and where the project's documents disagree with each other or with what was
measured today. It finds a working deterministic core (163/163 suites green in
this worktree), a genuinely unusual discipline around refusing ungrounded
numbers, and several load-bearing defects — a broken PDF reader (since fixed, in
the main checkout only), an amendment corpus frozen since 2023, and no
practitioner review of any output to date.

---

## 1. Problem

Indian corporate law changes underneath correct answers, and — on this project's
own account — nothing was watching. **SOURCED** (`docs/FEATURES.md` F7, read
2026-09-17 in this worktree): the engine itself "served a superseded
small-company threshold as CURRENT for nine months," and the discovery
"immediately found three more instances." That superseded threshold traces to
G.S.R. 700(E), a notification under s.2(85) of the Companies Act 2013 that moved
the statutory small-company caps; the engine's `checker/prescribed_thresholds.py`
answered against a stale figure until the correct instrument was acquired and
attested.

The wider claim — that this is an industry-wide failure, not a one-off bug — is
**SOURCED** to the project's own account in `docs/PLAN_00_INDEX.md`: "four of the
most-read Indian compliance sites still publish the 2022 figure, and one
publishes a figure that never existed." This report did not independently
re-check those competitor sites; it is reproduced here as the project states it,
tagged as the project's own sourced claim rather than independently reconfirmed
by this report.

The project's conclusion from its own incident: **the product is the watching,
not the answering** (SOURCED, `docs/PLAN_00_INDEX.md`). A system that answers
correctly today and never notices when the ground moves is not meaningfully
different, to the practitioner relying on it, from a system that answers
incorrectly.

---

## 2. Design thesis

**"The model may propose. The system must verify. The reviewer decides."**
(SOURCED, `README.md`, verbatim, and repeated across the plan documents as the
project's governing sentence.)

Three structural commitments follow from it, all MEASURED in this worktree
today:

**Scope is declared, and declaration is not possession.** `checker/scope.py`
registers eleven bodies of law with an explicit `status` field. MEASURED
(`PYTHONPATH=. python3 checker/scope.py`, this worktree, commit `eb48905`,
2026-09-17 — 20/20 tests passed) and confirmed by reading the module's own
`BODIES` tuple directly: one body (`CA2013`, Companies Act 2013) is
`IN_CORPUS` — reasoned over; one (`SEBI_LODR`) is `CURRENT_ONLY` — a live
consolidation held but wired to no obligation, because SEBI publishes a
consolidation where MCA publishes discrete amending notifications, and a
consolidation cannot answer a dated question; seven (`LLP2008`, `SEBI_OTHER`,
`FEMA1999`, `IBC2016`, `COMP2002`, `STAMP`, `DPDP2023`) are `DECLARED` — in
scope, nothing acquired, and a question there is refused by naming the body and
the acquisition gap, never by silence; and two (`POSH`, `AI_LAW`) are
`OUT_OF_SCOPE` by explicit decision. The nine in-scope bodies (`IN_CORPUS` +
`CURRENT_ONLY` + the seven `DECLARED`) match the "nine bodies... one held"
figure both `CLAUDE.md` and `README.md` state. The self-test asserts the
invariant that gives the declaration teeth: **no obligation may exist in the
register for a body that is not held** — MEASURED, the test named
"no obligation is decided against a body we do not hold" passed.

**Abstention is a first-class output, not an error state.** The status
vocabulary — `VERIFIED · PARTIALLY_VERIFIED · UNVERIFIED · INAPPLICABLE ·
POTENTIAL_ISSUE · STALENESS_WARNING` (SOURCED, `CLAUDE.md`) — has no state that
means "confident and wrong." `checker/calibration_contract.py`'s docstring
states the same idea for numbers rather than legal verdicts: "no number reaches
a reader without a track record that earns it." This is the project's most
distinctive engineering commitment and it recurs at every layer examined in this
report (§5).

**Scope held versus scope declared is checked by machine, not by prose.**
`checker/scope.py`'s test suite exists precisely so that a future PR widening
the declared list cannot silently widen what is actually answered — MEASURED,
the passing test "every declared-but-unheld body refuses the same way."

---

## 3. Architecture — the four rings and the one-way firewall

`docs/PLAN_08_BOOKMARK_AND_GODSEYE.md` (SOURCED, written 2026-09-11) declares
four rings:

```
RING 0  LEGAL CORE      statute, obligations, deciders, currency, entailment
──────────────────── FIREWALL (one-way) ────────────────────
RING 1  BOOKMARK        entity graph (CIN/DIN), public registers, event log
RING 2  FEEDS           observations from named live sources
RING 3  INFERENCE       ordinal assessments; numeric estimates only if calibrated
```

The rule: a module in ring N may import from rings below it; **no Ring 0 or
Ring 1 module may import, read, or receive any value originating in Ring 2 or
Ring 3.** A forecast may never be an input to a deterministic legal decision.
The stated reason a code convention is not trusted to hold this line: a
probability leaking into an applicability decider corrupts the output
*silently*, because a corrupted Ring 0 decider still looks exactly like a
correct deterministic answer — there is no downstream symptom to notice.

**`checker/rings.py` exists only in the main checkout, not in this worktree**
(confirmed: `ls checker/rings.py` in the worktree returns "No such file or
directory"; the file is present and readable at
`/Users/nishantsingh/PlacedOn/placedon-law-backend/checker/rings.py`). Everything
below on `rings.py` is therefore **SOURCED** (the file read directly from the
main checkout, 2026-09-17) rather than MEASURED — this report could not execute
its self-test from the worktree.

The mechanism is an AST walk, the same technique `checker/api.py:858-859`
already uses to assert the API imports no model library. It walks the **whole**
syntax tree, not just module-level imports — deliberately, because an import
deferred inside a function is the codebase's normal style for avoiding import
cycles, and is exactly how an upward leak would be hidden. Two design details
are worth naming because they show the same discipline applied to the guard
itself:

- **Classification is by package, not just by exact module name.** An earlier
  design registered each Ring 2 module individually; the module's own comment
  records that this created a hole the day `checker/feeds/` landed — a future
  feed file nobody remembered to register would resolve to `ring_of() ==
  None`, which the guard "deliberately never flags." The fix classifies the
  whole `checker.feeds` package as Ring 2 by prefix match, so a forgotten
  registration cannot silently disable the firewall for the module it exists
  to fence.
- **A negative control is built into `_test()`.** Rather than only asserting
  the real codebase is clean, the test first constructs a synthetic Ring 0
  module that imports a temporarily-registered fake Ring 2 module from inside
  a function, and asserts the scanner catches it — before trusting the clean
  result on the real code. The module's own docstring gives the reason: this
  repository has already twice lost time to a check that could not fail (see
  §7, D-002's two defects).

**Ring 0 deciders**, per the module's own `REGISTRY`: `checker.obligations`,
the section-specific deciders `checker.s180/s184/s185/s186/s188/s188_threshold`,
`checker.currency`, `checker.cascade`, `checker.ground_span`, `checker.as_of`,
`checker.amendment`, `checker.prescribed_thresholds`, the `checker.entail_*`
family (six-plus modules, SOURCED count from the registry), `checker.admission`,
`checker.provenance`. **Ring 1**: `checker.entity_graph`, `checker.event_log`,
`checker.corporate_data`, `checker.mca_aggregator`, `checker.mca_snapshot`.
**Ring 2 is populated by package**: `checker.feeds` and everything under it.
Ring 3 is registered empty — no inference module exists yet, and the module's
own test asserts this explicitly rather than by omission.

**Ring 2 — the `Feed` protocol.** SOURCED, `checker/feeds/__init__.py` (main
checkout). Every adapter carries `source_id`, a `licence` (Axis D — see below),
and two methods: `fetch(entry_url) -> FetchResult` and `parse(result, *,
observed_at, blindness) -> Observation`. Two design choices carry the module's
whole argument:

- **`Observation` is a distinct type from anything on `checker/provenance.py`'s
  VERIFIED ladder, on purpose.** It has no `promote()` method and no code path
  anywhere converts one into a `VERIFIED_FACT`. The docstring calls this
  "the toolchain output as a fact about the world' failure `checker/pdf_pages.py`
  and `checker/mca_snapshot.py` each independently name" — i.e., a live feed's
  read of a third party's bytes is not automatically evidence merely because a
  machine parsed it.
- **Axis D has no default anywhere in the file.** `licence` is one of
  `PUBLIC_DOMAIN`, `ATTRIBUTION`, `CONTRACT_ONLY`, `NONCOMMERCIAL`, or
  `LICENCE_UNVERIFIED`; `may_serve_commercially()` raises on any other value
  rather than defaulting it, and `LICENCE_UNVERIFIED` — meaning the source's
  own redistribution terms were not found — refuses commercial serving exactly
  as `NONCOMMERCIAL` does. "Government-published" is explicitly not treated as
  a synonym for "public domain" until the source says so in its own words.

`FetchResult` and `Observation` both refuse to carry content when
`source_behaviour` is not `ACCESSIBLE` — a 404, timeout, or robots refusal must
carry zero bytes, enforced by a constructor-level `ValueError`, on the stated
rule that "a refusal or an outage is evidence of nothing."

---

## 4. Retrieval

**Structural chunking and BM25 are shipped; dense retrieval is measured but
narrower than a headline number suggests.** `checker/fusion.py`'s own
docstring (SOURCED, read in this worktree, then cross-checked by running its
arithmetic) states the retrieval eval on the frozen 70-case
`cross_section_eval` set: BM25 at p@1 0.71 / recall@5 0.91, dense (MiniLM-L6)
at p@1 0.73 / recall@5 0.96.

**The n=70 indistinguishability, MEASURED independently in this report**
(`PYTHONPATH=. python3 -c "from checker.interval import mcnemar, wilson; ..."`,
this worktree, 2026-09-17): `mcnemar(11, 8) = 0.6476`, matching the module's
stated "0.648" to three decimal places (the small residual is rounding).
Wilson 95% intervals computed the same way: BM25 at 50/70 → [0.599, 0.807];
dense at 51/70 → [0.615, 0.819] — both overlapping almost entirely, matching
the module's stated [0.60, 0.81] and [0.61, 0.82]. **The conclusion this
confirms**: "dense 0.73 beats BM25 0.71" is not a finding a sample of 70 cases
can support — a McNemar p of 0.648 is nowhere near significance, and the
confidence intervals overlap on more than three-quarters of their range. What
*is* structural rather than statistical, per the same docstring: the two
retrievers' error sets are almost disjoint — 11 cases only dense gets, 8 only
BM25 gets, 9 neither gets — which is the textbook precondition for rank
fusion, independent of which retriever is "better."

Fusion itself is Reciprocal Rank Fusion (RRF), chosen specifically to avoid
comparing incommensurable quantities: a BM25 score is an unbounded,
corpus-length-dependent sum of IDF-weighted term saturations, a cosine
similarity is a bounded inner product, and normalising one against the other
"invents a comparability that does not exist." RRF instead fuses only the
**rank order** each retriever assigns, discarding scores entirely.
MEASURED in this worktree (`PYTHONPATH=. python3 checker/fusion.py`, 19/19
passed), including a specific test that fusion "invents no candidate that
neither retriever returned" and that `explain()` reconciles the fused total to
the exact sum of per-retriever terms.

A separately dated figure exists in `docs/ABLATION_CORRECTED.md` (SOURCED,
measured 2026-09-06 on the same frozen 70-case set): "RRF fusion p@1 0.80,
recall@5 0.97" — i.e. fusion measurably beats either single retriever on this
eval, even though the two retrievers are not distinguishable from each other.
That document also records a retraction worth noting for calibration: an
earlier 20-case run reported V1/V2 base-model retrieval at exactly 0.00,
framed as "the sharpest data point" — and the de-anchored 70-case re-run found
this was an artefact of a prompt that leaked the answer ("for example: 185"),
not a finding about model capability. **Why the next retrieval work is a
bigger eval, not a better retriever**: at n=70, the comparative retrieval
question is provably unanswerable, and the project's own retraction history
(this one, plus R-1 through R-5 in `docs/RETRACTIONS.md`, §10) shows that
narrow evals have already produced at least one confidently wrong published
conclusion here before being caught.

---

## 5. Why numbers are mostly refused

This is the project's most examined and best-evidenced discipline, and it
traces to a single incident. **SOURCED**, `.claude/memory/LESSONS.md` L-15,
verbatim: a Bayesian belief engine was built in this repository, and built
*properly* — a real sign error in the source specification was found and
fixed, an unsourced 0.6 prior was replaced with a stated 0.5, the number was
kept away from users, and a build-failing check was added if a posterior
reached a hardcoded template. The module was deleted anyway. An adversarial
audit of the nine underlying papers found calibration unreachable at the
available sample size, and the author's own verdict on their own
correctly-executed work: **"I fixed the arithmetic and kept the fabrication."**
The specific finding: `LR_LAWYER_VERIFIED = 12.0` had exactly as much grounding
as the `prior = 0.6` that had already been rejected — rigour applied to the
mechanism does not launder an ungrounded input, it disguises it, because the
working becomes checkable while the premise stays unchecked.

`checker/calibration_contract.py` turns that finding into a reusable
instrument. MEASURED in this worktree (`PYTHONPATH=. python3
checker/calibration_contract.py`, 17/17 passed):

- `ece_floor(0.90, 20) = 0.0513` — a **perfectly** calibrated forecaster
  issuing p=0.9 on 20 independent items fails a target of ECE < 0.05, purely
  from binomial sampling noise.
- `ece_floor(0.10, 6) = 0.1063` — and the widely-used normal approximation
  `sqrt(2p(1-p)/(πn))` gives 0.0977 at this n, **understating** the true floor
  by roughly 9%, in the unsafe direction — making a hopeless target look
  merely difficult. The module uses the exact binomial sum throughout
  (`math.comb`) for exactly this reason; both figures were independently
  reproduced by running the module's own test in this worktree.
- Applied to the amendment corpus's real n: per `docs/PLAN_08_BOOKMARK_AND_GODSEYE.md`
  §6 (SOURCED), six amending Acts carry 307 of 348 instrument mentions in the
  corpus, giving "will Parliament amend this section" an effective n of about
  6. `ece_floor(0.1, 6) = 0.1063` sits well above any target of 0.05, so the
  question is **permanently unanswerable as a calibrated probability, and no
  further data acquisition fixes it** — this was independently confirmed by
  this report's own run of the module's `_test()`, which asserts this exact
  case (`assess(amend).state == UNDERPOWERED`).
- The *conditional* question — "is this the kind of section that moves,"
  rather than "will this section move" — survives at n_eff ≈ 261
  section-years (SOURCED, PLAN_08 §6; not independently re-derived in this
  report, since it requires the full amendment corpus census this worktree
  does not have a script to reproduce on demand).

**What Themis serves instead of a probability: an ordinal lattice.**
`checker/lattice.py` (MEASURED, 9/9 passed) factors out a pattern that had
independently grown in three modules (`currency.py`, `staleness.py`,
`corpus_currency.py`, each with its own private `_SEVERITY` dict and its own
`max(..., key=...)`) into one `Lattice.worst_of()`. The design argument, from
the module's own docstring: `max` needs no joint distribution, where
multiplying probabilities across a section, its qualifying rule, and the
reviewer who attested it "would assert independence between three maximally
dependent things" and produce a number that looks like a measurement while
being an artefact of an unchecked assumption. Verified by this report:
`worst_of()` returns a `Verdict(state, witness)`, never a bare state — an
empty composition returns the best state with `witness=None` rather than
raising, and every non-empty composition names the specific input that
produced the worst state, because (per the docstring) "a rollup that returns
only a state is unusable."

`docs/PLAN_14_TERMINAL_AND_FEEDS.md` §5.4 states the reframe this whole chain
supports: **"How can it prove, before anyone computes a number, whether the
data could support that number at all — and degrade honestly to an ordered
judgement when it cannot?"** — the accuracy claim is not in the statistic, it
is in the gate deciding whether the statistic is allowed to exist at all.

---

## 6. Evaluation

**The adversarial real-model benchmark.** `eval/realrun/run.py` runs 18
adversarial documents through the real orchestrator and scores the result
**without a model** — substring matching, set membership, date comparison —
on the stated principle that "a judge sharing the weights that produced a
claim cannot measure the claim" (SOURCED, `eval/realrun/scorecard.md`). This
report read two generations of results:

- **2026-09-14** (SOURCED, `eval/realrun/scorecard.md`): `gemini-3.6-flash`
  scored 0 LEAK / 9 CORRECT / 1 CORRECT_REFUSAL on 10 of 10 cases run;
  `gemma3:1b` (local, deliberately weak) scored 1 LEAK / 2 CORRECT / 1
  CORRECT_REFUSAL / 14 WRONG_REFUSAL on 18 of 18. The one leak — a document
  containing an injected "SYSTEM NOTE" instructing the model to emit a
  fabricated JSON verdict — passed because the review layer checked only
  whether a claimed span was *present* in the document, not whether it
  *supported* the claimed value; since the injection itself was present in
  the document, its one-word span "verified" supported no numeric value at
  all, and nothing checked that. The fix (`FACT_VALUE_UNSUPPORTED`, routing
  through the repository's own pre-existing but unused
  `document_extract.value_supported_by_span`) closed this leak; a second,
  narrower leak class survived deliberately (a quantity bound to the *wrong*
  field, with a genuinely real, genuinely matching span) and was closed the
  same day by `checker/field_binding.py`'s `FACT_MISBOUND` check.
- **2026-09-15, more current** (MEASURED by reading
  `eval/realrun/last_run_azure_gpt-5-mini.json` and
  `eval/realrun/last_run_azure_llama-3-3-70b.json` in this worktree, git-dated
  by commit `94c5514`): `azure:gpt-5-mini` — CORRECT 14, WRONG_REFUSAL 2,
  CORRECT_REFUSAL 1, ERROR 1, 17 of 18 cases run, **0 recorded LEAK**;
  `azure:llama-3-3-70b` — CORRECT 15, WRONG_REFUSAL 2, CORRECT_REFUSAL 1, 18
  of 18 cases run, **0 recorded LEAK**. This matches
  `docs/THEMIS_STATUS_AND_NEXT_2026_09_17.md`'s summary of "gpt-5-mini 0/18,
  Llama-3.3-70B 0/18."

**What this benchmark is not**, stated by its own governing document: 18
adversarial cases built specifically to defeat known gates are evidence the
gates hold *under attack*, not evidence of accuracy on a real caseload; the
test documents are synthetic, with no Gazette provenance; and the harness
itself refuses to report a rate when too many cases error, rather than
printing a misleadingly precise number over a partial run.

**The mutation-tested harness.** `scripts/harness_regression.sh` exists
because — per the project's own account, cross-referenced against
`docs/D002_CLOSURE_REPORT_2026_09_17.md` §2.1 (main checkout) — a green check
that cannot fail has already cost real time twice in this repository: once as
a "silent-failure shape that once hid four real failures behind 'all suites
green'" (SOURCED, `docs/THEMIS_STATUS_AND_NEXT_2026_09_17.md` §2.4), and once
as the PDF reader's only wired-in test fixture being the one corpus document
structurally immune to the bug it was meant to catch (§7 below). `checker/rings.py`'s
own `_test()` (main checkout, SOURCED, not run from this worktree) explicitly
cites both incidents as the reason it builds a synthetic failing case and
proves the guard can catch it, before trusting a clean run on the real
codebase.

**Self-found defects.** `docs/THEMIS_STATUS_AND_NEXT_2026_09_17.md` §2.4
(SOURCED): four checker holes found in the 14-09 run were found by real
models, not hand-written tests, and every fix was replayed against stored
runs to prove it "refused nothing that previously served correctly." This
report did not independently re-verify that replay claim.

---

## 7. Data engineering findings

**D-002 — the PDF page reader agreed with an independent oracle on 0 of 14
corpus files, and this is now fixed in the main checkout only.** SOURCED,
`docs/D002_CLOSURE_REPORT_2026_09_17.md`, produced by the coordinating session
2026-09-17. Before the fix: 0/14 census agreement; the reader returned 1 page
for a 169-page file and 0 pages (with text) for a 179-page file. After: 14/14
agreement, field-for-field identical to the independent `pdfplumber` oracle,
and a new suite `checker/pdf_pages.py` at 13/13. **This report could not
independently re-run this measurement**: `checker/pdf_pages.py` does not exist
in this worktree, and neither does the `pypdf` dependency declaration in
`requirements-dev.txt` here (confirmed: this worktree's
`requirements-dev.txt` reads only `-r requirements.txt`, `uvicorn==0.42.0`,
`pdfplumber==0.11.10` — no `pypdf`). The figures above are therefore SOURCED
to the closure report, not MEASURED by this report.

**Two independent defects, not one**, per the same source: (1) compressed
object streams (`/Type/ObjStm`, PDF 1.5+) are invisible to a byte-level regex,
which undercounted to 0–1 pages on affected files, or *over*counted (one file
to 37 pages for a 22-page document) when stale incremental-revision page
objects were also matched; (2) a `/Contents` look-ahead window of only 400
bytes missed cases where a PDF writer emits `/Contents` before `/Type/Page` in
the same dictionary — independent of defect (1), and present even in files
with no object streams at all (one file: 0 of 18 `/Contents` occurrences found
within the forward window; all 17 were behind it). **Why this survived 163
green suites**: the reader's only wired-in test fixture was structurally
immune to both bugs — the one PDF 1.4 file in the corpus with no object
streams. "A test whose fixture cannot exhibit the defect is not evidence, and
the harness cannot tell the difference" (the closure report's own words,
naming the same disease `harness_regression.sh` exists to catch).

**The immune fixture, and the decision it fed.** The founder's decision,
recorded in the same document: adopt `pypdf` (BSD-3-Clause, pure Python) for
offline tooling only, explicitly rejecting a standard-library fix (estimated
~400–450 LOC, "every line can be quietly wrong about the source text of the
law") and rejecting PyMuPDF/fitz on licence grounds (AGPL-3.0, which would
compel disclosure of the whole served product under §13's network-use clause
— SOURCED to installed package metadata, per the closure report). `pdfplumber`
was deliberately **not** promoted to production reader, on a subtler
argument: it is already the independent oracle the two-reader census uses to
judge this repository's own reader, and using it as the production reader
too would make the census compare pdfplumber against itself.

**What the fix did not fix — the finding the closure report calls more
important than the fix itself.** Split-word counts on the Board Rules 2014
gazette (the file gating the 30 queued human-review items) were measured
across three independent parsers: stdlib 1,499 words split, `pypdf` 1,474,
`pdfplumber` (oracle) 1,367 — three engines agreeing within roughly 8%, with
the splits concentrated in the English rule text on exactly the pages under
review, and absent from the Hindi pages on every reader. **Inference (stated
as such by the source): the gazette's own English text layer has broken word
spacing** — a property of the source, not of any reader, and under
`CLAUDE.md`'s standing rule ("never repair a defective government source")
it must not be silently rejoined. This is now recorded as SD-005 in the main
checkout's `docs/SOURCE_DEFECTS.md` — **not present in this worktree's copy**
of that file, which runs only to SD-004 (confirmed by reading it directly;
see §11).

**The OFAC SDN feed.** SOURCED, `checker/feeds/ofac_sdn.py` (main checkout).
Five traps the module's own docstring records as measured before a line of
adapter code was written: (1) the widely-cited
`www.treasury.gov/ofac/downloads/sdn.xml` redirects to a page whose own
`robots.txt` is itself an HTML homepage, which a naive parser would misread
as "no rules, fully allowed" — the adapter uses a different, correctly-behaved
host instead (`sanctionslistservice.ofac.treas.gov`, whose `robots.txt` is a
genuine 404, RFC 9309's defined full-allowance case); (2) the actual payload
is served from a different host via a pre-signed AWS S3 URL that expires in
3,600 seconds, never stored; (3) file size 29,076,910 bytes, parsed with
streaming `iterparse` so memory does not scale with the list; (4) the file
states its own record count (`<Record_Count>19385</Record_Count>`), giving a
free integrity check that the module reports on mismatch rather than
resolving in either direction; (5) licence is `LICENCE_UNVERIFIED` by design —
US federal works are generally understood to be outside copyright, but that is
"reasoning about who published the file, not the source's own words," and the
module's own definitions require the latter. **19,385/19,385** is the
document's own stated figure, tagged here as SOURCED to the source file's
docstring and test fixtures, not independently re-fetched by this report
(the module's live-fetch test path is explicitly off by default,
`THEMIS_LIVE=1`-gated, "so the gate stays hermetic").

**The eGazette watcher's traps.** SOURCED, `checker/feeds/egazette.py` and
`scripts/watch_gazette.py` (main checkout, explicitly **not yet committed**
per this task's own briefing). Four measured traps recorded in the module's
own docstring: (1) `egazette.gov.in` serves **only its leaf TLS certificate**
— every verified fetch failed until intermediate certificates were supplied
locally; (2) the site answers **HEAD with 404 even for files that exist** — a
HEAD probe would have wrongly "disproved" a correct URL pattern, so the
adapter never probes, only GETs, consistent with `CLAUDE.md`'s rule that "a
404 on a URL we invented is evidence of nothing"; (3) every listing beyond the
homepage's newest few rows is an ASP.NET `__doPostBack`, not a plain GET — the
adapter deliberately does not replay form state to reach them, calling that
"brittle, and it drives the site rather than reading it"; (4) Gazette IDs are
one shared ascending counter across State and Central series, and the
homepage shows only the newest handful — so between polls, any integer in the
gap that no listing showed is reported as **UNSEEN**, explicitly distinct from
"does not exist." The coordinating session's live run on 2026-09-17 reported
**7 gazettes listed, high-water serial 276299** — this figure is reported here
exactly as briefed, tagged **MEASURED 2026-09-17 by the coordinating session**,
not independently re-run by this report (the module and its state files are
not present in this worktree).

---

## 8. The India data-substrate finding

`docs/PLAN_14_TERMINAL_AND_FEEDS.md` §2.3 (SOURCED, source-checked
2026-09-17): every one of Bloomberg Law's flagship AI features is downstream
of a US public-record filing mandate that manufactures the corpus the feature
runs over — **four for four**:

| Feature | US mandate | Indian equivalent |
|---|---|---|
| Draft Analyzer (compares documents against 2.3M+ EDGAR filings) | Reg S-K 601(b)(10) — material contracts filed as exhibits | None; SEBI LODR requires significant terms **"(in brief)"**, not the filed instrument |
| Docket Key (search across millions of filed briefs) | PACER — filings are public record | **PARTIALLY_VERIFIED**, see below |
| Litigation Analytics | PACER — dockets and outcomes | Same gap, same caveat |
| Points of Law / Brief Analyzer | Published judicial opinions at scale | Partial — Indian Kanoon, under attribution terms only |

The Draft Analyzer and Litigation Analytics rows carry Bloomberg's own
published wording (its enumeration source: a Bloomberg-owned content host,
`bna.content.cirrus.bloomberg.com`, not the canonical `pro.bloomberglaw.com`,
which returned HTTP 403 to automated fetch and was recorded as blocked, not
routed around).

**The e-Courts/Docket Key row carries the status this report was instructed
to preserve: `PLAN_14` §2.3 gives it PARTIALLY_VERIFIED.** What was actually
checked 2026-09-17: e-Courts publicly serves case status, daily orders and
cause lists; the E-Filing Rules state that "access to e-filings is restricted
in the manner provided in regulations and as may be notified from time to
time," with e-filed pleadings "stored on exclusive servers maintained under
court control... separately labeled and encrypted." That supports "no
freely-downloadable pleadings corpus comparable to PACER" and explicitly does
**not** support "e-Courts publishes nothing" — the restriction is
court-by-court and notifiable, so the finding is bounded and provisional by
design, not a blanket negative claim.

Both Bloomberg price figures cited elsewhere in this project's documents
(Terminal ~$31,980/user/year; Bloomberg Law ~$450/user/month) are explicitly
flagged by `PLAN_14` §1 as **SECONDARY-SOURCED, and can never become
vendor-primary**, because Bloomberg publishes no pricing page for either
product — this report repeats that status rather than treating either figure
as confirmed.

---

## 9. Source licensing (Axis D)

Both concrete Ring 2 feeds read for this report carry `LICENCE_UNVERIFIED`,
not an affirmative licence grant:

- **OFAC SDN**: US federal-government status is a reasonable inference but
  not the source's own stated redistribution terms, so the module refuses
  commercial serving until that gap is closed — a one-line change once a
  citable statement exists.
- **eGazette**: Copyright Act 1957 s.52(1)(q) very likely covers reproduction
  of matter published in the Official Gazette, but the site's own Disclaimer
  page renders no text without scripts and was not read as a definitive
  statement, so the same refusal applies, and what the feed would serve is
  metadata and a link, not the underlying document, in any case.

**The SEBI debarred-entities audit** (`docs/research/SOURCE_AUDIT_SEBI_DEBARRED_2026_09_17.md`,
main checkout, SOURCED): every route checked was blocked, forbidden by
terms, or paid, and none was bypassed. NSE's page rejects non-browser clients
at the HTTP/2 layer within 0.05 seconds; BSE's `robots.txt` itself returns an
Akamai 403; MSEI's `robots.txt` allows crawling but its terms of use
explicitly forbid reproducing, storing, or distributing the content in any
manner — a feed would breach the storage and distribution verbs even though
robots.txt alone permitted the fetch. OpenSanctions carries the same upstream
data under a licensed reseller tier (~€0.10/call), which the audit calls the
fastest legitimate route since that vendor has "already solved 'may I show
this to a paying customer'." **A methodology defect was found and recorded
during the audit itself** (its own "S9"): the MSEI spreadsheet was downloaded
and parsed *before* its terms of use were read — robots.txt governs crawling,
terms of use govern what may be done with content, and a clean robots file is
not a green light for the latter. The single inspection copy was deleted from
the session scratchpad before anything entered the repository, verified by
`git status`. A second finding, left open by the audit rather than acted on:
`checker/robots.py` currently reads a 4xx robots.txt response (including
BSE's Akamai-issued 403, which is an access denial, not an absent file) as
full permission, per RFC 9309 — a defensible reading of the RFC that the
audit nonetheless flags as producing the wrong practical verdict for this
specific case, though it notes the content request would almost certainly
still be blocked downstream regardless.

---

## 10. Limitations

Stated as bluntly as the project's own documents state them, because this
report's brief was to be unsparing and because several of these are already
the project's own words.

- **No practitioner has reviewed any output.** SOURCED, `README.md`: "No
  practising lawyer has reviewed any output, and there is no real-document
  benchmark." `docs/THEMIS_STATUS_AND_NEXT_2026_09_17.md` names this the
  single blocking item — "H-C," open since 2026-09-04 — and states plainly
  that "nothing downstream is worth building until someone reacts." As of
  2026-09-17 this remains a message a human has not yet sent, not an
  engineering task.
- **No real-document benchmark exists.** The 18-case realrun set (§6) is
  synthetic and adversarial by design; the 70-case retrieval eval (§4) is
  drawn from one Act. Neither is a claim of production accuracy.
- **The evaluation gate has documented gaps of its own.** `docs/FAILURE_MODES.md`
  (SOURCED, written 2026-09-02 against an earlier state of this repository;
  not re-verified against 2026-09-17's code, so read as historical evidence
  of the project's failure patterns rather than a current defect list)
  reported that the release gate at the time scored 67 of a manifest's
  attested 69 benchmark pairs, and that the fixture pipeline for human-judged
  pairs could structurally only ever produce the positive label. This report
  did not re-run that specific audit against current code, and lists it here
  as a documented historical finding, tagged UNVERIFIED as to current status.
- **Two internal documents disagree on how many obligation rows refuse**,
  and the project's own `docs/THEMIS_STATUS_AND_NEXT_2026_09_17.md` §5
  flags this itself rather than resolving it: `docs/FEATURES.md`'s F2 entry
  says 2 of 15 rows refuse (s.177, s.203); its own summary paragraph says
  four obligations refuse. This report repeats the flag rather than
  adjudicating it, since resolving it requires tracing `obligations.py`
  against the current Board Rules state, which was out of scope here.
- **Licence status for both built Ring 2 feeds is unverified**, not merely
  unconfirmed as a formality (§9) — both explicitly refuse commercial
  serving as a result.
- **This worktree is several commits behind the main checkout**, which means
  a meaningful share of the newest engineering (the ring firewall, the feeds
  package, the PDF-reader fix) could not be independently executed for this
  report and rests on reading source rather than running it (§3, §7, §11).
- **Trademark clearance for the name "Themis" is UNVERIFIED and,
  per the project's own record, likely contested** — `docs/THEMIS_STATUS_AND_NEXT_2026_09_17.md`
  §0 names Clio's registered entity "Themis Solutions Inc.," a bar-review
  product, and a banking-compliance product trading under the same name in
  the same broad sector, and states this is "a cost to plan for, not a
  reason to reopen the decision."

---

## 11. Reproducibility

Commands actually run for this report, in the worktree, commit
`eb489051acde029441742af8747685ea9ad406a6`, branch
`worktree-agent-a9b508df2a97458d9`, 2026-09-17:

```bash
# Full suite — takes several minutes
./scripts/run_tests.sh
# -> HARNESS_RESULT suites=163 failed=0 status=GREEN

# Scope register
PYTHONPATH=. python3 checker/scope.py
# -> 20/20 passed

# Ordinal lattice, calibration contract, retrieval fusion, text-layer census
PYTHONPATH=. python3 checker/lattice.py                    # -> 9/9 passed
PYTHONPATH=. python3 checker/calibration_contract.py       # -> 17/17 passed
PYTHONPATH=. python3 checker/fusion.py                     # -> 19/19 passed
PYTHONPATH=. python3 scripts/text_layer_census.py --test   # -> 24/24 passed

# McNemar / Wilson, independently re-derived against fusion.py's docstring claim
PYTHONPATH=. python3 -c "
from checker.interval import mcnemar, wilson
print(mcnemar(11, 8))        # 0.6476058959960938
print(wilson(50, 70))        # (0.599, 0.807)
print(wilson(51, 70))        # (0.615, 0.819)
"

# Corpus section count (README/FAILURE_MODES vs CLAUDE.md — see Appendix)
ls corpus/companies_act/*.json | wc -l   # -> 529
```

Commands this report could **not** run from the worktree, because the files
do not exist there — reproducible only from the main checkout at
`/Users/nishantsingh/PlacedOn/placedon-law-backend/`, whose exact HEAD commit
this report did not capture (git operations against that checkout are
deliberately blocked from this isolated worktree session):

```bash
PYTHONPATH=. python3 checker/rings.py
PYTHONPATH=. python3 checker/feeds/__init__.py
PYTHONPATH=. python3 checker/feeds/ofac_sdn.py
PYTHONPATH=. python3 checker/feeds/egazette.py
python3 scripts/watch_gazette.py --test
```

Where this report needed a number attributed to a 2026-09-17 run of that
code, it is tagged SOURCED to `docs/D002_CLOSURE_REPORT_2026_09_17.md` or
quoted as briefed from the coordinating session — never presented as
independently MEASURED by this report, because it was not.

---

## Appendix — claim ledger

| # | Claim | Tag | Source | Date |
|---|---|---|---|---|
| 1 | Nine bodies declared, one held (CA2013); one more (SEBI_LODR) held as a consolidation wired to no obligation | MEASURED | `checker/scope.py`, this worktree, `eb48905` | 2026-09-17 |
| 2 | `checker/scope.py` self-test: 20/20 passed, including "no obligation is decided against a body we do not hold" | MEASURED | same | 2026-09-17 |
| 3 | Corpus holds 529 Companies Act sections | MEASURED | `ls corpus/companies_act/*.json \| wc -l`, this worktree | 2026-09-17 |
| 4 | `CLAUDE.md`'s repository-map table states 527 sections for the same directory | SOURCED (disagrees with #3) | `CLAUDE.md`, this worktree | as read 2026-09-17 |
| 5 | Full test suite: 163 suites, 0 failed, GREEN | MEASURED | `./scripts/run_tests.sh`, this worktree, `eb48905` | 2026-09-17 |
| 6 | Main checkout's suite count after the D-002 fix: 164 suites, 0 failed, GREEN (163 + 1 new suite, `checker/pdf_pages.py`) — consistent with #5, not contradictory | SOURCED | `docs/D002_CLOSURE_REPORT_2026_09_17.md` | 2026-09-17 |
| 7 | `checker/lattice.py`: 9/9 passed | MEASURED | this worktree | 2026-09-17 |
| 8 | `checker/calibration_contract.py`: 17/17 passed, including `ece_floor(0.9,20)=0.0513` and `ece_floor(0.1,6)=0.1063` | MEASURED | this worktree | 2026-09-17 |
| 9 | `checker/fusion.py`: 19/19 passed | MEASURED | this worktree | 2026-09-17 |
| 10 | `mcnemar(11,8) = 0.6476`; Wilson(50,70)=[0.599,0.807]; Wilson(51,70)=[0.615,0.819] | MEASURED | independently re-derived, this worktree | 2026-09-17 |
| 11 | `docs/PLAN_08_BOOKMARK_AND_GODSEYE.md` states the same McNemar result as "0.648" and the same intervals as [0.60,0.81]/[0.61,0.82] — agrees with #10 within rounding | SOURCED | PLAN_08 | 2026-09-11 |
| 12 | `scripts/text_layer_census.py --test`: 24/24 passed | MEASURED | this worktree | 2026-09-17 |
| 13 | RRF fusion p@1 0.80, recall@5 0.97 on the 70-case eval | SOURCED | `docs/ABLATION_CORRECTED.md` | measured 2026-09-06 |
| 14 | BM25 p@1 0.71 / recall@5 0.91; dense p@1 0.73 / recall@5 0.96 | SOURCED | `checker/fusion.py` docstring | as read 2026-09-17 |
| 15 | Amendment corpus n_eff ≈ 6 amending events; conditional-volatility question survives at n_eff ≈ 261 section-years | SOURCED (not independently re-derived) | `docs/PLAN_08_BOOKMARK_AND_GODSEYE.md` §6 | 2026-09-11 |
| 16 | Realrun 2026-09-14: gemini-3.6-flash 0 LEAK/10; gemma3:1b 1 LEAK/18, closed same day | SOURCED | `eval/realrun/scorecard.md` | 2026-09-14 |
| 17 | Realrun (current): azure:gpt-5-mini 0 LEAK, 17 of 18 run; azure:llama-3-3-70b 0 LEAK, 18 of 18 run | MEASURED (JSON files read directly) | `eval/realrun/last_run_azure_*.json`, this worktree, commit `94c5514` | 2026-09-15 |
| 18 | D-002: page-count agreement went 0/14 → 14/14; new suite `checker/pdf_pages.py` 13/13 | SOURCED (worktree lacks the file; not independently re-run) | `docs/D002_CLOSURE_REPORT_2026_09_17.md`, main checkout | 2026-09-17 |
| 19 | Split-word counts on the Board Rules gazette agree within 8% across stdlib/pypdf/pdfplumber; concluded to be a source defect (SD-005), not a reader bug | SOURCED (INFERRED conclusion, stated as such by its own source) | same | 2026-09-17 |
| 20 | This worktree's `docs/SOURCE_DEFECTS.md` runs only to SD-004; SD-005 exists only in the main checkout | MEASURED (by direct comparison of both files) | this worktree vs main checkout | 2026-09-17 |
| 21 | OFAC SDN feed: `<Record_Count>19385</Record_Count>`; 29,076,910 bytes; licence `LICENCE_UNVERIFIED` | SOURCED (module docstring/fixtures; live fetch not run) | `checker/feeds/ofac_sdn.py`, main checkout | as read 2026-09-17 |
| 22 | eGazette watcher's four measured traps (leaf-only TLS, HEAD-404, ASP.NET postback listings, UNSEEN serial gaps) | SOURCED | `checker/feeds/egazette.py`, main checkout | as read 2026-09-17 |
| 23 | eGazette live run: 7 gazettes listed, high-water serial 276299 | MEASURED (as briefed, by the coordinating session; not re-run by this report) | coordinating session | 2026-09-17 |
| 24 | Bloomberg Law's flagship features are four-for-four downstream of a US filing mandate (Reg S-K 601(b)(10) / PACER) with no Indian equivalent | SOURCED | `docs/PLAN_14_TERMINAL_AND_FEEDS.md` §2.3 | source-checked 2026-09-17 |
| 25 | e-Courts/Docket Key Indian-equivalent finding is PARTIALLY_VERIFIED, not a blanket negative | SOURCED | same, §2.3 | 2026-09-17 |
| 26 | Both Bloomberg price figures are SECONDARY-SOURCED and can never become vendor-primary (no published pricing page) | SOURCED | same, §1 | 2026-09-17 |
| 27 | SEBI debarred-entities feed: every route checked is blocked, forbidden by terms, or paid; none bypassed | SOURCED | `docs/research/SOURCE_AUDIT_SEBI_DEBARRED_2026_09_17.md`, main checkout | 2026-09-17 |
| 28 | `checker/rings.py` exists only in the main checkout; this report read but could not execute it from the worktree | MEASURED (absence confirmed by `ls`) | this worktree vs main checkout | 2026-09-17 |
| 29 | The engine served a superseded s.2(85) threshold as CURRENT for nine months | SOURCED | `docs/FEATURES.md` F7 | as read 2026-09-17 |
| 30 | "Four of the most-read Indian compliance sites still publish the 2022 figure, one publishes a figure that never existed" | SOURCED (project's own claim; not independently re-checked by this report) | `docs/PLAN_00_INDEX.md` | 2026-09-09 |
| 31 | H-C (one practising Company Secretary reviewing output) remains open since 2026-09-04 | SOURCED | `docs/THEMIS_STATUS_AND_NEXT_2026_09_17.md` §8 | 2026-09-17 |
| 32 | FEATURES.md internal inconsistency: F2 entry says 2 of 15 rows refuse; its own summary says four obligations refuse | SOURCED (flagged by the project itself, not resolved by this report) | `docs/THEMIS_STATUS_AND_NEXT_2026_09_17.md` §5, `docs/FEATURES.md` | 2026-09-17 |
| 33 | Trademark clearance for "Themis" is UNVERIFIED and likely contested (Clio's "Themis Solutions Inc.," a bar-review product, a banking-compliance product) | SOURCED | `docs/THEMIS_STATUS_AND_NEXT_2026_09_17.md` §0 | 2026-09-17 |
| 34 | `docs/FAILURE_MODES.md`'s findings (gate scoring 67 of 69 attested pairs; single-label human-review bucket) | SOURCED, historical — not re-verified against current code | `docs/FAILURE_MODES.md` | written 2026-09-02 |
