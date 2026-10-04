# 05: Learning and adaptation — how Themis learns a company and updates itself

## 1. The principle

The founder asked for a system that "trains by itself, adapts to the company's data, and
updates itself frequently". The evidence (02 §2) forces a precise reading of that:

- **What learns:** memory, indexes, rules-as-data, small per-tenant scorers, and calibration.
  All of them are stored as dated, sourced, reversible data.
- **What does not learn:** the weights of a language model. Weights cannot be dated (L5), make
  hallucination worse when fed new facts (L2), and leak what they were fed (L3).
- **What decides that something learned may be used:** a frozen test and a person. The model
  never decides, and neither does the system on its own authority.

## 2. The loop

```
  (a) a lawyer approves / rejects / edits a run     runs.approve / runs.reject  [R:H]
        │   stored with reason, span viewed, reviewer, tenant, matter, law versions
        ▼
  (b) the decision becomes a LABEL                   labels table, per intent, per tenant
        │   HUMAN provenance; SYNTHETIC may never carry an answer key (goldset rule [R])
        ▼
  (c) labels flow into two places
        ├─► tenant MEMORY (immediately usable, retrieval only)
        │     precedent positions: "on 12-08 we decided X because Y"
        └─► EVAL SETS (dev / frozen test, hash committed)
        ▼
  (d) a CANDIDATE change is proposed                 lexicon entry, ranker weights, threshold,
        │                                            prompt, model route, playbook rule
        ▼
  (e) the GATE                                       McNemar on the frozen test split (S6)
        │   verdict ∈ {better, worse, undecided}; below the required n → undecided
        ▼
  (f) a PERSON promotes                              edits the version table; PLAN_22 D2
        ▼
  (g) BEHAVIOUR VERSION increments                   every served answer records it
        │
        └─► recall: answers served under the old version that the change would alter
```

**What updates automatically, and what never does:**

| Changes without a gate (a deterministic function of new data) | Changes only through (e)+(f) | Never changes |
|---|---|---|
| Observations from feeds; indexes; the citation graph; descriptive statistics (L2–L3 recomputed nightly); operations; recall lists; tenant precedent memory | Anything that changes *what is served for the same input*: retrieval ranking, lexicons, thresholds, prompts, model routes, playbook defaults, forecast models | The ring firewall; the scope register's invariant; "a model may not decide law" |

"Frequently" means this in practice:

- feeds poll daily (eGazette) or as each source allows;
- statistics recompute nightly;
- the promotion gate runs whenever the label count crosses the n the gate needs;
- calibration recomputes monthly, or on drift (§4).

## 3. Adapting to one company without training on it

| Mechanism | What it learns | Where it lives | Isolation |
|---|---|---|---|
| **Tenant ontology instance** | Their companies, people, matters, documents, as typed objects | observation store, tenant-marked | RLS [R:H] |
| **Tenant playbook** | Their standards: "we never accept uncapped indemnity" | `checker/playbook.py` as data [R:H] | per tenant |
| **Precedent memory** | Their past reviewed positions, retrievable as "how we handled this before" | positions + labels, retrieval-indexed | per tenant; shown with date and reviewer, and re-checked against current law before display |
| **Tenant retrieval index** | Their vocabulary: internal names, deal code-names, abbreviations | a per-tenant BM25 index over the vault (dense only if the D4 bake-off wins) | per tenant |
| **Tenant scorer** (later) | Which findings their reviewers accept or reject | a small logistic / gradient-boosted model over *features*, not text: rule id, clause type, severity, playbook deviation | per tenant, trained only on that tenant's labels; only after ≥ 200 labels on the intent, and only through the gate |
| **Tenant calibration** (later) | How often served claims survive their reviewers | a conformal threshold per tenant × intent | per tenant; n ≥ 59 zero-error or conformal minimums (PLAN_21 C1) |

**What the tenant scorer may do:** reorder findings, and suppress a finding class the tenant's
reviewers have rejected in ≥ 95% of ≥ 60 cases. Even then the finding stays one click away.
**What it may not do:** create a finding, alter a legal status, or cross tenants.

**Placedon's own layer** learns from:

- law changes, through the corpus and currency;
- Placedon's reviewers, on public material;
- tenant cases **only where the tenant opted in, per matter, revocably**. They enter the
  global *eval* set, not a training set. This is PLAN_21's recommendation, adopted here.

## 4. Drift: the law moves, so the numbers move

| Drift | Detector | Response |
|---|---|---|
| A provision changes | `currency.affected_by()` [R] → `recall` | Answers relying on the old version are listed; affected cached answers are invalidated (PLAN_23 O9) |
| The question mix changes (new clients, new topics) | Weekly share of each intent; a population-stability check on the retrieval-score distribution | Recalibrate; if coverage breaks, see next row |
| Served-claim coverage falls | ACI running coverage on reviewed answers (S5) | Below 1 − α on the rolling window: **stop serving the certified tier** for that intent; answers revert to fully quoted, uncertified mode |
| A forecast degrades (if L5 ever ships) | Rolling Brier vs the L4 base rate | Worse than base rate for 2 consecutive months: withdraw |

## 5. The promotion gate, stated as a function

```python
def promote(candidate, incumbent, test_split, *, n_required) -> Verdict:
    assert test_split.hash_committed_before(candidate.created_at)   # no peeking
    # McNemar: b = only the incumbent right, c = only the candidate right
    b, c = discordant_pairs(candidate, incumbent, test_split)
    if len(test_split) < n_required:
        return Verdict.UNDECIDED          # not "slightly better"
    p = mcnemar_exact(b, c)
    if p < 0.05 and c > b:
        return Verdict.BETTER             # a PERSON still has to promote
    if p < 0.05 and b > c:
        return Verdict.WORSE
    return Verdict.UNDECIDED
```

`n_required` comes from Connor's formula (PLAN_19 04 §8). For example, 312 when ψ = 0.10 and
δ = 0.05. On today's labels (0 HUMAN), every candidate returns `UNDECIDED`. **That is the
correct output, and the system should say it plainly.**

## 6. DPDP and privilege, before any label is stored

- **Purpose.** Each stored label records its purpose:
  - `serve` (answering this tenant);
  - `evaluate` (tenant eval set);
  - `contribute` (global eval, opt-in).

  DPDP's core obligations bind from **13 May 2027** (02 R3). Build to them now.
- **Third parties' data.** Directors' names, DIN and PAN inside documents are personal data.
  Labels store *spans by offset*, not copies, wherever the task allows. Where text must be
  copied, it is kept in the tenant's vault under its retention policy.
- **Privilege.** Matter-marked observations are never used outside the matter's ethical wall,
  including for that tenant's own scorer, unless the matter owner allows it.
- **Deletion.** Tenant deletion is crypto-shredding of the tenant's data key
  (STUDY_GUIDE 2.12). Every derived artifact (index, scorer, calibration) is keyed to the
  tenant and dies with it. **A tenant scorer trained on deleted labels is itself deleted, not
  kept.**
- **E6** (`annotation.to_sft()` puts raw text into an SFT export). It stays dormant, and this
  plan keeps it dormant: no path in §2 produces training text for an LLM.
- **Counsel.** DPDP's application to labels built from client documents needs counsel's view
  before the first tenant label is stored (PLAN_21, repeated).
