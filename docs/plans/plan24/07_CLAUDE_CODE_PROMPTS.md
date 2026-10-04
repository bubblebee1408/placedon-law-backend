# 07: Claude Code prompts — the first one in full, then one per phase

Each prompt is self-contained. Paste it into Claude Code at the repository root. It follows
`CLAUDE.md`:

- inspect before editing;
- one logical change per commit;
- no production change without tests;
- the code-task output format.

It uses the subagents in `.claude/agents/`. If a subagent type is not registered in the running
session (TASKS G-P1), use `general-purpose` with that agent's `.md` brief pasted in. Do not skip
the role.

---

## Prompt 1: T0, finish the incomplete work (run this first)

```text
You are working on Themis, the engine inside placedon-law-backend. Read CLAUDE.md,
docs/plans/plan24/00_INDEX.md and docs/plans/plan24/01_STATE_AND_UNFINISHED.md before anything else.
Your job is phase T0: finish the incomplete work that code can close. You build no new
intelligence feature in this run.

PRE-FLIGHT (stop and report if any step fails)
1. The main worktree may hold other sessions' uncommitted work. Do NOT touch it.
   Create an isolated worktree:
     git fetch origin
     git worktree add ../themis-t0 -b t0/finish origin/claude/harvey-india-platform-analysis-d2mmqi
   and work only in ../themis-t0. If that branch has been merged to main, base on origin/main instead.
2. python3 -m venv .venv && . .venv/bin/activate &&
   pip install -r requirements.txt -r requirements-dev.txt
3. ./scripts/run_tests.sh and record the HARNESS_RESULT line verbatim. This is the baseline.
4. List research/TASKS.md rows in state open/blocked/ready. Confirm which of
   T0.2-T0.7 in plan24/01 §3.1 are still open on this branch. Skip any that are already closed,
   and say so.

WORK, in this order. One commit per item, each with its test.
T0.2 Hermetic harness.
  (a) checker/provenance.py: the "unreadable file" test must not depend on file permissions,
      because it fails when run as root. Inject a PermissionError (monkeypatch the open
      used by file_digest). Keep the assertion: unreadable -> refused as unreadable, not None.
  (b) checker/s96_slice.py needs "Act 1 of 2018" from a network cache. Find how
      Corroborator.witness_text resolves it. Add a committed, hashed fixture of the witness,
      from the Gazette copy if you can obtain it by permitted means; otherwise an Indian Kanoon
      copy under its attribution terms, recorded with URL and date. Make the suite read the
      fixture when the network is absent.
      If no permitted copy can be obtained, STOP this item and record it in TASKS.md.
      Never fabricate the witness text.
  (c) Add a CI job (.github/workflows) that runs ./scripts/run_tests.sh in a clean
      checkout with requirements-dev installed. The PR check is the proof.
T0.3 D-002b. Subagent: corpus-engineer, then qa-reviewer.
  Move checker/pdf_pages.extract_pages from pypdf to pdfplumber (already in
  requirements-dev.txt; state the reason in the commit). Re-extract
  corpus/rules/board_powers_2014.json with the new reader. Report split-word warnings
  per rule, before and after. Never repair source text by hand. A remaining artifact is
  listed, not fixed.
T0.4 PLAN_23 O1. Finish review_document, runs.approve, runs.reject and the playbook text, each
  gated per PLAN_23 §4. A decision stores: reviewer, reason, whether the quote was viewed,
  run id, and the law versions used. Test: an approve without "quote viewed" is refused.
T0.5 R-013 and R-014 as described in research/TASKS.md.
T0.7 A-011: re-verify /v1/ask against web/assistant/contract.md with a fresh subagent
  (qa-reviewer) that did not write the fixes. Record the verdict in TASKS.md.

STOP CONDITIONS
- A decision that belongs to the founder or to legal-verifier (G0.5, L-007, anything that
  changes what is served): stop, write the question into TASKS.md, and continue with the next item.
- Any test you would need to skip or weaken to go green: stop and report. Never skip a test.
- Two consecutive failed attempts at one item: stop that item and report.

FINISH
- ./scripts/run_tests.sh: record HARNESS_RESULT before and after.
- Update research/TASKS.md rows you closed, with commit hashes.
- Push t0/finish and open a DRAFT PR against the branch you based on.
- Report in CLAUDE.md's code-task format: Files changed · Tests added or updated ·
  Commands run · Results · Known limitations · Commit hash.
Do NOT touch T0.1: merging branches is the founder's call. T0.6 lives in the website repo
(placedon-claude-legal-3300/AGENTS.md route list); do it there as its own PR, not here.
```

---

## Prompt 2: T1, ontology, observation store, evidence semiring

Entry: T0 merged, and the G0.5 evidence order decided and recorded by a person.

```text
Read CLAUDE.md, docs/plans/plan24/03_ARCHITECTURE.md §2, and docs/plans/plan19/03_ARCHITECTURE.md
§2-§4 and 04 §1-§4 (on the branch that holds them). Implement PLAN_19 G1.1-G1.4 and
G2.1-G2.4 exactly as specified there. Use the G0.5 decision recorded in docs/ as
provenance.EVIDENCE_ORDER. Do not choose the order yourself; if it is not recorded, STOP.
Subagents: architect (review the ontology types against checker/entity_graph.Rel before
code), developer, qa-reviewer; then a red-team pass in general-purpose on the store.
Exit gates: replay byte-identical under the red team's attempts; the G2.3 differential test
shows zero diffs across every existing obligation. Register ontology.py and derivation.py
in checker/rings.py with their ring. Report in CLAUDE.md's code-task format.
```

## Prompt 3: T2, the learning loop (the first "it learns" prototype)

Entry: T1 exit met. Either counsel Q1 is answered, or labels are restricted to Placedon's own
reviews of public material.

```text
Read docs/plans/plan24/05_LEARNING_AND_ADAPTATION.md. Build, one commit each with tests:
1. gateway/migrations/006_labels.sql: a labels table (tenant_id, intent, run_id,
   step_id, decision, reason, quote_viewed, reviewer, purpose in {serve,evaluate,contribute},
   law_versions, behaviour_version, created_at), under FORCE ROW LEVEL SECURITY like
   001-005. Add an RLS mutation test.
2. runs.approve / runs.reject write a label in the same transaction. Test the round trip.
3. checker/promotion.py: promote(candidate, incumbent, test_split, n_required) exactly
   as 05 §5. It uses Connor's n from PLAN_19 04 §8 and exact McNemar. A test split hash must be
   committed before the candidate's creation time, or the call raises.
   Fixture tests: a known-better candidate returns BETTER; equal returns UNDECIDED; small n
   returns UNDECIDED.
4. behaviour_version: a versions table edited only by a person (no API verb writes it).
   Every run records the version it was served under.
5. scripts/learning_report.py: labels per intent and tenant, n needed per pending candidate,
   and the gate verdict. Run it on today's data: expect UNDECIDED everywhere, and say so.
6. The research registry: checker/research_registry.py holds PaperCard records (claim, venue,
   year, dataset, n, metric, tag, task_type in {identification, categorisation,
   forecasting}, rule_forced). Seed it from docs/plans/plan24/02_EVIDENCE.md by hand. No model
   admits a card.
Subagents: architect (schema), developer, cost-governor (if any model call is added: none
should be), trust-boundary-reviewer (the report's wording), qa-reviewer.
```

## Prompt 4: T3, tenant adaptation

```text
Read docs/plans/plan24/05 §3 and docs/plans/PLAN_20_INHOUSE_CORPORATE.md rows 1-3. Build the vault
retention and deletion (crypto-shred of a per-tenant data key; every derived index, memory
entry and scorer keyed to the tenant). Also build the position of record, the recall register
(reverse index Position -relied_on-> Provision@version), precedent-memory retrieval (shown with
date and reviewer, re-checked against current law before display), and a per-tenant BM25 index.
Exit gate: the two-tenant isolation test in plan24/06 T3, and a deletion test proving that
no artifact of a deleted tenant remains readable.
```

## Prompt 5: T4, watch → recall

```text
Implement PLAN_23 O7 and O9 and PLAN_19 G3.1-G3.3 (SEBI RSS through feeds/common/fetch.py,
robots honoured; data.gov.in MCA master data by API key and ZIP only; never crawl). Exit gate:
a replay of 12 months of eGazette events where incremental alerts equal a full recompute, and
G.S.R. 880(E) recall listing every stored position that relied on s.2(85).
```

## Prompt 6: T6, forum analytics (only after NCLT access terms are read and quoted)

```text
Read docs/plans/plan24/04 §1-§3 and the quoted NCLT/NCLAT access terms in docs/research/. If
they are absent, STOP. Build checker/analytics/ as Ring 3: Wilson proportions, Kaplan-Meier
with Greenwood intervals and censoring, and a hierarchical Beta-Binomial, each with a synthetic
test of known answer. ForumCase ingestion covers Companies Act matter types only (04 §2).
Add a source scan to the gate: no analytics module reads a judge-identity field. Every
Estimate carries n, interval, method, data cutoff, and the sentence "not a prediction for
your matter". Subagents: architect, developer, benchmark-engineer (the synthetic tests),
trust-boundary-reviewer, qa-reviewer.
```

T5 (citator) uses PLAN_19 06's G5 prompt unchanged, after counsel Q2. T7 has no build prompt:
its first act is to commit the pre-registration of 04 §5 and have a person sign it.
