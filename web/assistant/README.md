# The Ask section — static prototype

Styled on the **finalized frontend** (`placedon-claude-legal-3300`, the site placedon.com serves): the
web is the site's dark ink shell, each answer is a sheet of Compliance Note paper, Brass Gold is the one
accent, Cool Grey marks abstention only. The Word pane (≤400px) is the light cream variant.

Design: [`docs/PLAN_13_ASSISTANT_UX.md`](../../docs/PLAN_13_ASSISTANT_UX.md) ·
Plan: [`docs/PLAN_13_ASSISTANT_UX_PLAN.md`](../../docs/PLAN_13_ASSISTANT_UX_PLAN.md) ·
Contract: [`contract.md`](contract.md)

**This is a prototype, not a product surface.** `POST /v1/ask` exists (ASK-1, `checker/ask.py` +
`checker/api.py`) and each fixture is a request put through the route's own `answer()`
(`scripts/assistant_contract.py`), so what you see here is what a caller would get. Nothing here
calls a model, and neither does the route — `uses_model` is always false.

## Run the demo (live answers, on this computer)

```
python3 scripts/serve_ask.py            # then open http://127.0.0.1:8021
```

`scripts/serve_ask.py` binds **127.0.0.1 only** — there is no host option — serves this directory
read-only, and forwards `POST /v1/ask` to `checker.api.handle` in the same process. It also serves
`GET /v1/ask/documents` (the public documents it will check) and `POST /v1/ask/document` (check
one). Those two sit under `/v1/ask` because what they return is a `placedon.ask/0` turn, the
contract `/v1/ask` already serves; they are deliberately **not** `/v1/document`, which sits one
character from `checker/api.py`'s existing `/v1/document-check` — a different request and a
different shape — and they live on this server rather than in the api because they read files
under `corpus/testdocs/`, which `checker/api.py` never does. The page and the
route share one origin, so no CORS header is ever sent; a request that names another Host or comes
from another Origin is refused with a `403`. If port 8021 is already in use the server refuses to
start rather than share it (`--port N` picks another). `python3 scripts/serve_ask.py --test` runs its
67 checks; the gate runs them too.

**What live mode does.** Pressing Ask sends `{question, context}` — the words you typed and what the
About control says — to `/v1/ask` on this machine and nowhere else, and renders the reply through the
same renderer the fixtures use. While the request is out you get the waiting card, and Cancel (or
Esc) aborts it: a reply that arrives after that is never rendered. A dead server, any non-200, or a
body that is not a `placedon.ask/0` turn in a state this client knows renders the **service error**
("No result") — never an abstention, never a state the server did not send.

**What live mode does not do.** It sends no facts, no `provisions` and no `figures`, because this
page has no fields for them (the capability rows and facts fields of PLAN_13 §11 wait on
`GET /v1/scope`). A live turn is therefore answered by what the question itself names (contract §6
D1): a question carrying a citation gets that section's text, a question about a body we do not hold
is refused with that body, and everything else comes back `partial`. The answered small-company turn
with dated figures is reachable through the route with `facts`, `provisions` and `figures` — see the
fixtures, and `scripts/serve_ask.py --test` — but not by typing into this page. The route's open
items in [`contract.md`](contract.md)'s notice all still stand; the demo server is the one client the
notice sanctions, and it is local.

## Check a document (the repository's PUBLIC documents, and only those)

Choose **This document** in the composer, pick one from the list, and press Ask. The page sends
`{document_id, question}` to `POST /v1/ask/document`; the server reads the date that document
declares on its own face, runs the document check that already existed (`checker/ask.py`'s
document branch into `api.document_check`) and returns the `placedon.ask/0` turn beside an entry
for the document it read. **No model is called on this path either.**

**There is no upload, and there will not be one.** The founder's rule is that no client or
confidential document goes anywhere, and a demo is where a lawyer would first try one. The page
has no file input and no drop target, and the server refuses a body naming any field that could
carry a document (`text`, `document`, `file`, `path`, `base64`, `url`, …) **by the name, before
the value is looked at** — so the refusal cannot depend on reading what arrived, and what arrived
is never echoed back. The refusal is shown on the page, where someone would look for the upload
that is not there:

> There is no upload here, by design. This demo checks the public documents held in this
> repository (`corpus/testdocs/`) and nothing else: no client document, nothing confidential and
> nothing you hold is sent anywhere by this page. Choose one of the listed documents instead.

The list itself is `eval/prelabel/corpus.py`'s enumerator (D5's), imported read-only: ONE list
answers "is this document public", and it refuses any path outside `corpus/testdocs/`. A second
copy would be a second answer to the only question that keeps a confidential document out.

**The document's own date drives the check, or there is no check.** `checker/document_date.py`
accepts a line reading `Date: ` and then a bare date, and only that: the colon is required
(`dated April 13, 2020 and subsequent circulars` is a wrapped sentence about somebody else's
instrument, and without this rule TCPL's 2025 notice is dated to an MCA circular of 2020), the
date must begin immediately after it (not `Date of Birth`, not `Date: Friday, June 5, 2026` — a
record-date table row), and every declaration it can read must agree. Over the 29 public
documents **9 declare a date and 20 do not**, and the 20 are not failures to tune away: an ICSI
specimen carries `Date : ______ 20_.` because a specimen has no date, Titan's date line did not
survive text extraction, and `routemobile_outcome_board_meeting_2025-11-03` genuinely bears two
(the letter 4 November, the signatures 3 November). A document with no readable date is refused
in the **engine's own words** (`checker/orchestrator.py`'s `NO_DOCUMENT_DATE`), on its own card —
not an abstention, because nothing about the law was decided, and not the service error, because
nothing failed. No date is ever guessed.

**What could not be read is shown, not swallowed.** A date declaration this reader cannot parse
(`Date: 2026.05.07 21:59:27 +05'30'` — a PDF signature stamp; `Date: 28 Janua ry 2025` — somebody
else's OCR, left unrepaired) is counted as `declarations_unread` and **printed on the card**:
`routemobile_outcome_board_meeting_2026-05-07` is checked at 07-May-2026 and says, in the card,
that twelve further date lines could not be read and one of them could name a different date.

**The company profile is a placeholder, and the card says exactly what it decided.**
`api._profile` requires `company_class` and `incorporation_date`; these filings state no
incorporation date, so the profile is the demo's own input. It was claimed here that it could
decide nothing. **That was false** (D3 check 2, finding 2): `company_class: "public"` alone
decides `s.2(85)` as `DOES_NOT_APPLY` — "a public company is never a small company" — on any
document dated after G.S.R. 880(E), while a 2025 document hides it because `s.2(85)` lands in
`superseded` instead. Measured: no class → `400`; `public` → decides that one row; `private` →
decides none. `public` is kept, because every real filing here is a listed public company's and
choosing `private` would buy a quieter card with a fact known to be false of every document on
the list. The claim is what changed: `_profile_decides()` computes which rows the profile decided
and the note names them, so the sentence cannot drift from the register. What the turn decides is
**whether the legal basis of each obligation moved between the date the document declares and
today** — not what law the document rests on, which nothing here established.

`date_quote` is the declaration line verbatim in the payload; HTML collapses runs of whitespace,
so a doubled space inside a date (`Date: July 19,  2024`) reads as one on screen. `date_line` is
the line **in the file**, header included, so `sed -n '<line>p' <path>` opens it.

**Live mode is loopback-only.** Opened from a file, or served from any host but 127.0.0.1 /
localhost, the page sends nothing and behaves exactly as it did before: fixtures, and a status line
saying nothing was sent. The concept note says which of the two it is.

## Run it from a file (fixtures only)

Open `index.html` in a browser. With no parameter it shows the empty state; `?fixture=<name>`
renders a saved response. **Ask sends nothing**: it says so in a status line and keeps your question.
Both parameters keep working over http, where `?state=` is still the stand-in and sends nothing.

| Fixture | State |
|---|---|
| `answered_small_company` | answered |
| `partial_s173_s16` | partial |
| `out_of_scope_fema` | out_of_scope |
| `document_context_2024` | partial, document context |
| `followup_turnover` | answered, follow-up turn (its parent turn is shown collapsed above it) |
| `partial_nothing_confirmed` | partial, nothing confirmed — the state the design expects to dominate |

**Waiting, cancelled, no result** (PLAN_13 §4.4, §7.3, §7.11; words from §13). None is an answer
state, so none carries `data-state`, a glyph or a state word, and none is drawn on answer paper.
Add `?state=waiting`, `?state=cancelled` or `?state=error`, since the page has no endpoint to wait
on. With a fixture, the page shows the state that fixture's request was in (its question, what it
was about, its as-of date and nothing from its response). Without one, the page stays empty until you
press Ask. `waiting` and `cancelled` never reply: Cancel or Esc ends the wait, and the card keeps its
stamp. `error` fails at once: "No result". This card is a plain bordered box with no abstention grey,
badge or dashed mark, because a service failure is never an abstention. Your question stays in the
box, and Send again sends it again. Nothing runs on a client timer: no spinner, stages or skeleton.
The code for these states is in `nonanswer.js`, which loads before `app.js`.

Fixtures are embedded in `fixtures.js` because a page opened from `file://` cannot fetch local JSON.
Both it and `fixtures/*.json` are written by the same builder in one pass:

```
PYTHONPATH=$PWD python3 scripts/assistant_contract.py --write   # after any engine change
PYTHONPATH=$PWD python3 scripts/assistant_contract.py --test    # in scripts/run_tests.sh
```

## Acceptance checks

The six checks in PLAN §6 run headless against the cached Chromium. The runner is in the repo
(`tools/accept.mjs`); **Playwright is deliberately not a repository dependency**, so install it
anywhere outside the repo and point the runner at it:

```
mkdir -p ~/.cache/placedon-ux-tools && cd ~/.cache/placedon-ux-tools
printf '{"private":true,"type":"module"}' > package.json && pnpm add playwright

cd ~/PlacedOn/placedon-law-backend
PLAYWRIGHT=$HOME/.cache/placedon-ux-tools/node_modules/playwright/index.mjs \
  node web/assistant/tools/accept.mjs web/assistant/index.html web/assistant/fixtures \
  [--shots=<dir>]
```

`FONTS_DIR=<dir>` loads the brand fonts (Fraunces, Inter, IBM Plex Mono — the finalized frontend
self-hosts them from `placedon-claude-legal-3300/brand-kit/fonts/`) for the **file:// screenshots**;
that repository is not checked out beside this one, so the only copy on this Mac is the
read-only job clone under `~/.claude/jobs/*/tmp/repos/placedon-claude-legal-3300/brand-kit/fonts`;
the page itself names them and falls back to system faces, and no font file is copied into this
repository. It is deliberately not applied to the live-mode screenshots (check 14): the served page
allows no injected inline style and no font from another origin under its own CSP, so the runner
would have to break that policy to fake the brand faces in a shot of a page that cannot load them.
The live shots therefore show the system faces a viewer of the demo actually gets. (Before this was
decided, setting `FONTS_DIR` killed every live check: 883/884 and no `live-*` screenshot at all.)
`CHROMIUM=<path>` overrides the browser binary (the default is the Playwright-cached Chromium on
macOS). The runner exits non-zero on any failure.

It asserts, for every fixture at 320 / 360 / 768 / 1024 / 1440:

1. exactly one `[data-state]`, equal to the fixture's state;
2. the state is named in words (grayscale-safe);
3. no horizontal overflow;
4. every figure shows its amount, instrument and in-force date;
5. `[data-law-version]` is present wherever rows, confirmed, superseded items or citations are;
6. **no number on screen the fixture did not supply** (chrome is marked `data-chrome`);
7. keyboard: the composer is reached within six tab stops; citation records are **not** tab
   stops — each is reached from a `[data-marker]` button in the card, and offers "Back to answer";
   every disclosure carries `aria-expanded`; one `h1`; group labels are headings;
8. every `confirmed[]` and `superseded[]` element is rendered in the card; an empty `confirmed[]`
   says "Confirmed: none"; the model-use line is always present; a follow-up names its parent;
   no duty is printed twice; no overclaiming copy ("still current", "holds the law as it stands",
   a "not recorded" link that was recorded) outside the user's own words;
9. the question field's border meets 3:1; pressing Ask does not navigate, keeps the question and
   announces that nothing was sent;
10. no motion over 200ms, and none at all under `prefers-reduced-motion`;
11. no network request leaves the page;
12. the empty state (no fixture) shows the title as the page's only `h1` and no answer;
13. each non-answer state (`?state=`), at 360 (the light pane, reduced motion) and 1440 (the dark
    web shell), both with each fixture's request and with none (typed, then Ask). Checked: the
    §13 words verbatim, in an `article` with its own `h2`; no `[data-state]` and no glyph. The service
    error has no abstention or badge class, no dashed border, no abstention grey, no answer paper,
    no state word, and a solid border of at least 3:1. The question stays in the box. The composer
    is disabled while waiting and only then, and the waiting card does not change by itself. Cancel
    and Send again are `<button>`s you can reach by Tab. On arrival, focus goes to Cancel, or to the
    card's heading. Cancel, Esc and Send again each do what they say. The card carries the request's
    band, parent line and stamp, and no number the request did not supply. No overflow, motion
    within limits, one `h1`, no page errors, no network.
14. **live mode**, at 360 and 1440: the runner starts `scripts/serve_ask.py` on a free loopback
    port and drives this page against it. Three questions are typed and asked — the small-company
    question, an FDI/RBI question about a body we do not hold, and "What does s.173 require?" —
    and for each it checks that exactly one `{question, context}` was POSTed as JSON to `/v1/ask`,
    that the waiting card was up with the composer locked while the request was held, and that the
    rendered turn is **the server's**: its state, its `turn_id` (no fixture's), its `as_of` in the
    stamp, the typed words as the question, and no number the reply did not supply. Cancel aborts
    the request (the abort is observed at the network layer) and a reply released afterwards
    renders nothing. Four failures each render the service error and are put through check 13's
    whole battery: a 500, a reply whose `schema` is not `placedon.ask/0`, a reply in an unknown
    state, and the server killed under the page. `?fixture=` over http still renders the saved
    sample and sends nothing; `?state=` over http is still the stand-in. Every live page is also
    checked for **Content Security Policy violations**, so the page must live inside the policy the
    server sends rather than the runner loosening it.

15. **the document path**, at 360 and 1440: the page offers the public list and **no file input
    or drop target anywhere**; the no-upload refusal is shown; choosing a dated document POSTs
    `{document_id, question}` once to `/v1/ask/document` and no document text, the ASK-3 waiting
    card is up with the composer locked while the check runs, and the rendered turn is the
    server's — its state, its document named on the card, the placeholder profile declared, the
    scope frame leading the findings, the law-version line saying this is not the law as it stood
    on the document's date, and the superseded rows drawn. A document that declares no date
    renders the refusal with the engine's words verbatim, with no `[data-state]`, no glyph, no
    dashed or grey abstention mark, and not the service error either; the question stays in the
    box, and the count of date declarations that could not be read is named on the refusal too.
    A document checked with unread date declarations names that count on its card as well. Cancel
    aborts the check. A 500 and a reply that is not a turn each render the service error and go
    through check 13's whole battery. Every number on screen must come from the server's own reply
    or its list.

Last run: **1189/1189** (2026-09-23, D3 fix round 1, with `FONTS_DIR` set): the 883 below, plus
148 live-mode checks (D2) and **158 for the document path** (D3). Before the document path existed the same
runner scored **1053/1114**, every one of the 61 failures in check 15. 403 across
6 fixtures × 5 widths plus the empty state (unchanged), and 480
for the three non-answer states × 7 requests × 2 widths (2026-09-18, ASK-3). Before the states
existed, 114 of check 13's 162 assertions failed (451/565). The 48 that passed hold on any page
("empty until Ask", "no page errors"). Of 14 deliberate breakages in a scratch copy
(dashed or grey error border, abstention class, `data-state`, answer paper, emptied box, a ticking
waiting card, changed copy, a non-button Cancel, 300ms motion, no Esc, no focus move, unlocked
composer, a state word), the runner caught every one. Before the red-team rebuild, checks 1–12
passed 233/396. Check 14 was written first and run against the page before live mode existed:
916/975, with all 59 of its assertions failing (the page sent nothing, so there was no reply to
render and no waiting card to find).

## The hooks the checks depend on

`data-state` · `data-state-heading` · `data-figure` · `data-citation` · `data-marker` · `data-back` ·
`data-source-panel` · `data-composer` · `data-law-version` · `data-group` · `data-disclosure` ·
`data-confirmed-item` · `data-superseded-item` · `data-not-confirmed-item` · `data-nonanswer`
(`waiting` / `cancelled` / `error`) · `data-cancel` · `data-send-again` · `data-chrome` (a label
the response did not supply) · `data-f` (the response path an element was rendered from — the audit
trail behind check 6) · `data-origin` (`fixture` or `live` — where the rendered turn came from) ·
`data-concept` (the note that says whether anything is sent) · `data-doc-picker` ·
`data-doc-select` · `data-doc-upload` (the no-upload refusal) · `data-doc-meta` · `data-document`
(the block naming the document a card checked) · `data-document-refusal` (a document that declares
no date; not one of the three `data-nonanswer` states, so `?state=` cannot select it).

## What is deliberately absent

A non-answer state page does not draw the session rail or the Sources column. §7.3 wants the rail
row to read "Waiting" and then "Cancelled", so that row is not yet shown.

No streaming, no model picker, no confidence, no skeleton loaders, no history search (C1–C6). The
`headline`, `capabilities[]` and `scope.bodies[]` fields the design wants do not exist in the contract
yet, so **nothing renders in their place** — including the capability list that §19 Q1 leans on. That
gap is listed as blocking in the spec's §18.1.
