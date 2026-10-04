# Repository audit — 27 September 2026

**What this is.** A map of the contradictions several AI sessions have written into four
repositories, precise enough to be fixed. It proposes deletions; it performs none.
Nothing outside this file was written, committed or pushed.

**Repositories audited**

| # | Repo | Access taken | State when read |
|---|---|---|---|
| 1 | `placedon-law-backend` (private, the engine) | read; wrote only this file | branch `loop/bookmark-godseye-v0` @ `97ed91f` |
| 2 | `Placedon-law-business-plan` (**PUBLIC**) | read only | `main` @ `4e902b7` |
| 3 | `placedon-claude-legal-3300` (frontend, local clone) | read only, never pushed | `fix/site-copy-claims` @ `b64fdce` |
| 4 | `probonhs/Main-product-frontend-` | cloned read-only to `/tmp` | `main` @ `b84c910` |

**Repo 4 is not a mirror — it is the newer of the two frontends.** Its root commit
`77dc2c5` is shared with repo 3, and `git merge-base main mirror/main` = `939f40f`,
which *is* repo 3's `main` head. Repo 4 is **17 commits ahead** of repo 3's `main` and
repo 3's `main` holds nothing repo 4 lacks. Repo 4 also carries a second root commit
`e7b508b` (LICENSE), merged at `6176dc2`. Practical consequence: **repo 3 is a stale
checkout with one unmerged fix branch on it, and repo 4 is what the site is built
from.** Everything in §2.3 follows from that.

**`git status` surprises, recorded and not acted on** (another session is committing
continuously):
- Backend HEAD is `loop/bookmark-godseye-v0`, **42 ahead / 20 behind `origin/main`**.
- Staged by another session: `docs/plans/PLAN_20_INHOUSE_CORPORATE.md`.
- Modified, unstaged: `backend/budget.py`, `checker/robots.py`.
- Six locked/active git worktrees live **inside** `.claude/worktrees/` (`sweep-a`,
  `store-c`, `redteam-d`, `agent-a208…`, `agent-a9b5…`, `agent-ab24…`), plus
  `../intel-worktree`. Each is a full copy of the tree. They are the reason a naive
  `grep -r` in this repo returns every hit seven times.

---

## 1. What runs today

*Five minutes, grounded in what executes — not what is planned.*

### 1.1 One sentence

A dependency-free Python engine that, given facts about an Indian company and a date,
returns which Companies Act 2013 duties attach and what evidence supports each one —
and refuses, by name, wherever the source is missing. It is a **loopback-only local
service with no authentication and no CORS.** There is no deployed backend.

### 1.2 The gate

```bash
bash scripts/run_tests.sh          # the gate. Prints one parseable line:
                                   # HARNESS_RESULT suites=205 failed=N status=GREEN|RED
bash scripts/verify_green.sh       # the only oracle anything downstream may read
```

Measured today: `HARNESS_RESULT suites=205 failed=2 status=RED`. **Both failures are the
two files the other session has open in the working tree.** At `HEAD` those same files
pass (`backend/budget.py` 92/92; `checker/robots.py` 66/67, the one failure being a
path-dependent check when run outside the tree). Treat the gate as green at HEAD and
red in the working tree for reasons that are not defects.

### 1.3 Entry points that actually serve something

| Command | Port | What it serves |
|---|---|---|
| `python3 scripts/serve_api.py` | 8020 | the JSON API — 8 routes, `checker/api.py::handle` |
| `python3 scripts/serve_ask.py` | 8021 | the Ask demo page (`web/assistant/`) + `/v1/ask`, `/v1/ask/documents`, `/v1/ask/document` |
| `python3 scripts/serve_matrix.py` | 8014 | an HTML obligation-matrix form (`/`, `/matrix`, `/pack`) — not `/v1/*` |
| `python3 addin/serve.py` | 3000 (https, self-signed) | Word task-pane dev server; proxies `/v1/*` to 8020 |
| `python3 scripts/themis_mcp.py` | stdio | MCP surface, **13 read-only tools**, no write of any kind |

`checker/api.py::handle(method, path, body)` is a pure function returning
`(status, dict)`. It is unit-testable without a socket, and that is where the routes
actually live — the servers are thin wrappers.

### 1.4 The two things that genuinely work end to end

1. **Point-in-time obligation attachment with a refusal.** `POST /v1/compliance-pack`
   takes company facts plus an `as_of` date and returns one row per duty in five states,
   plus an explicit *"what could not be verified"* list. No model is consulted; the
   register is deterministic, so this path cannot emit a guess. Boundary behaviour is
   proved on s.177, s.447 and s.35 — 6/6 boundaries, text changing across each
   (`scripts/prove_temporal.py`, `docs/evidence/TEMPORAL_PROOF.md`).
2. **Document currency check.** `POST /v1/document-check` reads a document's own date
   and answers whether the law it relies on is still current. It **refuses to run
   without a document date** rather than guessing one, because a guessed date silently
   moves the law the check runs against. `serve_ask.py` exposes this over the 22 public
   test documents in `corpus/testdocs/` — and deliberately has **no upload**.

### 1.5 What is held

- `corpus/companies_act/` — **527 section records** (529 files: 527 sections plus
  `_index.json` and `_manifest.json`). `_manifest.json` `count` = 527 and
  `section_ids` = 527. `_index.json` `entries` = 517.
- Scope: **9 bodies of law declared, 1 held** (Companies Act 2013). `checker/scope.py`
  is the authority. The tested invariant is that no obligation may exist in the
  register for a body that is not held.

### 1.6 What a new engineer must not believe

- **There is no deployed API.** `HOST = "127.0.0.1"` in every server; there is no host
  option; no auth; no CORS. A Vercel frontend cannot reach it, now or by configuration.
- **The website's product pages show fixtures.** `.env.example:27` leaves
  `PLACEDON_API_ORIGIN` blank, and `provider.ts::getEngine()` returns `MockEngineProvider`
  on a blank origin. The four `/product/*` surfaces therefore render `mock.ts`, not the
  engine.
- **No fine-tuned model, and none planned.** `docs/plans/PLAN_20_INHOUSE_CORPORATE.md:44-49`
  makes refusing a fine-tuned legal model the product thesis: weights cannot be
  as-of-dated.
- **No MCA21 read path.** `LicensedAggregatorProvider.fetch` raises
  `NotImplementedError`; the concrete adapter raises `NotConfigured` without `MCA_AGG_*`;
  no route imports either.

---

## 2. Contradictions

### 2.1 Backend ↔ frontend — the route table

Backend, enumerated from source. `checker/api.py` docstring lines 8-15 and dispatcher
lines 611-661 agree with each other and with the 404 fallback's `routes` list.

| Route | Backend: served at | Frontend believes | Verdict |
|---|---|---|---|
| `GET /v1/health` | `api.py:611` (8020) | `types.ts:8`, `AGENTS.md:58` | agree |
| `POST /v1/compliance-pack` | `api.py:648` (8020) | `types.ts:9`, `AGENTS.md:58` | agree |
| `POST /v1/document-check` | `api.py:638` (8020) | `types.ts:10`, `AGENTS.md:58` | agree |
| `GET /v1/company/{cin}/events` | `api.py:581` (8020) | `types.ts:11`, `AGENTS.md:59` | agree |
| `GET /v1/company/{cin}/events/{event_id}` | `api.py:587` (8020) | `types.ts:12`, `AGENTS.md:59` | agree |
| `GET /v1/instruments/{fragment}/affected` | `api.py:601` (8020) | `types.ts:13`, `AGENTS.md:60` | agree |
| **`POST /v1/ask`** | **`api.py:621` (8020)**, built `be078a6` 2026-09-18 | **`AGENTS.md:61` "DOES NOT EXIST — Do not call it"; `types.ts:5` "never add them here"** | **CONTRADICTION** |
| **`POST /v1/mca-strip`** | **`api.py:643` (8020)**, built `5a521fa` 2026-09-13 | **absent from all six-route lists** | **OMISSION** |
| **`GET /v1/ask/documents`** | **`serve_ask.py:62` (8021)** | unknown to the frontend | **OMISSION** |
| **`POST /v1/ask/document`** | **`serve_ask.py:61` (8021)** | unknown to the frontend | **OMISSION** |
| `GET|POST /`, `/matrix`, `/pack` | `matrix_view.py:391` (8014) | unknown to the frontend | omission (HTML, not `/v1`) |
| `GET /v1/company/{cin}/standing` | **never existed on any branch** | `api.ts:123-131` calls it, `catch {}` → abstention | **live trap, see 2.1.2** |

**Total: the backend serves 10 `/v1/*` routes across two processes, plus 3 HTML routes
on a third.** The frontend's contract names six.

#### 2.1.1 Why it went stale, and the exact date
`src/lib/engine/types.ts:4` pins the contract to backend commit **`f2ebcb3`, dated
2026-09-10**. `/v1/ask` landed 2026-09-18 and `/v1/ask/{documents,document}` on
2026-09-21 (`8caf15a`). The contract has been wrong for nine days and has not moved.

#### 2.1.2 The frontend already knows, in writing, and did not act
`docs/council/FINAL_DECISION_FRONTEND.md` (dated 26-09-2026) records the finding
against itself:

- `:206` — *"8 routes including /v1/ask and /v1/mca-strip … **CONFIRMED** — `api.py`
  docstring lines 8-15 and dispatcher 611-660."*
- `:219` — *"`types.ts` is stale (six routes; '/v1/ask DOES NOT EXIST') … **CONFIRMED**."*
- `:263` — *"Stale site client. `types.ts` and `AGENTS.md` deny that `/v1/ask` exists.
  Add a zod `askSchema` … and `ask()` / `mcaStrip()` in both providers."*

And `docs/FINAL_FRONTEND_DEVELOPMENT_PROMPT.md:417-428` prints the **correct eight-route
list**. So inside one repo, two documents written days apart give two different route
contracts, and the wrong one is the one the code imports.

**Every place the wrong six-route contract survives** (all paths relative to the repo-4
clone; identical in repo 3 except where noted):

| File:line | What it says |
|---|---|
| `AGENTS.md:57-62` | *"exactly SIX routes (verified against `checker/api.py`)"*; *"nor does `/v1/ask` … Do not call it"* |
| `src/lib/engine/types.ts:4-5` | *"Exactly six routes exist"*; *"`/v1/ask` DO NOT EXIST — never add them here"* |
| `src/lib/engine/types.ts:8-13` | `ENGINE_ROUTES` — the six-key record the code compiles against |
| `src/lib/engine/http.ts:88` | *"Wire adapter for the six routes the engine actually serves"* |
| `src/lib/engine/provider.ts:17` | *"one method per route the backend actually serves (six, no more)"* |
| `README.md:55-56` | *"Contract: the backend has exactly SIX routes"* |
| `docs/RAG-INTEGRATION.md:73-82`, `:302`, `:324-326` | six-route list; *"There is NO `/v1/ask`"* |
| `docs/ASTRA_MASTER_PROMPT.md:382`, `:391` | *"These six routes exist"*; *"There is **no `/v1/ask`**"* |
| `docs/specs/backend-architecture-dossier.md:53-73`, `:313-315`, `:454`, `:1180`, `:1257` | *"exactly six, no more [VERIFIED]"*; *"`POST /v1/ask` — DOES NOT EXIST. No F9 answer endpoint. No model is wired."* |
| `docs/specs/codex12-claude13-integration-dossier.md:176`, `:386`, `:532` | *"There is no `/v1/ask` or `/v1/company/{cin}/standing`"* |

**The live trap.** `src/lib/api.ts` (152 lines) is still present and still implements
`standing(cin)` → `GET /v1/company/{cin}/standing` (`:123-131`), a route that has never
existed on any backend branch, wrapped in `catch {}` that converts the inevitable 404
into an *abstention*. `backend-architecture-dossier.md:409` calls this *"the single most
dangerous defect — a wiring error disguised as the product's honesty feature."*
Nothing imports `api.ts` today; it survives as the file a new engineer would reach for
because it looks like the canonical client.

### 2.2 Frontend ↔ frontend — the waitlist

The founder's brief says `AGENTS.md` and the locked rules *"directly contradict each
other"* on `"Join the waitlist"`, and that `/waitlist` 404s. **Verified: the code was
fixed and the documents were not.** As read today in repo 4:

| Claim | Status | Evidence |
|---|---|---|
| `AGENTS.md` still lists `"Join the waitlist"` as a primary CTA | **FALSE now** | `AGENTS.md:36` says *"Primary CTA: **'Request a pilot.'**"* only; `:37` bans the phrase. The two lines agree. |
| The banned phrase survives in shipped copy | **FALSE now** | `grep -rn "Join the waitlist" src/ tests/` returns nothing. |
| `sections.tsx:104` carries the banned CTA | **FALSE now** | `sections.tsx:99` reads `{ label: "Request a pilot", href: "/waitlist?intent=pilot" }`. |
| `/waitlist` 404s | **FALSE now** | `src/app/waitlist/page.tsx` exists and renders. |
| `request-form.tsx` is dead | **FALSE now** | imported at `src/app/waitlist/page.tsx:2`, used at `:45`. |

**So the contradiction has inverted: the docs are now the wrong artefact.** Five
documents still describe a codebase that no longer exists, and a new engineer reading
them would "fix" working code:

| File:line | Stale assertion |
|---|---|
| `docs/specs/2026-09-11-build-execution-plan.md:11` | *"Dead components `sections.tsx` … banned **'Join the waitlist'** (line 104) + 404 `/waitlist` links"* |
| `docs/specs/3300-codebase-dossier.md:75` | *"`POST /api/waitlist` … **no UI calls it** — `request-form.tsx` is dead"* |
| `docs/specs/3300-codebase-dossier.md:77` | *"**There are no other pages.** No `/product`, `/pricing` … `/waitlist`"* — all eleven now exist |
| `docs/specs/3300-codebase-dossier.md:110` | *"`request-form.tsx` — **DEAD**"* |
| `docs/specs/3300-codebase-dossier.md:295` | *"`content/home, product, pricing, faq, about, security, how-it-works, waitlist, shared` — **NO — dead.**"* |
| `docs/specs/codex12-claude13-integration-dossier.md:210` | *"The CTA rule is a **direct reversal** of the :3300 `AGENTS.md`, which still says 'Join the waitlist'"* |
| `docs/specs/codex12-claude13-integration-dossier.md:476`, `:536` | same, twice more |

**What does survive** is the *word*, in names and paths rather than in copy, and this is
a genuine ambiguity worth a decision rather than a grep:
`src/lib/placedon-content/content/shared.ts:13-15` exports `waitlistCta = { label:
"Register interest", href: "/waitlist" }` — a renamed label on a route still called
`/waitlist`; `:130-131` puts both `waitlistCta` and `pilotCta` in the footer;
`src/app/waitlist/page.tsx:28` branches on `intent === "waitlist"`;
`src/app/api/waitlist/route.ts` is the intake endpoint; `README.md:115` and
`AGENTS.md:37` name the phrase only to ban it (correct usage).
`docs/specs/codex12-claude13-integration-dossier.md:83` proposes `/early-access` as the
canonical intake instead, and that was never done.

### 2.3 Frontend ↔ frontend — four unsupported claims, never propagated

Repo 3's branch `fix/site-copy-claims` holds exactly one commit, `b64fdce`
(*"copy: four home-page claims the backend does not support"*, 2026-09-25, 6 insertions
/ 6 deletions in `src/app/page.tsx`). It is **not in repo 4**, which is what the site is
built from. Its corrections are therefore not live.

| # | Repo 4 (live) | Why it is wrong | Fixed on `fix/site-copy-claims`? |
|---|---|---|---|
| C1 | *"Connected to your filings"* | no wired MCA21 read path — `LicensedAggregatorProvider.fetch` raises `NotImplementedError`; no route imports it | yes → `page.tsx:319` |
| C4 | `page.tsx:519` *"**Draft** board resolutions, notices, and Board's-report extracts **inside Word**"* | the add-in's own rule is that it never modifies the document; no Word write call exists; `checker/drafting.py` implements one template (the AGM notice), called only by a slice script | yes |
| C6 | `page.tsx:529` *"**Practice packs** … MCA annual filings (AOC-4, MGT-7, **DIR-3 KYC**) … your registers and **ROC calendar**"* | two filing-timeliness rows exist (s.137, s.92). **No DIR-3 KYC row at all**, no plugin, no pack, no calendar code | yes — the row was removed entirely |
| C8 | `page.tsx:542` *"Connect your registers, MCA21 filings, and minute books to Placedon through the open **Model Context Protocol**"* | an MCP surface exists (13 read-only tools, confirmed: `checker/mcp/tools.py::TOOLS` has 13 entries) but the claim is **backwards** — MCP carries answers *out*, and the surface has no write of any kind | yes → `page.tsx:557` |

#### Claims that were never caught by that audit

| File:line | Claim | Evidence against |
|---|---|---|
| `page.tsx:294` | *"**Write** board resolutions, notices and Board's report sections in Word, with the source attached to each clause"* | **the same unsupported drafting claim as C4, in a second card.** It is present on *both* branches — the fix commit touched `:519` and not this one. The card is marked `status: "Prototype · Microsoft Word"` (`:307`), which softens but does not correct *"Write"*. |
| `page.tsx:534` | *"**Integrate** Placedon into your secretarial or GRC stack **through the API**"* | the API binds to `127.0.0.1` only, has no host option, no auth and no CORS. There is nothing to integrate against. |
| `page.tsx:550` | *"Designed to hold data under India's **DPDP Act, 2023**"* | DPDP was **ruled out on 2026-08-16** — `docs/BUSINESS_PLAN.md:45` (business-plan repo): *"Different buyer (DPO/IT, not CS), corpus cost roughly doubles."* Naming it as a design commitment on the homepage contradicts a recorded scope refusal. |
| `page.tsx:554-560` | six "Evidence & resources" — *"How the record works"*, *"When Placedon abstains"*, *"Source defects, preserved verbatim"*, *"The frozen benchmark"*, *"AGM timing, end to end"*, *"Reading the obligation matrix"* | rendered at `:864` with **no `href` field on any entry**. Six titled resources that lead nowhere. (Each has a real backend document behind it — `SOURCE_DEFECTS.md`, `BENCHMARK_GOVERNANCE.md` — so this is publishable, not fabricated. But today it is decoration.) |
| unfixed and recorded as such in `b64fdce` | the add-in manifest points `SupportUrl` at `placedon.com/support`, **which 404s** | left deliberately: *"inventing a support page here would be a fifth unsupported claim."* Needs a decision, not an edit. |

### 2.4 Business plan ↔ founder's decision — the buyer

`docs/BUSINESS_PLAN.md` (business-plan repo) is explicit and now wrong:

- `:52-54` — *"## 3. The buyer — **Primary: practising Company Secretaries and CAs doing
  ROC/compliance work.**"*
- `:64` — *"**Not the buyer:** large enterprises, listed companies, litigation lawyers,
  tax…"*
- `:49` — *"SEBI / listed company obligations | Buyer is not an SME; market already
  served."*
- `:71`, `:83`, `:88`, `:104`, `:112` — the ten-CS-conversations gate, break-even mix,
  and *"Zero interviews with a practising CS"* all rest on that buyer.

The replacement is `docs/plans/PLAN_20_INHOUSE_CORPORATE.md:1-8` in **this** repo (staged by
another session, 27-09-2026): *"**Supersedes the customer decision in
`docs/BUSINESS_PLAN.md`** … The founder has decided: **in-house legal teams first**,
then law firms, then individual lawyers … Scope also widens: **corporate law**, not the
Companies Act 2013 alone."*

**Every document that asserts the old customer.** All are now wrong on the buyer; most
are otherwise sound and should be corrected rather than deleted.

*Business-plan repo (**PUBLIC** — the highest-priority correction):*
`docs/BUSINESS_PLAN.md:45,49,52-54,64,71,83,88,96,98,104,112`.

*Backend (`placedon-law-backend`), current working tree:*

| File | Note |
|---|---|
| `docs/product/PRODUCT_SCOPE.md` | headed *"locked 20 Aug 2026"* — the lock is now broken |
| `docs/product/PERSONAS.md` | the persona set is CS-first |
| `docs/product/H001_FIND_A_CS.md`, `docs/product/H001_OUTREACH.md` | the whole outreach programme targets one practising CS |
| `docs/evidence/FAILURE_MODES.md` | falsification arguments turn on the CS buyer |
| `docs/reports/STRATEGY_REVIEW_RESPONSE.md` | |
| `docs/market/BLOOMBERG_FOR_INDIA_ANALYSIS.md` | |
| `docs/product/FEATURE_REVIEW_PANEL.md` | |
| `docs/plans/PLAN_08_BOOKMARK_AND_GODSEYE.md`, `docs/plans/PLAN_14_TERMINAL_AND_FEEDS.md` | |
| `docs/reports/LOOP_BOOKMARK_V0.md`, `docs/reports/LOOP_EVENT_LOG.md`, `docs/reports/LOOP_INTELLIGENCE_V0.md` | live loop runbooks |
| `docs/reports/THEMIS_STATUS_AND_NEXT_2026_09_17.md`, `docs/reports/THEMIS_TECHNICAL_REPORT_2026_09_17.md`, `docs/reports/D002_CLOSURE_REPORT_2026_09_17.md`, `docs/reports/EXECUTION_PLAN_2026_09_17.md`, `docs/evidence/PRELABEL_REVIEW_2026-09-23.md` | dated reports — mark superseded, do not rewrite |
| `docs/product/validation_kit.html` | rendered artefact |
| `docs/research/GOLDSET_FIRST_RUN_2026_09_25.md` | |
| `research/INTERVIEW_KIT.md`, `research/TASKS.md` | the interview script is CS-specific |
| `.claude/plans/loop-gateway-2026-09-24.md`, `.claude/plans/loop-next10-2026-09-17.md`, `.claude/plans/loop-twenty-moves-2026-09-26.md`, `.claude/plans/ML_PROGRAM.md` | another session's plans — **KEEP**, mark superseded only |
| `docs/plans/PLAN_00_INDEX.md:—` | *"All four are answerable in ten conversations"* — the ten CS conversations |

*Frontend (repo 4, and identically in repo 3):*

| File:line | Assertion |
|---|---|
| `src/lib/placedon-content/content/home.ts:86` | section heading *"Company Secretaries and Chartered Accountants"* |
| `src/lib/placedon-content/content/home.ts:79` | *"Corporate lawyers and in-house counsel"* — **already right**, and ordered first |
| `src/lib/placedon-content/content/faq.ts:30` | *"intended **first** for advocates, corporate lawyers, in-house counsel, Company Secretaries … including the Practising Company Secretary who carries a book of client companies"* |
| `src/lib/placedon-content/content/waitlist.ts:118-122` | intake options: `in-house-counsel`, `company-secretary`, `Practising Company Secretary (PCS)` — data collection, arguably keep all three |
| `src/app/page.tsx:894` | *"Whether you are an in-house secretary scaling filings or an advisor…"* |
| `docs/ASTRA_MASTER_PROMPT.md:183` | *"Ten practitioners. You shape what gets built."* — the CS research-programme framing |

Note the frontend is **less** wrong than the business plan: it already leads with
in-house counsel. The edit is a reordering and a demotion, not a rewrite.

### 2.5 Backend ↔ backend — the roadmap is on a branch the work is not

This is the largest single source of "what are we building" confusion, and it is fully
provable.

Three documents on the **current branch** cite `PLAN_17`, `PLAN_18` and `PLAN_19` as the
authority for what to build:

- `docs/plans/PLAN_20_INHOUSE_CORPORATE.md:50` — *"PLAN_19 §5.6 already refuses it."*
- `.claude/plans/loop-twenty-moves-2026-09-26.md:3-5` — *"Extends **PLAN_19's G0–G7
  roadmap**; does not replace it."* Also `:25`, `:48` (*"Codes from PLAN_18 §2.4.1"*),
  `:59` (*"PLAN_17 M1.1"*), `:63`, `:67`, `:70`, `:74`, `:95`.
- `.claude/plans/loop-ten-moves-2026-09-24.md:109` — *"PLAN_16-18 merged the same
  morning; PLAN_17 M6…"*

**None of those three documents exists on this branch.** They exist on `origin/main`:

```
docs only on origin/main, missing from HEAD:
  docs/PLAN_16_RESEARCH_PROGRAMME.md
  docs/plans/PLAN_17_BETA_BUILD.md          (added b774756, 2026-09-24)
  docs/plans/PLAN_18_TECHNICAL_DESIGN.md    (added 9d27a16, 2026-09-24)
  docs/plans/plan19/00_INDEX.md  01_GOTHAM_FROM_PUBLIC_SOURCES.md  02_SOURCES_AND_FEASIBILITY.md
  docs/plans/plan19/03_ARCHITECTURE.md  04_MATHS_AND_ALGORITHMS.md  05_ROADMAP.md
  docs/plans/plan19/06_LOOP_PROMPTS.md  07_INVESTOR_BRIEF.md  08_SELF_CRITIQUE.md
  docs/guides/STUDY_GUIDE_THEMIS.md
```

And **`PLAN_16` is a number collision across the two branches** — two different
documents, written a day apart, both numbered 16:

| Branch | File | First line |
|---|---|---|
| `origin/main` | `docs/PLAN_16_RESEARCH_PROGRAMME.md` | *"# PLAN_16 — research programme, architecture, and what we can prove"* (2026-09-24) |
| `HEAD` | `docs/plans/PLAN_16_BACKEND_ARCHITECTURE.md` | *"# PLAN 16 — the backend a user actually meets"* (2026-09-25) |

Worse, `HEAD` carries `docs/plans/plan19/decisions/` — five decision records
(`G0_1_INSTRUMENT_REGISTRY.md`, `M1_ABSTAIN_REASON.md`, `M10_ONTOLOGY.md`,
`M11_OBSERVATION_STORE.md`, `M13_DERIVATION.md`) that annotate a PLAN_19 spec **which is
only on `origin/main`**. `ece562a` is literally titled *"docs: four types PLAN_19's
ontology spec names do not exist"* — a decision about a document not on its own branch.
Note also the mixed numbering inside one directory: `G0_1` is PLAN_19's gate scheme,
`M1`/`M10`/`M11`/`M13` are PLAN_17's milestone scheme.

**A new engineer cloning this branch cannot read the plan the code is being written
against.** Fixing this is a merge decision, not a deletion.

### 2.6 Backend ↔ backend — the two "twenty moves" runbooks

Both exist, both are current, both are being executed:

| File | Opened | Claims |
|---|---|---|
| `.claude/plans/loop-twenty-moves-2026-09-26.md` | 2026-09-26 | *"Extends PLAN_19's G0–G7 roadmap"* |
| `.claude/plans/loop-plan16-twenty-moves-2026-09-26.md` | 2026-09-26 ~04:30 | *"Supersedes `loop-next10-2026-09-17.md`. Source of truth for WHAT: `docs/plans/PLAN_16_BACKEND_ARCHITECTURE.md`"* |

Commit `5f2f9ed` is titled *"docs: rename this loop's runbook out of a collision, and
start the loop"* — one session hit the other's filename and renamed rather than merged.
Both survive with the same date, the same "twenty moves" title, and **different sources
of truth** (PLAN_19 vs PLAN_16_BACKEND_ARCHITECTURE). `loop-plan16-…:85` records the
cause: *"[the] Themis session then wrote its own PLAN_19 G0–G7 runbook over that exact
path in the working tree."*

**No other filename collisions found** in `.claude/plans/` — `git log --all
--diff-filter=A --name-only -- .claude/plans/` lists 29 distinct paths with no repeats.

### 2.7 Backend ↔ backend — the corpus size, stated eight ways

Ground truth measured today:
`ls corpus/companies_act/ | grep -v '^_' | wc -l` → **527**;
`_manifest.json`: `count` = **527**, `section_ids` len = **527**;
`_index.json`: `entries` = **517**;
`ls corpus/companies_act/*.json | wc -l` → **529** (the two `_`-prefixed files are
`.json` too).

| Value | Asserted at | What it actually is |
|---|---|---|
| **529** "sections" | `README.md:60`; `CLAUDE.md:121`; `docs/evidence/FAILURE_MODES.md:47`, `:384`, `:386` | **the bug.** `CLAUDE.md:121` even records its own method — ``ls corpus/companies_act/*.json \| wc -l`` — which counts `_index.json` and `_manifest.json` as sections. `README.md:60` and `CLAUDE.md:121` cite each other as corroboration, so one miscount became two "independent" sources. |
| **527** sections | `docs/architecture/COMPLIANCE_MECHANICS.md:4`; `docs/evidence/CLAIMS_LEDGER.md:7`; `docs/market/COMPETITOR_PATTERN_ANALYSIS.md:71`, `:212`; `docs/plans/PLAN_10_ADOPTION_REVIEW.md:178` | **correct** |
| **526** | `docs/evidence/SOURCE_DEFECTS.md:23` — *"the only record of 526"* | 527 minus s.1, the record under discussion — internally consistent |
| **517** index entries | `CLAUDE.md:134`; `docs/market/COMPETITOR_PATTERN_ANALYSIS.md:71` | correct for `_index.json` |
| **474** mapped | `CLAUDE.md:134` (474/517); `docs/market/COMPETITOR_PATTERN_ANALYSIS.md:71`, `:212`; `.claude/plans/ML_PROGRAM.md:40` (*"~474"*) | 474/517 = 91.7% |
| **464/474 = 97.9%** | `docs/evidence/CLAIMS_LEDGER.md:27`, `:53`; **`CLAUDE.md:112`** | a *different fraction*. `:54` explains the denominator (*"the 43 sections omitted in the source are excluded"*) — but `CLAUDE.md` prints **97.9% at line 112 and 474/517 at line 134**, two mapping rates 22 lines apart in one file, with no note that they measure different things. |
| **464** records | `docs/evidence/SOURCE_DEFECTS.md:57`, `:86`; `CLAUDE.md:130`; `docs/market/ARCHITECTURE_DEEP_DIVE.md:66`; `docs/market/COMPETITOR_PATTERN_ANALYSIS.md:185` | the cross-render comparison set |
| **~470** sections | `docs/policy/NON_GOALS.md:18` | a rounding of nothing measured |
| **529 files / manifest says 527** | `.claude/plans/loop-plan16-twenty-moves-2026-09-26.md:170` — *"529 files on disk and a manifest saying the Act has…"* | **this session found the same discrepancy and treated it as the fetch-loop bug (`:167`), not as a docs miscount.** Both readings are partly right; neither is written down as the resolution. |

**The one-line fix:** the Act holds 527 sections; `corpus/companies_act/` holds 529
files; `_index.json` maps 474 of its 517 entries (91.7%), and 464 of the 474
live sections are cross-validated (97.9%). Four numbers, four meanings, stated once.

### 2.8 Public repo ↔ backend — the deletions were undone in public

`docs/plans/PLAN_00_INDEX.md` (this repo) records a prior consolidation: *"**38 superseded
documents were removed** rather than left to rot: 19 planning and roadmap documents in
`docs/`, and 19 completed loop runbooks in `.claude/plans/` … a repository where five
documents each claim to be the roadmap has no roadmap."*

**All 19 of those deleted `docs/` files are alive in the PUBLIC business-plan repo**, in
its untracked-as-submodule `backend/` copy — checked one by one:

```
backend/docs/{FEATURE_PLAN_INDIA, WORKFLOW_BACKLOG_INDIA, ROADMAP, BUILD_ROADMAP,
BUILD_PLAN_PRODUCT, BUILD_PLAN_2026_08, PLAN_TWO_MONTH, NEXT_PHASE_PLAN,
TECHNICAL_PLAN, TECHNICAL_PLAN_CORPORATE, ARCHITECTURE, AGENT_ARCHITECTURE_PLAN,
ML_PLAN, MODEL_DEVELOPMENT_PLAN, WEEK2_RULE_INGESTION_PLAN, LOOP,
NEXT_MOVE_PLAN_2026_09_04, SONNET_ERA_REVIEW, PLAN_REVIEW_KIMI_2026_08_22}.md
```
— 19 for 19. `backend/.claude/plans/` likewise holds **22** files including the 19
retired loop runbooks. So every roadmap this repo deliberately retired is still
readable, and still says it is the roadmap, in the repo an outsider would find first.

To its credit the public repo **does** warn — `README.md:26`, `CLAUDE.md:23-25`,
`AGENTS.md:23-38`: *"`backend/` is a partial, stale snapshot … Do not edit `backend/`
here."* But **the warning's own numbers are wrong in all three copies**: each says
*"145 files against the real 980."* Measured today: the snapshot has **979** tracked
files (147 `.py`, 141 `.md`); the engine has **1193** tracked files (240 `.py`). The
warning compares a `.py` count to a total-file count, and both figures have drifted.
`AGENTS.md:33` also promises *"19 of the 30 engine self-tests skip in CI"* — the engine
harness now runs **205** suites.

`AGENTS.md:20` names a `landing-page/` directory; it exists. No contradiction there.

### 2.9 Backend ↔ backend — smaller contradictions worth one line each

| Contradiction | Evidence |
|---|---|
| `CLAUDE.md:142-152` states `.nic.in` works and serves real PDFs (measured 26-09-2026), and in the same paragraph that *"`checker/provenance.py` still excludes `.nic.in` 'on purpose: it is dead', so the permitted-host list refuses a host that works."* | A known live defect, documented and unfixed. Code and doc disagree and the doc says so. |
| `docs/plans/PLAN_00_INDEX.md:5` — *"**Seven documents**, each one scoped…"* | There are now **19** `docs/PLAN_*.md` files on this branch (00–16, 20, plus a duplicate 13) and four more on `origin/main`. The index is three weeks stale and is the first file a new engineer opens. |
| `docs/plans/PLAN_13_ASSISTANT_UX.md` and `docs/PLAN_13_ASSISTANT_UX_PLAN.md` | Two files, same plan number, near-identical titles (*"the Ask section: design spec"* vs *"the Ask section (grounded assistant): research, design, pr…"*). |
| `CLAUDE.md:115` — *"It said 'all 8 suites' until 2026-09-25; the harness runs **195** today"* | Measured today: **205**. Correct in spirit (the point of the line is that counts go in `HARNESS_RESULT`, not prose) and wrong in fact, which proves its own argument. |
| `docs/evidence/CLAIMS_LEDGER.md:53` — *"8 suites green"* | 205 suites. Stale by the same drift `CLAUDE.md:115` warns about. |
| `docs/evidence/FAILURE_MODES.md:44`, `:357`, `:879` — the release gate scores 67 rows against a manifest of 69 | Recorded as failure mode **F3, *"present now"***. Still open. `THEMIS_TECHNICAL_REPORT_2026_09_17.md:616` repeats it, and `:705` records that *"`CLAUDE.md`'s repository-map table states 527 sections for the same directory | SOURCED (disagrees with #3)"* — a session already logged the corpus-count disagreement as a sourced conflict and nobody resolved it. |

---

## 3. Proposed deletions

**Nothing in this section has been deleted.** Default is ASK. Per the brief, everything
under `corpus/`, `.git/`, and another session's plan files is **KEEP** unless proved
otherwise.

### 3.1 Recommend DELETE

| Path | Evidence it is dead | Risk if deleted | Rec |
|---|---|---|---|
| `scripts/build_register.py` (230 ln) | Builds the **PoSH** District-Officer notified-date register. PoSH was retired (`docs/product/RETIRED_POSH.md`, closed `R-010`). Not in `scripts/run_tests.sh`; no `--test`; **only referrer is `scripts/draft_letters.py`**, itself dead. Docstring: *"Every guide to PoSH compliance in India…"* | None to the corporate product. Loses a worked example of the register pattern that `Placedon-law-business-plan/CLAUDE.md:59` cites as the model for an `sdf_register`. Git keeps it. | **DELETE** |
| `scripts/draft_letters.py` (173 ln) | *"Render the 31 District Officer letters"* — PoSH. Not in gate, no `--test`; **only referrer is `scripts/send_letters.py`**, dead. | None. | **DELETE** |
| `scripts/send_letters.py` (161 ln) | Sends the PoSH letters via Gmail OAuth. Not in gate, no `--test`, **zero code referrers**. Also the only file in the repo wanting a Google OAuth client. | None. Removes an outbound-email path from a repo that has no other one. | **DELETE** |
| `scripts/ingest_district_officers.py` (163 ln) | Ingests the SHe-Box District Officer directory for *"s.21/22"* of the **PoSH** Act. Not in gate, no `--test`, **zero code referrers**. | None. | **DELETE** |
| `scripts/build_research_register.py` (194 ln) | *"Turn the collected practitioner comments into a structured … evidence base … one author wrote 62% of them."* Tier-E anecdote from the HR/CS research era. Not in gate, no `--test`, **zero referrers of any kind**. | None. The finding it produced (`research/comment_analysis.md`) stays. | **DELETE** |
| `src/lib/api.ts` (152 ln, frontend repos 3 **and** 4) | Implements the obsolete three-route contract including `standing()` → `/v1/company/{cin}/standing`, a route that has **never existed on any backend branch**, with `catch {}` converting the 404 into an abstention. **Zero importers** (`grep -rn 'lib/api"' src/ tests/` → nothing). Already condemned at `backend-architecture-dossier.md:409` as *"the single most dangerous defect"* and at `codex12-…:386`, `:532`. | None — nothing imports it. **Leaving it is the risk:** it is the file a new engineer would wire up, and it fails silently as honesty. | **DELETE** (frontend, not this repo) |

### 3.2 Recommend ASK

| Path | Evidence | Risk if deleted | Rec |
|---|---|---|---|
| `scripts/preflight.py` (76 ln) | **Zero code referrers and zero doc referrers**, not in gate, no `--test` — yet it references `ingest_companies_act.py`, `parse_board_rules.py`, `slice_s96.py`. Docstring: *"Check whether this checkout can actually run … Without this, a fresh clone's first command is a FileNotFoundError."* | **High if it is meant to be the onboarding step.** A fresh-clone guard with no caller is either an unfinished feature or a genuine dead file — and given `corpus/` is deliberately not in version control, the need is real. | **ASK** — decide whether to wire it into `setup.sh` instead of deleting |
| `scripts/render_review_html.py` (409 ln), `scripts/render_review_table.py` (59 ln) | Zero code referrers, not in gate, no `--test`. But their outputs are committed: `docs/evidence/fixture_review.html`, `docs/evidence/FIXTURE_REVIEW.md`, `docs/review_pack.html`. Generated *"from `checker.review_table` so it cannot drift."* | Losing the generators while keeping the generated files makes those pages unreproducible. | **ASK** |
| `scripts/verify_against_pdf.py` (106 ln), `scripts/verify_reconstruction.py` (150 ln), `scripts/cross_validate_corpus.py` (176 ln) | None in the gate; none has `--test`. `verify_reconstruction.py`'s docstring opens *"**RETRACTED CLAIM, recorded so it is not repeated**"*. | **Do not delete.** These are the only **non-circular** verification against an independent rendering — `CLAUDE.md:129-133` rests `PASS_WITH_DEFECTS` on them, and `verify_reconstruction.py` is a retraction record. | **ASK** — likely KEEP + add to gate |
| `scripts/index_codebase.py` (168 ln), `scripts/search_memory.py` (158 ln) | Zero code referrers, not in gate, no `--test`. An agent meta-RAG index over the repo. `search_memory.py` cites `RESEARCH_LOG.md` and `DECISIONS.md` — **neither file exists in this repo**. | Low. Built for a retired agent workflow and pointing at absent files. | **ASK** |
| `scripts/scan_testdocs.py` (71 ln) | Zero code referrers, not in gate, no `--test`. But: *"This is the check that matters. Every other test for `defects.py` was written by the same author as the regexes, which is circular."* | **High.** The only non-circular test of the SS defect scanner. | **ASK** — add `--test` and gate it, don't delete |
| `scripts/seed_admission.py` (130 ln) | Zero code referrers, not in gate, no `--test`. Written 2026-09-25 — **two days old.** Seeds admission records / review queue from SD-002 findings. | Likely in-flight work by another session. | **ASK** |
| `scripts/build_section_index.py` (224 ln) | Not in gate, no `--test`. *"Nothing downstream works without this"* — builds the number→id map. Referred to by `verify_against_pdf.py`. | **Critical.** Rebuilds `_index.json`. Deleting it makes the 517-entry index unreproducible. | **ASK** — almost certainly KEEP + gate |
| `scripts/check_deps.py` (45 ln) | Not in gate, no `--test`; referrers are `setup.sh` and `.claude/scripts/setup.sh`. | Load-bearing for setup. | **KEEP** (listed for completeness) |
| `eval/realrun/documents.py` (299 ln), `eval/realrun/local_model.py` (128 ln) | Neither in gate nor has `--test`, though sibling `eval/realrun/run.py --test` and `azure_model.py` are gated. Adversarial documents + a deliberately weak local model. | Medium — they are the fixtures the gated `run.py` exercises. | **ASK** |
| `backend/services/llm.py` (248 ln) | *"The only file that talks to Anthropic. Every paid call goes through here."* Referrers: `checker/anthropic_model.py`, `checker/mcp/server.py`. Not in gate, no `--test`. | **Do not delete** — it is the single paid-call chokepoint. | **KEEP** |
| `addin/serve.py` (107 ln) | Only referrer is `scripts/themis_mcp.py`. Not in gate, no `--test`. Dev-only HTTPS proxy for the Word task pane. | Low, but the add-in is `page.tsx:307`'s *"Prototype · Microsoft Word"* claim. | **ASK** |
| `.claude/worktrees/{sweep-a, store-c, redteam-d, agent-a208…, agent-a9b5…, agent-ab24…}` | Six live `git worktree` entries, **three of them `locked`**, inside the repo. They are why any recursive grep returns sevenfold duplicates. | **Deleting a locked worktree destroys another session's uncommitted work.** | **ASK the founder, never delete unprompted.** Safe interim: add `.claude/worktrees/` to grep/ripgrep ignore config |
| `__pycache__/`, `applicability.cpython-312.pyc`, `.DS_Store` (10 KB at repo root, 6 KB in `PlacedOn/`) | Build/OS artefacts. `.gitignore` is 3.6 KB — check whether these are tracked before touching. | None. | **ASK** (mechanical; verify `git ls-files` first) |

### 3.3 Recommend KEEP — and here is the proof, because each looks deletable

| Path | Why it looks dead | Why it must stay |
|---|---|---|
| `checker/code_transition.py` | `CLAUDE.md:43-44`: *"kept as machinery only. It serves no obligation, **is wired to nothing**, and every verdict it returns is `INSTRUMENT_NOT_HELD`."* Its only code referrer is `scripts/run_tests.sh`. | **Two explicit keep decisions.** `docs/plans/PLAN_10_ADOPTION_REVIEW.md:221`: *"**Keep `code_transition.py`.** It is machinery, it is correct, and it is the bridge if…"*; `:151` records 20 green checks. It is also load-bearing for two assertions in `eval/temporal/harness.py:84-86` and is cited at `eval/temporal/scorecard.md:67`, `:107`. **A purge that trusts "wired to nothing" deletes this. Don't.** | 
| 19 further `checker/*.py` whose only code referrer is the gate — `ablation`, `attribution`, `backtest`, `benchmark_versions`, `buyer_sim`, `chunk_fusion`, `lawyer_summary`, `licence`, `objection_sim`, `paraphrase_negatives`, `pit_bench`, `promotion_preview`, `reranker`, `resubmission`, `revocation`, `s96_slice`, `timeline`, `feeds/ibbi`, + `eval/prelabel/run_prelabel`, `eval/temporal/harness` | No importer. Nothing calls them in a request path. | Every one carries a **green self-test inside the 205-suite gate**. In this repo a self-test is the unit of evidence, not decoration — `PLAN_00_INDEX.md` defines **BUILT** as *"In the repo, covered by a self-test in `scripts/run_tests.sh`."* Deleting them lowers the gate. Each needs an individual decision about whether the capability is still wanted; none is a mechanical delete. |
| `corpus/**` (all of it) | Large; `companies_act/` is not in version control by design. | Per the brief, and because `README.md:39` / `preflight.py` record that a public repo of bare Act text would breach Copyright Act 1957 s.52(1)(q)(ii). **KEEP, and do not commit it either.** |
| `.claude/plans/*` (all 10) | Several are superseded. | Another session's plan files. `PLAN_00_INDEX.md` already names *"the measured results under `.claude/plans/`"* as deliberately kept. Mark superseded (§4); delete nothing. |
| `docs/product/RETIRED_POSH.md`, `docs/evidence/RETRACTIONS.md`, `docs/evidence/SOURCE_DEFECTS.md`, `docs/evidence/CLAIMS_LEDGER.md`, `docs/{SOURCE,SOURCE_PROVENANCE,ACQUISITION,METRIC}_POLICY.md`, `docs/evidence/TEMPORAL_PROOF.md`, `docs/evidence/CORROBORATION.md`, `docs/policy/BENCHMARK_GOVERNANCE.md`, `docs/reports/SESSION_BUILD_LOG_2026_09.md`, `docs/product/H001_OUTREACH.md` | Describe retired products and invalidated claims. | `PLAN_00_INDEX.md` already ruled: *"**Deliberately kept**, because they are evidence or policy rather than plans … `RETIRED_POSH` (a decision record — **deleting those is how a team re-litigates settled questions**)."* That ruling stands. |
| `docs/plans/PLAN_17_BETA_BUILD.md`, `docs/plans/PLAN_18_TECHNICAL_DESIGN.md`, `docs/PLAN_16_RESEARCH_PROGRAMME.md`, `docs/plans/plan19/0*.md`, `docs/guides/STUDY_GUIDE_THEMIS.md` | Absent from this branch; easy to conclude they were retired. | They are on `origin/main` and are **cited as the authority by three live documents on this branch** (§2.5). They need **merging in**, not deleting. |

### 3.4 Not mine to touch

`Placedon-law-business-plan/backend/**` (979 tracked files) is the single largest block
of resurrected, contradictory material found (§2.8). It is in a **PUBLIC, read-only**
repo under a standing instruction. **I propose nothing there beyond a recommendation
for the founder:** replace the 979-file snapshot with a git submodule or a README
pointer, since the repo's own three warnings already say it should not be edited and
their file counts have drifted 7×. That is a decision, not an audit finding.

---

## 4. Proposed doc consolidation

Inventory: **78** `docs/*.md` at top level, **108** `.md` under `docs/` in total (plus
`docs/research/` ×19, `docs/research/ux/`, `docs/plans/plan19/decisions/` ×5), **10**
`.claude/plans/*.md`. Plus 13 in the frontend's `docs/` and 4 in `docs/specs/`.

`docs/plans/PLAN_00_INDEX.md` already set the right precedent and the right rule — *"a
repository where five documents each claim to be the roadmap has no roadmap"* — and
recorded a superseded-to table. **Reuse that mechanism; do not invent another.**

### 4.1 Merge

| Merge | Into | Why |
|---|---|---|
| `docs/plans/PLAN_13_ASSISTANT_UX.md` + `docs/PLAN_13_ASSISTANT_UX_PLAN.md` | one `PLAN_13_ASSISTANT_UX.md` | Same plan number, near-identical titles. One is the design spec, the other the research+design+prompt. Nothing should hold plan number 13 twice. |
| `docs/plans/PLAN_14_TERMINAL_AND_FEEDS.md` + `docs/plans/PLAN_15_TERMINAL_BUILD.md` | `PLAN_14_TERMINAL.md`, with 15 as its build section | The Terminal is analysed in one and built in the other; a reader cannot tell which decides. |
| `docs/market/SPELLBOOK.md` + `docs/market/SPELLBOOK_INFERRED_ARCHITECTURE.md` | `docs/market/SPELLBOOK.md` | Same competitor, one file inferring the architecture of the other's business model. |
| `docs/evidence/ABLATION_CORRECTED.md` | `docs/plans/PLAN_06_EVALUATION.md` | Its title presupposes an `ABLATION.md` that no longer exists, so it reads as a correction to nothing. |
| `docs/market/ARCHITECTURE_DEEP_DIVE.md` + `docs/market/LEGAL_AI_ARCHITECTURE_ANALYSIS.md` | `docs/market/COMPETITOR_PATTERN_ANALYSIS.md` | Both are competitor-architecture analyses shelved beside our own architecture plans, where they read as our design. |
| **The corpus-count sentence** — `README.md:60`, `CLAUDE.md:112`, `CLAUDE.md:121`, `CLAUDE.md:134`, `docs/policy/NON_GOALS.md:18`, `docs/evidence/FAILURE_MODES.md:384`, `docs/evidence/CLAIMS_LEDGER.md:27` | one authoritative paragraph, quoted by reference everywhere else | §2.7. Seven files, eight figures, two of them citing each other. |
| The frontend's `docs/RAG-INTEGRATION.md` + `docs/ASTRA_MASTER_PROMPT.md` + `docs/specs/backend-architecture-dossier.md` route sections | `docs/FINAL_FRONTEND_DEVELOPMENT_PROMPT.md:417-428`, which is **already correct** | §2.1. Four documents, two contracts. The eight-route list wins; the others should cite it rather than restate it. |

### 4.2 Mark superseded — keep the file, add a header

A superseded plan is history. Add one line at the top (`> **SUPERSEDED** <date> by
<file>. Kept as history.`) and leave the body untouched.

| File | Superseded by |
|---|---|
| `docs/BUSINESS_PLAN.md` §3 "The buyer" (**public repo**) | `docs/plans/PLAN_20_INHOUSE_CORPORATE.md` — **highest priority: it is public and it is wrong about who the customer is** |
| `docs/product/PRODUCT_SCOPE.md` (*"locked 20 Aug 2026"*) | PLAN_20 — the lock is broken; say so rather than deleting the lock |
| `docs/product/PERSONAS.md`, `docs/product/H001_FIND_A_CS.md`, `docs/product/H001_OUTREACH.md` | PLAN_20's buyer. Keep: `H001_OUTREACH` is already on the deliberately-kept list |
| `docs/reports/THEMIS_STATUS_AND_NEXT_2026_09_17.md`, `docs/reports/THEMIS_TECHNICAL_REPORT_2026_09_17.md`, `docs/reports/D002_CLOSURE_REPORT_2026_09_17.md`, `docs/reports/EXECUTION_PLAN_2026_09_17.md`, `docs/reports/NEXT10_REPORT_2026_09_17.md`, `docs/reports/LOOP_THEMIS_20_MOVES_2026_09_17.md`, `docs/reports/LOOP_THEMIS_20_MOVES_REPORT.md` | Seven documents dated 2026-09-17. They are dated reports; **date-stamped reports do not need superseding, they need a manifest** listing what each measured |
| `docs/reports/OVERNIGHT_REPORT_2026_09_14.md`, `docs/reports/ASSISTANT_UX_REPORT_2026_09_15.md`, `docs/evidence/PRELABEL_REVIEW_2026-09-23.md`, `docs/reports/THEMIS_V0_PLAN_ASSESSMENT_2026_09_23.md`, `docs/reports/BATCH1_FINAL.md` | same — dated evidence, keep as-is under a manifest |
| `.claude/plans/loop-next10-2026-09-17.md` (109 KB) | explicitly superseded by `loop-plan16-twenty-moves-2026-09-26.md:3`. Header only; another session's file |
| `.claude/plans/{loop-overnight-2026-09-14, loop-assistant-ux-2026-09-15, loop-ten-moves-2026-09-24, loop-gateway-2026-09-24}.md` | completed loops. Header only |
| The frontend's `docs/specs/3300-codebase-dossier.md`, `docs/specs/2026-09-11-build-execution-plan.md`, `docs/specs/codex12-claude13-integration-dossier.md`, `docs/specs/visual-audit-3300.md` | §2.2 — these describe a frontend that no longer exists. **Mark superseded, do not delete:** they are the record of why the fixes were made |

### 4.3 Fix rather than merge or retire

| Action | Where |
|---|---|
| **Rewrite `docs/plans/PLAN_00_INDEX.md`.** It says *"Seven documents"*; there are 19 `PLAN_*` on this branch and 4 more on `main`. It is the first file a new engineer opens and it is the most wrong. | `PLAN_00_INDEX.md:5` |
| **Merge `origin/main` into the working branch, or cherry-pick `PLAN_16_RESEARCH_PROGRAMME`, `PLAN_17`, `PLAN_18`, `docs/plans/plan19/0*.md`, `STUDY_GUIDE_THEMIS`.** Until then the branch cannot show a reader the plan it is executing. | §2.5 |
| **Resolve the `PLAN_16` collision.** Two documents, both numbered 16, on two branches. Renumber one (e.g. `PLAN_21_BACKEND_ARCHITECTURE`) as part of the merge. | §2.5 |
| **Reconcile the two `twenty-moves` runbooks** — or write one line in each naming the other and which owns which moves. | §2.6 |
| **Apply `FINAL_DECISION_FRONTEND.md:263`'s own prescription:** add `askSchema` + `ask()`/`mcaStrip()` to both providers, update `types.ts`/`AGENTS.md`/`README.md` to eight routes, extend `tests/contracts.mjs`. The fix is already written down; only the doing is missing. | §2.1.2 |
| **Merge `fix/site-copy-claims` (`b64fdce`) into repo 4**, then fix the fourth drafting claim at `page.tsx:294`, the API-integration claim at `:534`, the DPDP claim at `:550`, and either link or cut the six resources at `:554-560`. | §2.3 |
| **Correct the snapshot warning's numbers** in the public repo's `README.md:26`, `CLAUDE.md:23`, `AGENTS.md:28`: 979 files (147 `.py`) against 1193 (240 `.py`), and 205 harness suites — not *"145 against 980"* and *"30 self-tests"*. | §2.8 |

---

## 5. What I could not check, and why

| Not checked | Why |
|---|---|
| **Whether `placedon.com` actually serves mock data.** | I established that `.env.example:27` leaves `PLACEDON_API_ORIGIN` blank and that `getEngine()` falls back to `MockEngineProvider`. I did **not** read Vercel's production environment — that needs a deploy-scoped credential, and the standing instruction forbids touching the frontend deployment. **If a real origin is set in Vercel it must be a public URL, which the loopback-only backend cannot be** — so the conclusion holds either way, but the env var itself is unread. |
| **Whether repo 4 (`probonhs`) is the repo Vercel builds.** | Repo 3's `origin` is `placedon007-prog/placedon-claude-legal-3300`; repo 4 is `probonhs/Main-product-frontend-`. Both are plausible build sources and I could not query Vercel's project→repo binding read-only. I have shown repo 4 is 17 commits ahead; which one *deploys* is unverified. Everything in §2.3 is stated as "live in repo 4", not "live on placedon.com". |
| **The three `locked` git worktrees' contents.** | `agent-a208…`, `agent-a9b5…` are locked and `redteam-d`/`store-c`/`sweep-a` are active. Reading them is safe but they are another session's working state; I counted them as duplication sources and read nothing from them. All greps in this report exclude `.claude/worktrees/`. |
| **`../intel-worktree`** (branch `loop/intelligence-v0` @ `856c2be`). | Outside the four repos in scope. Noted because it is a seventh full copy of the engine sitting in `~/PlacedOn/`. |
| **Whether `docs/plans/plan19/0*.md` on `origin/main` actually contains the §5.6, G0–G7, and "03 §2/§4" sections cited on this branch.** | I confirmed the nine files exist on `origin/main`. I did not read them, because the finding (*"the branch cites documents it does not have"*) is established by absence and reading them would not change the fix, which is a merge. |
| **Whether the 20 commits this branch is behind `origin/main` conflict.** | Determining that requires a merge or a `git merge-tree`, and another session is committing continuously. Out of scope for a read-only audit. |
| **The dangling `PLAN_17`/`PLAN_18` deletion point.** | Both commits (`b774756`, `9d27a16`) are reachable from `origin/main`, so nothing is lost. I did not trace *how* they left this branch — it is a branch-divergence artefact, not a deletion. |
| **The 43 "omitted" sections and the 517-vs-527 gap.** | `CLAUDE.md:134-138` explains them as legislature-omitted provisions (s.11; ss.253-269) resolving to `None` by design. I took that at its word rather than re-verifying against India Code — `scripts/verify_section_index.py` needs the network and returned `NOT_FOUND` for all 12 MVP sections when I ran it, which is a live-source result I am not equipped to interpret and did not treat as evidence either way. |
| **Frontend build, lint, and the two test suites** (`tests/browser.mjs`, `tests/contracts.mjs`). | Running them means `npm install` in a read-only repo and, for `browser.mjs`, a Playwright browser. Not attempted. Every frontend finding here is from source, not execution. |
| **Whether `docs/evidence/fixture_review.html` / `review_pack.html` still match `checker/review_table`.** | Would require running the two ungated renderers, which write files. Not attempted; that is why §3.2 rates them ASK. |

---

*Read-only on repos 2, 3 and 4. In this repo, `docs/reports/REPO_AUDIT_2026_09_27.md` is the only
file written. Nothing was deleted, committed or pushed. The mirror clone lives at
`/tmp/audit_2026_09_27/mirror` and can be discarded.*
