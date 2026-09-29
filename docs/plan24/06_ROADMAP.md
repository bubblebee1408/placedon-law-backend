# 06: Roadmap — phases T0–T8, with entry and exit gates

**Rules of the roadmap** (inherited from PLAN_19 05):

- A phase starts only when its entry gate is met.
- A phase ends only when its exit gate is met by **a test or a measurement**, never by an
  assertion.
- Sizes: S ≈ 1–3 agent-days, M ≈ 1–2 weeks, L longer. They are **[I]**, and every estimate in
  this repository so far has been optimistic.

## Dependency map

```
FOUNDER TRACK (parallel, never blocked by code):
  H-001 CS session ─ counsel Q1 (DPDP labels) ─ counsel Q2 (CC-BY court text) ─ counsel Q3 (judge analytics) ─ G0.5 decision

CODE TRACK:
  T0 finish ──► T1 ontology/store/semiring ──► T2 learning loop ──► T3 tenant adaptation ──► T8 surfaces
                          │                          │
                          └────► T4 watch → recall ◄─┘
                                        │
                     counsel Q2 ──► T5 citator
                 NCLT access ──► T6 forum analytics (L2–L4) ──► T7 forecasting research (L5, may never ship)
```

| Phase | Covers | Size | Entry gate | Exit gate |
|---|---|---|---|---|
| **T0 Finish** | 01 §3.1: T0.1–T0.7 | S–M | none | Harness GREEN **in a clean clone** (a CI job, not a laptop); Board Rules re-extracted with 0 split-word warnings, or each remaining one listed; O1 done criteria met; website AGENTS.md route list matches `checker/api.py` |
| **T1 Ontology + store** | PLAN_19 G0.5, G1, G2 | M | T0; the G0.5 decision recorded by a person | PLAN_19's own exit gates: replay byte-identical under red-team; G2.3 differential test shows **zero diffs** |
| **T2 Learning loop** | 05 §2, §5; research registry; behaviour versions | M | T1 (labels reference ontology ids); counsel Q1 answered **or** labels restricted to Placedon's own public-material reviews | (i) A decision in `runs.approve` round-trips to a label with purpose, span and law versions; (ii) `promote()` returns UNDECIDED on today's data and BETTER/WORSE on a synthetic fixture with a known answer; (iii) every served run records `behaviour_version`; (iv) 20 PaperCards admitted by a person |
| **T3 Tenant adaptation** | PLAN_20 rows 1–3 (vault, position of record, recall register); 05 §3 memory + index | M–L | T2 | Two-tenant isolation test: tenant B's retrieval, memory and statistics are byte-identical whether or not tenant A exists. RLS mutation test (drop a policy → suite red) |
| **T4 Watch → recall** | PLAN_23 O7, O9; PLAN_19 G3 (SEBI RSS, data.gov.in MCA master data) | M–L | T1; T3 for positions | Replay of the last 12 months of eGazette events: incremental alerts = full recompute; G.S.R. 880(E) recall lists every stored position that relied on s.2(85) |
| **T5 Citator (L1)** | PLAN_19 G5 | L | Counsel Q2 in writing; AWS SC dataset pinned by version and hash | Citation-extraction precision and recall on a hand-checked sample of 200 citations, reported with Wilson intervals; only human-labelled treatments served as fact |
| **T6 Forum analytics (L2–L4)** | 04 §2–3 | M–L | NCLT/NCLAT access terms read and quoted in `docs/research/`; permitted | Recomputation test (same data → same estimates); censoring test (a synthetic set with known survival → KM within tolerance); **judge-field source scan** in the gate; every screen shows n, interval and cutoff |
| **T7 Forecasting research (L5)** | 04 §5 | L | T6 exit; the pre-registration committed with its hash | 04 §5 steps 1–8. **"Closed, did not pass" is an acceptable exit** and is recorded in `NON_GOALS.md` |
| **T8 Surfaces** | PLAN_19 G4/G4b (verb table → API/MCP/CLI, terminal), PLAN_17 M9 (hosted MCP + OAuth), Word add-in; optional ASR | M each | T2 for the verbs, T3 for tenant data | Parity test across the three generated surfaces; the terminal kill criterion (PLAN_19 08: 3 pilot users, nobody uses it twice → drop it) |

## How the phases map onto existing plans

| This plan | Existing step it absorbs or extends |
|---|---|
| T0 | TASKS D-002b, A-011, R-013/014; PLAN_23 O1 |
| T1 | PLAN_19 G0.5, G1.1–G1.4, G2.1–G2.4 |
| T2 | PLAN_23 rule 5 ("every human decision is stored as labelled data"), O8 (MAST tagging); master plan §105 criterion 18 (paper registry) |
| T3 | PLAN_20 rows 1–3; PLAN_21 decision 3 |
| T4 | PLAN_23 O7, O9; PLAN_19 G3 |
| T5 | PLAN_19 G5 |
| T6–T7 | New. Replaces PLAN_19 04 §7's flat "do not build" with a gated ladder, and **keeps its conclusion for L5 until the gate passes** |
| T8 | PLAN_19 G4/G4b, PLAN_17 M9–M10, PLAN_22 D6–D7 |

## What is deliberately absent

- **Any GPU, fine-tuning or foundation-model step.** PLAN_22 D1's revisit condition (1,000+
  reviewed traces **and** a repeated workflow failure) is unmet.
- **International data**, per the founder.
- **NSE, Zauba, district courts** (PLAN_19 02; 04 §7).
