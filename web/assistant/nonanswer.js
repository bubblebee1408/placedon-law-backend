/* The Ask section's three non-answer states, split from app.js to keep each file focused.
 * Loaded BEFORE app.js; it uses app.js's helpers (el, label, field, add, human, today,
 * contextBand, parentLine, priorLine, setComposer, status, submitComposer), which exist by the
 * time anything here runs: app.js's boot, at its foot, is the first caller. */
'use strict';

/* ── not an answer: waiting, cancelled, no result (§4.4, §7.3, §7.11; copy from §13) ──────
 * None of these is a server state: no data-state, no glyph, no state word, and never the
 * Compliance Note paper an answer is printed on. The service error above all must never read as
 * an abstention (placedon-claude-legal-3300 AGENTS.md): no abstention grey, no badge, no dashed
 * mark (dashed has meant abstention since §27) -- a plain bordered box that says there is no
 * answer, partial or otherwise.
 * Served by scripts/serve_ask.py these three states are real: the waiting card is up while the
 * POST /v1/ask is out, Cancel and Esc abort it, and a dead server or anything that is not a
 * placedon.ask/0 turn brings the error card (app.js askLive). ?state= keeps the stand-in for
 * demonstrating them anywhere, including from a file: 'waiting' and 'cancelled' never reply,
 * 'error' fails at once.
 * Nothing is timed on the client: no spinner, timer, stage names or skeleton (C1, C4, K9). */
var NA = {
  waiting: "Waiting for the server's decision.",
  cancelled: 'Cancelled before a result arrived. Nothing is shown.',
  errorHead: 'No result',
  error: 'The service did not return a result, so there is no answer, partial or otherwise. '
    + 'Your question is still in the box.',
  docLine: 'Nothing was changed in your document.'
};
var NON_ANSWER = ['waiting', 'cancelled', 'error'];
var demo = null;        // the ?state= value, when it names one of the three
var base = null;        // the request values a ?fixture= carried: as_of, context, parent
var pending = null;     // { kind, req, card, abort? }: the one non-answer card on the page

/* The request values the user set: the only things a waiting card may carry (§4.4). */
function composerRequest() {
  var docRadio = document.querySelector('input[value="document"]');
  // Live, a document is one the user picked from the server's public list (D3); with a
  // ?fixture= it is that fixture's own document. Both are document turns; neither is typed.
  var chosen = typeof chosenDocument === 'function' ? chosenDocument() : null;
  var doc = docRadio.checked && base && base.context && base.context.kind === 'document';
  return {
    question: document.getElementById('q').value,
    as_of: base ? base.as_of : null,            // null: today, from the client clock
    context: chosen ? { kind: 'document', document_date: chosen.date }
      : doc ? base.context : { kind: 'general' },
    parent_turn_id: base ? base.parent_turn_id : null,
    parent: base ? base.parent : null,
    document_id: chosen ? chosen.id : null
  };
}

function actionButton(text, hook, onClick) {
  var b = label('button', 'act', text);
  b.type = 'button';
  b.setAttribute(hook, '');
  b.addEventListener('click', onClick);
  return b;
}

function nonAnswerCard(kind, req) {
  var card = el('article', 'nonanswer' + (kind === 'error' ? ' nonanswer-error' : ''));
  card.setAttribute('data-nonanswer', kind);
  var head = label('h2', 'na-head', kind === 'error' ? NA.errorHead : NA[kind]);
  head.id = 'na-' + (++uid);
  head.setAttribute('tabindex', '-1');         // focused on arrival (§4.3 step 6); not a tab stop
  var bar = el('div', 'na-actions');
  if (kind === 'error') {
    // §7.11: the heading, the sentence, Send again. The question is in the box, not on the card.
    card.setAttribute('aria-labelledby', head.id);
    add(card, head, label('p', 'na-said', NA.error),
      req.context.kind === 'document' ? label('p', 'caption', NA.docLine) : null);
    add(bar, actionButton('Send again', 'data-send-again', submitComposer));
  } else {
    add(card, contextBand(req.context));
    if (req.parent_turn_id) add(card, parentLine(req, req.parent, card));
    var q = field(el('p', 'question', req.question), 'question');
    q.id = head.id + '-q';
    add(card, q, req.as_of
      ? field(el('p', 'stamp', 'Asked as of ' + human(req.as_of)), 'as_of')
      : label('p', 'stamp', 'Asked as of ' + today()), head);
    card.setAttribute('aria-labelledby', q.id + ' ' + head.id);
    if (kind === 'waiting') add(bar, actionButton('Cancel', 'data-cancel', cancelWait));
  }
  return add(card, bar.firstChild ? bar : null);
}

/* Disabled while waiting, and saying why: aria-disabled and described by the waiting line, so it
 * is never silently inert (§6, §15). */
function lockComposer(reasonId) {
  var q = document.getElementById('q');
  var ask = document.querySelector('[data-composer] .ask');
  q.readOnly = !!reasonId;
  [q, ask].forEach(function (n) {
    if (reasonId) n.setAttribute('aria-disabled', 'true'); else n.removeAttribute('aria-disabled');
  });
  q.setAttribute('aria-describedby', reasonId ? 'keyhint ' + reasonId : 'keyhint');
  if (reasonId) ask.setAttribute('aria-describedby', reasonId); else ask.removeAttribute('aria-describedby');
}

/* The one non-answer card. `arrived` (the user caused it) moves focus and speaks; a page load does
 * neither. Focus moves before the old card goes, so it is never left on a destroyed node (§15). */
function showNonAnswer(kind, req, arrived) {
  var old = pending && pending.card;
  var card = nonAnswerCard(kind, req);
  document.querySelector('[data-turns]').appendChild(card);
  document.querySelector('[data-status]').textContent = '';
  pending = { kind: kind, req: req, card: card };
  lockComposer(kind === 'waiting' ? card.querySelector('h2').id : null);
  if (arrived && kind === 'waiting') {
    card.querySelector('[data-cancel]').focus();
    status(NA.waiting, '[data-announce]');
  } else if (arrived) {
    card.querySelector('h2').focus();
    status(NA.errorHead + '. ' + req.question, '[data-announce]');
  }
  if (old) old.remove();
}

/* Cancel rewrites the waiting card in place, keeping its stamp (§4.4); focus goes to its heading
 * before the Cancel button is removed. The question stays in the box. */
function cancelWait() {
  if (!pending || pending.kind !== 'waiting') return;
  // Live, the request is aborted first: a reply that arrives anyway is never rendered.
  if (pending.abort) pending.abort();
  var head = pending.card.querySelector('h2');
  head.textContent = NA.cancelled;
  head.focus();
  pending.card.setAttribute('data-nonanswer', 'cancelled');
  pending.card.querySelector('.na-actions').remove();
  pending.kind = 'cancelled';
  lockComposer(null);
  status('Cancelled. ' + pending.req.question, '[data-announce]');
}

/* The engine refuses to read a document that does not say when it was made: every temporal
 * answer compares the law at the document's date with the law now, and without one it would
 * compare today with today. That is a DECISION, so this card is neither of the other two
 * things it could be mistaken for -- not an abstention (nothing about the law was decided;
 * no state, no glyph, no dashed mark, no abstention grey) and not the service error (nothing
 * failed). The engine's own words are shown verbatim, with the reader's finding beside them,
 * and no date is ever guessed to get past this. */
function showDocumentRefusal(req, payload) {
  var old = pending && pending.card;
  var card = el('article', 'nonanswer nonanswer-refusal');
  card.setAttribute('data-document-refusal', '');
  var head = label('h2', 'na-head', 'Not checked: this document does not say when it was made');
  head.id = 'na-' + (++uid);
  head.setAttribute('tabindex', '-1');
  card.setAttribute('aria-labelledby', head.id);
  add(card, contextBand(req.context), head,
    field(el('p', 'na-said', payload.detail), 'detail'));
  if (payload.reason) add(card, field(el('p', 'caption', payload.reason), 'reason'));
  // Looked at the 1440 and 360 shots: this line used to offer "or supply the date this one
  // bears", which this page has no field for. A refusal must not promise a way out that does
  // not exist, so it names only the one that does.
  add(card, label('p', 'caption', 'No date was assumed and none was guessed. '
    + 'Choose a document that carries its own date.'));
  var bar = el('div', 'na-actions');
  add(bar, actionButton('Choose another document', 'data-choose-again', function () {
    var full = document.getElementById('composer-full');
    if (full) full.hidden = false;
    var sel = document.querySelector('[data-doc-select]');
    if (sel) sel.focus();
  }));
  add(card, bar);
  document.querySelector('[data-turns]').appendChild(card);
  document.querySelector('[data-status]').textContent = '';
  pending = null;
  lockComposer(null);
  head.focus();
  status('Not checked. ' + (payload.reason || payload.detail), '[data-announce]');
  if (old) old.remove();
}

/* ?fixture=…&state=…: the page as it stood while that fixture's request was out -- the request
 * values it carried, and no part of its response. */
function renderRequest(r, parent) {
  setComposer(r, false);
  base = {
    as_of: r.as_of,
    context: r.context || { kind: 'general' },
    parent_turn_id: r.parent_turn_id || null,
    parent: { n: 1, r: parent }
  };
  if (parent) document.querySelector('[data-turns]').appendChild(priorLine(parent, 1));
  document.getElementById('q').value = r.question;
  showNonAnswer(demo, composerRequest(), false);
}
