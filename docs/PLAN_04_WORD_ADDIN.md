# The v1 product surface — a Word task-pane add-in

## Why Word, and why this is the whole product for v1

The research settles the delivery question. Harvey ships Word and Outlook
add-ins; Bloomberg Law's contract product lives inside Word. The adoption blocker
in Indian legal teams is **workflow fit and IT friction**, not price and not a
confidentiality veto — top Indian firms already send client-matter data to a US
cloud vendor.

And the distribution path is far lighter than expected: **admin-deployed via the
Microsoft 365 Admin Center requires no AppSource review, no Partner Center
enrolment and no public listing.** An IT admin uploads a manifest and pushes it to
named users. Live the same week.

## What it dodges

This is the reason to build it first. Every blocker the research surfaced applies
to *other* products, not this one.

| Verified blocker | Does the add-in hit it? |
|---|---|
| No MCA API, no verifiable authorised reseller | **No** — works on the open document |
| No Gazette feed | **No** — we serve only instruments we hold |
| OCR on scanned Indian paper | **No** — the file is already a `.docx` |
| No citator | **No** |
| IT procurement friction | **No** — admin-deployed |
| Confidentiality objection | **Reduced** — stays in the tenant |

**OCR becomes a v2 concern**, needed only for bulk review of scanned archives.
That defers the single largest technical risk without slowing the product.

## The one function

> **Check the document open in front of the lawyer against law current on the date
> that matters — and refuse where it cannot verify.**

This is the wedge already stated in `CLAUDE.md`: document generation is
commoditised, every firm's templates are a private fork drifting from the law,
and *the defect is only detectable at the output.* The add-in is where the output
is.

## The flow

```
[lawyer has a document open]
        │
        ├─ 1. EXTRACT           the facts the document asserts and the dates it turns on
        │                       (extraction_schema — model proposes, every span verified)
        │
        ├─ 2. DATE              which law was in force on the DOCUMENT'S date, not today's
        │                       (as_of — this is the step everyone else skips)
        │
        ├─ 3. DECIDE            applicability and obligations on those facts
        │                       (obligations, s185/186/188 — no model)
        │
        ├─ 4. CHECK CURRENCY    is every figure and rule relied on still in force?
        │                       (currency + staleness — the ₹4 crore check)
        │
        └─ 5. RENDER            three kinds of line, never blurred:
                                  ✓ verified   — cited, dated, sourced
                                  ⚠ superseded — the instrument that moved it, named
                                  ○ cannot say — what is missing, and the reference
```

Step 4 is the one no competitor performs. Step 5's third state is the product's
character: it is the line a lawyer trusts precisely because the tool declined.

## What renders in the sidebar

Three sections, in this order — worst first, because a reader scanning for risk
should not have to scroll past what is fine.

1. **Superseded** — "This document relies on ₹4 crore. G.S.R. 880(E) of
   01-12-2025 raised it to ₹10 crore." With the instrument, the date, and a link
   to the held artifact.
2. **Cannot verify** — the row, what is missing, and the acquisition reference.
   Never a silent omission.
3. **Verified** — collapsed by default. Each line carries provision, date and
   source hash.

**No score. No confidence percentage.** Status is ordinal — a prior safety
benchmark showed confidence scores inverting trust, and this repo already bars
them.

## What it must never do in v1

- Draft or edit the document. Reading and reporting is a different liability
  surface from writing, and mixing them on day one loses the argument that this is
  an audit layer.
- Show a green tick for the whole document. It covers a named set of obligations,
  not the whole Act. The pack already says this on its face; the sidebar must too.
- Send the document anywhere it does not need to go. The narration model (role 17)
  sees only the evidence pack, never the client's document body.

## Verified implementation detail

Researched against Microsoft Learn, 2026-09-10. Four findings change the spec.

**1. Use the XML manifest, not the unified JSON one.** The unified manifest is
real, but it is **not supported on non-subscription Word** (perpetual/LTSC), and
the Microsoft 365 admin center's "upload add-in from file" flow accepts **only**
the XML manifest — a unified-manifest add-in needs the separate Integrated Apps
path. For an enterprise legal team on mixed Office versions, XML has the reach.

**2. Comments, not highlighting — this is the important one.**
`Range.insertComment()` (WordApi 1.5) anchors an annotation to a range while
living in a **separate comment part** of the `.docx`: the body text and its
formatting are untouched. `font.highlightColor` by contrast is a genuine
formatting edit to existing runs — it shows up under Track Changes and in a
version diff.

Since v1 must not modify the document, **comments are the mechanism.** They also
happen to be better product: reviewable, resolvable, and already the surface a
lawyer uses for exactly this.

There is no overlay/annotation layer independent of the document object model —
anything visible is either a range property or a comment. So this is not one
option among several; it is the only non-destructive one.

**3. CORS applies exactly as on a normal web page.** The task pane is a webview
(WebView2 on Windows, WKWebView on Mac, a sandboxed iframe on the web) under the
same-origin policy. Our backend must send `Access-Control-Allow-Origin` for the
add-in's origin, or the pane must call a same-origin proxy. Not a surprise, but
it means the API is not optional infrastructure — it is the only way in.

**4. macOS sideloading is a file copy, and the usual CLI does not work.**
Drop the manifest in
`~/Library/Containers/com.microsoft.Word/Data/Documents/wef`, restart Word, then
**Home → Add-ins**. `office-addin-dev-settings` — which several Yeoman templates
assume — is **not supported on Mac**, which matters because the dev machine is one.

**Requirement sets:** WordApi **1.1** for `body.text`, `body.paragraphs`,
`body.contentControls` and `search()`; **1.3** for document properties
(`creationDate`, `lastSaveTime` — the document's own date, which this whole
feature turns on); **1.5** for `insertComment`. 1.5 reaches Word Windows 2302+,
Mac 16.70+ and the web — broad enough.

**Auth:** Nested App Authentication (NAA) + MSAL.js is Microsoft's current
recommendation; the older `getAccessToken()` SSO is marked legacy. For a single
design partner, ship with our own token first and layer NAA later — Microsoft
tells developers to keep a fallback path regardless.

**One correction to an earlier claim:** admin-deployed add-ins take **24–72 hours**
to appear on users' ribbons. Still far faster than AppSource review, but "live the
same week" is the honest phrasing, not "live the same day."

## Build shape

- **Frontend:** Office.js task pane, hosted as a static page over HTTPS.
- **Backend:** the existing `checker/api.py` `handle()` — already a pure function
  returning `(status, body)`, already testable without a server. One new route.
- **Auth/tenancy:** none in v1. A single design partner, admin-deployed.
- **Effort:** 2–6 weeks for an MVP by someone who knows Office.js. **This estimate
  is INFERRED — no credible sourced benchmark was found.** Treat it as a planning
  figure, not a commitment.

## The gate before any of it

**The four unacquired rules.** Today the pack answers 11 of 15 rows and refuses
four — s.2(85), s.177, s.188, s.203 — because the delegated rules behind them are
unheld or unreviewed. An add-in that refuses a quarter of its rows demos badly.

Acquiring and attesting those four is a day of human work and raises the quality
of every downstream surface at once. **It should happen before the add-in, not
after.**
