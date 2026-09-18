<!-- Research output of a read-only analysis agent (2026-09-16/17), copied in by the main session.
     Main-session spot checks before use, all HOLD:
     1. 3300 `AGENTS.md:58` says `/v1/ask` does not exist and must not be called; `src/lib/engine/types.ts:5`
        "never add them here" (the client); `docs/RAG-INTEGRATION.md:60` "do not present a working chatbot".
        NUANCE: these ban a client method and a working-chatbot presentation, not the Ask design itself.
     2. Tokens `src/app/globals.css:4-19` (ink #0c0c0d, cream #f4efe6, gold #c9a24b, abstain #5b6472, radius 3px).
     3. Dark only: `src/app/layout.tsx:46` data-theme="dark".
     4. Abstain card `src/components/surfaces/surfaces.css:176-186` (dashed badge, 3px muted left rule).
     5. Live https://www.placedon.com title "Placedon — the record for Indian corporate law" (curl, 2026-09-17).
     Applied in commit 5202f85 (web/assistant) and PLAN_13 §27. -->

# Frontend alignment report — Ask section vs the finalized PlacedOn frontend

Status: COMPLETE. Read-only analysis, 2026-09-16/17. No repo was modified.

**Headline:** the finalized frontend (placedon-claude-legal-3300 = the live placedon.com) is a **dark**, cream-and-ink, Fraunces / Inter / IBM Plex Mono Next.js 16 site with a brass-gold accent and cool-grey abstention. It has **no Ask or chat surface**, and its docs forbid `/v1/ask` and "a working chatbot". The Ask prototype was designed against the older business-plan design system (light Parchment, Slate, Caution brown, system fonts), which the finalized site does not use. The data contract mostly fits (shared serializers). The visual system, the state vocabulary ("abstain") and the placement do not fit yet (sections C, D4 and F).
Clone of the finalized repo: `/Users/nishantsingh/.claude/jobs/c886fa96/tmp/repos/placedon-claude-legal-3300` (path prefix `3300/` below).
Backend repo: `~/PlacedOn/placedon-law-backend` (prefix `backend/`). Business-plan repo: `~/PlacedOn/Placedon-law-business-plan` (prefix `bizplan/`).

## A. Sources (partial)

### A1. placedon-claude-legal-3300 (the "finalized" frontend)
- Clone: `git clone --depth 50` over HTTPS succeeded (so the repo was readable without auth at clone time, even though README says "private").
- What: "marketing + product-concept website" for "Indian corporate law (Companies Act, 2013)" — `3300/README.md:7-14`.
- Stack: Next.js 16.3.4 App Router + React 19.2.8 + TS strict + Tailwind v4 + framer-motion 13 + zod 4 (`3300/package.json:12-38`; `3300/README.md:29-31`). package name is still `"placedon-web"` (`package.json:2`). Dev port 3300 (`package.json:6`).
- Hosting: Vercel, auto-deploy on push to `main`; claims production URL https://placedon.com + www (`3300/README.md:18-27`). Optional Azure App Service (`next.config.ts` `output: "standalone"`, `README.md:91-94`).
- Status per README: "LIVE (pilot)", `noindex` pre-launch (`README.md:18-27`; `src/app/layout.tsx:34` `robots: { index: false, follow: false }`).
- Last commit: `939f40f` 2026-09-15 13:34 +0530, author "Placedon <placedon007@gmail.com>", "Humanize copy: FAQ answers". First commit `77dc2c5` 2026-09-11 "Placedon :3300 Claude-legal prototype — baseline + Claude→Claude handoff" (author Saiyam Upadhyay). 34 commits total, single branch `main`.
- Product: the LEGAL product (Companies Act 2013), not HR/hiring.
- HEAD analysed: `939f40f21ce3bca3ff31484c8a6bbf69b8072204`. `.env.example` exists (not printed); no `.env` committed.
- Doc lineage: the repo carries its own backend contract docs (`3300/docs/RAG-INTEGRATION.md`, `3300/docs/ASTRA_MASTER_PROMPT.md`, `3300/docs/specs/backend-architecture-dossier.md`) that were verified against `checker/api.py @ f2ebcb3` (`3300/src/lib/engine/types.ts:3-4`).

## B. placedon-claude-legal-3300 in depth

### B1. Purpose and binding rules
- `README.md:7-10`: "evidence-first legal-intelligence product for Indian corporate law (Companies Act, 2013). Voice: 'a witness, not a tool.' Golden rule: 'the model explains, the code decides, the record verifies.' Every answer carries its provision, amending instrument, and operative date — or it abstains."
- `AGENTS.md` is declared binding ("re-read it every session", `README.md:111-116`). Key rules:
  - Colour: "near-monochrome. Base = near-black `#0C0C0D` + warm cream `#F4EFE6` ... Accent = Brass Gold `#C9A24B`, ≤10% of any screen, ONE accent element per view. `--gold-muted #9F743B` for citations only. Cool Grey `#5B6472` is reserved only for the 'abstained / unknown' state ... No navy-dominant, no second accent colour." (`AGENTS.md:12-15`)
  - Fonts: "Fraunces (display serif) · IBM Plex Mono (every section reference `s.96(1)`, figure `₹10,00,00,000`, instrument `G.S.R. 880(E)`, and date) · Inter/Archivo (body). Mono citations are the brand signature" (`AGENTS.md:16-18`).
  - Voice: banned words list incl. "solution", "easy", "smart", "seamless"; "Join the waitlist" banned; primary CTA "Request a pilot" (`AGENTS.md:22-34`).
  - Honesty: never claim an accuracy rate; never invent a statutory figure/section/date (`AGENTS.md:30-37`).
  - Design: "Corners ≤6px. Shadows minimal. One orchestrated hero motion moment; everywhere else ≤250ms" (`AGENTS.md:44-45`). Forbidden: "glassmorphism everywhere", "everything centered", "`rounded-lg`+accent-bar on every card" (`AGENTS.md:41-43`).
  - Engineering: "no colour-only status (the answer classes must be distinguishable without colour)"; output classes `verified_fact | deterministic_conclusion | predictive_signal` + `abstained` (`AGENTS.md:48-53`).
  - API: "The backend has exactly SIX routes ... ⚠ `/v1/company/{cin}/standing` DOES NOT EXIST — nor does `/v1/ask`." (`AGENTS.md:54-59`); "A transport failure must NEVER render as an abstention" (`AGENTS.md:62-64`); "The engine is plain HTTP on `127.0.0.1:8020`, unauthenticated, no CORS. It is server-only" (`AGENTS.md:65-66`).
  - Note: `AGENTS.md:3` still says "Next.js 15 ... + shadcn/ui" — stale: package.json is Next 16.3.4 and there is NO shadcn (no `components/ui`, no radix deps; only `class-variance-authority`, `clsx`, `tailwind-merge` which are unused shadcn leftovers — `package.json:17-26`). Tailwind v4 is imported (`globals.css:1`) but the redesign spec found "zero utility classes used" (`docs/specs/2026-09-11-placedon-frontend-redesign-design.md` §1 F1); styling is hand-written CSS classes.
- F9 (the Ask feature) is explicitly NOT to be presented as a working chatbot:
  - `docs/RAG-INTEGRATION.md:58-60`: "The deterministic path is the live product today. The grounded-answer path exists as a safety spine ... there is no answer endpoint and no model connected. Build the UI so the spine's design (grounded-or-abstain) is the visible feature; do not present a working chatbot."
  - `docs/RAG-INTEGRATION.md:326-327`: "Designed, engine present, surface pending: the grounded-answer path (F9) — spine built, no `/v1/ask`, no model. Do not build a client method for it yet; when it lands it will follow the model-adapter claim schema in §5."
  - `docs/ASTRA_MASTER_PROMPT.md:123`: "F9 | Grounded Research Assistant | Ask a question → a cited answer, or an honest refusal. Never composes advice, never invents a citation. | Safety spine built; no endpoint/model wired".
  - `docs/ASTRA_MASTER_PROMPT.md:127`: "Not in the plan — do not add ... a general legal chatbot, a free-text document generator ...".
  - `docs/ASTRA_MASTER_PROMPT.md:210-211`: "Research Assistant (F9) and Drafting (F10) — present with their safety story visible; where the model isn't wired yet, show the grounded/abstain design as the feature, not a broken input."
  - `docs/specs/design-research-dossier.md:483`: "Design consequence: Placedon's output should be shaped like a junior's memo with a source-checked margin, not like a chat reply. Proposition, pin-cite, the quoted provision itself, and a 'what would change this answer' line."
- Redesign spec status: "awaiting owner approval" in the header but §7 says "Owner decisions — SETTLED 2026-09-11": full multi-page site; autonomous execution; keep hero video (`docs/specs/2026-09-11-placedon-frontend-redesign-design.md:2, 157-166`). Its "anchor artefact" is the Compliance Note card: "cream paper, Fraunces title, mono `Note No. PL-2026-014 · Companies Act, 2013`, numbered clauses, inline `s.96(1)`. It is the strongest thing on the site ... The redesign is built around it" (same file, §2).

### B2. Architecture
- Server-only typed engine client `src/lib/engine/*`: `getEngine()` reads `PLACEDON_API_ORIGIN` at call time; unset → `MockEngineProvider`, set → `HttpEngineProvider(origin, {token: PLACEDON_API_TOKEN})` (`src/lib/engine/provider.ts:63-73`). Origin must be https, or http only on loopback (`src/lib/engine/http.ts:31-46`); 8 s timeout (`http.ts:30`). `server-guard.ts` throws if imported in a browser (`server-guard.ts:9-12`).
- Every call returns `EngineResult<T> = {ok:true,data}|{ok:false,error}`; error kinds `transport_error | timeout | schema_mismatch | not_found | bad_request | server_error` (`src/lib/engine/errors.ts:11-39`). "An engine failure is NOT an abstention" (`errors.ts:5-9`).
- Interface has exactly six methods: `health, compliancePack, documentCheck, events, event, instrumentAffected` (`provider.ts:26-48`); routes constant `ENGINE_ROUTES` (`types.ts:7-14`) with the comment "`/v1/company/{cin}/standing` and `/v1/ask` DO NOT EXIST — never add them here." (`types.ts:5`).
- Product answer classes: `verified_fact`, `deterministic_conclusion`, `predictive_signal`, `abstained` (`types.ts:55-60`). Row states `APPLIES_SATISFIED | APPLIES_NOT_SATISFIED | APPLIES_UNDETERMINED | DOES_NOT_APPLY | CANNOT_DETERMINE`; `APPLIES_UNDETERMINED`/`CANNOT_DETERMINE` map to `abstained` (`types.ts:29-73`). Event output classes `VERIFIED_FACT | DETERMINISTIC_CONSEQUENCE | SIGNAL` (`types.ts:38-42`). `Abstention` has `obligation_id, provision, basis, missing_facts, blocked_by` and can only be built from a payload (`types.ts:431-464`).
- Interactive calls must go through same-origin route handlers (`docs/specs/...redesign-design.md` §4: "Server Components for render-time reads; same-origin route handlers for interaction ... client-side fetch fails by construction"). The only route handler today is `src/app/api/waitlist/route.ts` (origin check, JSON content-type check, in-memory 10-per-10-min rate limit — lines 11-38).
- Legacy `src/lib/api.ts` still exists with the old fictional contract (`standing(cin)`, lines 47-52) and is still exercised by `tests/contracts.mjs:147` (`bad.standing("invalid")`), though no page imports it (only the four product pages import `getEngine`).
- Hosting/integrations: Web3Forms lead form (client-side key in `src/components/request-form.tsx`), consent-gated GA4 `G-DE8BMPJRVL` (`README.md:76-86`).

### B3. UI surfaces (routes)
| Route | File | What it is |
|---|---|---|
| `/` | `src/app/page.tsx` (944 lines, `"use client"`) | Home: breadcrumb, image hero ("The evidence-first workspace for Indian corporate law.", eyebrow "Research · Compliance · Monitoring · Drafting", `page.tsx:624-635`), hero video, 01 "Built for the record" features, 02 "How compliance teams use Placedon" interactive demo, 03 Tools, 04 principles, 05 Platform, 06 resources, CTA band, secondary hero |
| `/product` | `src/app/product/page.tsx` | `MarketingPage` over `content/product.ts` (answer record, currency, compliance pack, company standing [planned], event log, abstain state) |
| `/product/compliance-pack` | `src/app/product/compliance-pack/page.tsx` (190) | Server Component, `getEngine().compliancePack(...)` on fixed sample data |
| `/product/document-check` | `.../document-check/page.tsx` (177) | same pattern, `documentCheck` |
| `/product/events` | `.../events/page.tsx` (100) | "Currency events", law-change stream, shows `scope` |
| `/product/instruments` | `.../instruments/page.tsx` (103) | "Instrument impact" |
| `/how-it-works`, `/pricing`, `/about`, `/security`, `/faq`, `/waitlist` | `src/app/*/page.tsx` | marketing pages via `MarketingPage` / own CSS |
| `/privacy`, `/terms`, `/cookies` | `src/app/*/page.tsx` + `legal/*.md` | legal pages |
| `/api/waitlist` | `src/app/api/waitlist/route.ts` | intake POST |
| `/icon.svg`, `/og/placedon.png`, robots, sitemap | route handlers | assets/SEO |

- Main nav: Product · How it works · Security · Pricing + "Request a pilot" button (`src/components/site-chrome.tsx:31-36, 114-121`). There is no Ask/Research/Assistant link.
- Product surfaces share `SurfaceShell` (`src/components/surfaces/surface-shell.tsx:27-73`): `.dash` wrapper → `SiteNav` → head (eyebrow, h1, intro, a "Product concept, shown on fixed sample data. It is not a live answer for a real company, and registration is not open." note at `:52-55`) → pill sub-nav of the four surfaces (`:20-25, 56-66`) → body → `SiteFooter`. Kit components in the same file: `ClassBadge` (icon + label, never colour alone, `:77-128`), `Citation` (mono boxed provision, `:136-142`), `Stamp` ("Jurisdiction India · Companies Act, 2013 / As of / Law as of / Generated (IST)", `:144-173`), `EngineErrorPanel` ("Service unavailable — The record could not be reached. This is a connection or service problem, not a legal finding. No answer, and no abstention, is implied.", `:177-193`), `AbstentionCard` (badge + citation + basis + "What would settle it" mono chips + "Blocked by", `:197-236`), `ProvenanceFooter` (`dl`, `:240-255`).
- Bug noticed: `SurfaceShell` renders `<main id="main-content">` (`surface-shell.tsx:43`) inside the root layout's `<main id="main-content">` (`src/app/layout.tsx:54`) → nested `main` and duplicate id. Any Ask page reusing `SurfaceShell` inherits this.

### B4. The chat / ask experience in the finalized frontend
- There is NO chat, composer, streaming, or model call anywhere in `src/` (grep for ask/chat/composer/assistant/stream returns only copy strings; see `how-it-works.ts:13` "Ask. Verify. Cite. Or abstain."). No LLM SDK in `package.json`.
- The closest thing is the home-page "In practice" demo (`src/app/page.tsx:717-791`): APG-ish tablist of five use cases (`AGM timing`, `Board meetings`, `Small-company status`, `Board's report`, `Registers`, data at `page.tsx:367-548`); left: a cream "paper" **Compliance Note** (`.ddoc`/`.ddoc-paper`: title "Compliance Note", mono italic meta "Note No. PL-2026-014 · Companies Act, 2013", numbered blocks "1. The rule" / "2. For this company", inline `.dcite` citations like `s.96(1)`, `G.S.R. 700(E)`, and a left-ruled `.ddoc-note`); right column: a `.dcard` "Prompt" card showing the question and a "Connectors" card (e.g. "MCA21 Portal", "Board minutes"). Caption: "Illustrative example. The sample data shows the format, not a live answer for a real company." (`page.tsx:726-729`). The Small-company tab is the abstention example: "Placedon does not answer this one, and it will not guess ... G.S.R. 700(E) ... is not in the record yet" (`page.tsx:459-478`).
- So the de-facto "answer" design language is: a document-like note on cream paper inside a dark page, question shown separately as a "Prompt" card — not chat bubbles.
- `src/components/evidence-card.tsx` has an "Evidence record" abstention card ("No verified answer. The required evidence has not been established.", `:23-60`) and a roving-tabindex `AnswerExplorer` (`:66-147`).

### B5. Design tokens actually in use (finalized frontend)
- Global `:root` (`src/app/globals.css:3-77`): `--ink #0c0c0d`, `--cream #f4efe6`, `--grey #6b665f`, `--rule #d8d1c5`, `--gold #c9a24b`, `--gold-muted #9f743b`, `--abstain #5b6472`, `--paper #ede7dc`, `--radius: 3px`; type axes `--opsz-body 15 / m 24 / l 54 / xl 88`, tracking `-0.022/-0.016/-0.008em`, leading `1.05/1.1/1.3`; motion "One curve, three durations": `--ease: cubic-bezier(0.2,0,0,1)`, `--dur-1 140ms`, `--dur-2 220ms`, `--dur-3 320ms`, `--reveal-floor: 0.55` ("Text never rests at opacity 0"); glass tiers `--glass-1/2/3` blur 10/24/36px, tint .55/.7/.78, `--glass-solid #16161a`, `--glass-cast: 0 24px 48px -12px rgb(12 12 13 / .55)`.
- Mirror in TS: `src/lib/tokens.ts:2-10` (ink/cream/grey/rule/gold/goldMuted/abstain).
- Theme: DARK ONLY. `<html data-theme="dark">` is hard-coded (`layout.tsx:44-47`); `:root[data-theme="dark"]` sets background ink, foreground cream (`globals.css:78-85`); no `prefers-color-scheme` rule exists in any CSS file. Every page wraps in `.dash` which re-declares a darker scope: `--ink #0b0b0c`, `--ink-2 #141416`, `--paper #e9e3d8`, `--line rgba(244,239,230,.12)`, `--line-strong .22`, `--muted .6`, `--muted-2 .42`, background ink, colour cream (`src/app/dashboard.css:7-22`; header comment "Claude-Legal-style, pure black & white ... 60/40: ink ground dominant, cream for type + key surfaces", `:1-5`).
- Fonts: self-hosted via `next/font/local` — Fraunces Variable → `--font-display`, Inter Variable → `--font-body`, IBM Plex Mono 400/500 → `--font-code` (`layout.tsx:6-25`). Body 15px/1.7, `tabular-nums`, Fraunces `SOFT 0, WONK 0` globally (`globals.css:99-116`). h1 `clamp(48px,6.4vw,88px)` wt 400; h2 `clamp(34px,4vw,54px)` wt 420; h3 18px/500 (`globals.css:123-153`); `.dash` overrides h1 `clamp(44px,6vw,88px)`, h2 `clamp(34px,4.4vw,58px)`, h3 `clamp(22px,2vw,27px)` (`dashboard.css:39-75`). `.dash .mono` = Plex Mono 0.86em; `.dash .dcite` = mono 0.9em, cream, 1px underline `--line-strong` (`dashboard.css:107-119`).
- Radius actually shipped (counts from grep): `dashboard.css` uses 16px ×9, 999px ×6, 8px ×6, 10px ×4, 20px ×2, 18px, 14px; `globals.css` uses `var(--radius)`=3px ×4, 6px ×2, 12px ×2, 10px; `surfaces.css` uses `var(--radius)` ×5, pills 999px ×3, 4px ×2. So the marketing chrome breaks its own "Corners ≤6px" rule (buttons `.dbtn` 8px `dashboard.css:128`; `.ddoc` 18px `:729`; `.ddoc-paper` 10px `:734`; `.dcard` 10px `:791`; `.daside` 14px `:666`; `.dres-card` 16px `:989`; `.dband` 20px `:1020`), while the product surfaces (`surfaces.css`) mostly honour 3–4px except pills.
- Shadows: 7 `box-shadow` declarations; glass `inset` hairlines + `--glass-cast`; `.dbtn-solid:hover` `0 6px 20px -8px rgba(0,0,0,.55)` (`dashboard.css:169-173`).
- Motion: `.dbtn` transitions 0.18s; `.dbtn-solid:hover::after` 0.6s shimmer sweep (`dashboard.css:153-177`); home `Reveal` 0.32s with opacity floor (`page.tsx:276-311`); demo tab swap 0.34s with `filter: blur(6px)` (`page.tsx:754-758`); reduced-motion branches exist (`dashboard.css:181, 1228`; `globals.css:355, 466, 1082, 1572`), plus `prefers-reduced-transparency` / `prefers-contrast` branches (`globals.css:272, 285`; `dashboard.css:240, 805`).
- Gold is nearly unused: focus outline `globals.css:268`, one fill `globals.css:364-365`, one border `dashboard.css:1124-1125`, and citation text `surfaces.css:160` (`.cite { color: var(--gold-muted) }`). Default focus ring is `2px solid var(--foreground)` offset 5px (`globals.css:186-189`).
- Status chips (`dashboard.css:1263-1301`): mono 11px uppercase, 5px radius, shape-coded dot (solid = met/verified, hollow = attaches, hatched = missing, dashed = abstain). Product-surface badges (`surfaces.css:164-177`): pill; verified = cream border; abstained = `--abstain` text + dashed; signal = dotted. Abstain card = cream 4% tint + 3px left rule `--muted` (`surfaces.css:180-186`); error panel = plain bordered box (`surfaces.css:230-235`).
- Brand-kit file disagrees with the site: `brand-kit/colors/placedon-colors.css:3-9` / `.json` define **Ink Navy `#0B0F1A`** and **Deep Navy `#0E1526`** as primary backgrounds, which `AGENTS.md:15` forbids ("No navy-dominant"); the site uses neutral ink `#0C0C0D`. Brand kit also ships Playfair Display (`brand-kit/fonts/PlayfairDisplay-Variable.ttf`), which the site does not load.
- Component library: none (no shadcn/Radix). Icons: hand-drawn inline SVG monoline 1.5–1.7 stroke (`page.tsx:16-110`, `surface-shell.tsx:84-116`); `lucide-react` is a dependency but not the house icon set. Motion: framer-motion. Toasts: sonner.

## A (continued). Other sources

### A2. placedon-law-backend (`bubblebee1408/placedon-law-backend`, on disk, branch `loop/bookmark-godseye-v0`)
- What: the deterministic legal engine (Python, zero third-party runtime deps per `3300/docs/RAG-INTEGRATION.md` §7) + a Word add-in (`backend/addin/`) + the static Ask prototype (`backend/web/assistant/`). Legal product ("Placedon — an India-first legal intelligence and audit platform", `backend/CLAUDE.md`; scope authority `checker/scope.py`: nine bodies of law in scope, one — Companies Act 2013 — held).
- Last commit on branch: `ea627b7` 2026-09-16 22:48 +0530, bubblebee1408, "fix: a document turn says what law it was checked against". `origin/main` last commit `56dbb91` 2026-09-13. Working tree has uncommitted edits in `web/assistant/{app.js,assistant.css,index.html,tools/accept.mjs}` (+1066/−364, the other session's rebuild) — this report quotes `HEAD` for those files unless it says "working tree".
- Frontends in this repo:
  - `web/assistant/` — static HTML/CSS/JS prototype (`index.html` 82 lines, `app.js` 742, `assistant.css` 258, `fixtures.js` + `fixtures/*.json`), no build, no framework, opened from `file://`; "This is a prototype, not a product surface. `POST /v1/ask` does not exist; the page renders fixtures built from the engine" (`web/assistant/README.md:7-8`). Acceptance runner `tools/accept.mjs` (Playwright outside the repo). Working-tree README reports "403/403 across 6 fixtures × 5 widths, plus the empty state (red-team rebuild, 2026-09-17)".
  - `addin/` — Office.js Word task pane (`taskpane.html` 82 lines with inline `<style>`, `taskpane.js` 321, `serve.py`, `manifest.xml`). Sections: "Currency check" + "Register strip" (`addin/taskpane.html:58-78`). Own tokens: `--ink #0A0A0A; --parch #F5F3EF; --slate #475569; --caution #8B4513; --rule #D8D4CC`, radius 3px, a green `#7a9a7a` for `.row.ok` (`taskpane.html:9-30`). Manifest SupportUrl `https://placedon.com/support` (`addin/manifest.xml:22`) — that route does not exist in the 3300 site (no `src/app/support`). Last add-in commit `411e77c` 2026-09-13.
  - No `ask.html` in this repo (the `ask.html` is in the business-plan repo, A3).
- HTTP API (`checker/api.py`, served by `scripts/serve_api.py`, "Binds to 127.0.0.1 by design — this serves an unauthenticated compliance API", `serve_api.py:8`, port 8020 `:25`). The 404 route list on this branch has **seven** routes (`checker/api.py:562-567`): `GET /v1/health`, `POST /v1/compliance-pack`, `POST /v1/document-check`, **`POST /v1/mca-strip`**, `GET /v1/company/{cin}/events`, `GET /v1/company/{cin}/events/{event_id}`, `GET /v1/instruments/{fragment}/affected`. `/v1/mca-strip` was added in `5a521fa` (2026-09-13) and is also on `origin/main` (`api.py:522-527` there). No `/v1/ask` and no `/v1/scope` anywhere in `*.py` (only the contract/validator `scripts/assistant_contract.py` mentions `/v1/ask`).
- Ask design docs: `docs/PLAN_13_ASSISTANT_UX.md` (1,551 lines), `docs/research/ux/DESIGN_BRIEF.md` (417), `web/assistant/contract.md` (117). None of them mentions the finalized site: `git grep -i 'fraunces|3300|claude-legal|C9A24B|brass|dark theme'` over `docs/ web/ addin/` finds only PLAN_13's "a dark theme" in "Out of v1" (`PLAN_13:1364`) and "Word's dark mode ... the design commits to the light palette" (`PLAN_13:1415-1416`).

### A3. Placedon-law-business-plan (`placedon007-prog/Placedon-law-business-plan`, PUBLIC, on disk, `main`) — read only
- Last commit `4e902b7` 2026-09-08 02:22 +0530, placedon007-prog, "Merge pull request #10 ... company-event-log-spec". Contains an older copy of the backend under `backend/` and a static `landing-page/`.
- `landing-page/` (static HTML, last touched `365479c` 2026-08-17, Saiyam Upadhyay): `index.html` (hero "The law doesn't need an opinion. It needs a citation.", `index.html:6, 762`), `ask.html`, `dashboard.html`, `auth.html`, `waitlist.html` + `waitlist_server.py`, `privacy.html`, `thankyou.html`, `404.html`, `fonts/PlayfairDisplay-Variable.ttf`. Tokens are the DESIGN_SYSTEM set: `--ink #0A0A0A; --parchment #F5F3EF; --slate #475569 ...` (`landing-page/index.html:28-40`; `ask.html:15-27`). Legal product (Companies Act), pre-dating the 3300 site.
- `landing-page/ask.html` ("Placedon — Ask"): dark Ink header with Playfair logo + search + avatar (`ask.html:36-60`), left nav (Ask · Corpus Manager · Clients · Deadlines · District / ROC Lookup · Settings · Billing), h1 "Ask a question", subtitle "Every answer traces to source, or tells you why it can't.", a client `<select>` ("ABC Pvt Ltd"...), textarea "Ask about AGM deadlines, small company thresholds, KMP requirements…", "📎 Attach PDF" and "🎙 Voice" ghost buttons, Slate "Ask" button (`ask.html:225-252`). No fetch/API calls. PLAN_13 records that this page was "condemned" for seven colours in audit R5 A17/A18 (`PLAN_13:1058-1059`).
- `docs/DESIGN_SYSTEM.md` (written 2026-08-16; last commit touching it or the landing page 2026-08-17): the source the Ask prototype cites ("tokens from BP:docs/DESIGN_SYSTEM.md §2-§4", `web/assistant/assistant.css:1` at HEAD). Rules: "Quiet authority. No gradients, no shadows, no rounded corners beyond 4px" (§1); "Max 3 colors"; "No animation > 200ms"; "if a screen has more than one accent-colored element, the design has failed"; palette Ink/Parchment/Slate/Ink-80/Ink-40/Ink-10/Slate-80/Slate-20/Caution (§2, Slate replaced a brown "Seal" on 2026-08-16); fonts Playfair Display (headings), system sans (body), JetBrains Mono, Noto Sans Devanagari (§3); type scale Display 32 / H1 24 / H2 18 / H3 14 / Body 14 / Caption 12 / Mono 13; 4px grid, 1280 max width, 240 sidebar (§4); stack "Next.js 15 + Tailwind v4 + shadcn/ui, Zustand, TanStack Table, Recharts" (§10). Pages: Dashboard, **Ask** ("The core interaction — question in, verified/abstained answer out"), Corpus Manager, Client Manager, Deadlines, ROC lookup, Settings/Billing (§6).
- `backend/checker/templates/posh_policy.html` in this public repo is a leftover of the HR/PoSH era (stale content, not a frontend).

### A4. https://www.placedon.com (live, fetched 2026-09-17 ~04:20 UTC)
- `https://placedon.com/` redirects to `https://www.placedon.com/`. Headers: `server: Vercel`, `x-vercel-id: bom1::…`, `x-nextjs-prerender: 1`, `x-vercel-cache: HIT`, `age: 303462` (saved at `tmp/live_home.headers`). Title "Placedon — the record for Indian corporate law"; `<html … data-theme="dark">`; `noindex, nofollow`. WebFetch of the same URL agrees: H1 "Every answer carries its evidence."; nav Product · How it works · Security · Pricing · Request a pilot; "Legal (Companies Act) product"; "HR/Hiring Mentions: None found"; "No mention of an 'Ask' feature or chat assistant interface".
- **It is the legal product only.** There is no HR/hiring content, and no violet: `#6922F5`/"violet" is absent from both live CSS bundles (`/_next/static/immutable/chunks/1-x_aolcpc90h.css`, `2iv0yyaeqacq7.css`). The live CSS tokens are exactly the 3300 tokens (`--ink:#0c0c0d`, `--cream:#f4efe6`, `--gold:#c9a24b`, `--gold-muted:#9f743b`, `--abstain:#5b6472`, `--paper:#ede7dc`, `.dash --ink:#0b0b0c`, `--paper:#e9e3d8`), and the page preloads Fraunces, Inter and IBM Plex Mono. The memory note (placedon.com = `placedon-web`, "Frost Luxe", violet `#6922F5`, hiring) is **stale**, and `~/PlacedOn/placedon-web` no longer exists on disk. Which Vercel *project name* owns the domain is UNVERIFIED: the repo's `package.json` name is `placedon-web`, its README names `placedon-claude-legal-3300.vercel.app`, and that URL serves the same H1.
- **The live build is older than repo HEAD.** Live H1 "Every answer carries its evidence." was replaced by "The evidence-first workspace for Indian corporate law." in `c0dd31d` (2026-09-15). The live footer has no "Connect" column (added `f2b5167`, 2026-09-14), and the live copy still has the em-dashes removed in `3d0f855` (2026-09-15). `age: 303462` s puts the cached render at ≈2026-09-13 16:02 UTC (21:32 IST), just after `2c2cdb3` (21:21 IST) and before `4bf6bbf` (22:17 IST). INFERRED: live ≈ `2c2cdb3`, and the six later commits (`4bf6bbf` … `939f40f`) are not deployed. Why is UNVERIFIED (README gotcha 1 describes Vercel silently blocking deploys).
- Pages fetched (all HTTP 200): `/`, `/product`, `/how-it-works`, `/security`, `/pricing`, `/about`, `/faq`, `/product/compliance-pack`, `/waitlist`, plus `/product/document-check`. **`/ask` → 404. `/support` → 404**, although it is the add-in manifest's SupportUrl.
  - `/product`: "Product concept · Pre-launch — The answer. Its authority. Its limits." The six concept sections include "The company-standing check — A company-standing view is planned."
  - `/how-it-works`: H1 "Ask. Verify. Cite. Or abstain."; "Three classes. Different kinds of evidence."; "An unresolved record is an abstention."
  - `/product/compliance-pack` (mock data): stamp "Jurisdiction India · Companies Act, 2013 · As of 2026-09-01 · Law as of 2026-09-01 · Generated 11 Sept 2026, 05:30 IST". The abstained row is `s.96(1)`, blocked by `G.S.R. 880(E)`, "not yet settled in the corpus". Provenance: "Corpus companies-act-2013@2026-09-01 · Benchmark bench-2026.09 · Checker f2ebcb3".
  - `/security`, `/pricing`, `/about`: pre-launch framing, no certifications, no tariff, "does not claim live customers, validated accuracy results, or complete statutory coverage".
  - `/faq` questions include "Can I use Placedon for a live compliance question now?", "How is Placedon intended to differ from ChatGPT?" and "…from Harvey?".
  - `/waitlist`: pilot / register-interest form with a role list (Advocate … Cost Accountant (CMA)).

## C. The design system in use vs the Ask prototype's tokens

Ask side: `backend/web/assistant/assistant.css` `:root` (HEAD and working tree), `PLAN_13 §14/§17`, and `bizplan/docs/DESIGN_SYSTEM.md` (its declared source). Frontend side: `3300/src/app/globals.css`, `3300/src/app/dashboard.css`, `3300/src/components/surfaces/surfaces.css`, `3300/AGENTS.md`, and the live CSS, which matches them.

Root cause: **the Ask prototype was designed against the business-plan design system of 2026-08-16. The finalized site (built 2026-09-11 to 09-15) uses a different, later system.** No backend Ask doc mentions the finalized site (A2). `grep -i '475569|f5f3ef|8b4513|playfair'` over `3300/src` returns nothing.

| # | Aspect | Ask prototype | Finalized frontend (3300 + live) | Severity |
|---|---|---|---|---|
| C1 | Ground / theme | Light: `--parchment #F5F3EF` page, `--white #FFFFFF` cards (`assistant.css:6-7, 23, 135`). "A dark theme" is out of v1 (`PLAN_13:1364`); "the design commits to the light palette" (`PLAN_13:1415`) | **Dark only.** `data-theme="dark"` is hard-coded (`layout.tsx:46`); `.dash` has ink ground `#0b0b0c` and cream text (`dashboard.css:7-18`); no `prefers-color-scheme` rule anywhere. The only light surface is the Compliance Note paper `.ddoc-paper #fbf8f2` inside `.ddoc #e9e3d8` (`dashboard.css:727-738`) | **High** |
| C2 | Accent | Slate `#475569` on the web Ask button, current tab and focus (`assistant.css:3, 8, 121`; `PLAN_13 §14`) | Brass Gold `#C9A24B`, ≤10% of a screen, one element per view (`AGENTS.md:13`). In practice gold appears only on a focus ring, one fill and one border (`globals.css:268, 364`; `dashboard.css:1124`). The primary button is cream-solid on ink (`dashboard.css:142-151`). No Slate anywhere. Slate on ink is 2.60:1, which fails even the 3:1 non-text minimum | **High** |
| C3 | Colour of the "not confirmed / abstain" state | Caution `#8B4513` left rule and label, "the only hue on the page" (`PLAN_13 §6 NotConfirmedItem`; `assistant.css:9`) | Cool Grey `#5B6472` is "reserved only for the 'abstained / unknown' state", and there is "no second accent colour" (`AGENTS.md:14-15`). It is "a surface/border token only — never text on ink" (`globals.css:243-244`). The abstain card is a cream 4% tint with a 3px `--muted` left rule (`surfaces.css:180-186`). Caution on ink is 2.77:1, so it cannot move onto the dark page as text | **High** |
| C4 | Fonts | System sans body (`--sans: -apple-system, "Helvetica Neue"…`); system text serif `--serif: "Iowan Old Style", Palatino…` for title and state word; `--mono: ui-monospace, Menlo` (`assistant.css:13-15`). PLAN_13 names Playfair Display (≥22px) and JetBrains Mono (`PLAN_13 §14`) | Self-hosted Inter Variable (body), Fraunces Variable (display; opsz 9–144, so it also covers text sizes) and IBM Plex Mono 400/500 (`layout.tsx:6-25`). "IBM Plex Mono (every section reference, figure, instrument, and date)" (`AGENTS.md:16-18`). Playfair ships in the brand kit but the site never loads it | **High** |
| C5 | Type scale | Body 14/1.55; title 28; state word 24; question 17; group labels 13 uppercase; 12px minimum (`assistant.css:24, 97, 141, 145, 153`; `PLAN_13 §16`) | Body 15/1.7 (`globals.css:104-105`); `.dash h1` 44–88px, h3 22–27px (`dashboard.css:46-75`); surface row h3 17px (`surfaces.css:127`); **11px** text in provenance `dt` (`surfaces.css:300`) and chips (`dashboard.css:1269`) | Medium |
| C6 | Secondary text | Ink-80 `#4A4A4A` (8.0:1 on Parchment) | `--muted` cream@0.60 = 6.51:1; **`--muted-2` cream@0.42 = 3.70:1**, used for 12–13px text (`.surface-concept`, `.surface-stamp`, `.abstain-label`, `.evt-dates`: `surfaces.css:24, 65, 203, 264`), which fails AA 4.5:1. `.cb-abstained { color: var(--abstain) }` (`surfaces.css:176`) is 3.29:1 on ink, which fails AA and breaks the file's own "never text on ink" rule | Medium: Ask's contrast checks would fail on reused frontend classes |
| C7 | Radius | 4px (2px on status/band) (`assistant.css:101, 126, 135, 137`) | `--radius: 3px` on product surfaces; **999px pills** for the sub-nav, class badge and row state (`surfaces.css:43, 135, 171`); 4px cites; marketing chrome 8/10/14/16/18/20px (`dashboard.css:128, 666, 729, 734, 791, 989, 1020`), which breaks its own "Corners ≤6px" (`AGENTS.md:44`) | Low–Medium |
| C8 | Shadow / glass | None. "Separation is by border and panel header, never by fill or shadow" (`PLAN_13 §5`) | "Shadows minimal" (`AGENTS.md:44`). Glass tiers with inset and cast shadows (`globals.css:207-242`); `.dcard` is glass-solid with inset shadows (`dashboard.css:789-797`). The redesign thesis puts "citation chip, provenance card, sticky rail, abstain panel, command bar" on glass (redesign spec §2). **But the product surfaces (`surfaces.css`) are flat bordered boxes with no glass** | Medium (decision) |
| C9 | Motion | ≤200ms; only a 120ms opacity swap; hover/focus instant; `--fast: 120ms` (`assistant.css:16`; `PLAN_13 §17`). Acceptance check 10 fails any motion over 200ms (`web/assistant/README.md:66`) | ≤250ms apart from one hero moment (`AGENTS.md:44-45`); `--ease cubic-bezier(0.2,0,0,1)`, `--dur-1 140 / --dur-2 220 / --dur-3 320ms` (`globals.css:46-49`). **`.surface-nav a` uses 220ms** (`surfaces.css:44`); `.dbtn-solid` uses 220ms plus a **0.6s shimmer** (`dashboard.css:147-177`); the demo swap is 0.34s with blur (`page.tsx:758`); `BrandMark` hover is 0.22s (`site-chrome.tsx:24`) | Medium: reusing `SiteNav`/`SurfaceShell` as-is fails Ask check 10 |
| C10 | Hover / focus | No hover motion; focus 2px Slate (DS §9); working tree sets `accent-color: var(--ink)` (`assistant.css:17`) | Designed hover (lift, shimmer, arrow nudge); `:focus-visible { outline: 2px solid var(--foreground); outline-offset: 5px }` in cream (`globals.css:186-189`) | Low |
| C11 | Date format | Client-formatted **DD-Mon-YYYY** (`app.js:21, 83-87`; `PLAN_13` header) | ISO `YYYY-MM-DD` shown raw in mono (`Stamp`, `surface-shell.tsx:159`; demo `2026-03-31`). Timestamps via `formatIST` in `en-IN` render as "**11 Sept 2026**, 05:30 IST" (live) (`format.ts:10-26`) | Medium (decision) |
| C12 | Numbers | User facts are rendered "exactly as `facts.*.value` arrives (`120000000`…) no grouping, no ₹… and **not mono**"; figure `amount` is a server string ("₹10 crore") (`PLAN_13 §6 SuppliedFacts`) | "IBM Plex Mono (every … figure `₹10,00,00,000`)" (`AGENTS.md:17`); `formatIndianRupees` / `formatIndianNumber` apply lakh/crore grouping (`format.ts:28-36`); README calls it an India-first rule (`README.md:117-118`) | Medium (decision) |
| C13 | State vocabulary | "Answered / Partly answered / Not held"; CONFIRMED / NOT CONFIRMED / SUPERSEDED; the word "Abstain" appears **0 times** in `app.js`/`index.html` (working tree) | The brand is built on the word: "Ask. Verify. Cite. Or abstain." (live `/how-it-works` H1). Class labels "Verified fact / Determined / Signal, not asserted / Abstained" (`surface-shell.tsx:81-117`); chips "Verified / Attaches / Abstained" (`page.tsx:684-688`) | **High** (voice) |
| C14 | Non-colour state cue | Filled / half / hollow square glyphs, "reserved for states" (`PLAN_13 §2 #3, §16`) | Monoline SVG per class: check, two bars, pulse, circle-minus (`surface-shell.tsx:84-116`); chip dot shapes solid / hollow / hatched / dashed (`dashboard.css:1277-1301`); badge border solid / dashed / dotted (`surfaces.css:175-177`) | Medium |
| C15 | Chrome | Own `.bar` (serif wordmark and pane tabs "Currency check · Register strip · Ask", shown on the web too); "This session" rail; Sources aside (`index.html:12-78`) | `SiteNav` (sticky, 68px, logo image, Product / How it works / Security / Pricing, "Request a pilot") and `SiteFooter` on every route (`site-chrome.tsx:93-140`). Product surfaces use `SurfaceShell`: eyebrow, 44–88px h1, intro, concept note, 4-pill sub-nav (`surface-shell.tsx:27-73`) | **High** (web) |
| C16 | Layout | Rail 232 · measure 680 · panel 384; one column below 820px (`assistant.css:11, 51-60`) | `.dash-container` = `min(1200px, 100% − 80px)`, and `100% − 40px` below 900px (`dashboard.css:31, 1166-1168`). The home demo puts the note on the left and the question as a "Prompt" card on the right (`.ddemo-stage 1.55fr 1fr`, `dashboard.css:721-726`) | Medium |
| C17 | Token names | `--ink #0A0A0A`, `--parchment`, `--white`, `--slate`, `--caution` at `:root` | `--ink` is `#0c0c0d` in `:root` and `#0b0b0c` in `.dash`; `--paper` is `#ede7dc` / `#e9e3d8`; cream is "the 'white'" (`AGENTS.md:12-13`). **Importing `assistant.css` into the Next app would silently redefine `--ink` at `:root`.** That is the same trap the redesign spec warns about for `astra.css` (§3.4) | **High** (engineering) |
| C18 | Italics | DS: "Never italicize except input placeholders" | `.ddoc-meta { font-style: italic }` (`dashboard.css:752`) | Low |
| C19 | Stack | Static HTML + vanilla JS from `file://`; Playwright runner outside the repo | Next.js 16 App Router, React 19, TS strict, zod 4, framer-motion; server-only engine; "No hard-coded hex in components" (`AGENTS.md:20`) | High (port needed) |
| C20 | Business-plan DS vs 3300 | DS §10 specifies "Next.js 15 + Tailwind v4 + shadcn/ui, Zustand, TanStack Table, Recharts" | None of shadcn, Zustand, TanStack or Recharts is in `3300/package.json` | Info |

What already agrees: a serif/sans/mono three-face system; mono for statute references; no colour-only status; 44px targets (`AGENTS.md:48-49`; `assistant.css:12`); reduced-motion honoured; no confidence numbers; "never render a figure the backend did not supply"; a transport error visually distinct from an abstention (`EngineErrorPanel` ≈ Ask `ServiceError`); a cream "paper" document as the answer artefact (Compliance Note ≈ Ask turn card).

## D. How the Ask section should plug into the finalized frontend

### D1. Where it would live
- **Web: `3300/src/app/product/ask/page.tsx`, as a fifth product surface.** Add `{ href: "/product/ask", label: "Ask" }` to `SURFACES` (`surface-shell.tsx:20-25`). All four existing product views live under `/product/*`, share `SurfaceShell`, carry the "Product concept, shown on fixed sample data…" note, and get per-route metadata via `pageMetadata()` (`src/app/product/page.tsx:5-7`). PLAN_13 asks for a top-level `/ask` (`PLAN_13 §3`); on the finalized site `/ask` is a 404 today and has no sibling pages, so the `/product/ask` choice is recommended but is a **founder decision**. Adding "Ask" to the main nav (`site-chrome.tsx:31-36`, currently Product · How it works · Security · Pricing) is a second decision. The nav carries no product-surface links today.
- **Word pane: stays in `backend/addin/`.** It is a static Office.js pane served from `https://localhost:3000/taskpane.html` (`addin/manifest.xml:24, 38`), not part of the Next app. PLAN_13 makes the pane the v1 deliverable and the web page secondary (`PLAN_13 §3`: "The pane is the deliverable; the 1440 frames are illustrative"). The finalized site sells Word as "Placedon for Word — Draft board resolutions, notices… inside Word" (`3300/src/app/page.tsx` tools, live). The pane is read-only (`addin/README.md:6-13`), so the site's description of the pane must change or the pane's scope must (see E).
- So there are two hosts with two constraints. The web page must adopt the 3300 dark system. The pane may stay light (Word's canvas is light, and PLAN_13 §23 item 8 flags Word dark mode as untested), but it should use the 3300 palette and faces, not the business-plan ones (F2).

### D2. What the web Ask must reuse from 3300
- **Shell:** `SurfaceShell` → `SiteNav` / `SiteFooter` / concept note / sub-nav (`surface-shell.tsx:27-73`) in place of the prototype's `.bar` wordmark and pane tab strip (`web/assistant/index.html:12-19`). Two caveats. `SurfaceShell` nests a second `<main id="main-content">` inside the layout's (`surface-shell.tsx:43` vs `layout.tsx:54`), and Ask's one-`h1`/landmark checks would catch it. Its sub-nav and the nav button animate at 220ms plus a 0.6s shimmer (`surfaces.css:44`; `dashboard.css:147-177`), which fails Ask acceptance check 10 (≤200ms) (C9).
- **Tokens:** the `.dash` scope (`--ink`, `--ink-2`, `--cream`, `--paper`, `--line`, `--line-strong`, `--muted`); global `--abstain`, `--gold-muted`, `--radius`, `--ease`, `--dur-1`; fonts `var(--font-display)` / `var(--font-body)` / `var(--font-code)` (`layout.tsx:6-25`). `assistant.css` must not be imported as-is (C17).
- **Components** (all in `src/components/surfaces/surface-shell.tsx` unless noted):
  - `ClassBadge` for the state or class chip, `Citation` for every `ref`/`cite`/`provision`, `Stamp` for the turn stamp (with the wording fix in F4).
  - `EngineErrorPanel` for Ask's `ServiceError`. The same concept already exists: "not a legal finding. No answer, and no abstention, is implied."
  - `AbstentionCard` only for obligation-row abstentions. `ProvenanceFooter` for `evidence_pack` / `law_version`.
  - From `surfaces.css`: `.ob-row` / `.ob-state` for `rows[]`, `.doc-super` / `.doc-thennow` for `superseded[]`, `.surface-notes` for `what_it_is_not[]`.
  - The home page's **Compliance Note** paper (`.ddoc` / `.ddoc-paper` / `.ddoc-h` / `.ddoc-note`, `dashboard.css:727-780`) as the answer body, and the `.dcard` "Prompt" card (`dashboard.css:789-823`) for the user's question. The redesign spec names the Compliance Note as the site's anchor artefact.
  - Status chips `.chip` (`dashboard.css:1263-1301`) for CONFIRMED / NOT CONFIRMED.
- **Engine client:**
  - Extend `EngineProvider` (`provider.ts:26-48`) with `ask(req)` and `scope()`. Add `ENGINE_ROUTES.ask` / `.scope` (`types.ts:7-14`), a zod `askResponseSchema` discriminated on `state`, and `EngineResult<AskResponse>`.
  - Build a Mock provider from `backend/web/assistant/fixtures/*.json` (engine-built, so admissible as mock data under `AGENTS.md:51-53`).
  - Add a same-origin route handler `src/app/api/ask/route.ts` for submit, following `src/app/api/waitlist/route.ts:11-38` (origin check, JSON check, rate limit), with a client composer posting to it. That split is what the redesign spec prescribes for interaction (§4).
  - **This requires lifting a written ban** (`types.ts:5`; `AGENTS.md:58`; `RAG-INTEGRATION.md:60, 327`). Until `/v1/ask` exists, the page must be concept-only: server-rendered fixtures, with Ask sending nothing. That matches the prototype's current behaviour ("Ask sends nothing: it says so in a status line", working-tree `README.md:12-13`).
- **Tests:** port the prototype's hooks (`data-state`, `data-figure`, `data-citation`, `data-law-version`, `data-chrome`, `data-f` …, working-tree `README.md:73-79`) into the TSX components, and run `tools/accept.mjs` against `localhost:3300/product/ask` instead of `file://`.

### D3. API it would call
- `POST /v1/ask` and `GET /v1/scope`. **Neither exists in the backend** (no match in `*.py`; `checker/api.py:562-567` lists seven routes). `/v1/scope` is a "blocking Phase C deliverable" (`PLAN_13 §4.1`).
- The Next server calls the engine at `PLACEDON_API_ORIGIN` (https, or http on loopback) with an optional bearer `PLACEDON_API_TOKEN` (`provider.ts:63-73`; `http.ts:31-46`). The engine is loopback-only and unauthenticated (`scripts/serve_api.py:8`), so a hosted deployment needs TLS and auth first; that is not specific to Ask. The 8 s client timeout (`http.ts:30`) has not been checked against document-path latency (UNVERIFIED).

### D4. Does `placedon.ask/0` fit what the frontend expects?
**Partly.** It fits at the data level, where the producers are shared. It does not fit the frontend's classification model, and it contradicts the frontend's written F9 expectation.

| Contract element (`web/assistant/contract.md`) | Frontend expectation (3300) | Fit |
|---|---|---|
| `rows[]` from `api._row_json` (§3) | `obligationRowSchema` from the same serializer (`types.ts:171-180`) | ✓ same shape |
| `superseded[]` from `api.document_check` (§4) | `supersededEntrySchema` (`types.ts:246-257`) | ✓ |
| `not_confirmed[{kind:"cannot_verify",…}]` | `cannotVerifyEntrySchema`, two shapes (DRIFT 2, `types.ts:259-289`) | ~ wrapped differently; must keep the two-shape discrimination |
| `what_it_is_not[]` | same field name on pack / doc-check (`types.ts:227, 312`) | ✓ |
| `uses_model: bool` (§2) | `no_model: z.literal(true)` on five routes (`types.ts:86, 313, 365, 374, 396`) | ✗ inverted name, one must be chosen |
| `law_version {basis, point_in_time_verified, corpus_fetched, statement}` + `evidence_pack` | `provenance {benchmark_version, corpus_version, checker_commit, working_tree_dirty, law_as_of}` rendered as Corpus / Benchmark / Checker (`types.ts:183-192`; live pack page) | ✗ Ask carries no corpus / benchmark / checker stamp |
| Turn `state ∈ answered / partial / out_of_scope`; items carry `evidence_state` (e.g. `CORROBORATED`) | "Output classes `verified_fact / deterministic_conclusion / predictive_signal` + `abstained`" on every rendered answer (`AGENTS.md:52-53`; `types.ts:55-73`) | ✗ no mapping defined; no frontend state for **Not held** |
| `not_confirmed[]` items (fixture `partial_s173_s16`: keys `detail, kind` only) | `Abstention` needs `obligation_id, provision, basis, missing_facts, blocked_by` (`types.ts:431-440`) | ✗ cannot be built; needs its own type and card |
| Empty-`confirmed` `partial` = the abstention (§6: `INSUFFICIENT_EVIDENCE` → `partial`) | F9 "abstains as `INSUFFICIENT_EVIDENCE` — 'the law itself is not here'… visibly different from an error and from `DOES_NOT_APPLY`" (`ASTRA_MASTER_PROMPT.md:416-417`; `RAG-INTEGRATION.md:195-197`) | ✗ naming conflict: "Partly answered / Confirmed: none" vs "Abstained" |
| No `claims[]`; `confidence` refused at any depth (§1.5, §7) | "when it lands it will follow the model-adapter claim schema in §5" (`decision` + `claims[]` with `confidence`) (`RAG-INTEGRATION.md:118-120, 327`) | ✗ the frontend docs describe a different F9 shape |
| `BUDGET_EXHAUSTED`, 5xx, timeout → not a state (§6) | `EngineError` kinds `server_error / timeout / transport_error`; "never render as an abstention" (`errors.ts:11-17`) | ✓ same principle |
| `as_of` ISO; client shows DD-Mon-YYYY | ISO shown raw in mono; IST timestamps via `formatIST` | ~ format decision (C11) |
| `POST /v1/ask`, `GET /v1/scope` | "exactly SIX routes… `/v1/ask` DOES NOT EXIST — never add" (`AGENTS.md:54-59`; `types.ts:5`) | ✗ needs a founder decision; the six-route claim is already stale (E1) |

## E. Contradictions between the repos
E1. **Route count.** 3300 says "exactly SIX routes" (`AGENTS.md:54`; `README.md:55`; `types.ts:4`, verified at `f2ebcb3`, 2026-09-10). The backend has **seven**: `POST /v1/mca-strip` was added in `5a521fa` (2026-09-13), is on `origin/main`, and powers the add-in's Register strip (`checker/api.py:407, 550, 562-567`; `addin/taskpane.html:62-77`).

E2. **The F9 / Ask shape.** The 3300 docs say F9 "will follow the model-adapter claim schema" (`RAG-INTEGRATION.md:327`) and "do not present a working chatbot" (`:60`). The backend now has a full Ask spec plus the `placedon.ask/0` contract, which has no claims and refuses confidence (`contract.md:25, 96`). The frontend's copy of the contract is behind the backend's decision.

E3. **Confidence.** Backend `CLAUDE.md:52`: "Every legal finding carries source, date, rule ID, reasoning, and confidence." `contract.md:25`: "No confidence, anywhere." 3300 `AGENTS.md:35-36` forbids "confidence percentages". This is an internal backend contradiction that the frontend rule sides against.

E4. **Small-company threshold, three stories.**
- Home demo (HEAD and live): "The size limit was changed by a government notification, G.S.R. 700(E), that is not in the record yet… stays unconfirmed" (`3300/src/app/page.tsx:470-476`).
- Compliance-pack mock (HEAD and live): "G.S.R. 880(E) — not yet settled in the corpus… operative date is pending Gazette attestation" (`3300/src/lib/engine/mock.ts:29, 64-66, 124-131`).
- Backend Ask fixture built 2026-09-15: *answers* it from G.S.R. 880(E) with `₹10 crore` / `₹100 crore`, `effective_from 2025-12-01`, `evidence_state CORROBORATED` (`web/assistant/fixtures/answered_small_company.json`).

So the two frontend surfaces name different instruments for the same limit, and both say "unsettled" while the engine now serves it. Which instrument set which limit was not checked here (UNVERIFIED); the mock and demo copy need re-deriving from the engine.

E5. **"Law as of" vs "current consolidation".** The 3300 `Stamp` prints "Law as of 2026-09-01" (`surface-shell.tsx:161-165`; live). The backend says the corpus is "the CURRENT CONSOLIDATION… as ingested (2026-08-18). It is NOT a point-in-time version" (`answered_small_company.json` `law_version.statement`), and PLAN_13 §9 mandates "Text as ingested 18-Aug-2026. Current consolidation, not a point-in-time version." The mock's `corpus companies-act-2013@2026-09-01` also differs from the engine's `corpus_fetched 2026-08-18`.

E6. **Scope.**
- Backend: nine bodies "in scope", one held. `checker/scope.py` `BODIES`: CA2013 IN_CORPUS; LLP2008, SEBI_OTHER, FEMA1999, IBC2016, COMP2002, STAMP, **DPDP2023** DECLARED; SEBI_LODR CURRENT_ONLY; POSH and AI_LAW OUT_OF_SCOPE. The Ask shows "1 of 9 in-scope bodies of law are held".
- 3300 FAQ: "Tax, employment law, securities regulation, and case-law research are not covered" (`faq.ts:10-12`).
- Business-plan DS: "DPDP is out of scope" (`DESIGN_SYSTEM.md:3`).
- The user's memory index: "Companies Act 2013 only, DPDP out".

The public framing ("not covered") and the engine framing ("in scope, not held") differ.

E7. **Home-page claims with no backend implementation found** (HEAD and live, `3300/src/app/page.tsx:315-340, 551-580`):
- "Connected to your filings — built to read from your MCA21 filings, board minutes, and statutory registers." The add-in says "No register is wired — paste one" (`addin/taskpane.html:66-67`). Backend rules forbid bypassing the MCA WAF and obtaining private minutes (`backend/CLAUDE.md`). The redesign spec itself asked to "remove the present-tense claim of live MCA21 integration" (§5); the wording is softened but still there.
- "Placedon for Word — Draft board resolutions, notices, and Board's-report extracts inside Word." The add-in "never modifies text or formatting" (`addin/README.md:6-13`). Drafting has one template (`draft_agm_notice`, `RAG-INTEGRATION.md` §6).
- "Use Placedon… in email, and alongside the secretarial software." No email or secretarial-software integration found in backend `*.py` (grep for imaplib/smtplib/outlook: none). UNVERIFIED beyond that grep.
- "Plugins — Practice packs… AOC-4, MGT-7, DIR-3 KYC." AOC-4 / MGT-7 appear in `checker/` only as filing-date evidence (e.g. `aoc4_filed_on`, `types.ts:153`). No plugin or pack system found.
- "MCP for statutory data — … through the open Model Context Protocol." No MCP file or server in the backend (`git ls-files | grep -i mcp`: none).
- "Platform — Integrate… through the API." The API is loopback-only and unauthenticated (`serve_api.py:8`).
- "an audit trail on every answer" vs the add-in's "writes nothing durable" (`addin/README.md:16-17`). INFERRED tension, not a proven contradiction.
- HEAD (not yet live) hero: "Research · Compliance · Monitoring · Drafting… into one place" (`page.tsx:625-635`). Research (F9) has no endpoint; law-change alerts are "not built" (`ASTRA_MASTER_PROMPT.md:118`).

E8. **"Company standing".** `/product` says "A company-standing view is planned" (`content/product.ts:67-69`; live). `ASTRA_MASTER_PROMPT.md:127-129` lists a "'verified company card'" under "Not in the plan — do not add", and `/standing` "DOES NOT EXIST". Whether "company standing" is the barred card is INFERRED.

E9. **Deployment drift.** The live site is an older build than `main`: six commits (2026-09-13 → 09-15) are not live (A4).

E10. **Stale design docs.**
- 3300 `AGENTS.md:3` says "Next.js 15… + shadcn/ui"; actual is Next 16.3.4 with no shadcn.
- The 3300 brand kit's navy backgrounds (`brand-kit/colors/placedon-colors.css:3-4`) conflict with `AGENTS.md:15` "No navy-dominant".
- The business-plan DS (2026-08-16) is superseded in practice by 3300, but the Ask prototype still cites it (`assistant.css:1`).
- `3300/tests/contracts.mjs:147` still tests the retired `standing()` client.

E11. **Stale HR-era and other content.**
- The memory note that placedon.com is the violet "Frost Luxe" hiring site is wrong today (A4).
- The public business-plan repo still ships `backend/checker/templates/posh_policy.html`.
- The public business-plan repo's `landing-page/ask.html` still shows a client picker, "📎 Attach PDF" and "🎙 Voice" (`ask.html:239-249`), all cut by PLAN_13 §3 and §21. It uses emoji, which 3300 bans ("emoji section markers", `AGENTS.md:41`).
- 3300 `docs/RAG-INTEGRATION.md:11-13` notes that older memory/docs still describe PoSH/HR.

E12. **Dead links.** The add-in manifest's SupportUrl `https://placedon.com/support` returns 404 (`addin/manifest.xml:22`). PLAN_13's web route `/ask` returns 404 (expected; not built).

E13. **Where the Ask lives in the pane vs how the site describes Word.** PLAN_13 adds Ask as the third pane tab ("Currency check · Register strip · Ask"). The site describes the Word product as drafting (E7). Neither repo describes the other's version.

## F. Recommended changes to the Ask design (ranked)

Contrast figures were computed with the WCAG relative-luminance formula (script run 2026-09-17): cream@0.60 on `#0b0b0c` = 6.51:1; cream@0.42 = 3.70:1 (0.49 is the lowest alpha that reaches 4.5:1); `#5B6472` on ink = 3.29:1 and on paper `#fbf8f2` = 5.64:1; `#8B4513` on ink = 2.77:1 and on paper = 6.70:1; `#475569` on ink = 2.60:1; `#9F743B` on ink = 4.72:1 and on paper = **3.93:1**; `#171512` on paper = 17.19:1; `#6a6459` on paper = 5.53:1.

**F1. Re-base the Ask tokens on the finalized 3300 system, not the business-plan design system of 2026-08-16.**
- Touches `web/assistant/assistant.css:1-18` (`:root` and its source comment "tokens from BP:docs/DESIGN_SYSTEM.md") and `PLAN_13 §14` ("Reused unchanged from DESIGN_SYSTEM §2–§4").
- Target: `ink #0C0C0D`, `cream #F4EFE6`, `paper #EDE7DC` / `#E9E3D8`, rule `#D8D1C5`, `gold-muted #9F743B`, `abstain #5B6472`, `--radius 3px`, `--ease cubic-bezier(0.2,0,0,1)`, `--dur-1 140ms`.
- In the Next app, reference the site variables rather than redeclaring `--ink` at `:root`.
- Evidence: C1–C4, C17; `3300/AGENTS.md:12-20` ("Everything reads from central design tokens"); live CSS matches 3300 (A4). **Founder confirmation needed** that 3300 is the system of record, as "we have finalized" implies.

**F2. On the web, the page is dark and the answer sits on the Compliance Note "paper".**
- Touches `PLAN_13 §5` (layout zones), `§7.2 / §7.5 / §7.10` (web wireframes) and `§14`; `assistant.css` `body` (`:22-25`), `.turn` (`:135`), `.sources`, `.rail`.
- Chrome (nav, rail, sources panel, composer shell) uses the `.dash` ink ground. Each turn card uses `.ddoc-paper`: `#fbf8f2`, ink `#171512`, meta `#6a6459` (`dashboard.css:727-780`).
- All of PLAN_13's contrast work stays valid inside the card (light on light), and the site's anchor artefact becomes the Ask answer (redesign spec §2).
- Keep every status hue on paper, never on ink (Caution 2.77:1 and abstain 3.29:1 on ink both fail).
- Keep citations on the paper **ink with an underline, as `.ddoc-p .dcite` does** (`dashboard.css:769-773`), not gold-muted (3.93:1 on paper).
- The Word pane stays light (PLAN_13 §23 item 8) but uses cream/paper and the F1 tokens.

**F3. Vocabulary: reconcile "Partly answered / Not held" with the site's "abstain" (founder decision).**
- Touches `PLAN_13 §2 #1`, `§6 StateHeading / NotConfirmedItem / ConfirmedItem`, `§13` (exact copy), `§16`; `contract.md §6` (the `INSUFFICIENT_EVIDENCE → partial` with empty `confirmed` row, audit U2).
- The site's promise is "Ask. Verify. Cite. Or abstain." (live `/how-it-works` H1), its class label is "Abstained" (`surface-shell.tsx:108-117`), and the F9 docs say F9 "abstains as `INSUFFICIENT_EVIDENCE`" (`ASTRA_MASTER_PROMPT.md:416`). The Ask never uses the word (C13).
- Minimum: map the item level onto the site's classes. `rows[]` → `ClassBadge kind="deterministic_conclusion"` "Determined" (`types.ts:71-73`); `not_confirmed[]` → `ClassBadge kind="abstained"`. Add a label decision for the empty-`confirmed` turn, the state PLAN_13 expects to dominate (`§7.12`). "Partly answered" over a turn where nothing was confirmed reads as an overclaim against 3300's honesty rules.

**F4. Colour of NOT CONFIRMED: use the abstain token and shape, not Caution brown.**
- Touches `PLAN_13 §6 NotConfirmedItem`, `§14` (colour count, "Caution is a semantic status hue, not an accent"); `assistant.css` `--caution` (`:9`) and `.item.caution`.
- `AGENTS.md:14-15` reserves `#5B6472` for abstention and bans a second accent; `globals.css:243-244` makes it a surface/border token. On paper it is 5.64:1, so it works as a rule and label there.
- **Collision to resolve:** Ask uses a *dashed* rule to mean "section text as ingested" (`PLAN_13 §14 --rule-text-style: dashed`), while the site uses *dashed* to mean abstained (`surfaces.css:176`; `.chip-abstain`, `dashboard.css:1291-1298`). Keep dashed for abstention (the site's meaning) and give text-basis another marker, such as a double or dotted rule, or a mono "Text as ingested" label with a thin solid rule. **Founder or design decision.**

**F5. Placement and shell: web Ask is a fifth product surface inside `SurfaceShell`, concept-only until `/v1/ask` exists.**
- Touches `PLAN_13 §3` (web row "`/ask`, one screen"), `§5`, `§12` (rail); `web/assistant/index.html:12-19` (the `.bar` pane tab strip is shown on the web too); `web/assistant/README.md`.
- Route: `/product/ask`, with an "Ask" entry in `SURFACES`. Chrome: `SiteNav` / `SiteFooter` plus the "Product concept, shown on fixed sample data" note.
- Keep "Ask sends nothing" until the backend route ships.
- Evidence: D1–D2; the written bans in `3300/types.ts:5`, `AGENTS.md:58`, `RAG-INTEGRATION.md:60, 327`. **Founder decision:** lift the ban (and say so in 3300's AGENTS.md) or keep Ask concept-only.
- Also fix, or avoid inheriting, the nested `<main id="main-content">` (`surface-shell.tsx:43`).

**F6. Contract changes so the frontend can render `placedon.ask/0` without inventing anything.**
- Touches `web/assistant/contract.md §2–§7` and `scripts/assistant_contract.py`.
- (a) Add the provenance stamp the site already shows (`corpus_version`, `benchmark_version`, `checker_commit`; `types.ts:183-192`).
- (b) Settle `uses_model` vs the site's `no_model` (`types.ts:86` etc.).
- (c) Define the item → product-class mapping, and state that `CORROBORATED` is not rendered as "Verified fact": `SERVABLE = (CORROBORATED, VERIFIED)`, and "Nothing reaches VERIFIED without… human review" (`RAG-INTEGRATION.md` §7).
- (d) Give `not_confirmed[]` items a `ref` / `provision` where one exists, so the `Citation` chip can render (fixture items carry only `kind, detail`).
- (e) Add a display class for `out_of_scope` ("Not held"), which the site's taxonomy lacks.
- (f) Tell the 3300 side that F9 will **not** follow the model-adapter `claims[]` schema (`RAG-INTEGRATION.md:327` is stale).

**F7. Fonts: Fraunces, Inter and IBM Plex Mono; drop Iowan/Palatino, Playfair and JetBrains.**
- Touches `assistant.css:13-15`, `.wordmark` (`:41`), `.title` (`:97`), the state heading (`:145`); `PLAN_13 §14` (`--font-text` row, "Playfair stays for headings and state words", "Mono is JetBrains Mono").
- Fraunces Variable has an `opsz` axis from 9 to 144 (`globals.css:23-30`). That covers PLAN_13's stated reason for a separate text serif ("Playfair… degrades below 18px"): set opsz ≈ 14–15 for statute quotations, and the site already sets WONK/SOFT to 0.
- Plex Mono for every `ref`, figure, instrument and date (`AGENTS.md:16-18`).
- For the Word pane, serve the OFL files from `addin/serve.py` (licences ship in `3300/brand-kit/fonts/*-OFL-LICENSE.txt`) or accept the fallback. Pane option is a decision.

**F8. Accent and buttons: remove Slate.**
- Touches `PLAN_13 §6 AskButton` ("Slate on the web; Ink in the pane"), `§14` colour count; `assistant.css:3, 8, 121-122` (`.ask`), `.tab.is-current`.
- Web Ask button: the site's cream-solid primary (`.dbtn-solid`, `dashboard.css:142-151`) **without** the shimmer and lift. Pane: ink-solid.
- Focus: the site's `outline: 2px solid var(--foreground)` (`globals.css:186-189`).
- If a gold element is wanted, it is the one per view (`AGENTS.md:13`). Slate on ink is 2.60:1.

**F9. Dates and numbers: one convention across site and Ask (founder decision).**
- Touches `PLAN_13` header ("DD-Mon-YYYY"), `§9`, `§6 SuppliedFacts`; `web/assistant/app.js:21, 83-87`.
- The site shows ISO dates in mono and IST timestamps ("11 Sept 2026, 05:30 IST", `format.ts:10-26`). The Ask shows `01-Jun-2024`. Pick one, and make `formatIST` and the Ask formatter agree ("Sept" vs "Sep").
- User-typed facts: PLAN_13 deliberately renders `120000000` un-grouped and not mono. `AGENTS.md:17` says mono on every figure, and `format.ts` groups lakh/crore. Either record the exception in 3300's AGENTS.md or render facts with a "You entered" label in mono, ungrouped. (C11, C12)

**F10. Motion: align to site tokens and resolve the 200 vs 250ms rule.**
- Touches `PLAN_13 §17`; `assistant.css:16` (`--fast`); `tools/accept.mjs` check 10.
- Use `--ease` and `--dur-1` (140ms). The reused site chrome animates at 220ms plus a 0.6s shimmer (`surfaces.css:44`; `dashboard.css:147-177`): either override those on the Ask route, or relax check 10 to the site's ≤250ms (`AGENTS.md:45`). (C9)

**F11. Glyphs, radius, pills.**
- Touches `PLAN_13 §6 StateHeading`, `§16` (square glyphs); `assistant.css` `.glyph`, radius values.
- Use `var(--radius)`. For row-level classes, reuse the site's `ClassBadge` icon + label (`surface-shell.tsx:77-128`) so a "Determined" or "Abstained" item looks the same on `/product/compliance-pack` and in Ask. Keep the square turn-state glyph only if the founder wants a separate turn-level mark. (C7, C14)

**F12. Glass or flat: stay flat, like the existing product surfaces.**
- Touches `PLAN_13 §5` ("never by fill or shadow").
- Compatible with `surfaces.css`, which uses no glass. It conflicts with the redesign thesis that the "sticky rail, abstain panel" are glass (redesign spec §2). Flag it rather than change it. (C8)

**F13. Accessibility: do not inherit the site's sub-AA label styles.**
- Touches `PLAN_13 §16`, plus a note in the port plan.
- `--muted-2` (cream@0.42, 3.70:1) is used for 12–13px text. `.cb-abstained` puts `#5B6472` text on ink (3.29:1). 11px labels appear in `surfaces.css:300` and `dashboard.css:1269`.
- On the site side, `--muted-2` needs alpha ≥ 0.49 to reach 4.5:1 (a frontend change, not an Ask change). (C5, C6)

**F14. Stamp wording: the site should adopt Ask's honesty.**
- Touches `PLAN_13 §9`: add "do not reuse `Stamp`'s 'Law as of' label".
- Frontend: `surface-shell.tsx:161-165` should say what the engine says ("current consolidation as ingested 2026-08-18, not point-in-time"). (E5)

**F15. Frontend fixes the Ask work depends on** (frontend owners; recorded here for completeness):
- Update the route list to seven (plus `/v1/ask` and `/v1/scope` when built) (E1).
- Regenerate `mock.ts` and the home demo from the engine: the G.S.R. 700(E) vs 880(E) story (E4).
- Deploy `main` or find why it is not live (E9).
- Fix `/support` (E12).
- Reconcile Word-add-in marketing with the read-only pane (E7, E13).
