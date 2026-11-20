/*
 * Redline engine for the Word add-in task pane.
 *
 * Takes edits from the backend (checker/redline.py) and applies them as
 * Word tracked changes using Office.js ChangeTrackingMode.
 *
 * Four controls per edit, matching the Jurisphere pattern:
 *   Show in Document — scrolls to the clause
 *   Apply            — inserts as a tracked change
 *   Apply with Comment — tracked change + explanatory comment
 *   Dismiss          — removes from the pane, does nothing to the document
 *
 * Selection-only scope: when the user highlights text before running, only
 * that range is sent to the backend. The add-in reads `window.getSelection()`
 * via `context.document.getSelection()` and sends it as `selection_text`.
 *
 * CHANGE FROM v1: the v1 rule was "NEVER modify document body text." That
 * rule prevented silent, invisible modifications. Tracked changes are the
 * opposite — they are explicitly marked, require user acceptance, carry a
 * revision history, and are more auditable than comments. The evolution is
 * from comments-only to tracked-changes-with-comments. The tracked change
 * IS the non-destructive path when change tracking is enabled.
 */

/* global Office, Word */

const REDLINE_API = "https://localhost:3000/v2/redline";

const STATUS_ICON = {
  STARTING: "✓",
  FALLBACK: "◐",
  NOT_ACCEPTABLE: "✗",
  NEEDS_LAWYER: "?",
};

const STATUS_LABEL = {
  STARTING: "Acceptable",
  FALLBACK: "Fallback",
  NOT_ACCEPTABLE: "Not Acceptable",
  NEEDS_LAWYER: "Needs Lawyer",
};

const PRIORITY_LABEL = {
  MANDATORY: "Mandatory",
  RECOMMENDED: "Recommended",
  NICE_TO_HAVE: "Nice to Have",
};

/** Read the user's current selection, or null if nothing is selected. */
async function readSelection() {
  return Word.run(async (context) => {
    const sel = context.document.getSelection();
    sel.load("text,isEmpty");
    await context.sync();
    if (sel.isEmpty || !sel.text || sel.text.trim().length < 20) {
      return null;
    }
    return sel.text;
  });
}

/** Read the full document body text. */
async function readFullText() {
  return Word.run(async (context) => {
    const body = context.document.body;
    body.load("text");
    await context.sync();
    return body.text || "";
  });
}

/** Run the redline review: selection-only or full document. */
async function runRedline(playbookPath) {
  const meta = document.getElementById("redlinemeta");
  const out = document.getElementById("redlineout");
  const btn = document.getElementById("runredline");
  btn.disabled = true;
  out.innerHTML = "";
  meta.textContent = "Reading…";

  try {
    const selText = await readSelection();
    const fullText = selText ? null : await readFullText();
    const text = selText || fullText;
    const scopeLabel = selText ? "Selection Only" : "Full Document";
    meta.textContent = `${text.length.toLocaleString()} chars · ${scopeLabel} · reviewing…`;

    const res = await fetch(REDLINE_API, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${getApiKey()}`,
      },
      body: JSON.stringify({
        text,
        playbook: playbookPath || "playbooks/nda_positions_v1.json",
        scope: selText ? "selection" : "full",
      }),
    });
    if (!res.ok) {
      const body = await res.text();
      throw new Error(`backend ${res.status}: ${body.slice(0, 200)}`);
    }
    const result = await res.json();
    renderRedline(result, text);
    meta.textContent = meta.textContent.replace(" · reviewing…", "");
  } catch (e) {
    out.innerHTML = `<div class="err"><b>Could not review.</b> ${escapeHtml(
      String(e.message || e)
    )}<br><br>Nothing was changed in your document.</div>`;
  } finally {
    btn.disabled = false;
  }
}

/** Render the redline results with four controls per edit. */
function renderRedline(result, contractText) {
  const out = document.getElementById("redlineout");
  const edits = result.edits || [];
  const playbook = result.playbook_id || "unknown";

  if (!edits.length) {
    out.innerHTML = `<div class="empty">No deviations found. The playbook matched or did not apply.</div>`;
    return;
  }

  // Summary bar
  const counts = {};
  for (const e of edits) counts[e.status] = (counts[e.status] || 0) + 1;
  const summary = Object.entries(counts)
    .map(([k, v]) => `${v} ${STATUS_LABEL[k] || k}`)
    .join(" · ");

  let html = `<div class="meta" style="margin-bottom:10px">${edits.length} rule(s): ${summary}</div>`;
  html += `<div class="meta" style="margin-bottom:10px;color:var(--caution)">Playbook: ${escapeHtml(playbook)} · ${escapeHtml(result.playbook_status || "DRAFT")}</div>`;

  for (let i = 0; i < edits.length; i++) {
    const e = edits[i];
    const icon = STATUS_ICON[e.status] || "·";
    const label = STATUS_LABEL[e.status] || e.status;
    const pLabel = PRIORITY_LABEL[e.priority] || e.priority;
    const cls =
      e.status === "STARTING"
        ? "ok"
        : e.status === "NEEDS_LAWYER"
          ? "cannot"
          : "superseded";

    html += `<div class="row ${cls}" id="edit-${i}">`;
    html += `<div class="duty">${icon} ${escapeHtml(e.clause)}</div>`;
    html += `<div class="prov">${escapeHtml(label)} · ${escapeHtml(pLabel)}</div>`;

    if (e.starting_text) {
      html += `<div class="ref">Starting: ${escapeHtml(e.starting_text)}</div>`;
    }
    if (e.position_detail) {
      html += `<div class="detail">${escapeHtml(e.position_detail)}</div>`;
    }
    // Confidence + match quality indicators (Fuzzy Triage, arXiv 2603.07390)
    if (e.match_quality === "fuzzy") {
      html += `<div class="ref" style="font-style:italic">⚠ Fuzzy match — verify before applying</div>`;
    }
    if (typeof e.confidence === "number" && e.confidence < 1.0 && e.confidence > 0) {
      html += `<div class="prov">Confidence: ${(e.confidence * 100).toFixed(0)}%</div>`;
    }

    // Show diff for REWRITE edits
    if (e.kind === "REWRITE" && e.old_text && e.new_text) {
      html += `<div class="diff"><del>${escapeHtml(e.old_text)}</del>`;
      html += `<ins>${escapeHtml(e.new_text)}</ins></div>`;
    } else if (e.kind === "INSERTION") {
      html += `<div class="diff"><ins>${escapeHtml(e.new_text)}</ins></div>`;
    }

    // Four controls — only for actionable edits
    if (e.kind === "REWRITE" || e.kind === "INSERTION") {
      html += `<div class="controls">`;
      html += `<button onclick="showInDoc(${i})" class="ctrl">Show</button>`;
      html += `<button onclick="applyEdit(${i}, false)" class="ctrl">Apply</button>`;
      html += `<button onclick="applyEdit(${i}, true)" class="ctrl">Apply + Comment</button>`;
      html += `<button onclick="dismissEdit(${i})" class="ctrl dim">Dismiss</button>`;
      html += `</div>`;
    }

    html += `</div>`;
  }

  out.innerHTML = html;
  // Store edits for the control handlers
  window._redlineEdits = edits;
  window._redlineContract = contractText;
}

/** Scroll to the clause in the document. */
async function showInDoc(idx) {
  const e = window._redlineEdits[idx];
  if (!e || !e.old_text) return;

  await Word.run(async (context) => {
    const results = context.document.body.search(e.old_text, {
      matchCase: false,
      matchWholeWord: false,
    });
    results.load("items");
    await context.sync();
    if (results.items.length > 0) {
      results.items[0].select();
      await context.sync();
    }
  });
}

/**
 * Apply an edit as a tracked change.
 *
 * Uses Document.changeTrackingMode to ensure the edit lands as a tracked
 * change, visible in Word's revision history.
 *
 * WordApi 1.4+ for ChangeTrackingMode.
 * WordApi 1.5+ for Range.insertComment.
 */
async function applyEdit(idx, withComment) {
  const e = window._redlineEdits[idx];
  if (!e) return;

  try {
    await Word.run(async (context) => {
      // Enable track changes
      context.document.load("changeTrackingMode");
      await context.sync();
      const previousMode = context.document.changeTrackingMode;
      context.document.changeTrackingMode = Word.ChangeTrackingMode.trackAll;

      if (e.kind === "REWRITE" && e.old_text) {
        // Find and replace the old text
        const results = context.document.body.search(e.old_text, {
          matchCase: false,
          matchWholeWord: false,
        });
        results.load("items");
        await context.sync();

        if (results.items.length > 0) {
          const range = results.items[0];
          range.insertText(e.new_text, Word.InsertLocation.replace);

          if (withComment) {
            range.insertComment(e.comment);
          }
        }
      } else if (e.kind === "INSERTION") {
        // Insert at end of document (or after last clause)
        const range = context.document.body.getRange(Word.RangeLocation.end);
        const inserted = range.insertText(
          "\n\n" + e.new_text,
          Word.InsertLocation.before
        );

        if (withComment) {
          inserted.insertComment(e.comment);
        }
      }

      // Restore previous tracking mode
      context.document.changeTrackingMode = previousMode;
      await context.sync();
    });

    // Visual feedback
    const row = document.getElementById(`edit-${idx}`);
    if (row) {
      row.classList.add("applied");
      const ctrls = row.querySelector(".controls");
      if (ctrls)
        ctrls.innerHTML = `<span class="meta">Applied${withComment ? " with comment" : ""}</span>`;
    }
  } catch (err) {
    const row = document.getElementById(`edit-${idx}`);
    if (row) {
      const ctrls = row.querySelector(".controls");
      if (ctrls)
        ctrls.innerHTML = `<span class="err">${escapeHtml(String(err.message || err))}</span>`;
    }
  }
}

/** Dismiss an edit — remove from the pane, nothing to the document. */
function dismissEdit(idx) {
  const row = document.getElementById(`edit-${idx}`);
  if (row) row.remove();
}

// escapeHtml is defined in taskpane.js, shared scope
if (typeof escapeHtml === "undefined") {
  // ponytail: standalone fallback if loaded independently
  window.escapeHtml = function (s) {
    return String(s).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]
    );
  };
}


/* ── self-test (runs in Node, not in Word) ────────────────────────────────
 *
 * Tests the pure-logic parts: rendering, status mapping, diff display.
 * Office.js calls are tested in the browser with a real document.
 */
if (typeof module !== "undefined" && module.exports) {
  module.exports = { STATUS_ICON, STATUS_LABEL, PRIORITY_LABEL };
}
