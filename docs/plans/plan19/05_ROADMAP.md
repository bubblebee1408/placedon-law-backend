# 05: Roadmap, phases G0–G7, interleaved with PLAN_17's M0–M12

**Rule of the roadmap:** no phase starts until its entry gate is met, and none ends until its
exit gate is met *by a measurement or a test*, never by an assertion. Sizes follow PLAN_17: S is
about 1–3 agent days, M about 1–2 weeks, and L longer. Sizes are **[I]** estimates. Every
estimate made in this repository so far has been optimistic.

## Dependency map

```
PLAN_17:  M0 ─ M1 ─┬─ M2 ─ M3 ─ M4 ─ M5 ─ M6 ─ M7 ─ M8 ─ M9 ─ M10 ─ M11 ─ M12
                    │         │    │                        │     │
PLAN_19:  G0 ───────┤         │    │                        │     │
                    └─ G1 ─ G2 ┴─ G3 ─────────────── G4 ────┴── G4b (terminal)
                                    └─ G5 (citator) ── G6 (entity resolution)
                                                       G7: gated, and most of it never
```

- G0 runs **alongside M1**. Both are about trusting what already exists.
- G1 and G2 need nothing from the platform. They are Ring 1 algebra and storage, testable
  offline.
- G3 needs M4's database only to persist subscriptions per tenant. It can run on JSONL first,
  like the operation store.
- G4 **is** M3's CLI and M9's MCP authorisation, done once through a verb table instead of three
  times.
- G4b (the terminal) is a page in M10's web app.

---

## G0: truth before breadth · S–M · runs with M1

**Why first.** The gold set's first run found two failures that every later phase would inherit:

- 5 of 7 practitioner-phrased questions about unheld law walked past the scope gate
  (`ask_scope.py:196`) and returned an empty pack. That is silence that reads as "no obligation
  found".
- 19 of 22 practitioner abbreviations retrieve nothing.

A watch engine built on this would alert from a retriever that cannot find "KMP".

| Step | What | Subagent | Done when |
|---|---|---|---|
| G0.1 | Fix `currency.acquisition_for`: anchor the match to a registered instrument id; return a distinct PENDING for registered-but-unread | developer → qa-reviewer | Tests: "Companies Act 2013" and "G.S.R." alone do not return `read=True`; KMP, PAS and SEBI instruments return PENDING, not `None` |
| G0.2 | Freeze a **held-out split** of the gold set. Commit the split's hash before any fix is scored | benchmark-engineer | `eval/goldset/split.json` committed; `run.py` refuses to score the test split twice without a new hash |
| G0.3 | Scope gate from practitioner phrasing: a **declared lexicon per unheld body** (regulator forms, defined terms, signature concepts such as "open offer" and "demand notice"), written by the legal-source-researcher from the statutes' own text | legal-source-researcher → developer | Dev split: 7/7 practitioner phrasings refuse. Test split: reported as a count with its Wilson interval, **no rate below n = 30** |
| G0.4 | Abbreviation lexicon for retrieval, from s.2 definitions and chapter headings, each entry citing the provision it came from | corpus-engineer → developer | Abbreviation retrieval measured on the test split; McNemar against the incumbent (04 §8). If n is too small to decide, the result is reported as **undecided**, not as a gain |
| G0.5 | Declare the evidence-chain order (04 §1) | legal-verifier (decision) → developer | `provenance.EVIDENCE_ORDER` is a `lattice.Lattice`; the legal-verifier's reasoning is recorded in `docs/` |

**Exit gate:** `scripts/verify_green.sh` is green, the gold-set run is recorded, and the
`RETRIEVAL_DEFECT` doc (local branch) is landed on `main`.

## G1: ontology v1 and the observation store · M

**Entry:** G0.5 is done, because `Observed.evidence` needs the declared order.

| Step | What | Done when |
|---|---|---|
| G1.1 | `checker/ontology.py`: the types in 03 §2. `LINK_TYPES` built from `entity_graph.Rel` | Rings registered; `_test()` proves no Individual carries a name field (a dataclass-field scan) |
| G1.2 | `checker/observation_store.py`: append, `as_of`, history, retract. JSONL, log first, atomic | Theorem 6 (replay) as a gate test: write, retract, and query at the old `known_at`; the answer is byte-identical |
| G1.3 | `event_log` reads `known_at` from the store when present | The docstring's stated limitation is removed, **and only then** |
| G1.4 | Red-team pass on the store, in the RT-08…RT-14 style | New findings are logged in `docs/research/RED_TEAM_*`; each is fixed with a test or recorded as accepted |

**Exit gate:** replay holds under the red-team's attempts, and the peer suites stay green.

## G2: derivations and the evidence semiring · S–M

| Step | What | Done when |
|---|---|---|
| G2.1 | `checker/derivation.py`: `Derivation`, `evaluate`, `dependents`, `reevaluate` | Property tests for Theorem 1's axioms, Lemma 2 (minimal witnesses give the same result as the full DNF on random formulas) and Corollary 3 (monotonicity) |
| G2.2 | Same-value guard: OR over conflicting values raises and surfaces `SOURCE_CONFLICT` | Test |
| G2.3 | **No behaviour change:** every existing single-derivation rollup (`currency`, `staleness`, `corpus_currency`) gives an identical verdict and witness through `derivation` | A differential test over every existing obligation. Zero diffs, or the phase stops |
| G2.4 | `scripts/revocation_report.py`: retract fact x → the conclusions affected, before and after | Demonstrated on G.S.R. 880(E) against a copy of the store |

**Exit gate:** G2.3 shows zero diffs. That is the proof that the new algebra is a
generalisation, not a replacement.

## G3: the watch engine and the permitted feeds · M–L

**Entry:** G1 and G2 are done. G0.1 is done, because propagation starts at `acquisition_for`.

| Step | What | Done when |
|---|---|---|
| G3.1 | `checker/watch.py`: `Subscription`, `Alert`, `on_observation`, nightly full-recompute check | Incremental equals full on a replay of every event in `event_log` |
| G3.2 | SEBI RSS feed (Ring 2, `SIGNAL`) through `feeds/common/fetch.py` (robots, TLS, RT-04 truncation) | Recorded fixture; robots honoured; a live fetch only on explicit run |
| G3.3 | data.gov.in MCA Company Master Data, **API key and ZIP only**, GODL attribution shown | The key is founder-owned (a new H- task); no HTML crawl anywhere (`robots.txt: Disallow: /`) |
| G3.4 | GDELT, **optional**, as `SIGNAL` only, attributed as its terms require | Skip unless a named subscription kind needs it |
| G3.5 | **Human audit** of edge types on alert paths, to the n of 04 §5 | Per-type counts published; alert precision is stated as counts until each type reaches its audit n |
| G3.6 | Verbs `watch.subscribe` (WRITE) and `watch.alerts` (READ) | WRITE is exposed only through the gateway with token identity; never over MCP before M9 |

**Exit gate:** a replay of the last 12 months of eGazette events over the subscriptions of 3
synthetic matters. Every alert carries a path and a derivation, and **zero** alerts come from
unread instruments without `BASIS_UNACQUIRED`.

## G4: one verb table, three surfaces · M · this *is* M3's CLI and M9's MCP

| Step | What | Done when |
|---|---|---|
| G4.1 | `checker/verbs.py` wraps today's 8 routes and 13 MCP tools. **No behaviour change** | Parity test: the verb set is equal across surfaces; byte-identical payloads for the recorded fixtures |
| G4.2 | `mcp/tools.py` generated from `verbs` | The existing `scripts/themis_mcp.py` tests pass unchanged |
| G4.3 | CLI `scripts/themis` generated (PLAN_17 M3) | `themis company events <cin> --as-of …` equals the HTTP payload |
| G4.4 | Gateway mounts `http_routes()` (PLAN_18 §2.1) | M3's own gate |
| G4.5 | MCP over HTTP with OAuth 2.1, PKCE S256, Protected Resource Metadata (PLAN_18 §2.12) | M9's own gate; also makes the server BYOMCP-compatible with Harvey (`CONNECTORS_AND_THE_WHITE_SPACE` §4) **[I: verify against Harvey's partner requirements when M9 lands]** |
| G4b | Terminal grammar file, shared by the CLI and a web page in M10 | ux-designer spec first; AGENTS.md checklist; the abstain-grey and transport-failure states are visibly distinct |

## G5: the citator · L

**Entry:** counsel has answered whether the SC corpus's CC-BY grant is sound
(02 §5, **[BLOCKED]**, a founder task).

| Step | What | Done when |
|---|---|---|
| G5.1 | Ingest the SC corpus via `feeds/common`, hash-stamped, with licence tag CC-BY-4.0 plus the maintainer's name | `SOURCE_POLICY` updated; the attribution renders |
| G5.2 | Citation extraction (SCC, AIR, SCR, neutral) | Precision and recall on a 200-citation hand-checked sample, as counts with Wilson intervals |
| G5.3 | Treatment labels: a model proposes, a human labels; only labelled treatments are VERIFIED | An annotation guide written by the legal-source-researcher; inter-annotator agreement measured if there are two labellers |
| G5.4 | `case.cite` verb: `good_law(ref, as_of)` with the four outcomes of 03 §8 | "No negative treatment found" always states the corpus boundary |

## G6: entity resolution and the counterparty overlay · M

| Step | What | Done when |
|---|---|---|
| G6.0 | architect records: FS in stdlib, Splink as the test reference only (03 §9) | Decision doc |
| G6.1 | Labelled set of known true matches (sanctions and IBBI entries ↔ CIN/DIN), built by a human | n stated; used to set the recall threshold |
| G6.2 | `checker/resolve.py`: EM for m/u, weights, proposals to `review_queue` | Weights equal Splink's on a shared fixture, to 1e-6 |
| G6.3 | OpenSanctions/FtM mapping, **only if** the founder approves its paid reseller tier (PLAN_08 §5) | **[BLOCKED]** on budget; OFAC SDN (built) meanwhile |

## G7: gated, and mostly never

| Item | Gate to open it | Default |
|---|---|---|
| Licensed NSE/BSE market data | SEBI LODR/SAST law **held** in `scope.py`, plus a paying listed-company client, plus the terms read and quoted, plus a signed vendor contract | **Closed** |
| Zauba shipment data | All three conditions in 02 §3 | **Closed** |
| Judgment prediction | Every one of 04 §7's five reasons answered | **Closed. Do not reopen without the founder writing down which reason stopped holding** |
| 3-D globe or map | A compliance question that geography decides | **Closed** (PLAN_08 §5) |

## Milestone-to-claim table, for investors

| After | What may truthfully be said |
|---|---|
| G0 | "Refuses questions about law it does not hold, including when the Act is not named, measured on a held-out set (count and interval)" |
| G1 + G2 | "Every answer can be replayed as given on its date, and every answer resting on a withdrawn source can be listed" |
| G3 | "Watches Gazette changes against your companies and says why each alert fired" |
| G4 | "One engine, available as a CLI, an API, and inside Claude, Copilot or Harvey via MCP" |
| G5 | "Says whether a Supreme Court authority has been overruled, within the corpus it holds" |
| **Never, at any phase** | An accuracy rate without a human-labelled benchmark; "real-time market intelligence"; "predicts outcomes" |
