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
  document.getElementById("runstrip").disabled = false;
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
  // The coverage frame leads, and it is not collapsible. Two practitioners in
  // different registers independently said the same thing: a quiet panel reads as
  // a clean document, and a staff member who is not a lawyer cannot tell "the law
  // did not change" from "we never looked". It goes first, it names every gap in
  // full, and there is deliberately no <details> around it.
  out.innerHTML = coverageBlock(r.coverage) +
    block("Superseded — the law moved after this document", r.superseded, "superseded",
          x => `<div class="detail">Governed then: <span class="prov">${escapeHtml(short(x.governed_then))}</span><br>
                Governs now: <span class="prov">${escapeHtml(short(x.governs_now))}</span>
                ${x.reference ? `<br><span class="ref">acquire ${escapeHtml(x.reference)}</span>` : ""}</div>`)
  + block("Could not verify", r.cannot_verify, "cannot",
          x => `<div class="detail">${escapeHtml(truncate(x.detail, 220))}
                ${x.reference ? `<br><span class="ref">${escapeHtml(x.reference)}</span>` : ""}</div>`)
  + collapsed("Verified", r.verified);
}

function coverageBlock(c) {
  if (!c) return "";
  const gaps = c.unchecked || [];
  const head = `<div class="cov"><div class="k">Scope of this check</div>
    <div class="v">Checked ${c.checked_count} of ${c.checked_count + c.unchecked_count}
    ${c.corpus ? "against " + escapeHtml(c.corpus) : ""}${c.as_of ? ", as at " + escapeHtml(c.as_of) : ""}.</div>`;
  if (!gaps.length) {
    return head + `<div class="b">Nothing was withheld. This states what was examined,
      not a conclusion about the document.</div></div>`;
  }
  return head + `<div class="b"><b>NOT checked (${gaps.length})</b> — these were not
    examined at all, and silence about them is not a finding:</div>` +
    gaps.map(u => `<div class="gap">· ${escapeHtml(u.what)}<br>
      <span class="ref">needs: ${escapeHtml(u.acquire)}</span></div>`).join("") +
    `</div>`;
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

/* ── the register strip ────────────────────────────────────────────────────
 *
 * Runs with no register at all, and that is the point: with no contracted
 * aggregator the strip's first job is identity -- which companies this document
 * names, whether their CINs survive the scanner, and which of them each rule
 * would need. Everything else is a refusal that says what is missing.
 *
 * Roles are read from defined terms only. "the Company" is deliberately NOT
 * mapped: in a share purchase agreement it is usually the target and in a board
 * resolution it is the executing entity, and guessing between them is the
 * failure this whole strip exists to avoid. An unmapped term becomes
 * NAMED_PARTY, which no rule asks for -- so a deal document refuses and names
 * the role it needs, while a single-company document resolves under a verdict
 * that says the assumption was used.
 */
const STRIP_API = "https://localhost:3000/v1/mca-strip";

/* Loose on the character classes a scanner confuses, so a damaged CIN is FOUND
 * and reported rather than silently missed. The backend decides if it parses. */
const CIN_RE = /\b[LU][0-9OISBZGQ]{5}[A-Z]{2}[0-9OISBZGQ]{4}[A-Z]{3}[0-9OISBZGQ]{6}\b/gi;

const ROLE_TERMS = {
  target: "TARGET", "target company": "TARGET",
  purchaser: "ACQUIRER", acquirer: "ACQUIRER", buyer: "ACQUIRER", investor: "ACQUIRER",
  seller: "SELLER", vendor: "SELLER", promoter: "SELLER",
  issuer: "ISSUER", guarantor: "GUARANTOR"
};

document.getElementById("runstrip").addEventListener("click", runStrip);

async function runStrip() {
  const btn = document.getElementById("runstrip");
  const out = document.getElementById("stripout");
  btn.disabled = true; out.innerHTML = "";
  try {
    const doc = await readDocument();
    const parties = findParties(doc.text);
    if (!parties.length) {
      out.innerHTML = `<div class="err">No CIN found in this document. The strip
        identifies companies by CIN; without one there is nothing to reconcile
        against a register.</div>`;
      return;
    }
    let registers = [];
    const raw = (document.getElementById("reg").value || "").trim();
    if (raw) {
      try { registers = JSON.parse(raw); }
      catch (e) { throw new Error(`the pasted register is not valid JSON: ${e.message}`); }
    }
    const res = await fetch(STRIP_API, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        document_date: doc.documentDate || null,
        parties, registers,
        document: documentFacts(doc.text)
      })
    });
    if (!res.ok) throw new Error(`backend ${res.status}: ${(await res.text()).slice(0, 200)}`);
    renderStrip(await res.json());
  } catch (e) {
    out.innerHTML = `<div class="err"><b>Could not read the parties.</b>
      ${escapeHtml(String(e.message || e))}<br><br>Nothing was changed in your document.</div>`;
  } finally { btn.disabled = false; }
}

function findParties(text) {
  const seen = new Set(); const out = [];
  let m;
  CIN_RE.lastIndex = 0;
  while ((m = CIN_RE.exec(text)) !== null) {
    const cin = m[0].toUpperCase();
    // Look forward for the defined term this company is given.
    const after = text.slice(m.index, m.index + 400);
    const term = after.match(/\(\s*(?:the\s+)?["“'‘]?([A-Za-z][A-Za-z ]{2,24}?)["”'’]?\s*\)/);
    const role = term ? ROLE_TERMS[term[1].trim().toLowerCase()] : null;
    const key = cin + "|" + (role || "NAMED_PARTY");
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({ cin, role: role || "NAMED_PARTY",
               span: (term ? term[0] : m[0]).slice(0, 120) });
  }
  return out;
}

/* Only what the draft itself says. Every value is optional; a field we cannot
 * read becomes a refusal downstream, never a default. */
function documentFacts(text) {
  const f = {};
  const allot = text.match(/allot(?:ment of)?\s+([\d,]{3,})\s+equity shares/i);
  if (allot) { f.allotment_shares = parseInt(allot[1].replace(/,/g, ""), 10);
               f.allotment_class = "equity"; }
  if (/\b(?:free from|free of)\s+(?:all\s+)?(?:encumbrances?|charges?|liens?)/i.test(text)
      || /\bunencumbered\b/i.test(text)) f.states_unencumbered = true;
  const din = text.match(/\bDIN[:\s]*([0-9]{8})\b/i);
  if (din) f.signatory_din = din[1];
  return f;
}

function renderStrip(r) {
  const out = document.getElementById("stripout");
  const sev = (r.severity || "").toLowerCase();
  let html = `<div class="head ${sev === "blocking" ? "blocking" : ""}">${escapeHtml(r.headline)}</div>`;

  html += (r.cins || []).map(c => {
    const bad = !c.usable;
    return `<div class="who"><span class="cin ${bad ? "bad" : ""}">${escapeHtml(c.raw)}</span>
      ${bad ? `<br><span class="b" style="color:var(--caution)">${escapeHtml(c.issues.join("; "))}</span>` : ""}</div>`;
  }).join("");

  html += `<h2 style="margin-top:14px">Who each check runs against</h2>`;
  html += Object.entries(r.subjects || {}).map(([rule, s]) =>
    `<div class="who"><span class="r">${escapeHtml(rule.replace(/_/g, " "))}</span>
     ${s.cin ? `<span class="cin">${escapeHtml(s.cin)}</span> <span style="color:var(--slate)">(${escapeHtml(s.role || "")})</span>`
              : `<span style="color:var(--caution)">${escapeHtml(s.verdict)}</span>`}</div>`
  ).join("");

  if ((r.chips || []).length) {
    html += `<h2 style="margin-top:14px">Register</h2>` + r.chips.map(c =>
      `<div class="chip"><div class="k">${escapeHtml(c.label)}</div>
       <div class="v">${escapeHtml(c.value)}</div>
       <div class="b">${escapeHtml(c.blindness)}</div></div>`).join("");
  }

  if ((r.findings || []).length) {
    html += `<h2 style="margin-top:14px">Findings</h2>` + r.findings.map(f =>
      `<div class="row ${f.severity === "BLOCKING" ? "superseded" : "cannot"}">
       <div class="duty">${escapeHtml(f.headline)}</div>
       <div class="detail">${escapeHtml(f.question)}</div>
       ${f.citations.length ? `<div class="ref">${escapeHtml(f.citations.join(" · "))}</div>` : ""}
       ${f.blindness ? `<div class="b" style="font-size:11px;color:var(--slate);margin-top:4px">${escapeHtml(f.blindness)}</div>` : ""}
       </div>`).join("");
  }

  if ((r.not_run || []).length) {
    html += `<h2 style="margin-top:14px">Not run (${r.not_run.length})</h2>` +
      r.not_run.map(u => `<div class="row cannot"><div class="detail">${escapeHtml(u)}</div></div>`).join("");
  }

  html += `<div class="meta" style="margin-top:14px">Registry data is graded
    <b>${escapeHtml(r.evidence_grade)}</b>. ${(r.does_not_establish || []).map(escapeHtml).join(" · ")}</div>`;
  out.innerHTML = html;
}
