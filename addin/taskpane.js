/*
 * Placedon task pane.
 *
 * v1 RULE, enforced here and not merely intended: this add-in NEVER modifies the
 * document's text or formatting. It reads, and it annotates via the Comments API
 * (Word.Range.insertComment, WordApi 1.5), which lives in a separate part of the
 * .docx. font.highlightColor would be a real formatting edit -- visible under
 * Track Changes and in a version diff -- and there is no overlay layer
 * independent of the document object model, so comments are not one option among
 * several. They are the only non-destructive one.
 *
 * The pane sends the document's TEXT and DATE to the backend. It does not send
 * the file. The backend holds it in an ephemeral session and writes nothing
 * durable -- see checker/session.py.
 */
const API = "https://localhost:3000/v1/document-check";   // dev; CORS must allow this origin

let officeReady = false;

Office.onReady((info) => {
  const meta = document.getElementById("meta");
  if (info.host !== Office.HostType.Word) {
    meta.textContent = "This add-in runs in Word.";
    return;
  }
  officeReady = true;
  document.getElementById("run").disabled = false;
  meta.textContent = "Ready.";
});

document.getElementById("run").addEventListener("click", run);

async function run() {
  const btn = document.getElementById("run");
  const meta = document.getElementById("meta");
  const out = document.getElementById("out");
  btn.disabled = true; out.innerHTML = ""; meta.textContent = "Reading the document…";

  try {
    const doc = await readDocument();
    meta.textContent = `Document date ${doc.documentDate || "unknown"} · ${doc.text.length.toLocaleString()} characters`;

    if (!doc.documentDate) {
      // The whole feature turns on the document's date. Guessing today's date
      // would silently answer a different question from the one asked.
      out.innerHTML = `<div class="err"><b>No document date.</b> This check compares
        the law in force when the document was made against the law today. Without
        a date it would be comparing today with today, which answers nothing.
        Set the document's created date, or type a date into the document.</div>`;
      btn.disabled = false; return;
    }

    meta.textContent += " · checking…";
    const res = await fetch(API, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        document_date: doc.documentDate,
        company_class: doc.companyClass || "private",
        incorporation_date: doc.incorporationDate || doc.documentDate
      })
    });
    if (!res.ok) {
      const body = await res.text();
      throw new Error(`backend ${res.status}: ${body.slice(0, 200)}`);
    }
    render(await res.json());
    meta.textContent = meta.textContent.replace(" · checking…", "");
  } catch (e) {
    out.innerHTML = `<div class="err"><b>Could not check.</b> ${escapeHtml(String(e.message || e))}
      <br><br>Nothing was changed in your document.</div>`;
  } finally {
    btn.disabled = false;
  }
}

/* Read body text and the document's own date. WordApi 1.1 for body, 1.3 for props. */
async function readDocument() {
  return Word.run(async (context) => {
    const body = context.document.body;
    const props = context.document.properties;
    body.load("text");
    props.load("creationDate,lastSaveTime,title");
    await context.sync();

    const text = body.text || "";
    // Prefer a date stated IN the document over file metadata: a resolution
    // says when it was passed, while creationDate says when someone opened a
    // template. Falls back to the file's creation date.
    const stated = matchStatedDate(text);
    const created = props.creationDate ? isoDate(props.creationDate) : null;

    return {
      text,
      documentDate: stated || created,
      dateSource: stated ? "stated in the document" : (created ? "file created date" : null),
      companyClass: /\bprivate (?:limited )?compan/i.test(text) ? "private"
                  : /\bpublic (?:limited )?compan/i.test(text) ? "public" : null,
      incorporationDate: matchIncorporationDate(text)
    };
  });
}

function matchStatedDate(t) {
  const m = t.match(/\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:day\s+of\s+)?([A-Za-z]+),?\s+(\d{4})\b/);
  if (m) {
    const mon = MONTHS[m[2].toLowerCase()];
    if (mon) return `${m[3]}-${mon}-${String(m[1]).padStart(2, "0")}`;
  }
  const iso = t.match(/\b(\d{4})-(\d{2})-(\d{2})\b/);
  return iso ? iso[0] : null;
}
function matchIncorporationDate(t) {
  const m = t.match(/incorporated[^.]{0,40}?(\d{4}-\d{2}-\d{2})/i);
  return m ? m[1] : null;
}
const MONTHS = {january:"01",february:"02",march:"03",april:"04",may:"05",june:"06",
  july:"07",august:"08",september:"09",october:"10",november:"11",december:"12"};
function isoDate(d) { return new Date(d).toISOString().slice(0, 10); }

function render(r) {
  const out = document.getElementById("out");
  const s = r.summary || {};
  out.innerHTML =
    block("Superseded — the law moved after this document", r.superseded, "superseded",
          x => `<div class="detail">Governed then: <span class="prov">${escapeHtml(short(x.governed_then))}</span><br>
                Governs now: <span class="prov">${escapeHtml(short(x.governs_now))}</span>
                ${x.reference ? `<br><span class="ref">acquire ${escapeHtml(x.reference)}</span>` : ""}</div>`)
  + block("Could not verify", r.cannot_verify, "cannot",
          x => `<div class="detail">${escapeHtml(truncate(x.detail, 220))}
                ${x.reference ? `<br><span class="ref">${escapeHtml(x.reference)}</span>` : ""}</div>`)
  + collapsed("Verified", r.verified);
}

function block(title, rows, cls, body) {
  rows = rows || [];
  if (!rows.length) return `<section><h2>${title}</h2><div class="empty">None.</div></section>`;
  return `<section><h2>${title} (${rows.length})</h2>` + rows.map(x =>
    `<div class="row ${cls}"><div class="duty">${escapeHtml(x.duty || x.obligation_id)}</div>
     <div class="prov">${escapeHtml(x.provision || "")}</div>${body(x)}</div>`).join("") + `</section>`;
}
function collapsed(title, rows) {
  rows = rows || [];
  if (!rows.length) return "";
  return `<section><details><summary>${title} (${rows.length})</summary>` + rows.map(x =>
    `<div class="row ok"><div class="duty">${escapeHtml(x.duty || x.obligation_id)}</div>
     <div class="prov">${escapeHtml(x.provision || "")}</div></div>`).join("") + `</details></section>`;
}

const short = s => (s || "").split(",")[0] || "—";
const truncate = (s, n) => { s = s || ""; return s.length > n ? s.slice(0, n) + "…" : s; };
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
