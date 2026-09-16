# The Ask section — static prototype

Design: [`docs/PLAN_13_ASSISTANT_UX.md`](../../docs/PLAN_13_ASSISTANT_UX.md) ·
Plan: [`docs/PLAN_13_ASSISTANT_UX_PLAN.md`](../../docs/PLAN_13_ASSISTANT_UX_PLAN.md) ·
Contract: [`contract.md`](contract.md)

**This is a prototype, not a product surface.** `POST /v1/ask` does not exist; the page renders
fixtures built from the engine (`scripts/assistant_contract.py`). Nothing here calls a model.

## Run it

Open `index.html` in a browser. It reads `?fixture=<name>`:

| Fixture | State |
|---|---|
| `answered_small_company` (default) | answered |
| `partial_s173_s16` | partial |
| `out_of_scope_fema` | out_of_scope |
| `document_context_2024` | partial, document context |
| `followup_turnover` | answered, follow-up turn |

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

`CHROMIUM=<path>` overrides the browser binary (the default is the Playwright-cached Chromium on
macOS). The runner exits non-zero on any failure.

It asserts, for every fixture at 320 / 360 / 768 / 1024 / 1440:

1. exactly one `[data-state]`, equal to the fixture's state;
2. the state is named in words (grayscale-safe);
3. no horizontal overflow;
4. every figure shows its amount, instrument and in-force date;
5. `[data-law-version]` is present wherever citations are;
6. **no number on screen the fixture did not supply** (chrome is marked `data-chrome`);
7. the composer is reached early in the tab order and before any citation, every citation is
   keyboard-reachable, and the source panel is reachable;
8. no motion over 200ms, and none at all under `prefers-reduced-motion`;
9. no network request leaves the page.

Last run: **185/185 across 5 fixtures × 5 widths.**

## The hooks the checks depend on

`data-state` · `data-state-heading` · `data-figure` · `data-citation` · `data-source-panel` ·
`data-composer` · `data-law-version` · `data-chrome` (a label the response did not supply) ·
`data-f` (the response path an element was rendered from — the audit trail behind check 6).

## What is deliberately absent

No streaming, no model picker, no confidence, no skeleton loaders, no history search (C1–C6). The
`headline`, `capabilities[]` and `scope.bodies[]` fields the design wants do not exist in the contract
yet, so **nothing renders in their place** — including the capability list that §19 Q1 leans on. That
gap is listed as blocking in the spec's §18.1.
