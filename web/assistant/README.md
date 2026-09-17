# The Ask section — static prototype

Styled on the **finalized frontend** (`placedon-claude-legal-3300`, the site placedon.com serves): the
web is the site's dark ink shell, each answer is a sheet of Compliance Note paper, Brass Gold is the one
accent, Cool Grey marks abstention only. The Word pane (≤400px) is the light cream variant.

Design: [`docs/PLAN_13_ASSISTANT_UX.md`](../../docs/PLAN_13_ASSISTANT_UX.md) ·
Plan: [`docs/PLAN_13_ASSISTANT_UX_PLAN.md`](../../docs/PLAN_13_ASSISTANT_UX_PLAN.md) ·
Contract: [`contract.md`](contract.md)

**This is a prototype, not a product surface.** `POST /v1/ask` does not exist; the page renders
fixtures built from the engine (`scripts/assistant_contract.py`). Nothing here calls a model.

## Run it

Open `index.html` in a browser. With no parameter it shows the empty state; `?fixture=<name>`
renders a saved response. **Ask sends nothing**: it says so in a status line and keeps your question.

| Fixture | State |
|---|---|
| `answered_small_company` | answered |
| `partial_s173_s16` | partial |
| `out_of_scope_fema` | out_of_scope |
| `document_context_2024` | partial, document context |
| `followup_turnover` | answered, follow-up turn (its parent turn is shown collapsed above it) |
| `partial_nothing_confirmed` | partial, nothing confirmed — the state the design expects to dominate |

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
self-hosts them from `placedon-claude-legal-3300/brand-kit/fonts/`) for the screenshots; the page itself
names them and falls back to system faces, and no font file is copied into this repository.
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
12. the empty state (no fixture) shows the title as the page's only `h1` and no answer.

Last run: **403/403 across 6 fixtures × 5 widths, plus the empty state** (red-team rebuild and
re-base onto the finalized frontend's tokens, 2026-09-17). Before the rebuild the same checks passed 233/396.

## The hooks the checks depend on

`data-state` · `data-state-heading` · `data-figure` · `data-citation` · `data-marker` · `data-back` ·
`data-source-panel` · `data-composer` · `data-law-version` · `data-group` · `data-disclosure` ·
`data-confirmed-item` · `data-superseded-item` · `data-not-confirmed-item` · `data-chrome` (a label
the response did not supply) · `data-f` (the response path an element was rendered from — the audit
trail behind check 6).

## What is deliberately absent

No streaming, no model picker, no confidence, no skeleton loaders, no history search (C1–C6). The
`headline`, `capabilities[]` and `scope.bodies[]` fields the design wants do not exist in the contract
yet, so **nothing renders in their place** — including the capability list that §19 Q1 leans on. That
gap is listed as blocking in the spec's §18.1.
