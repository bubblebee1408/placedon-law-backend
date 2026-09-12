# The Word add-in

One function: **check whether the law this document relies on has moved since the
document was made.**

## What it does and does not touch

It reads the document body and the document's own date. It **never modifies text
or formatting** — annotation, when it lands, goes through the Comments API
(`Range.insertComment`, WordApi 1.5), which lives in a separate part of the
`.docx`. `font.highlightColor` would be a genuine formatting edit, visible under
Track Changes and in a version diff, and Office.js has no overlay layer
independent of the document object model. So comments are not one option among
several; they are the only non-destructive one.

It sends the document's **text and date**, not the file. The backend holds it in
an ephemeral session and writes nothing durable (`checker/session.py`).

## Run it locally (macOS)

```bash
python3 addin/serve.py            # generates a cert, serves pane + engine on :3000
```

Then trust the certificate once, or Word will silently refuse to load the pane:

```bash
open https://localhost:3000/taskpane.html     # accept the warning in the browser
```

Sideload into Word — a file copy, because `office-addin-dev-settings` is **not
supported on Mac**, which several Yeoman templates assume:

```bash
mkdir -p ~/Library/Containers/com.microsoft.Word/Data/Documents/wef
cp addin/manifest.xml ~/Library/Containers/com.microsoft.Word/Data/Documents/wef/
```

Restart Word, open a document, then **Home → Add-ins → Placedon**.

## Why the XML manifest

The unified JSON manifest is real but is **not supported on non-subscription
Word** (perpetual / LTSC), and the Microsoft 365 admin center's "upload add-in
from file" flow accepts only the XML form. For an Indian corporate legal team on
mixed Office versions, XML has the reach.

## Deploying to a firm

Microsoft 365 Admin Center → Settings → Integrated apps → Add-ins → Deploy
Add-in → upload `manifest.xml` → choose users. **No AppSource review, no Partner
Center enrolment, no public listing.** Allow **24–72 hours** for it to appear on
users' ribbons.

## Known limits, stated rather than discovered

- **No document date, no answer.** The check compares the law when the document
  was made against the law now. Without a date it would compare today with today,
  which answers nothing. The pane says so instead of assuming today.
- **Fact extraction is regex, not a model.** Company class and incorporation date
  are matched crudely. The model-backed extractor (`checker/anthropic_model.py`,
  `checker/gemini_model.py`) exists and is tested, but has not been wired here
  until its leak rate is measured at zero.
- **Self-signed certificate** is for development only.
