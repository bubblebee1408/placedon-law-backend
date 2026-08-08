# Research: T-7 — the report is passed in the URL query string

Agent: research · 2026-08-08 · no code modified

## Verdict

Real, and worth fixing — but **our own debt note was wrong about both the mechanism and the
threshold**, in a way that would have sent someone debugging the wrong layer.

## Confidence

High. Every number below was measured on this repo, not estimated. Limits are cited to primary
vendor documentation and confirmed empirically against a running `next dev`.

## Evidence

**Where it happens** — one line each way:

- encode: `frontend/components/checker-form.tsx:124-125`
  `router.push(\`/result?data=${encodeURIComponent(JSON.stringify(data))}\`)`
- decode: `frontend/app/result/page.tsx:66` → `parseReport` at `:15-29`, which returns `null` on
  any failure and renders the "No report found." card at `:69-80`.

**Measured, real reports the engine emits today** (full URL bytes):

| Scenario | findings | full URL |
|---|---:|---:|
| 5 employees | 1 | 2,267 |
| 25 employees, stale IC | 3 | **2,784** |
| 25 employees, nothing in place | 3 | **3,362** |

The 2,784 row reproduces the "2,786 chars" recorded in `TECH_DEBT.md` — confirming that figure
was the *encoded URL*. Today's true worst case is **3,362**.

**Scaling** (synthetic N-finding reports, real envelope):

| N | full URL bytes | Vercel 14,336 | Node 16,384 |
|---:|---:|:--|:--|
| 10 | 8,934 | ok | ok |
| 16 | 12,753 | ok | ok |
| **17** | **14,388** | **414** | ok |
| **20** | **17,161** | 414 | **431** |

**Empirically confirmed** against `next dev` (Next 14.2.15): binary search found last OK at
**16,357 bytes**, first rejected at **16,358 → HTTP 431**. Both the document GET *and* the
`RSC: 1` GET fail, so it breaks on first navigation, not only on reload.

`encodeURIComponent` inflation is **1.484×**, measured. At N=10 the JSON carries 19 `—`, 4 `“`,
4 `”`, 2 `…`, 1 `₹`; each 3-byte UTF-8 char becomes 9 URL characters. **The house prose style is
buying ~48% of the URL length.**

## Contradictions found

Two, both in our own `TECH_DEBT.md` row for T-7:

1. **"where some browsers truncate the URL" is wrong.** No browser is the binding constraint —
   Chrome allows 2,097,152 chars, Firefox ~65,000. The **Vercel CDN** fails first at **14,336
   bytes** with HTTP 414, roughly 100× tighter than the nearest browser limit.
2. **"~10 findings" is wrong.** The real threshold is **17 on Vercel, 20 on Node** — more
   headroom than we recorded, but a *hard 414/431 with an empty body*, not silent truncation.

The failure *is* silent in the product, though, for a different reason than we wrote:
`router.push` sits inside the `try` at `checker-form.tsx:111-132` but does not reject on a failed
navigation, so `setError` never runs. The user clicks the button and gets a browser error page
with no product-side error state.

## Options

| | 1. Inputs in URL, re-derive | 2. Compress payload | 3. POST + render server-side |
|---|---|---|---|
| URL size | **107 bytes, constant at any N** | 17,161 → 2,477 at N=20 | n/a |
| Complexity | low-medium, ~2 files | low, but two encodings to keep correct (`CompressionStream` needs Safari ≥16.4) | medium-high, fights the App Router |
| Cost | ₹0 | ₹0 | ₹0 |
| Bookmarkable | **yes, improved** | yes, unreadable | **no** |

`sessionStorage`/`localStorage` was rejected outright: a `/result` link would render "No report
found." in any other tab or device. A silently dead shared link is worse than the bug.

## Recommendation — Option 1

**The report is a pure function of the inputs.** `assess.py` is deterministic Python with no LLM,
so carrying the output in the URL is caching a value that is free to recompute. The length is the
symptom; the derivable-value-in-a-cache is the defect. Option 2 buys 70× headroom; Option 1 makes
URL length independent of finding count entirely.

Re-derivation is also *correct* for a compliance tool: a link shared in January and opened in
March re-runs against the current corpus. If Bengaluru's notification is ingested in between, the
abstention becomes a real deadline — for the person who was told "we will not guess."

## Open questions

1. **Snapshot vs live is a product decision.** Proceeding on: do not pin, but render
   "Re-checked against the corpus as of {today}" so drift is visible rather than silent.
   Pinning honestly is not currently possible — the corpus is not versioned per-date.
2. **`/result` gains a real failure mode.** "No report found." is the wrong message for a 500;
   it implies user error. A distinct error state is required, not optional polish.
3. **Rate limiting.** Re-deriving on every `/result` load means a refresh consumes quota. Five
   people opening a shared link in a meeting could 429. Check the window before shipping.
4. **Latent bug, same growth trigger:** `result/page.tsx:127` uses `key={f.title}`. At 17
   findings duplicate titles become likely and React will render incorrectly. Fix in the same
   pass.
5. **`vercel.json` rewrites `/(.*)` to the Python app.** Where the Next frontend deploys is
   unresolved. If it lands behind that rewrite the ceiling drops below 14,336.

Sources: [Vercel URL_TOO_LONG](https://vercel.com/docs/errors/URL_TOO_LONG) ·
[Node CLI](https://nodejs.org/api/cli.html) ·
[Chromium url_constants.h](https://chromium.googlesource.com/chromium/src/+/main/url/url_constants.h)
