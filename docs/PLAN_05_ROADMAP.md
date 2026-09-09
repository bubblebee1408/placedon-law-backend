# Roadmap, gates, and the Bloomberg layer scoped honestly

## The rule

Every phase clears a falsifiable gate before the next begins. The largest
historical risk in this project is building ahead of evidence, so **Phase 0 is not
code.**

## Phase 0 — now, no code

| Work | Who | Why it is first |
|---|---|---|
| **Attest G.S.R. 880(E)** | operator | Artifact is on disk, hashed, PENDING_HUMAN_REVIEW. One command. Flips s.2(85) from refusing to answering while every competitor still says ₹4 crore |
| **Acquire + review the other three rules** | operator | Rule 6 (held, unread), Rule 15 (staged), KMP Rules (not held). Takes the pack from 11 answerable rows to 15 |
| **The 20-document test** | operator | What does the buyer's actual document mix look like — typed or scanned, English or mixed, stamped or clean? Decides whether v2 bulk review is six weeks or a research project |
| **Show the pack to one corporate legal team** | operator | The falsifier. See below |

**Gate:** does a practising corporate lawyer call the refusals useful or annoying?
That single answer is worth more than any feature, and no autonomous work moves it.

## Phase 1 — the wedge, in the surface lawyers already use

Word task-pane add-in, admin-deployed to one design partner. Spec in
[PLAN_04_WORD_ADDIN](PLAN_04_WORD_ADDIN.md).

**Gate:** does the design partner run it on real documents unprompted, twice, in
two weeks? Retention, not sign-ups. If they use it once for the demo and never
again, the wedge is wrong and it is cheap to have learned that.

## Phase 2 — deepen the corpus, not the feature set

- Acquire more instruments; every acquisition raises every surface at once.
- The entailment head, **only if M0/M1 in [PLAN_02](PLAN_02_MODEL_TRAINING.md)
  clear their gates.**
- Event Log UI + subscriptions on the engine built in v0.

**Gate:** does anyone pay? Price only once retention is shown.

## Phase 3 — bulk document review (the "Vault" analogue)

Gated entirely on the 20-document test. If the buyer's documents are typed English
`.docx` and `.pdf`, this is a six-week build on `extraction_schema` + the OCR
tiering in [PLAN_03](PLAN_03_DATA_SOURCES.md). If they are scanned, stamped, mixed-script
paper, it is a research project and should be scoped as one.

**The differentiator, stated precisely:** Harvey's Vault extracts into a table and
flags statistical outliers. Ours refuses the cell it could not read. For a
diligence lawyer that is the difference between a spreadsheet they must re-check
entirely and one where twelve cells are flagged and the rest are sourced.

---

# The Bloomberg layer — what actually transfers

The "Bloomberg for India" ambition is **research-side only**, and most of it does
not survive contact with Indian data reality. Scoped honestly:

| Bloomberg mechanic | Verdict for India | Why |
|---|---|---|
| **Corporate entity graph** | **Transfers — and is BUILT** | `entity_graph.py`: typed, dated relationships, tri-state answers |
| **Law-change monitor** | **Transfers — and is BUILT** | `event_log.affected_by()`: a Gazette lands → these obligations move → these companies |
| Docket analytics | **No** | NJDG bulk API is government-only, not licensable |
| Clause benchmarking | **No — nobody can build it in India** | No filing mandate creates the corpus. SEBI LODR requires "significant terms **(in brief)**", never the instrument |
| Company financials / filings | **Blocked on a contract** | No verifiable authorised MCA reseller; ₹100/company statutory route only |
| Firm-software integration | **Transfers** | But via Word, not a DMS connector — see PLAN_03 |

**The load-bearing insight:** clause benchmarking is not a feature we are losing
to a better-funded rival. It is one **nobody can build in India**, because the
corpus is not public. With no public contract corpus, the statute is the only
dense, public, authoritative corpus in Indian corporate law — and that is the one
this engine is built on.

## Why "God's Eye" as originally conceived is the wrong shape

A spatial/telemetry engine is a WebGL client plus a proxy. None of it touches
statute text, entity resolution, provenance or entailment — the half of the
problem that is actually hard. It would also import a heavy frontend stack into an
engine whose stated virtue is zero dependencies outside the standard library.

The live telemetry that matters here is **Gazette amendments and registry
filings**, not moving objects. That is the Event Log, and it is built. If a
spatial product is ever wanted, it is a separate bet with a separate buyer.

## What would falsify all of this

1. A practitioner calls the abstention useless — "just answer."
2. Nobody is ever actually caught by a stale figure.
3. SCC Online or Manupatra ships dated-instrument tracking as one feature.
4. The as-of date reads as hedging rather than rigour.

Demand is currently **n = 1**. That is a signal, not proof, and Phase 0 exists to
settle it before any of the above is built.
