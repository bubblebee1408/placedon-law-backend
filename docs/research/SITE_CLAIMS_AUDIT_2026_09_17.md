# Site claims audit — placedon.com vs the backend (SITE-2)

Status: COMPLETE, revised after verifier round 1 (see *Revision log*). Read-only research job
SITE-2, 2026-09-17. No file was edited except this one.
Author: the SITE-2 implementer agent. Everything below is that agent's own evidence. No human has
checked it.

**How to read the negatives.** Where this document says something was "not found", that is
the result of a named search (S1–S16, listed under *Sources checked*) over **this backend
repository at `b37462e`**. It does not mean the thing exists nowhere.

## Question
1. Which capability claims on the live site https://www.placedon.com (source repo
   `placedon-claude-legal-3300`) does the backend (`placedon-law-backend`) implement?
2. Does the FAQ line "securities regulation … not covered" agree with `checker/scope.py`?
3. Is the live site behind the frontend repo's `main`? If so, which commit does it most likely serve?

Inputs: `docs/research/ux/FRONTEND_ALIGNMENT_2026_09_17.md` §E (E6, E7, E9, E12) and
`research/TASKS.md` row A-007.

## Sources checked
- **Live site**, fetched 2026-09-17 05:37 UTC with `curl -sL` (13 URLs; the raw HTML is in
  `/tmp/site2/` and is not committed). Pages: `/`, `/faq`, `/product`, `/how-it-works`,
  `/security`, `/pricing`, `/about`, `/product/compliance-pack`, `/product/document-check`,
  `/product/events`, `/product/instruments`, `/waitlist`, `/support`. The first twelve returned
  HTTP 200. `/support` returned 404. The home page's 13 static JS/CSS assets were also
  downloaded so their strings could be searched.
  - Home headers: `server: Vercel`, `x-vercel-cache: HIT`, `x-nextjs-prerender: 1`,
    `age: 308086`, `date: Thu, 17 Sep 2026 05:37:04 GMT`.
  - All 12 HTML pages that returned 200 reference the same Vercel deployment id,
    `dpl=dpl_3wuFWKjs7LG3632rQFYRct687JVf` (in `/_next/image` URLs).
- **Frontend repo**: a read-only clone at
  `/Users/nishantsingh/.claude/jobs/c886fa96/tmp/repos/placedon-claude-legal-3300`. `git fetch
  origin` on 2026-09-17 brought no new commits, so `origin/main` = `main` = `939f40f`
  (2026-09-15 13:34 +0530). Only `log`, `show`, `diff --stat` and `ls-tree` were used.
  **Citation form:** `page.tsx L319 / H319` means `src/app/page.tsx` line 319 at `2c2cdb3`
  (**L**, the inferred live commit) and line 319 at `939f40f` (**H**, HEAD). Where a line exists
  or reads the same at only one of them, only that one is given.
- **Backend**: `~/PlacedOn/placedon-law-backend` at **`b37462e`** (2026-09-17 10:16 +0530), read
  only; its paths are cited without a prefix. During the fix round HEAD moved to `dc2c399`
  (P-1). Of the files cited here, only `checker/prescribed_thresholds.py` changed between
  `b37462e` and `dc2c399` (`git diff --stat`). Every backend line number below is at `b37462e`.
- **Searches** (`git grep` at `b37462e` unless marked otherwise). Hits are given in full.
  - **S1**, MCA21 adapter use: `mca_aggregator|corporate_data` in `*.py *.js *.html *.sh`,
    excluding the two modules themselves. Hits: `api.py:438` (docstring) and
    `scripts/run_tests.sh:76-77`.
  - **S2**, SS scanner use: `from checker\.ss|checker\.ss\.` in `*.py`, outside `checker/ss/`.
    Hit: `scripts/scan_testdocs.py:22`.
  - **S3**, `minute` (case-insensitive) in `checker/api.py`, `scripts/serve_api.py`,
    `scripts/serve_matrix.py` and `addin/`: no hits.
  - **S4**, template references: `board_report\.html|ic_order\.html|posh_policy\.html|templates/`
    in `*.py *.js *.html *.sh *.json`: no hits. An unrestricted run also hits only
    `.claude/memory/MASTER_SPEC.md`, `.gitignore` and the FRONTEND_ALIGNMENT report.
  - **S5**, drafting use: `draft_agm_notice|from checker\.drafting|checker import drafting` in
    `*.py *.js`, outside `checker/drafting.py`. Hits: `scripts/slice_s96.py:28, 48`.
  - **S6**, other drafting functions: `draft_.*resolution|resolution_template|def draft_` in
    `*.py`. Hit: `checker/drafting.py:80` (`draft_agm_notice`).
  - **S7**, Word write APIs in `addin/taskpane.js`:
    `insert[A-Z]…|\.delete\(|\.clear\(|\.set\(|font\.|\.style|getOoxml|search\(`. Hits:
    comment lines `:6-7` only.
  - **S8**, `plugin|practice[ _-]?pack|roc[ _-]?calendar` (case-insensitive) in
    `*.py *.js *.html *.json *.xml`, excluding `corpus/`: no hits.
  - **S9**, MCP: a tracked-filename search for `mcp` (no hits), plus
    `(^|[^a-z])mcp([^a-z]|$)|model context protocol|modelcontextprotocol|fastmcp`
    (case-insensitive) in `*.py *.js *.json *.toml *.txt *.sh *.html *.cfg *.yml *.yaml`: no hits.
    A working-tree `grep -r` excluding `.git`, `.env*` and `__pycache__` hits only
    `docs/TOOLING.md` (MCP servers for developer tooling), the loop runbook and
    `research/TASKS.md`.
  - **S10**, deploy config in the tracked tree: `vercel.json|Dockerfile|Procfile|render.yaml|
    fly.toml|app.yaml|serverless|netlify.toml|azure-pipelines|.github/workflows`: no hits.
  - **S11**, `NOT_FULLY_VERIFIED` across all files: one hit, `CLAUDE.md:131`.
  - **S12**, schedulers and push delivery: `import sched|crontab|apscheduler|celery|def notify|
    send_alert|webhook` in `*.py`: no hits. An earlier, broader working-tree search for
    `sched|cron|notify|alert|webhook|rss` in `checker/*.py scripts/*.py` hit only comments, a
    retry-policy note, the `currency.py:226` "alert list" function and the SEBI feed URLs in
    `scope.py`.
  - **S13**, durable writes in the API path: `open\(|write_text|write_bytes|\.write\(|sqlite|
    logging\.FileHandler` in `checker/api.py`, `scripts/serve_api.py` and `addin/serve.py`.
    Hits: HTTP response writes, stderr request logs, `urlopen` in self-tests, and
    `api.py:851` (`open(__file__)` in a test).
  - **S14**, model imports: none of the module names `anthropic_model`, `gemini_model`,
    `ollama_runner`, `azure_model`, `services.llm` or `model_adapter` appears as an import in
    `checker/api.py`, `checker/matrix_view.py`, `checker/diligence_pack.py` or
    `checker/obligations.py`. The three servers `scripts/serve_api.py`, `addin/serve.py` and
    `scripts/serve_matrix.py` have no import line mentioning model, llm, anthropic, gemini,
    ollama, azure or services. Direct imports only: transitive imports through other checker
    modules were not traced.
  - **S15**, email: `(from|import) email([. ]|$)`, plus
    `imaplib|smtplib|poplib|gmail|googleapiclient|outlook|exchangelib|graph\.microsoft|sendgrid|
    mailgun|Office\.context\.mailbox` (case-insensitive) in `*.py *.js *.html *.xml *.json`,
    excluding `corpus/`. Hits:
    - `scripts/draft_letters.py:39` (`from email.message import EmailMessage`), plus its
      sender-address constant `:87` and comments `:120-121`;
    - `scripts/send_letters.py:52-53` (`from email import policy`, `BytesParser`), its Gmail API
      client (`:59-62, :70, :89`) and docstring lines;
    - `checker/robots.py:35` and `scripts/ingest_district_officers.py:47`, a contact address in a
      User-Agent string.

    There are no hits in `checker/api.py`, `addin/` or the server scripts.
  - **S16**, secretarial software and GRC: `complyrelax|secretarial software|(^|[^a-z])grc([^a-z]|$)|webhook`
    (case-insensitive) in `*.py *.js *.html`, excluding `corpus/`. Hit: `checker/ss/defects.py:231`
    (a docstring).
  - Also searched: board's report / s.134 / Board Report (`board.?s.?report|s\.134|S134`,
    and separately `board ?report|T2\.1|board_report`) in `checker/`, `scripts/`, `addin/` and
    `web/`. Hits: `checker/corroborate.py:346` (a normaliser test),
    `checker/cross_section_eval.py:48` (a retrieval eval case), `checker/ss/RULES.md:53`
    (rule T2.1, documented), `checker/templates/board_report.html:74` and
    `scripts/search_memory.py:104`.
- Files read at `b37462e`: `checker/api.py`, `checker/matrix_view.py` (header and routes),
  `scripts/serve_api.py`, `scripts/serve_matrix.py`, `checker/scope.py`,
  `checker/obligations.py`, `checker/diligence_pack.py`, `checker/drafting.py`,
  `checker/templates/board_report.html`, `checker/corporate_data.py`,
  `checker/mca_aggregator.py`, `checker/mca_snapshot.py`, `checker/mca_strip.py`,
  `checker/session.py`, `checker/event_log.py`, `checker/release_record.py`,
  `checker/prescribed_thresholds.py` (only the 880(E) lines), the headers of
  `checker/anthropic_model.py`, `checker/gemini_model.py`, `checker/ollama_runner.py`,
  `eval/realrun/azure_model.py` and `backend/services/llm.py`, the `addin/` files other than its
  certificate, `web/assistant/README.md`, `scripts/draft_letters.py`, `scripts/send_letters.py`
  (docstring and imports only; the credentials path it names was not opened) and
  `requirements*.txt`.
- No `.env*` or credential file was opened, and no secret was printed.
- **Not used:** the Vercel dashboard/API. It could map the deployment id to a commit, but it is
  not one of the sources this job was given.

## Evidence found

### 1. Capability claims
All quotes are the **live** wording unless marked. "…" marks a cut.

| # | Claim (site) | Site evidence | Backend evidence (`b37462e`) | Verdict |
|---|---|---|---|---|
| C1 | **MCA21 / registers / minutes connection.** Card "Connected to your filings": "Placedon is built to read from MCA21 filings, board minutes, and your statutory registers — no re-keying, no copy-paste, no re-explaining the company each time you open a question." The demo tabs' "Connectors" lists name, across the five tabs: MCA21 Portal, Board minutes, Secretarial software, Financials, Registers. | Live `/`. `page.tsx L318-319 / H318-319` (the body was reworded in `3d0f855`; the claim is unchanged). Connectors: `L398, 427, 462, 492, 521 / H398, 427, 462, 492, 522`. The demo is labelled "Illustrative example — sample data shown to demonstrate the format…" (`L719`). | **No wired MCA21 read path was found.** `LicensedAggregatorProvider.fetch` has one statement, `raise NotImplementedError(...)` ("…requires a contracted, MCA-sanctioned aggregator… Do not scrape MCA21…", `checker/corporate_data.py:90-95`). The concrete adapter raises `NotConfigured` unless `MCA_AGG_BASE_URL` and `MCA_AGG_API_KEY` are set (`checker/mca_aggregator.py:69-75, 138-141`). S1: neither module is imported by `api.py` or by any server script. `POST /v1/mca-strip` works on registers the caller supplies ("…there is no contracted aggregator -- `corporate_data` still refuses…", `api.py:434-439`). The add-in says "No register is wired — paste one to reconcile against it" (`addin/taskpane.html:70`) and offers a textarea for a hand-entered JSON register (`:72-76`), which is re-keying. The events route's v0 scope reads "law_change_only — company-fact events require the licensed registry…" (`api.py:197`). **Minutes:** the SS minutes scanner is imported only by `scripts/scan_testdocs.py:22` (S2), and S3 found no mention of minutes in the API, the servers or the add-in. The add-in reads whatever Word document is open (`addin/taskpane.js:80-87`), which could be minutes. | **NOT SUPPORTED BY THE BACKEND.** Whether any deployment sets `MCA_AGG_*` is UNVERIFIED (env files not opened). S1 found no route that calls the adapter. |
| C2 | **Obligation matrices.** "Matrices for the duties the Act actually imposes: AGM timing under s.96, the board-meeting cadence under s.173, small-company status under s.2(85), and the Board's-report extracts." | Live `/` (card "Built for your obligations"). `page.tsx L323-324 / H323-324`. | The register has `CA13-S96-AGM` (`checker/obligations.py:620`), `CA13-S173-BOARD` (`:635`) and `CA13-S2-85-SMALL` (`:710`). The complete obligation-to-body map lists 15 ids (`checker/scope.py:160-169`), and `POST /v1/compliance-pack` serves them (`api.py:137-163`). **Board's-report extracts:** there is no Board's-report id among the 15 (`scope.py:160-169`) and no such route (`api.py:562-567`). A template does exist: `checker/templates/board_report.html`, a **PoSH** "Extract for the Board's Report — sexual harassment disclosure" under Rule 8(5)(x) (`:7, :12`), added in `2006cd9` (2026-08-08). S4 found nothing that references or renders it; its renderer went with the PoSH surface in `5b58bde`. `checker/ss/RULES.md:53` documents an SS check on a Board Report (T2.1), but the search above found no implementation outside that file. | **PARTLY SUPPORTED.** 3 of the 4 items are served. For Board's-report extracts, the only related file the searches found is an orphaned PoSH-only template. |
| C3 | **Works in Word, email and secretarial software.** "Use Placedon in Word, in email, and alongside the secretarial software your team already runs. The citation travels with the answer wherever it goes." | Live `/` (card "Works where you file"). `page.tsx L328-329 / H328-329`. | **Word:** an add-in exists as a local development build. The manifest's `AppDomain` and `SourceLocation` are `https://localhost:3000` (`addin/manifest.xml:24, 38`), and its "Self-signed certificate is for development only" (`addin/README.md:64`). **Email:** S15 found two email-related scripts, both founder outreach to District Officers rather than product features: `scripts/draft_letters.py:39` renders `.eml` letters and "does not send" (`:23`), and `scripts/send_letters.py:52-53` imports `email` and **sends through the Gmail API** with scope `gmail.send` (`:62`, client `:89`). S15 found no email code in `checker/api.py`, `addin/` or the server scripts. **Secretarial software:** S16's only hit is a docstring about ComplyRelax (`checker/ss/defects.py:231`). | **PARTLY SUPPORTED** (Word, as a local prototype). No product integration with email or secretarial software was found by S15 or S16. |
| C4 | **Drafting in Word.** "Draft board resolutions, notices, and Board's-report extracts inside Word, each clause carrying its section and operative date." | Live `/` (card "Placedon for Word"). `page.tsx L528-529 / H529-530`. The card's link goes to `/product`, and the live `/product` text does not contain "Word". | The add-in's stated rule: "this add-in NEVER modifies the document's text or formatting" (`addin/taskpane.js:4-5`; `addin/README.md:8-9`). S7 found no Word write call in `taskpane.js`, only comment lines. Its two functions call `POST /v1/document-check` (`taskpane.js:16`) and `POST /v1/mca-strip`. The manifest's display name is "Placedon — currency check" (`manifest.xml:20`). **Drafting code:** `checker/drafting.py` says "Only ONE template is implemented -- the AGM notice" (`:9`). S5: its only caller outside the module is `scripts/slice_s96.py:28, 48`, and S6 found no other `draft_*` function. The `checker/templates/` directory holds three PoSH-era HTML templates, including the Board's-report extract `board_report.html` (see C2); S4 found nothing that renders any of them. No board-resolution template was found by S6 or by listing `checker/templates/`. The pack states: "It generates no resolution, notice, or other operative document" (`checker/diligence_pack.py:64-65`). | **NOT SUPPORTED BY THE BACKEND.** No drafting route (`api.py:562-567`), no renderer found (S4, S5) and no Word write call found (S7). |
| C5 | **Placedon Matrix.** "Hand off a company and get back the full obligation matrix — one row per duty, marked attaches, met, or missing." | Live `/` (card "Placedon Matrix", which links to `/product/compliance-pack`). `page.tsx L534-535 / H535-536`. | `POST /v1/compliance-pack` returns one row per obligation (`api.py:156`) in five states (`checker/obligations.py:47-51`). The local HTML matrix `scripts/serve_matrix.py` serves `checker/matrix_view.handle` on `127.0.0.1:8014` (`serve_matrix.py:4, 28-29`; routes `/`, `/matrix`, `/pack` at `matrix_view.py:379-420`). **"Full" is overstated:** the pack says of itself "It covers {len(REGISTER)} obligations, not the whole Companies Act…" (`diligence_pack.py:61-63`), and the map has 15 (`scope.py:160-169`). **"Hand off a company" is overstated:** the pack's company facts come from the request payload (`api.py:141`, via `_profile`/`_evidence` at `:84-119`), and S1 found no registry lookup. | **PARTLY SUPPORTED.** The matrix exists for 15 duties, locally. |
| C6 | **Plugins / practice packs.** "Practice packs for corporate-secretarial work and MCA annual filings — AOC-4, MGT-7, DIR-3 KYC — configured to your registers and ROC calendar." | Live `/` (card "Plugins", which links to `/product`; the live `/product` text does not contain "plugin"). `page.tsx L540-541 / H541-542`. | **AOC-4:** register row `CA13-S137-AOC4` decides whether filing was on time from a user-supplied `aoc4_filed_on` (`obligations.py:673-682, 429-443`; `api.py:116`). **MGT-7:** row `CA13-S92-RETURN` (`obligations.py:684-693`; `api.py:117`). **DIR-3 KYC:** there is no DIR-3 id among the 15 (`scope.py:160-169`), and `din_status` is `UNBOUNDED_BLIND` because the rule "is not held" (`checker/mca_snapshot.py:149-156`). **Plugins / packs / ROC calendar:** S8 found none. | **NOT SUPPORTED BY THE BACKEND** as described. Two filing-timeliness rows exist. S8 found no plugin, pack or ROC-calendar code, and there is no DIR-3 KYC row. |
| C7 | **API integration.** "Integrate Placedon into your secretarial or GRC stack through the API and the evidence contract — built for Indian corporate-law workflows." Also: "Embed the record into your platform through the API and the evidence contract." | Live `/` (card "Platform"; section 05). `page.tsx L546-547 / H547-548`; "Embed…" `L849 / H854`. | A JSON API with **seven routes** exists (`api.py:496-567`; route list `:562-567`). Its server binds `127.0.0.1` and is unauthenticated by design. Making it a hosted, authenticated, rate-limited service "is a deliberate deployment step with its own security work, not a default here" (`scripts/serve_api.py:8-12, 24`). The add-in's server (`addin/serve.py:95`) and the matrix server (`scripts/serve_matrix.py:28`) also bind `127.0.0.1`. The static Ask prototype `web/assistant/` is "a prototype, not a product surface. `POST /v1/ask` does not exist" (`web/assistant/README.md:11`), and a search of `web/assistant/` for `fetch\(|XMLHttpRequest|WebSocket|sendBeacon` had no hits (bare `fetch` matches prose such as `corpus_fetched`; the only dynamic `import()` is in the Playwright test tool `tools/accept.mjs`). The earlier hosted surface (`checker/app.py`, `api/index.py`, `vercel.json`) was removed in `5b58bde`, and S10 found no deploy config in the tracked tree. The comment "the deployed function" in `requirements.txt:1` is stale. | **PARTLY SUPPORTED.** The API exists and, as committed, binds to loopback only. No hosted instance was found in this repo (S10); whether one exists elsewhere is UNVERIFIED. |
| C8 | **MCP.** "Connect your registers, MCA21 filings, and minute books to Placedon through the open Model Context Protocol." | Live `/` (card "MCP for statutory data", section 05). `page.tsx L555-556 / H556-557`. | S9 found no MCP file, code, config or dependency in the tracked tree. `requirements.txt` lists `fastapi`, `python-multipart`, `jinja2`, `pydantic` and `anthropic`. The runbook's stop rules say "No MCP registration". | **NOT SUPPORTED BY THE BACKEND** (none found by S9). |
| C9 | **DPDP-ready data handling.** "Designed to hold data under India's DPDP Act, 2023: no personal data beyond what a request needs, an audit trail on every answer, and abstention wherever the source is missing." | Live `/` (card "Built for India's data law"). `page.tsx L565-566 / H566-567`. | **Minimisation, by design:** the add-in "sends the document's **text and date**, not the file" (`addin/README.md:16`). Facts arrive "in the POST body, never the URL", and responses are no-store (`scripts/serve_api.py:9-11`). **Audit trail:** S13 found no durable write in the API path (only response writes and stderr request logs). The add-in's session has "**no path to durable storage at all**" (`checker/session.py:9-11`), and the event log "v0 has no persistent store" (`checker/event_log.py` docstring). Each pack carries a provenance block (`diligence_pack.py:127-134`), which gives reproducibility, not a stored trail. **DPDP:** `DPDP2023` is `DECLARED`, and nothing has been acquired (`scope.py:136-142`). **Abstention:** see C11. | **PARTLY SUPPORTED.** No per-answer audit trail was found (S13). Compliance with the DPDP Act was not assessed (UNVERIFIED). The conflict between "audit trail" and "no durable storage" is INFERRED, since "audit trail" may mean only the provenance block. |
| C10 | **Deterministic engine.** "Every applicability decision is pure code, testable without a network. The model explains; it never decides." Also (live): "Applicability is pure, deterministic code — testable without a network, the same every time." | Live `/` (card "Deterministic engine"; step "Code decides"). `page.tsx L560-561 / H561-562`. The "Code decides" wording is at `L348-349`; H349 has different wording (`3d0f855`). | The API docstring says "No model is consulted" (`api.py:9`), and responses carry `"no_model": True` (`api.py:229, 403, 520`). Drafting: "No model is wired in" (`drafting.py:19`). **The "model explains" half is not wired into any served path:** the repo has several model clients (`checker/anthropic_model.py`, `checker/gemini_model.py`, `checker/ollama_runner.py`, `eval/realrun/azure_model.py`, `backend/services/llm.py`), and S14 found no direct import of any of them in `api.py`, `matrix_view.py`, `diligence_pack.py`, `obligations.py` or the three server scripts (transitive imports not traced). | **SUPPORTED** for "code decides". "The model explains" is present tense, but S14 found no model client directly imported by a served path. |
| C11 | **Abstention.** "When a limb of a provision is undecided, Placedon says so and names the missing instrument. It never renders a fabricated figure to fill a gap." | Live `/` (card "Abstains by design"). `page.tsx L333-334 / H333-334`. | `CANNOT_DETERMINE` rows carry `blocked_by`, the acquisition task named in the row's own basis (`obligations.py:828-846`), and a test checks it (`:972-976`). The API docstring says unknown figures stay unknown "(never coerced to 0)" (`api.py:11-12`). Fields that cannot be bounded come back "UNBOUNDED_BLIND naming what we would have to acquire — never with a number" (`mca_snapshot.py:36-37`). | **SUPPORTED** within the 15-obligation register (I did not test the "never" beyond the code and tests cited). |
| C12 | **Every answer is traced and verified.** "Every answer traces to a provision, an instrument, and an operative date. Nothing ships while it cannot be verified." Also: "Nothing reaches you while it is unverified. Abstention is the honest default, not an error." | Live `/`. `page.tsx L697-698 / H702-703`; `L354-355 / H354-355`. | **Provision tracing:** each row serialises `provision` and `cited_spans` with their sha256 (`api.py:122-135`). That serialiser has no dedicated instrument or effective-date field (`basis` is free text and may name one). Instrument and date appear on the currency and event outputs (`api.py:157-161, 243-248`). **Verification:** the backend's recorded corpus status is "NOT_FULLY_VERIFIED", and independent-publisher verification is "PENDING" (`CLAUDE.md:131-132`). The pack's provenance block has no verification-status field (`diligence_pack.py:128-134`), and S11 found the status string in no code file. The pack says "No lawyer has reviewed it" (`diligence_pack.py:66`). | **PARTLY SUPPORTED.** Provision tracing is real. The row serialiser has no dedicated instrument or operative-date field. "Nothing reaches you while it is unverified" is not borne out by the backend's own recorded corpus status. |
| C13 | **FAQ scope.** Live: "Tax, employment law, securities regulation, and case-law research are not represented as covered services." HEAD: "…are not covered." | Live `/faq` (first answer). `src/lib/placedon-content/content/faq.ts:12` at both commits, with the wording changed in `939f40f`. | **Securities:** `SEBI_LODR` is `CURRENT_ONLY`. SEBI's consolidation is held ("PENDING_HUMAN_REVIEW"), and "No obligation is wired to it yet" (`scope.py:91-102`). `SEBI_OTHER` (ICDR, SAST, PIT, Buyback) is `DECLARED`, "Nothing acquired" (`scope.py:104-108`). All 15 mapped obligations are `CA2013` (`scope.py:160-169`). `DECLARED` is "in product scope, nothing acquired yet -- must REFUSE, naming the body of law and what would have to be acquired" (`scope.py:19-20`). **Tax:** the self-test expects `body("GST")` to raise `LookupError` (`scope.py:320-326`). **Employment:** `POSH` is `OUT_OF_SCOPE` (`scope.py:144-148`). **Case law:** the `BODIES` tuple (`scope.py:76-153`) declares no case-law body, and `case.?law|kanoon` has no hit in `scope.py`. | **PARTLY SUPPORTED.** The FAQ matches what the engine can decide (no mapped securities obligation). It contradicts the backend's framing: securities law is declared in scope but not held, and the LODR text is already held. |
| C14 | **Hero pillars (HEAD only, not live).** "Research · Compliance · Monitoring · Drafting" and "Placedon brings research, compliance, monitoring, and drafting into one place for corporate teams and their lawyers. …" | `page.tsx H626, H630-631` (added in `c0dd31d`, edited in `70ac6d1`). Not on the live site (see §2). | **Research:** the seven routes (`api.py:562-567`) include no ask or research route. The static Ask prototype renders saved fixtures and says `POST /v1/ask` "does not exist" (`web/assistant/README.md:11`). ASK-1 was adding a deterministic `/v1/ask` concurrently, and it is not in `b37462e`. **Compliance:** `/v1/compliance-pack` and the local matrix (C5). **Monitoring:** pull-based law-change events (`GET /v1/company/{cin}/events`, `api.py:202-229`, v0 scope `law_change_only`). S12 found no scheduler or push delivery. **Drafting:** as in C4. | **PARTLY SUPPORTED,** and not live. |
| C15 | **Compliance-pack mock provenance.** Labels and values: Corpus `companies-act-2013@2026-09-01`, Benchmark `bench-2026.09`, Checker `f2ebcb3`. | Live `/product/compliance-pack`, labelled "Product concept — shown on fixed sample data, not a live answer for a real company. …". `src/lib/engine/mock.ts:35-37` at both commits. | `corpus_version` is `"sha256:"` plus a hash, and the code comment says "Not a date" (`checker/release_record.py:64-70`). The pack uses benchmark `"v3"` (`diligence_pack.py:127`). `bench-2026|companies-act-2013@` hits only the FRONTEND_ALIGNMENT report. `f2ebcb3` is a real backend commit (2026-09-10). | **PARTLY SUPPORTED.** This is a sample-data page, but 2 of its 3 identifiers use formats the backend's provenance code does not produce. |
| C16 | **Add-in support link.** `SupportUrl` is `https://placedon.com/support`. | `addin/manifest.xml:22` (backend). | Live `/support` redirects to `www.placedon.com/support` and returns **HTTP 404**. `git ls-tree` of `src/app` at `939f40f` has no path containing `support`. | **NOT SUPPORTED** (a dead link on the site side). |

I found no present-tense capability claim that the backend would have to meet on `/product`,
`/how-it-works`, `/security`, `/pricing`, `/about`, `/product/document-check`, `/product/events`
or `/product/instruments`. Their copy is hedged, for example "These views describe the intended
product; they are not live compliance checks" (`product.ts:16` at L) and "No company lookup, registry
connection, or certificate of compliance is offered on this site" (`product.ts:71` at L). The live FAQ also
says: "The planned company-standing and event views describe evidence review, not an authorised
connection to the Ministry of Corporate Affairs or a Registrar of Companies" (`faq.ts:102` at L).
That sits against C1 on the home page, **so the site contradicts itself.**

### 2. Is the live site behind `main`?

| Probe (commit → string) | Repo | Live | Reading |
|---|---|---|---|
| `f2b5167` (09-14 19:02), footer "Connect" column | adds `https://www.linkedin.com/company/placedon/` and Instagram | 0 matches for `linkedin.com` / `instagram.com` in `/` HTML or the 13 JS/CSS assets; live footer is Product · Company · Legal | live lacks it |
| `0e4c188` (09-14 19:09), X link | adds `https://x.com/placedonAI` | 0 matches for `placedonAI` | live lacks it |
| `3d0f855` (09-15 12:21), dash removal | "…your statutory registers — no re-keying…" → "…statutory registers, so you do not re-key…" | old em-dash wording on `/`; 7 of 28 long live lines absent from `3d0f855`'s `src/` | live lacks it |
| `c0dd31d` (09-15 12:35), hero H1 | "Every answer carries its evidence." → "The evidence-first workspace for Indian corporate law." | old H1 in `/` HTML and `3wdbnbbups_b5.js`; new H1 in no fetched file | live lacks it |
| `70ac6d1` (09-15 12:38), hero eyebrow | "Research · Compliance · Currency · Drafting" → "…Monitoring…" | "Monitoring" in no fetched file; live eyebrow "Placedon · Indian corporate law" | live lacks it |
| `359a5fc` (09-15 12:57), page descriptions | FAQ headline "What is proposed. What is not established." → "What we're building, and what we don't claim yet."; product subhead "Placedon is being designed around an inspectable evidence record…" → "Placedon is built around an evidence record you can inspect…" | old FAQ headline on `/faq`; old subhead on `/product`; new strings in neither | live lacks it |
| `88e93a6` (09-15 13:27), section prose | product claim "The intended answer carries the material needed to examine it." → "Every answer comes with the material you need to check it."; "Expose the official record." → "Show the official record." | both old strings on `/product`; neither new string | live lacks it |
| `939f40f` (09-15 13:34), FAQ answers | "…are not represented as covered services." → "…are not covered." | old wording on `/faq` | live lacks it |
| `4eec7ed` (09-13 00:36), GA funnel | `track("request_pilot_click", …)` | present in `3wdbnbbups_b5.js`, `0a7o59l3ym-25.js` | live has it |
| `2b05146` (09-13 00:55), GA injected on consent | `"ga4-src"`, `"ga4-init"`, localhost skip | all three present in `0srp54dij28go.js` | live has it |
| full-text match | 28 live home lines ≥ 40 characters vs each commit's `src/**/*.ts(x)` | 28/28 at `2b05146`, `4bf6bbf`, `f2b5167`, `0e4c188`; 21/28 at `3d0f855`, `c0dd31d`, `939f40f` | consistent |

- **Result: the live build is behind `main`.** Each of the **eight** content commits from
  `f2b5167` to `939f40f` (2026-09-14 → 09-15) has at least one probe string, and in every case
  the live site serves the pre-change wording. The live content matches the tree at some commit
  from `2b05146` to `4bf6bbf` inclusive.
- Within that window, `git diff --stat 2b05146 4bf6bbf -- src public` shows one changed file,
  `src/components/analytics.tsx` (`cdee7ba`, GA id `??` → `||`). When `NEXT_PUBLIC_GA_ID` is
  unset, both forms compile to the same literal, and the live JS has `let n="G-…"`. Whether that
  variable is set on Vercel is UNVERIFIED. `2c68d7b` is empty, `2c2cdb3` changes
  `next.config.ts`, `package.json` and docs, and `4bf6bbf` changes docs and root files outside
  `src/` and `public/`. **I could not tell from the fetched HTML and JS which commit in the
  window is live.**
- **Timing (INFERRED).** The largest page cache age (home, 308086 s) dates that cached render to
  **2026-09-13 16:02:18 UTC = 21:32:18 IST**. All twelve pages carry one deployment id, which
  suggests that deployment existed by then. That would exclude `4bf6bbf` (committed 22:17 IST),
  assuming Vercel's edge cache does not outlive a deployment (not verified). 21:32 IST is 11
  minutes after `2c2cdb3` (21:21 IST). **INFERRED: live ≈ `2c2cdb3`;** `cdee7ba` is still
  possible if the edge cache was refilled after the deploy. Cache ages vary across pages
  (292k–308k s), which suggests per-page fills. This agrees with FRONTEND_ALIGNMENT A4.
- Why none of the eight later commits is live is UNVERIFIED. The 3300 README "gotcha 1" (silently
  blocked Vercel deploys) is a candidate cause; I did not check it.

## Evidence quality
- **Strong (primary, reproducible):** backend statements are file:line at `b37462e`. Frontend
  statements are file:line at named commits. Live statements are exact strings from HTML and JS
  fetched on 2026-09-17, with headers recorded. The lag rests on ten string probes (eight
  showing the new wording is absent, two showing the old wording is present) plus a full-text
  match.
- **Moderate:** every "not found" verdict (C1 minutes, C2, C3 email and secretarial software,
  C4, C6, C8, C9 audit trail, C12, C14 monitoring) rests on the named searches S1–S16. Those
  cover this repository at `b37462e` only. Another repository, an unpublished branch or an
  external service would not show up. The round-1 errors (see *Revision log*) are exactly this
  failure: absence stated beyond what the search showed.
- **Weak / INFERRED:** the exact live commit (`2c2cdb3`) rests on one cache `age` header and on
  Vercel edge-cache behaviour that I did not verify. The meaning of "audit trail" (C9) is an
  interpretation.
- **Concurrency caveat:** the backend moved from `b37462e` to `dc2c399` during the fix round
  (P-1; `checker/prescribed_thresholds.py` changed). ASK-1 may add `/v1/ask`. C14 (research) and
  anything touching 880(E) may already have changed.

## Result
- **Verdicts (16 claims):**
  - SUPPORTED 2: C10, C11.
  - PARTLY SUPPORTED 9: C2, C3, C5, C7, C9, C12, C13, C14 (HEAD only), C15.
  - NOT SUPPORTED BY THE BACKEND 5: C1, C4, C6, C8, C16 (a site-side dead link).
  - No whole claim is UNVERIFIED; the UNVERIFIED sub-points are under *Unresolved issues*.
- **The three most serious unsupported claims** (present tense and live, each in conflict with a
  backend file or with the site's own FAQ):
  1. **C1, MCA21 connection ("no re-keying").** Both MCA21 adapters refuse without a licensed
     configuration (`checker/corporate_data.py:90-95`, `checker/mca_aggregator.py:138-141`), and
     S1 found neither imported by a route or server. The add-in asks for a pasted, hand-entered
     register (`addin/taskpane.html:70-76`). The live FAQ says the company views are "not an
     authorised connection to the Ministry of Corporate Affairs".
  2. **C4, drafting in Word.** The add-in's own rule is that it "NEVER modifies the document's
     text or formatting" (`addin/taskpane.js:4-5`), and S7 found no Word write call. The one
     implemented drafting template, the AGM notice (`checker/drafting.py:9`), is called only by
     `scripts/slice_s96.py` (S5). An orphaned PoSH Board's-report extract template exists
     (`checker/templates/board_report.html`), which S4 found nothing rendering. The pack states:
     "It generates no resolution, notice, or other operative document"
     (`checker/diligence_pack.py:64-65`).
  3. **C8, MCP, with C6, plugins.** S9 found no MCP code, config or dependency, and S8 found no
     plugin, pack or ROC-calendar code. DIR-3 KYC is explicitly unbounded because its rule is not
     held (`checker/mca_snapshot.py:149-156`).
  - Also serious, though phrased as a principle: **C12.** "Nothing reaches you while it is
    unverified" sits on a corpus whose recorded status is NOT_FULLY_VERIFIED (`CLAUDE.md:131`).
- **FAQ vs `scope.py`:** the framings differ, as E6 said. The FAQ says securities law is not
  covered. `scope.py` declares it in scope (`DECLARED`) and already holds the `SEBI_LODR` text
  (`CURRENT_ONLY`). In practice neither decides a securities obligation today (no securities id among the 15 mapped, `scope.py:160-169`); the scope statements differ.
- **Lag:** the live site is behind `main` by **eight** content commits (`f2b5167` … `939f40f`).
  Its content matches the tree at `2b05146`…`4bf6bbf`. **INFERRED: `2c2cdb3`.** Claims C1–C12
  are live in their pre-`3d0f855` wording. The broader HEAD-only hero (C14) is not live.

## Unresolved issues
1. **Deployment id `dpl_3wuFWKjs7LG3632rQFYRct687JVf` → commit:** UNVERIFIED. The Vercel
   dashboard or API can settle it; neither was a source for this job.
2. Why the eight later commits did not deploy is UNVERIFIED.
3. Whether a hosted backend or aggregator configuration exists outside this repo (C1, C7) is
   UNVERIFIED. Env files were not opened, and S10 found no hosting config in the tracked tree.
4. The meaning of "audit trail on every answer" (C9) and "the evidence contract" (C7) was not
   defined anywhere I checked.
5. **880(E)** (FRONTEND_ALIGNMENT E4): the live mock says "not yet settled in the corpus…
   pending Gazette attestation". At `b37462e` the backend decides servability through
   registration and attestation (`checker/prescribed_thresholds.py:176-203`), and `dc2c399`
   (P-1) changed that file. No verdict is given here.
6. DPDP compliance of the proposed data handling was not assessed.

## Recommended next action
1. **Founder (A-007):** remove or re-tense the home-page copy for C1, C4, C6 and C8, for example
   using "planned" as `/product` already does, or record a dated build commitment for each. The
   copy is at `page.tsx H318-319, H529-530, H541-542, H556-557`. Reconcile C12's "Nothing reaches
   you while it is unverified" with the corpus status. This work is in the 3300 repo, and agents
   must not push there.
2. **Founder:** choose one public scope wording, FAQ "not covered" or backend "in scope, not
   held", then align `faq.ts:12` or `scope.py`. Add a `/support` page or change
   `addin/manifest.xml:22`.
3. **Founder or main session:** in Vercel, look up `dpl_3wuFWKjs7LG3632rQFYRct687JVf` to confirm
   the live commit, and find out why the 2026-09-14/15 pushes did not deploy. **A redeploy of
   `main` would put the broader HEAD hero (C14) live, so review C14 before redeploying.**
4. **Backend, optional, in a separate commit:** correct the stale "deployed function" comment in
   `requirements.txt:1-3`. Decide whether the orphaned PoSH templates in `checker/templates/`
   (S4) should be retired as `5b58bde` retired their renderer.

## Revision log
- **Round 1 (verifier FAIL, main session confirmed findings 1-3 at `b37462e`):**
  1. C2, C4 and Result item 2 no longer say that no Board's-report template exists or that
     drafting.py is the only drafting code. They now cite
     `checker/templates/board_report.html` (PoSH, `2006cd9`, nothing renders it per S4).
  2. C3 now cites `scripts/send_letters.py:52-53, :62` (Gmail API send, founder outreach). The
     email search terms are listed as S15.
  3. C10 now lists all model clients found and cites S14 for "not imported by a served path".
  4. The lag is now eight commits, not six: `359a5fc` and `88e93a6` each got their own probe.
  5. C7 and C14 now mention `scripts/serve_matrix.py` (127.0.0.1:8014) and `web/assistant/`.
  6. Frontend line citations are now given per commit (L = `2c2cdb3`, H = `939f40f`).
  7. The C7, C10 and C14 quotes are corrected to the exact live or HEAD text, with ellipses where
     cut. The C1 quote is now given in full.
  8. Every "only", "no", "none" and "never" was re-read. Each now cites a search (S1–S16) or a
     file line, or is softened to "not found by …".
- Round 2 (main session, check 3): the verifier's two minor findings applied — the `product.ts` quote split across `:16` and `:71` at L; the C7 search pattern corrected to `fetch\(` with the reason. Hand checks: `curl -L https://placedon.com/support` → 404 at www.placedon.com/support (C16 holds); `addin/taskpane.js:4` states the add-in never modifies the document, and no `insertText`/`insertParagraph` call exists (C4 holds).

