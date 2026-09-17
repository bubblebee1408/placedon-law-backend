/* The Ask section, rendering a placedon.ask/0 response.
 *
 * It renders; it never decides. Four rules govern every line below:
 *   1. `state` comes from the server. The client never infers one (C3).
 *   2. Nothing is drawn that the response did not supply. A text node is a server
 *      string (field), a fixed label (label, marked data-chrome), or a line the client
 *      composed from fields -- and those are built with field(), NOT label(), so the
 *      acceptance check still traces every digit in them to the fixture.
 *   3. The two as-of truths never look alike: a figure carries an in-force date under a
 *      solid rule; section text carries "Text as ingested" under a dashed rule, and
 *      never an in-force date (C2, §9).
 *   4. Every array element is rendered. A count is the array's own length, and a
 *      heading is never the only thing a reader gets about a row (red team L1, DQ1).
 *
 * Fixtures are embedded (fixtures.js) because a page opened from disk cannot fetch
 * local JSON. ?fixture=<name> selects one; no fixture is the empty state.
 */
'use strict';

var FIXTURES = window.PLACEDON_ASK_FIXTURES || {};
var MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
var ROWS_SHOWN = 3;             // confirmed rows before "Show all"
var SUBSECTIONS_SHOWN = 2;      // verbatim sub-sections before "Show the full text"
var uid = 0;

/* ── display words: 1:1 maps from engine enums (§13). Unknown values render verbatim. ── */
var STATE = {
  answered:     { word: 'Answered',        fill: 'full' },
  partial:      { word: 'Partly answered', fill: 'half' },
  out_of_scope: { word: 'Not held',        fill: 'none' }
};
var ROW_STATE = {
  APPLIES_SATISFIED: 'Applies · met',
  APPLIES_NOT_SATISFIED: 'Applies · not met',
  APPLIES_UNDETERMINED: 'Applies · not determined',
  DOES_NOT_APPLY: 'Does not apply',
  CANNOT_DETERMINE: 'Cannot determine'
};
var NC_KIND = {
  pack_missing: 'Not in the evidence pack',
  unusable: 'Held, but its text may not be used',
  cannot_verify: 'Cannot verify',
  refusal: 'Stopped by review',
  model_decision: 'Not decided'
};
var SCOPE_STATUS = {
  DECLARED: 'In scope, nothing acquired',
  CURRENT_ONLY: 'Current text only, no history',
  OUT_OF_SCOPE: 'Outside scope'
};
var CURRENCY = { CURRENT: 'current' };
function currencyWord(v) { return CURRENCY[v] || sentence(v).toLowerCase(); }
function words(map, v) { return Object.prototype.hasOwnProperty.call(map, v) ? map[v] : String(v); }

/* ── nodes ─────────────────────────────────────────────────────────────── */
function el(tag, cls, text) {
  var n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined && text !== null) n.textContent = text;
  return n;
}
/* A fixed label the response did not supply. */
function label(tag, cls, text) {
  var n = el(tag, cls, text);
  n.setAttribute('data-chrome', '');
  return n;
}
/* A server string, or a line composed from server fields; `path` is the audit trail. */
function field(node, path) { node.setAttribute('data-f', path); return node; }
function add(parent) {
  for (var i = 1; i < arguments.length; i++) if (arguments[i]) parent.appendChild(arguments[i]);
  return parent;
}
function groupHead(text, lead) {
  var h = label('h3', 'group' + (lead ? ' lead' : ''), text);
  h.setAttribute('data-group', '');
  return h;
}

/* 2026-09-15 -> 15-Sep-2026. A rendering of a supplied date; no new digits enter. */
function human(iso) {
  var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(iso || ''));
  return m ? m[3] + '-' + MONTHS[+m[2] - 1] + '-' + m[1] : String(iso || '');
}
function today() {
  var d = new Date();
  return ('0' + d.getDate()).slice(-2) + '-' + MONTHS[d.getMonth()] + '-' + d.getFullYear();
}
/* CORROBORATED -> Corroborated; HELD_UNREVIEWED -> Held unreviewed. */
function sentence(v) {
  var s = String(v || '').replace(/_/g, ' ').toLowerCase();
  return s.charAt(0).toUpperCase() + s.slice(1);
}
/* 120000000 -> 12,00,00,000 (Indian grouping; the digits are the supplied ones). */
function rupees(n) {
  var s = String(n);
  if (!/^\d+$/.test(s) || s.length <= 3) return s;
  var head = s.slice(0, -3), tail = s.slice(-3);
  return head.replace(/\B(?=(\d{2})+(?!\d))/g, ',') + ',' + tail;
}
/* Dotted keys break at the dots, not mid-word (DQ6). */
function dotted(node, key) {
  String(key).split('.').forEach(function (part, i) {
    if (i) { node.appendChild(document.createTextNode('.')); node.appendChild(el('wbr')); }
    node.appendChild(document.createTextNode(part));
  });
  return node;
}

/* Filled / half / hollow square. Redundant with the word, never the only signal. */
function glyph(fill) {
  var ns = 'http://www.w3.org/2000/svg';
  var svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', '0 0 10 10');
  svg.setAttribute('class', 'glyph');
  svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('focusable', 'false');
  var box = document.createElementNS(ns, 'rect');
  box.setAttribute('x', '0.5'); box.setAttribute('y', '0.5');
  box.setAttribute('width', '9'); box.setAttribute('height', '9');
  box.setAttribute('class', 'glyph-edge');
  svg.appendChild(box);
  if (fill !== 'none') {
    var ink = document.createElementNS(ns, 'rect');
    ink.setAttribute('x', '0.5'); ink.setAttribute('y', '0.5');
    ink.setAttribute('width', fill === 'full' ? '9' : '4.5'); ink.setAttribute('height', '9');
    ink.setAttribute('class', 'glyph-ink');
    svg.appendChild(ink);
  }
  return svg;
}

/* A show/hide control that says whether it is open (A11Y-6). */
function disclosure(showText, hideText, content) {
  var id = 'd' + (++uid);
  content.id = id;
  content.hidden = true;
  var btn = label('button', 'disclose', showText);
  btn.type = 'button';
  btn.setAttribute('data-disclosure', '');
  btn.setAttribute('aria-expanded', 'false');
  btn.setAttribute('aria-controls', id);
  btn.addEventListener('click', function () {
    content.hidden = !content.hidden;
    btn.setAttribute('aria-expanded', String(!content.hidden));
    btn.textContent = content.hidden ? showText : hideText;
  });
  return btn;
}

/* ── what a reader may be shown of a model-facing string (NG-5, L4) ───────
 * Some engine strings are written to a model ("not admitted for model use",
 * "Its text is unknown to you"). The reader gets the identifier and the state the
 * string names, a plain sentence, and the engine's own words behind a disclosure --
 * never prose that drops the identifier, and never the string silently removed. */
var MODEL_FACING = /model use|for model|unknown to you/i;
function readerDetail(text, path) {
  var box = el('div', 'detail');
  if (!MODEL_FACING.test(text)) return add(box, field(el('p', 'basis', text), path));
  var ref = /^([A-Z]+:[A-Z0-9_]+:[A-Z0-9_]+(?: \([^)]*\))?)/.exec(text);
  var state = /(?:in state|model use:)\s+([A-Z_]+)/.exec(text);
  if (ref) add(box, field(dotted(el('p', 'ref'), ref[1]), path));
  if (state) add(box, field(el('p', 'basis', 'Recorded state: ' + sentence(state[1])), path));
  add(box, label('p', 'basis', 'In the corpus, but not admitted as evidence here.'));
  var raw = field(el('p', 'raw', text), path);
  add(box, disclosure("Show the engine's own wording", "Hide the engine's own wording", raw), raw);
  return box;
}

/* ── the two as-of truths ──────────────────────────────────────────────── */
function figureBlock(f, i) {
  var box = field(el('div', 'figure'), 'figures[' + i + ']');
  box.setAttribute('data-figure', f.key);
  add(box,
    field(dotted(el('p', 'key'), f.key), 'figures[' + i + '].key'),
    field(el('p', 'amount', f.amount), 'figures[' + i + '].amount'),
    // "No end date recorded" is the only true claim about the present (§9; red team L5).
    field(el('p', 'inforce', 'In force from ' + human(f.effective_from)
      + (f.effective_to ? ' · Until ' + human(f.effective_to) : ' · No end date recorded')),
      'figures[' + i + '].effective_from,effective_to'),
    field(el('p', 'instrument', f.instrument), 'figures[' + i + '].instrument'),   // never shortened
    field(el('p', 'caption', sentence(f.evidence_state)), 'figures[' + i + '].evidence_state'),
    sourceLine(f.source_url, 'Gazette copy of ' + f.instrument, 'Gazette link: not recorded',
      'figures[' + i + '].source_url'));
  return box;
}

/* The text basis, derived from basis + point_in_time_verified (L13). An unknown basis
 * falls back to the pack's own statement, verbatim. */
function lawVersion(lv, compact) {
  if (!lv) return null;
  var box = field(el('div', 'lawver'), 'law_version');
  box.setAttribute('data-law-version', '');
  var known = lv.basis === 'CURRENT_CONSOLIDATION_AS_INGESTED' && lv.point_in_time_verified === false;
  if (!known) {
    add(box, field(el('p', null, lv.statement), 'law_version.statement'));
    return box;
  }
  var fetched = (lv.corpus_fetched || []).map(human).join(', ');
  add(box, field(el('p', null, (fetched
    ? 'Text as ingested ' + fetched + '.'
    : 'Text as ingested on a date the corpus does not record.')
    + ' Current consolidation, not a point-in-time version.'), 'law_version.corpus_fetched'));
  if (compact) return box;
  if (lv.point_in_time_requested) {
    // A document turn: the rows were read against today's text, not the text in force on
    // the document's date (red team L2).
    add(box, field(el('p', 'strong', 'It is not the law as it stood on '
      + human(lv.point_in_time_requested) + '.'), 'law_version.point_in_time_requested'));
  }
  var st = field(el('p', 'raw', lv.statement), 'law_version.statement');
  add(box, disclosure("Show the pack's full statement", "Hide the pack's full statement", st), st);
  return box;
}

/* A source link, or a truthful line about why there is none (L7). */
function sourceLine(url, linkName, noUrlText, path) {
  var box = el('div', 'source-line');
  if (!url) return add(box, label('p', 'caption', 'No source link was supplied.'));
  var host = null;
  try { host = /^https:\/\//.test(url) ? new URL(url).hostname : null; } catch (e) { host = null; }
  if (!host) return add(box, label('p', 'caption', noUrlText));
  if (host.indexOf('indiacode.nic.in') !== -1) {
    // The recorded URL is on the retired host, which refuses every request. Shown as text,
    // unrepaired, and not linked.
    add(box, label('p', 'caption', 'The recorded link is on the retired host indiacode.nic.in, so it is not linked.'));
    var raw = field(el('p', 'ref hash', url), path);
    return add(box, disclosure('Show the recorded link', 'Hide the recorded link', raw), raw);
  }
  var a = el('a', null, linkName);
  a.href = url;
  return add(box, field(a, path));
}

/* ── citations: a marker in the card, a record in Sources (A11Y-4) ─────── */
var lastMarker = null;
var RECORD_ID = new Map();          // citation object -> its Sources record id
function marker(c, n, recordId) {
  var btn = el('button', 'marker');
  btn.type = 'button';
  btn.setAttribute('data-marker', c.ref);
  add(btn, label('span', 'marker-n', '[' + n + ']'), field(el('span', null, c.cite || c.ref), 'cite'));
  btn.addEventListener('click', function () {
    var rec = document.getElementById(recordId);
    if (!rec) return;
    lastMarker = btn;
    rec.focus();
  });
  return btn;
}

function citationRecord(c, n, path, lv, textInCard) {
  var box = field(el('section', 'cit'), path);
  box.id = 'rec-' + (++uid);
  box.setAttribute('data-citation', c.ref);
  box.setAttribute('tabindex', '-1');            // a focus target, not a tab stop
  box.setAttribute('aria-label', 'Source ' + n + ': ' + (c.cite || c.ref));
  add(box,
    add(el('p', 'cit-head'), label('span', 'marker-n', '[' + n + '] '), field(el('strong', null, c.cite || c.ref), path + '.cite')),
    field(dotted(el('p', 'ref'), c.ref), path + '.ref'),
    field(el('p', 'caption', sentence(c.evidence_state)), path + '.evidence_state'),
    c.defects && c.defects.length
      ? field(el('p', 'caption', 'Defects: ' + c.defects.join(', ')), path + '.defects')
      : label('p', 'caption', 'No defects recorded.'),
    c.unusable_reason ? field(el('p', 'basis', c.unusable_reason), path + '.unusable_reason') : null,
    label('p', 'caption', textInCard ? 'Its text is shown in the answer.' : 'Section text is not part of this response.'),
    lawVersion(lv, true),
    c.retrieved_on && c.retrieved_on.length
      ? field(el('p', 'caption', 'Fetched ' + c.retrieved_on.map(human).join(', ')
        + ' (fetch dates, not in-force dates)'), path + '.retrieved_on')
      : null,
    sourceLine(c.source_url, 'Source: ' + (c.cite || c.ref), 'No source link was supplied.', path + '.source_url'));
  var back = label('button', 'disclose', 'Back to answer');
  back.type = 'button';
  back.setAttribute('data-back', '');
  back.addEventListener('click', function () {
    var to = lastMarker && document.contains(lastMarker) ? lastMarker : document.querySelector('[data-marker]');
    if (to) to.focus();
  });
  return add(box, back);
}

/* Sub-clauses a row named, inside that row (L12). */
function citedSpans(spans, path) {
  var box = el('div', 'spans');
  add(box, label('p', 'caption', 'Sub-clauses this row rests on. Their text is not reproduced; '
    + 'each is identified by its content hash.'));
  var ul = el('ul', 'plain');
  spans.forEach(function (s, i) {
    var li = field(el('li', 'ref'), path + '.cited_spans[' + i + ']');
    li.appendChild(document.createTextNode(s.path));
    if (s.resolved === false) li.appendChild(label('span', 'caution-word', ' · not found in the corpus'));
    ul.appendChild(li);
  });
  var hashes = el('ul', 'plain');
  spans.forEach(function (s, i) {
    hashes.appendChild(field(el('li', 'hash', s.path + '  ' + s.sha256), path + '.cited_spans[' + i + '].sha256'));
  });
  return add(box, ul, disclosure('Show the content hashes', 'Hide the content hashes', hashes), hashes);
}

/* ── items ─────────────────────────────────────────────────────────────── */
function rowItem(r, path) {
  var box = field(el('div', 'row'), path);
  add(box,
    field(el('p', 'duty', r.duty), path + '.duty'),
    add(el('p', 'verdict'),
      field(el('strong', null, words(ROW_STATE, r.state)), path + '.state'),
      r.basis ? field(el('span', null, ' — ' + r.basis), path + '.basis') : null),   // never truncated
    field(el('p', 'ref', r.provision), path + '.provision'));
  if (r.missing_facts && r.missing_facts.length) {
    add(box, label('p', 'caption', 'Facts it still needs'));
    var ul = el('ul', 'plain');
    r.missing_facts.forEach(function (m, i) { ul.appendChild(field(el('li', 'basis', m), path + '.missing_facts[' + i + ']')); });
    add(box, ul);
  }
  if (r.blocked_by) add(box, field(el('p', 'caption', 'Waiting on ' + r.blocked_by), path + '.blocked_by'));
  if (r.cited_spans && r.cited_spans.length) add(box, citedSpans(r.cited_spans, path));
  return box;
}

function notConfirmedItem(n, i, docDate, dutyShownAbove) {
  var path = 'not_confirmed[' + i + ']';
  var box = field(el('div', 'item caution'), path);
  box.setAttribute('data-not-confirmed-item', '');
  add(box, label('p', 'kind', words(NC_KIND, n.kind)));
  // A duty the scope frame already names is not printed twice (L8, DQ8); the item is
  // identified by its provision instead.
  if (n.duty && !dutyShownAbove) add(box, field(el('p', 'duty', n.duty), path + '.duty'));
  if (n.provision) add(box, field(el('p', 'ref', n.provision), path + '.provision'));
  var ids = [n.ref, n.reference, n.instrument].filter(function (x, k, a) { return x && a.indexOf(x) === k; });
  if (ids.length) add(box, field(el('p', 'ref', ids.join(' · ')), path + '.ref'));
  if (n.detail) add(box, readerDetail(n.detail, path + '.detail'));
  if (n.reason) add(box, field(el('p', 'basis', n.reason), path + '.reason'));
  if (n.already_open_at_document_date && docDate) {
    add(box, field(el('p', 'caption', 'Already open on ' + human(docDate)
      + ', the document’s date. Nothing changed after it was written.'), path + '.already_open_at_document_date'));
  }
  return box;
}

function supersededItem(sp, i) {
  var path = 'superseded[' + i + ']';
  var box = field(el('div', 'item moved'), path);
  box.setAttribute('data-superseded-item', '');
  add(box,
    field(el('p', 'duty', sp.duty), path + '.duty'),
    field(el('p', 'ref', sp.provision), path + '.provision'),
    add(el('p', 'basis'), label('strong', null, 'Governed then: '),
      field(el('span', null, sp.governed_then), path + '.governed_then'),
      sp.was_at_document_date ? field(el('span', 'caption', ' (' + currencyWord(sp.was_at_document_date)
        + ' on the document’s date)'), path + '.was_at_document_date') : null),
    add(el('p', 'basis'), label('strong', null, 'Governs now: '),
      field(el('span', null, sp.governs_now), path + '.governs_now'),
      sp.is_at_read_date ? field(el('span', 'caption', ' (' + currencyWord(sp.is_at_read_date)
        + ' on the read date)'), path + '.is_at_read_date') : null),
    sp.detail ? add(el('p', 'caption'), label('span', null, 'What governs it now: '),
      field(el('span', null, sp.detail), path + '.detail')) : null);
  return box;
}

function verbatimBlock(c, path, lv) {
  var parts = String(c.verbatim).split(/\n(?=\(\d+[A-Z]?\)\s)/);
  var box = el('div', 'verbatim-box');
  add(box, field(el('div', 'verbatim', parts.slice(0, SUBSECTIONS_SHOWN).join('\n')), path + '.verbatim'));
  if (parts.length > SUBSECTIONS_SHOWN) {
    var rest = field(el('div', 'verbatim', parts.slice(SUBSECTIONS_SHOWN).join('\n')), path + '.verbatim');
    add(box, rest, disclosure('Show the full text of ' + (c.cite || c.ref), 'Hide the rest of the text', rest));
    box.insertBefore(box.lastChild, rest);        // the control sits above what it opens
  }
  if (/[¹²³]|<sup>/.test(c.verbatim)) {                // footnote markup, rendered literally
    add(box, label('p', 'caption', 'Bracketed spans marked ¹ are amendments recorded in the source.'));
  }
  return add(box, lawVersion(lv));
}

/* ── groups ────────────────────────────────────────────────────────────── */
function confirmedGroup(r, card, recs) {
  var items = r.confirmed || [];
  if (!items.length) {
    add(card, groupHead('Confirmed: none'));
    if (r.evidence_pack && r.evidence_pack.insufficient_evidence) {
      add(card, field(label('p', 'basis', 'The engine marked its evidence insufficient to answer.'),
        'evidence_pack.insufficient_evidence'));
    }
    return;
  }
  var rows = items.filter(function (x) { return x.obligation_id; });
  var cites = items.filter(function (x) { return !x.obligation_id; });
  if (rows.length) {
    add(card, groupHead('Checked against the Act (' + rows.length + ')'),
      label('p', 'caption', 'None of these is a finding of compliance.'));
    var more = el('div');
    items.forEach(function (x, i) {
      if (!x.obligation_id) return;
      var node = rowItem(x, 'confirmed[' + i + ']');
      node.setAttribute('data-confirmed-item', '');
      (card.querySelectorAll('[data-confirmed-item]').length < ROWS_SHOWN ? card : more).appendChild(node);
    });
    if (more.childNodes.length) {
      add(card, disclosure('Show all ' + rows.length + ' rows', 'Show fewer rows', more), more);
    }
    if (!r.scope_frame) add(card, lawVersion(r.law_version));
  }
  if (cites.length) {
    add(card, groupHead('Confirmed (' + cites.length + ')'));
    items.forEach(function (c, i) {
      if (c.obligation_id) return;
      var path = 'confirmed[' + i + ']';
      var n = recs.indexOf(c) + 1;
      var box = field(el('div', 'item confirmed'), path);
      box.setAttribute('data-confirmed-item', '');
      add(box,
        field(el('p', 'duty', c.cite || c.ref), path + '.cite'),
        field(el('p', 'caption', sentence(c.evidence_state)
          + (c.defects && c.defects.length ? ' · Defects: ' + c.defects.join(', ') : '')), path + '.evidence_state'),
        c.verbatim ? verbatimBlock(c, path, r.law_version) : lawVersion(r.law_version),
        marker(c, n, RECORD_ID.get(c)));
      add(card, box);
    });
  }
}

function factsBlock(facts) {
  var box = el('div', 'facts-box');
  add(box, groupHead('You supplied'),
    label('p', 'caption', 'Facts sent with this request, entered in fields, not read from the question.'));
  var dl = el('dl', 'facts');
  Object.keys(facts).forEach(function (k) {
    var v = facts[k] && facts[k].value;
    var shown = /_rupees$/.test(k) ? '₹' + rupees(v) : String(v);
    dl.appendChild(field(dotted(el('dt'), k), 'facts.' + k));
    dl.appendChild(field(el('dd', null, shown), 'facts.' + k + '.value'));
  });
  return add(box, dl);
}

function whatItIsNot(w) {
  if (!w || (Array.isArray(w) && !w.length)) return null;       // never a heading alone
  var box = el('div', 'bound');
  add(box, groupHead('What this does not establish'));
  if (Array.isArray(w)) {
    var ul = el('ul');
    w.forEach(function (line, i) { ul.appendChild(field(el('li', null, line), 'what_it_is_not[' + i + ']')); });
    return add(box, ul);
  }
  return add(box, field(el('p', null, w), 'what_it_is_not'));
}

function status(text) {
  var s = document.querySelector('[data-status]');
  s.textContent = '';
  // Re-set after a tick so a repeated message is announced again.
  setTimeout(function () { s.textContent = text; }, 30);
}

function actions(r, card) {
  var bar = el('div', 'actions');
  var copy = label('button', 'act', 'Copy with sources');
  copy.type = 'button';
  copy.addEventListener('click', function () {
    var panel = document.querySelector('[data-source-panel]');
    var text = card.innerText + (panel && !panel.hidden ? '\n\n' + panel.innerText : '');
    var done = function () { status('Copied with instruments and dates.'); };
    var failed = function () { status('Copy failed. Select the text and copy it instead.'); };
    try { navigator.clipboard.writeText(text).then(done, failed); } catch (e) { failed(); }
  });
  var edit = label('button', 'act', 'Edit question');
  edit.type = 'button';
  edit.addEventListener('click', function () {
    var q = document.getElementById('q');
    q.value = r.question;
    q.focus();
  });
  add(bar, copy, edit);
  if (r.demand_signal) {
    var ds = label('button', 'act', 'Tell us this is blocking you');
    ds.type = 'button';
    ds.addEventListener('click', function () { status('Prototype: nothing was recorded.'); });
    add(bar, ds);
  }
  return bar;
}

/* ── the turn ──────────────────────────────────────────────────────────── */
function stampLine(r) {
  var bits = ['Asked as of ' + human(r.as_of)];
  bits.push(r.uses_model === false ? 'No model used'
    : r.uses_model === true ? 'A model was used' : 'Model use: not stated');     // NG-4
  if (r.evidence_pack && r.evidence_pack.retrieval_query) bits.push('Looked up ' + r.evidence_pack.retrieval_query);
  return field(el('p', 'stamp', bits.join(' · ')), 'as_of,uses_model,evidence_pack.retrieval_query');
}

function turnCard(r, n, parent, recs) {
  var s = STATE[r.state];
  var card = el('article', 'turn');
  card.setAttribute('data-state', r.state);
  var qid = 'q-' + r.turn_id, hid = 'h-' + r.turn_id;
  card.setAttribute('aria-labelledby', qid + ' ' + hid);         // question + state (F11b)

  var doc = r.context && r.context.kind === 'document';
  add(card, field(el('p', 'band', doc
    ? 'About the open document · dated ' + human(r.context.document_date)
    : 'About the Act'), 'context'));
  if (r.parent_turn_id) {
    var pl = label('p', 'parent', parent.r
      ? 'Follow-up to turn ' + parent.n + ' · ' + parent.r.question
      : 'Follow-up to an earlier turn that is not in this session');
    pl.id = 'p-' + r.turn_id;
    card.setAttribute('aria-describedby', pl.id);
    add(card, pl);
  }
  var q = field(el('p', 'question', r.question), 'question');
  q.id = qid;
  q.setAttribute('tabindex', '-1');
  add(card, q, stampLine(r));
  var head = el('h2', 'state');
  head.id = hid;
  head.setAttribute('data-state-heading', '');
  add(head, glyph(s.fill), label('span', null, s.word));
  add(card, head);

  if (r.state === 'out_of_scope') {
    if (r.body) {
      add(card, add(el('p', 'body-line'),
        field(el('strong', null, r.body.name), 'body.name'),
        field(el('span', null, ' · ' + r.body.regulator), 'body.regulator'),
        label('span', null, ' · ' + words(SCOPE_STATUS, r.body.scope_status))));
    }
    add(card, field(el('p', 'reason', r.reason), 'reason'),
      groupHead('What we hold'));
    var ul = el('ul', 'plain');
    (r.held || []).forEach(function (h, i) { ul.appendChild(field(el('li', null, h), 'held[' + i + ']')); });
    add(card, ul, field(el('p', 'caption', r.scope.sentence), 'scope.sentence'), actions(r, card));
    return card;
  }

  if (r.state === 'answered') {
    (r.rows || []).forEach(function (row, i) { add(card, rowItem(row, 'rows[' + i + ']')); });
    if (recs.length) {
      add(card, groupHead('Section text'));
      recs.forEach(function (c, i) { add(card, marker(c, i + 1, RECORD_ID.get(c))); });
    }
    if ((r.rows || []).length || recs.length) add(card, lawVersion(r.law_version));
    if (r.facts) add(card, factsBlock(r.facts));
    if (r.figures && r.figures.length) {
      add(card, groupHead('Dated figures (' + r.figures.length + ')', true));
      r.figures.forEach(function (f, i) { add(card, figureBlock(f, i)); });
    }
    add(card, whatItIsNot(r.what_it_is_not), actions(r, card));
    return card;
  }

  // partial: the abstention is the finding, so it leads (§8).
  var unchecked = [];
  if (r.scope_frame) {
    unchecked = (r.scope_frame.unchecked || []).map(function (u) { return u.what; });
    add(card, groupHead('Scope of this check', true),
      field(el('p', 'scope-sentence', r.scope_frame.sentence), 'scope_frame.sentence'),
      lawVersion(r.law_version));
  }
  var nc = r.not_confirmed || [];
  if (nc.length) {
    add(card, groupHead('Not confirmed (' + nc.length + ')', !r.scope_frame));
    if (unchecked.length) add(card, label('p', 'caption', 'The duties listed as not checked above, and why.'));
    nc.forEach(function (item, i) {
      add(card, notConfirmedItem(item, i, r.context && r.context.document_date, unchecked.indexOf(item.duty) !== -1));
    });
  }
  if (r.superseded && r.superseded.length) {
    add(card, groupHead('Superseded (' + r.superseded.length + ')'));
    r.superseded.forEach(function (sp, i) { add(card, supersededItem(sp, i)); });
  }
  confirmedGroup(r, card, recs);
  if (r.figures && r.figures.length) {
    add(card, groupHead('Dated figures (' + r.figures.length + ')'));
    r.figures.forEach(function (f, i) { add(card, figureBlock(f, i)); });
  }
  add(card, whatItIsNot(r.what_it_is_not), actions(r, card));
  if (doc) add(card, label('p', 'caption', 'Nothing was changed in your document.'));
  return card;
}

/* A collapsed earlier turn: one line, and not an answer container (§12). */
function priorLine(r, n) {
  var p = el('p', 'prior');
  p.setAttribute('data-prior-state', r.state);
  add(p, label('span', 'caption', 'Turn ' + n + ' · '), glyph(STATE[r.state].fill),
    label('span', 'prior-word', ' ' + STATE[r.state].word + ' · '), field(el('span', null, r.question), 'question'));
  return p;
}

/* ── sources ───────────────────────────────────────────────────────────── */
function citationsOf(r) {
  if (r.citations && r.citations.length) return { list: r.citations, path: 'citations' };
  return { list: (r.confirmed || []).filter(function (c) { return c.ref && !c.obligation_id; }), path: 'confirmed' };
}

function renderSources(r, n, recs, path) {
  var panel = document.querySelector('[data-source-panel]');
  var body = document.querySelector('[data-sources-body]');
  body.textContent = '';
  panel.hidden = false;
  document.querySelector('[data-sources-head]').textContent = 'Sources · Turn ' + n + ' · '
    + (r.context && r.context.kind === 'document' ? 'About the open document' : 'About the Act');
  var textInCard = path === 'confirmed';
  recs.forEach(function (c, i) {
    var rec = citationRecord(c, i + 1, path + '[' + (r[path] || []).indexOf(c) + ']', r.law_version, textInCard && !!c.verbatim);
    RECORD_ID.set(c, rec.id);
    body.appendChild(rec);
  });
  if (!recs.length) {
    body.appendChild(label('p', 'caption', r.figures && r.figures.length
      ? 'This turn has no citations.' : 'Sources for this turn: none supplied.'));
  }
  var p = r.evidence_pack;
  if (p) {
    var ep = el('div', 'pack');
    add(ep, groupHead('Evidence pack'),
      p.retrieval_query ? field(el('p', 'ref', 'Looked up ' + p.retrieval_query), 'evidence_pack.retrieval_query') : null,
      field(el('p', 'ref', 'Route: ' + p.route), 'evidence_pack.route'));
    (p.usable_keys || []).forEach(function (k, i) {
      add(ep, field(dotted(el('p', 'ref'), 'Usable: ' + k), 'evidence_pack.usable_keys[' + i + ']'));
    });
    (p.unusable_keys || []).forEach(function (k, i) {
      add(ep, field(dotted(el('p', 'ref'), 'Not usable: ' + k), 'evidence_pack.unusable_keys[' + i + ']'));
    });
    if ((p.missing || []).length) add(ep, label('p', 'caption', 'Reported missing by the pack:'));
    (p.missing || []).forEach(function (m, i) { add(ep, readerDetail(m, 'evidence_pack.missing[' + i + ']')); });
    body.appendChild(ep);
  }
}

/* ── composer and rail ─────────────────────────────────────────────────── */
function setComposer(r) {
  document.querySelector('[data-today]').textContent = today();
  var docRadio = document.querySelector('input[value="document"]');
  var genRadio = document.querySelector('input[value="general"]');
  var hint = document.querySelector('[data-doc-hint]');
  var docDate = r && r.context && r.context.kind === 'document' && r.context.document_date;
  if (docDate) {
    // The pane has a dated document open, so the next question can be about it (L15, NG-9).
    docRadio.removeAttribute('aria-disabled');
    docRadio.checked = true;
    hint.removeAttribute('data-chrome');
    field(hint, 'context.document_date').textContent = 'Checks the open document, dated '
      + human(docDate) + ', against the Companies Act, 2013.';
  } else {
    genRadio.checked = true;
    hint.setAttribute('data-chrome', '');
  }
  document.querySelector('[data-doc-choice]').addEventListener('click', function (e) {
    if (docRadio.getAttribute('aria-disabled') === 'true') { e.preventDefault(); genRadio.checked = true; }
  });
  if (!r) return;
  // After a turn: compact, still first (see index.html).
  var full = document.getElementById('composer-full');
  var summary = document.querySelector('[data-summary]');
  var change = document.querySelector('[data-change]');
  full.hidden = true;
  summary.hidden = false;
  document.querySelector('[data-summary-text]').textContent = 'Next question: about '
    + (docDate ? 'the open document' : 'the Companies Act, 2013') + '.';
  change.addEventListener('click', function () {
    full.hidden = !full.hidden;
    change.setAttribute('aria-expanded', String(!full.hidden));
    change.textContent = full.hidden ? 'Change' : 'Done';
  });
  var q = document.getElementById('q');
  q.rows = 2;
  q.placeholder = 'Ask another question';
}

function renderRail(session) {
  var rail = document.querySelector('[data-rail]');
  var list = document.querySelector('[data-rail-list]');
  rail.hidden = false;
  session.forEach(function (r, i) {
    var li = el('li');
    var b = el('button', 'rail-row');
    b.type = 'button';
    add(b, label('span', 'rail-word', STATE[r.state].word + ' '), glyph(STATE[r.state].fill),
      field(el('span', 'rail-q', r.question), 'question'),
      field(el('span', 'caption', 'Asked as of ' + human(r.as_of)), 'as_of'));
    b.addEventListener('click', function () {
      var target = i === session.length - 1
        ? document.getElementById('h-' + r.turn_id)
        : document.querySelector('[data-prior-state]');
      if (target) { target.setAttribute('tabindex', '-1'); target.focus(); }
    });
    list.appendChild(add(li, b));
  });
}

function wireComposer() {
  var form = document.querySelector('[data-composer]');
  var q = document.getElementById('q');
  form.addEventListener('submit', function (e) {
    e.preventDefault();                          // NG-1: Ask never navigates
    status(q.value.trim()
      ? 'Prototype: nothing was sent. This page renders saved examples only.'
      : 'Type a question first. (Prototype: nothing is sent either way.)');
  });
  q.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      if (form.requestSubmit) form.requestSubmit(); else form.dispatchEvent(new Event('submit', { cancelable: true }));
    }
  });
}

/* ── boot ──────────────────────────────────────────────────────────────── */
function byTurnId(id) {
  var names = Object.keys(FIXTURES);
  for (var i = 0; i < names.length; i++) if (FIXTURES[names[i]].turn_id === id) return FIXTURES[names[i]];
  return null;
}

function render(name) {
  wireComposer();
  var turns = document.querySelector('[data-turns]');
  if (!name) { setComposer(null); return; }                     // the empty state
  var r = FIXTURES[name];
  if (!r) {
    setComposer(null);
    turns.appendChild(label('p', 'basis', 'No saved example has that name.'));
    return;
  }
  document.body.classList.add('has-turns');
  var parent = r.parent_turn_id ? byTurnId(r.parent_turn_id) : null;
  var session = parent ? [parent, r] : [r];
  var n = session.length;
  setComposer(r);

  var src = citationsOf(r);
  renderSources(r, n, src.list, src.path);                     // records first: markers point at them
  if (parent) turns.appendChild(priorLine(parent, 1));
  turns.appendChild(turnCard(r, n, { n: 1, r: parent }, src.list));
  renderRail(session);
}

render(new URLSearchParams(location.search).get('fixture'));
