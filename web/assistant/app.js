/* The Ask section, rendering a placedon.ask/0 response.
 *
 * It renders; it never decides. Three rules govern every line below:
 *   1. `state` comes from the server. The client never infers one (C3).
 *   2. Nothing is drawn that the response did not supply. Every text node is either
 *      a server string or a label marked data-chrome, and the acceptance checker
 *      fails the page if a number appears that the fixture does not carry.
 *   3. The two as-of truths never look alike: a figure carries an in-force date
 *      under a solid rule; section text carries "Text as ingested" under a dashed
 *      rule, and never an in-force date (C2, §9).
 *
 * Fixtures are embedded (fixtures.js) because a page opened from disk cannot
 * fetch local JSON. ?fixture=<name> selects one.
 */
'use strict';

var FIXTURES = window.PLACEDON_ASK_FIXTURES || {};
var MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/* The state word is the state, in words, so the three stay distinct with colour
 * removed (§16). The glyph is redundant, never the only signal. */
var STATE = {
  answered:     { word: 'Answered',       glyph: '■' },   // filled square
  partial:      { word: 'Partly answered', glyph: '◧' },  // half-filled
  out_of_scope: { word: 'Not held',       glyph: '□' }    // empty
};

function el(tag, cls, text) {
  var n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined && text !== null) n.textContent = text;
  return n;
}
/* A label the response did not supply. Marked so the "no invented text" check can
 * tell our chrome from the server's words. */
function label(tag, cls, text) {
  var n = el(tag, cls, text);
  n.setAttribute('data-chrome', '');
  return n;
}
function field(node, path) { node.setAttribute('data-f', path); return node; }

/* 2026-09-15 -> 15-Sep-2026. A rendering of a date the response supplied; no new
 * digits enter the page. */
function human(iso) {
  var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(iso || ''));
  return m ? m[3] + '-' + MONTHS[+m[2] - 1] + '-' + m[1] : String(iso || '');
}

/* §18.2 rule 4: the live host is indiacode.gov.in. A link to the dead host is
 * suppressed — the citation still renders in full. */
function usableLink(url) {
  if (!url || !/^https:\/\//.test(url)) return null;
  try {
    if (new URL(url).hostname.indexOf('indiacode.nic.in') !== -1) return null;
  } catch (e) { return null; }
  return url;
}

function stamp(r) {
  var bits = ['Asked as of ' + human(r.as_of)];
  if (r.evidence_pack && r.evidence_pack.retrieval_query) {
    bits.push('Looked up ' + r.evidence_pack.retrieval_query);
  }
  return bits.join(' · ');
}

/* ── the two as-of truths ──────────────────────────────────────────────── */
function figureBlock(f, i) {
  var box = field(el('div', 'figure'), 'figures[' + i + ']');
  box.setAttribute('data-figure', f.key);
  box.appendChild(el('div', 'ref', f.key));                       // label is NEW; key verbatim
  box.appendChild(el('div', 'amount', f.amount));
  // "still current" rather than "No end date recorded" (§25.1 rule 7).
  var inforce = 'In force from ' + human(f.effective_from)
    + (f.effective_to ? ', until ' + human(f.effective_to) : ', still current');
  box.appendChild(el('div', 'inforce', inforce));
  box.appendChild(el('div', 'instrument', f.instrument));          // never shortened
  box.appendChild(el('div', 'ref', f.evidence_state));
  var link = usableLink(f.source_url);
  if (link) {
    var a = el('a', null, 'Gazette copy');
    a.href = link;
    box.appendChild(a);
  } else {
    box.appendChild(label('div', 'why', 'Gazette copy: pending'));
  }
  return box;
}

function lawVersion(lv) {
  if (!lv) return null;
  var box = field(el('div', 'lawver'), 'law_version');
  box.setAttribute('data-law-version', '');
  var fetched = (lv.corpus_fetched || []).map(human).join(', ');
  box.appendChild(label('div', null, 'Text as ingested ' + fetched
    + '. Current consolidation, not a point-in-time version.'));
  return box;
}

/* ── citations ─────────────────────────────────────────────────────────── */
function citation(c, i, path) {
  var box = field(el('div', 'cit'), path + '[' + i + ']');
  box.setAttribute('data-citation', c.ref);
  // A citation record is reachable in its own right. It has to be: when the source
  // link is suppressed (dead host, §18.2 rule 4) and there is no verbatim text, the
  // record has no focusable child at all, and a keyboard reader could not reach the
  // evidence. Caught by the acceptance check, not by reading the code.
  box.setAttribute('tabindex', '0');
  box.setAttribute('role', 'group');
  box.setAttribute('aria-label', 'Source: ' + (c.cite || c.ref));
  var head = el('div');
  var b = el('strong', null, c.cite || c.ref);
  head.appendChild(b);
  box.appendChild(head);
  box.appendChild(el('div', 'ref', c.ref));
  box.appendChild(el('div', 'ref', c.evidence_state
    + (c.defects && c.defects.length ? ' · defects: ' + c.defects.join(', ') : '')));
  if (c.unusable_reason) box.appendChild(el('div', 'basis', c.unusable_reason));
  if (c.retrieved_on && c.retrieved_on.length) {
    box.appendChild(label('div', 'ref', 'Fetched ' + c.retrieved_on.map(human).join(', ')
      + ' (fetch dates, not in-force dates)'));
  }
  if (c.verbatim) {
    var btn = el('button', 'disclose', 'Show the text of ' + (c.cite || c.ref));
    btn.type = 'button';
    var pre = field(el('div', 'verbatim', c.verbatim), path + '[' + i + '].verbatim');
    pre.hidden = true;
    btn.addEventListener('click', function () {
      pre.hidden = !pre.hidden;
      btn.textContent = (pre.hidden ? 'Show' : 'Hide') + ' the text of ' + (c.cite || c.ref);
    });
    box.appendChild(btn);
    box.appendChild(pre);
  }
  var link = usableLink(c.source_url);
  if (link) { var a = el('a', null, 'Source'); a.href = link; box.appendChild(a); }
  else box.appendChild(label('div', 'why', 'Source link: not recorded'));
  return box;
}

/* Sub-clauses the row named. The contract says their text is not extracted, so the
 * heading says so too (§25.1 rule 13). Hashes are shown whole or not at all (rule 10). */
function citedSpans(spans, path) {
  var box = el('div');
  box.appendChild(label('div', 'group', 'Sub-clauses the row named'));
  box.appendChild(label('div', 'why',
    'Resolved to the section. Sub-clause text is not extracted.'));
  spans.forEach(function (s, i) {
    box.appendChild(field(el('div', 'ref', s.path), path + '.cited_spans[' + i + '].path'));
  });
  var btn = el('button', 'disclose', 'Show the content hashes');
  btn.type = 'button';
  var list = el('div');
  list.hidden = true;
  spans.forEach(function (s, i) {
    list.appendChild(field(el('div', 'hash', s.sha256), path + '.cited_spans[' + i + '].sha256'));
  });
  btn.addEventListener('click', function () {
    list.hidden = !list.hidden;
    btn.textContent = (list.hidden ? 'Show' : 'Hide') + ' the content hashes';
  });
  box.appendChild(btn);
  box.appendChild(list);
  return box;
}

/* ── groups ────────────────────────────────────────────────────────────── */
function rowItem(r, i) {
  var box = field(el('div', 'row'), 'rows[' + i + ']');
  box.appendChild(el('div', null, r.duty));
  box.appendChild(el('div', 'ref', r.provision + ' · ' + r.state));
  box.appendChild(el('div', 'basis', r.basis));       // never truncated (§18.2 rule 9)
  (r.missing_facts || []).forEach(function (m) {
    box.appendChild(el('div', 'basis', m));
  });
  return box;
}

function notConfirmedItem(n, i) {
  var box = field(el('div', 'item caution'), 'not_confirmed[' + i + ']');
  box.appendChild(label('div', 'ref', n.kind));
  if (n.ref) box.appendChild(el('div', 'ref', n.ref));
  if (n.duty) box.appendChild(el('div', null, n.duty));
  if (n.provision) box.appendChild(el('div', 'ref', n.provision));
  // §18.2 rule 6: a string written for a model is not the only text a reader gets.
  if (n.detail && !/model use|for model/i.test(n.detail)) {
    box.appendChild(el('div', 'basis', n.detail));
  } else if (n.detail) {
    box.appendChild(label('div', 'basis', 'Held, but not admitted as evidence here.'));
  }
  if (n.reason) box.appendChild(el('div', 'basis', n.reason));
  return box;
}

/* ── the turn ──────────────────────────────────────────────────────────── */
function turnCard(r) {
  var card = el('article', 'turn');
  var s = STATE[r.state];
  var head = el('h2', 'state');
  head.setAttribute('data-state-heading', '');
  head.appendChild(label('span', 'glyph', s.glyph));
  head.appendChild(label('span', null, s.word));
  head.id = 'state-' + r.turn_id;
  // The accessible name is question + state, not the state alone (F11b).
  card.setAttribute('aria-label', r.question + ' — ' + s.word);
  card.setAttribute('data-state', r.state);

  card.appendChild(label('div', 'band', r.context.kind === 'document'
    ? 'About the open document · dated ' + human(r.context.document_date)
    : 'About the Act'));
  card.appendChild(field(el('div', 'question', r.question), 'question'));
  card.appendChild(label('div', 'stamp', stamp(r)));
  card.appendChild(head);

  if (r.state === 'out_of_scope') {
    // The reason names the body and its regulator, so the structured lines are
    // suppressed rather than repeated (§25.1 rule 4).
    card.appendChild(field(el('div', 'basis', r.reason), 'reason'));
    card.appendChild(label('div', 'group', 'What this engine holds'));
    (r.held || []).forEach(function (h, i) {
      card.appendChild(field(el('div', null, h), 'held[' + i + ']'));
    });
    return card;
  }

  if (r.facts) {
    card.appendChild(label('div', 'group', 'You supplied'));
    var dl = el('dl', 'facts');
    Object.keys(r.facts).forEach(function (k) {
      dl.appendChild(field(label('dt', null, k), 'facts.' + k));
      dl.appendChild(field(el('dd', null, String(r.facts[k].value)), 'facts.' + k + '.value'));
    });
    card.appendChild(dl);
  }

  if (r.not_confirmed && r.not_confirmed.length) {
    // Not confirmed leads in `partial`: the abstention is the finding (§8).
    card.appendChild(label('div', 'group lead', 'Not confirmed (' + r.not_confirmed.length + ')'));
    r.not_confirmed.forEach(function (n, i) { card.appendChild(notConfirmedItem(n, i)); });
  }
  if (r.superseded && r.superseded.length) {
    card.appendChild(label('div', 'group', 'Superseded (' + r.superseded.length + ')'));
    r.superseded.forEach(function (sp, i) {
      var box = field(el('div', 'item caution'), 'superseded[' + i + ']');
      box.appendChild(el('div', null, sp.duty));
      box.appendChild(el('div', 'ref', sp.provision));
      box.appendChild(label('div', 'basis', 'Governed then: ' + sp.governed_then));
      box.appendChild(label('div', 'basis', 'Governs now: ' + sp.governs_now));
      card.appendChild(box);
    });
  }
  if (r.rows && r.rows.length) {
    r.rows.forEach(function (row, i) { card.appendChild(rowItem(row, i)); });
    var withSpans = r.rows.filter(function (x) { return x.cited_spans && x.cited_spans.length; });
    if (withSpans.length) card.appendChild(citedSpans(withSpans[0].cited_spans, 'rows[0]'));
  }
  if (r.figures && r.figures.length) {
    card.appendChild(label('div', 'group lead', 'Dated figures (' + r.figures.length + ')'));
    r.figures.forEach(function (f, i) { card.appendChild(figureBlock(f, i)); });
  }
  if (r.confirmed && r.confirmed.length) {
    // The count is the rendered array's own length, never scope_frame.checked_count
    // (§18.2 rule 8), and the label says checked, not cleared.
    card.appendChild(label('div', 'group', 'Checked against the Act (' + r.confirmed.length + ')'));
  }
  if (r.scope_frame && r.scope_frame.sentence) {
    card.appendChild(label('div', 'group', 'Scope of this check'));
    card.appendChild(field(el('div', 'scope-sentence', r.scope_frame.sentence), 'scope_frame.sentence'));
  }
  if (r.what_it_is_not) {
    card.appendChild(label('div', 'group', 'What this does not establish'));
    var w = r.what_it_is_not;
    if (Array.isArray(w)) {
      w.forEach(function (line, i) {
        card.appendChild(field(el('div', 'bound', line), 'what_it_is_not[' + i + ']'));
      });
    } else {
      card.appendChild(field(el('div', 'bound', w), 'what_it_is_not'));
    }
  }
  return card;
}

/* ── sources ───────────────────────────────────────────────────────────── */
function sourcesFor(r) {
  var frag = document.createDocumentFragment();
  var cites = (r.citations || []).slice();
  var path = 'citations';
  if (!cites.length && r.confirmed) {
    cites = r.confirmed.filter(function (c) { return c.ref; });
    path = 'confirmed';
  }
  cites.forEach(function (c, i) { frag.appendChild(citation(c, i, path)); });
  var lv = lawVersion(r.law_version);
  if (lv) frag.appendChild(lv);
  if (r.evidence_pack) {
    frag.appendChild(label('div', 'group', 'Evidence pack'));
    var p = r.evidence_pack;
    frag.appendChild(field(label('div', 'ref', 'Route: ' + p.route), 'evidence_pack.route'));
    (p.usable_keys || []).forEach(function (k, i) {
      frag.appendChild(field(el('div', 'ref', k), 'evidence_pack.usable_keys[' + i + ']'));
    });
    (p.missing || []).forEach(function (m, i) {
      frag.appendChild(field(el('div', 'basis', m), 'evidence_pack.missing[' + i + ']'));
    });
  }
  return frag;
}

/* ── boot ──────────────────────────────────────────────────────────────── */
function render(name) {
  var r = FIXTURES[name];
  var turns = document.querySelector('[data-turns]');
  var panel = document.querySelector('[data-source-panel]');
  var body = document.querySelector('[data-sources-body]');
  turns.textContent = '';
  body.textContent = '';
  if (!r) {
    turns.appendChild(label('p', 'basis', 'No fixture named ' + name + '.'));
    return;
  }
  document.querySelector('[data-holds]').textContent =
    r.scope.held.join(', ') + ' — ' + r.scope.sentence;
  document.getElementById('asof').value = human(r.as_of);
  turns.appendChild(turnCard(r));

  var hasSources = (r.citations && r.citations.length)
    || (r.confirmed && r.confirmed.filter(function (c) { return c.ref; }).length);
  panel.hidden = !hasSources;
  if (hasSources) {
    document.querySelector('[data-sources-head]').textContent =
      'Sources · ' + (r.context.kind === 'document' ? 'About the open document' : 'About the Act');
    body.appendChild(sourcesFor(r));
  }
}

var params = new URLSearchParams(location.search);
render(params.get('fixture') || 'answered_small_company');
