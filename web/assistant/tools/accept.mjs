// Acceptance checks for the Ask section prototype (docs/PLAN_13_ASSISTANT_UX_PLAN.md §6).
//
// Usage:
//   PLAYWRIGHT=<abs path to playwright's index.mjs> \
//     node web/assistant/tools/accept.mjs web/assistant/index.html web/assistant/fixtures [--shots=<dir>]
//
// Playwright is deliberately NOT a repository dependency. Install it anywhere outside the repo and
// point PLAYWRIGHT at it (see web/assistant/README.md). CHROMIUM overrides the browser binary; the
// default is the Playwright-cached Chromium on this Mac.
//
// DOM hooks the prototype MUST expose (the check is the spec):
//   index.html?fixture=<name>          renders that fixture (embedded via fixtures.js)
//   [data-state="answered|partial|out_of_scope"]   exactly one, on the answer container
//   [data-state-heading]               the heading word(s) that name the state, as visible text
//   [data-figure]                      one per figures[] item; visible amount, instrument, effective_from
//   [data-citation]                    one Sources record per citation / confirmed ref; NOT a tab stop
//   [data-marker="<ref>"]              the button in the card that moves focus to that record
//   [data-back]                        inside each record: returns focus to the answer
//   [data-source-panel]                the source panel; reachable by keyboard
//   [data-composer]                    the question input; reached early in the tab order and before
//                                      any citation (the pane's own tab strip legitimately precedes it)
//   [data-law-version]                 the section-text as-of ("Text as ingested …")
//   [data-chrome]                      a label the response did not supply (exempt from check 6)
//   [data-group]                       a group label; must be a heading element
//   [data-disclosure]                  a show/hide control; must carry aria-expanded
//   [data-confirmed-item] [data-superseded-item] [data-not-confirmed-item]
//                                      one per array element, inside the card <article>
//   no ?fixture                        the empty state: the title as the page's one h1, no answer
//   ?state=waiting|cancelled|error     a non-answer state: on load for ?fixture='s request; with no
//                                      fixture, the empty page shows it when Ask is pressed
//   [data-nonanswer="waiting|cancelled|error"]  the one card for it: an <article>, never [data-state]
//   [data-cancel] [data-send-again]    its buttons
//
// FONTS_DIR=<dir> (optional) loads the brand fonts from a local folder for screenshots only --
// the finalized frontend self-hosts Fraunces / Inter / IBM Plex Mono; the prototype names them and
// falls back to system faces. No font file is copied into this repository.
import { readFileSync, readdirSync, mkdirSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { resolve, join, basename } from 'node:path';

const [, , page_, fixturesDir, ...flags] = process.argv;
if (!page_ || !fixturesDir) {
  console.error('usage: PLAYWRIGHT=<path> node accept.mjs <index.html> <fixtures-dir> [--shots=dir]');
  process.exit(2);
}
const pwPath = process.env.PLAYWRIGHT;
const { chromium } = await import(pwPath ? pathToFileURL(resolve(pwPath)).href : 'playwright');
const shots = (flags.find(f => f.startsWith('--shots=')) || '').split('=')[1];
if (shots) mkdirSync(shots, { recursive: true });
const exe = process.env.CHROMIUM ||
  `${process.env.HOME}/Library/Caches/ms-playwright/chromium-1208/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing`;
const WIDTHS = [320, 360, 768, 1024, 1440];
const FONTS = process.env.FONTS_DIR ? [
  ['Fraunces', 'Fraunces-Variable.ttf', '100 900'],
  ['Inter', 'Inter-Variable.ttf', '100 900'],
  ['IBM Plex Mono', 'IBMPlexMono-Regular.ttf', '400'],
  ['IBM Plex Mono', 'IBMPlexMono-Medium.ttf', '500'],
].map(([family, file, weight]) =>
  `@font-face{font-family:"${family}";src:url("${pathToFileURL(join(process.env.FONTS_DIR, file)).href}");font-weight:${weight};}`).join('') : '';
async function withFonts(page) {
  if (!FONTS) return;
  await page.addStyleTag({ content: FONTS });
  await page.evaluate(() => document.fonts.ready);
}
// The design's state words are Answered / Abstained in part (Abstained, when nothing was
// confirmed) / Not held -- the finalized site's vocabulary ("Ask. Verify. Cite. Or abstain.").
const HEADING_WORD = {
  answered: /answered/i,
  partial: /abstained/i,
  out_of_scope: /outside|not held|out of scope/i,
};

const fixtures = readdirSync(fixturesDir).filter(f => f.endsWith('.json'))
  .map(f => ({ name: basename(f, '.json'), data: JSON.parse(readFileSync(join(fixturesDir, f), 'utf8')) }));
const results = [];
const fail = (fx, w, msg) => results.push({ ok: false, fx, w, msg });
const pass = (fx, w, msg) => results.push({ ok: true, fx, w, msg });

// Every number-like token the fixture supplies, so an on-screen number can be traced to it.
function fixtureNumbers(obj, acc = new Set()) {
  if (obj == null) return acc;
  if (typeof obj === 'string' || typeof obj === 'number') {
    for (const m of String(obj).matchAll(/\d[\d,.]*\d|\d/g)) acc.add(m[0].replace(/,/g, ''));
  } else if (Array.isArray(obj)) obj.forEach(v => fixtureNumbers(v, acc));
  else if (typeof obj === 'object') Object.values(obj).forEach(v => fixtureNumbers(v, acc));
  return acc;
}

// Numbers in visible, non-chrome text that the fixture did not supply.
async function inventedNumbers(page, allowedNums) {
  const screenNums = await page.evaluate(() => {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const out = [];
    while (walker.nextNode()) {
      const n = walker.currentNode;
      const el = n.parentElement;
      if (!el || el.closest('[data-chrome],script,style') || !el.offsetParent) continue;
      for (const m of n.textContent.matchAll(/\d[\d,.]*\d|\d/g)) out.push(m[0].replace(/,/g, ''));
    }
    return out;
  });
  return [...new Set(screenNums.filter(x => !allowedNums.has(x) && !allowedNums.has(x.replace(/\.$/, ''))))];
}

// The longest transition or animation any element declares, in ms.
async function worstMotion(page) {
  return page.evaluate(() => {
    let worst = 0;
    for (const el of document.querySelectorAll('*')) {
      const cs = getComputedStyle(el);
      for (const v of [cs.transitionDuration, cs.animationDuration]) {
        for (const p of v.split(',')) {
          const t = p.trim();
          const ms = t.endsWith('ms') ? parseFloat(t) : parseFloat(t) * 1000;
          if (ms > worst) worst = ms;
        }
      }
    }
    return worst;
  });
}

const browser = await chromium.launch({ executablePath: exe, headless: true });
try {
  for (const { name, data } of fixtures) {
    const allowedNums = fixtureNumbers(data);
    for (const w of WIDTHS) {
      const ctx = await browser.newContext({
        viewport: { width: w, height: 900 },
        reducedMotion: w === 320 ? 'reduce' : 'no-preference',
      });
      const page = await ctx.newPage();
      const external = [];
      await page.route('**/*', r => {
        const u = r.request().url();
        if (u.startsWith('file:') || u.startsWith('data:')) return r.continue();
        external.push(u);
        return r.abort();
      });
      const errors = [];
      page.on('pageerror', e => errors.push(String(e)));
      await page.goto(`${pathToFileURL(resolve(page_)).href}?fixture=${encodeURIComponent(name)}`, { waitUntil: 'load' });
      await withFonts(page);
      await page.waitForTimeout(150);
      if (errors.length) fail(name, w, `page errors: ${errors.join(' | ').slice(0, 200)}`);
      if (external.length) fail(name, w, `external requests attempted: ${external.length} (${external[0]})`);

      // 1. exactly one state, equal to the fixture's
      const states = await page.$$eval('[data-state]', els => els.map(e => e.getAttribute('data-state')));
      if (states.length !== 1 || states[0] !== data.state) fail(name, w, `expected one [data-state]=${data.state}, got ${JSON.stringify(states)}`);
      else pass(name, w, 'state rendered from fixture');

      // 2. the state is named in words, so it survives grayscale
      const heading = (await page.$eval('[data-state-heading]', e => e.innerText).catch(() => '')).trim();
      if (!HEADING_WORD[data.state]?.test(heading)) fail(name, w, `state heading ${JSON.stringify(heading)} does not name ${data.state} in words`);
      else pass(name, w, 'state named in words');

      // 3. no horizontal overflow
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
      if (overflow) fail(name, w, 'horizontal overflow'); else pass(name, w, 'no overflow');

      // 4. every figure shows its amount, instrument and in-force date
      for (const f of data.figures || []) {
        const txt = await page.$$eval('[data-figure]', els => els.map(e => e.innerText).join('\n'));
        const [y, m, d] = f.effective_from.split('-');
        const mon = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][Number(m) - 1];
        const dateShown = [f.effective_from, `${d}-${m}-${y}`, `${d}/${m}/${y}`, `${d}-${mon}-${y}`].some(s => txt.includes(s));
        const instShown = txt.includes(f.instrument.split(',')[0]);
        if (!(txt.includes(f.amount) && instShown && dateShown)) fail(name, w, `figure ${f.key} missing amount/instrument/in-force date on screen`);
        else pass(name, w, `figure ${f.key} dated inline`);
      }

      // 5. the section-text as-of is rendered wherever citations are
      if (['rows', 'confirmed', 'superseded', 'citations'].some(k => (data[k] || []).length)) {
        if (!(await page.$('[data-law-version]'))) fail(name, w, 'legal content shown without [data-law-version]');
        else pass(name, w, 'law version shown');
      }

      // 6. no number on screen that the fixture did not supply (chrome is exempt)
      const invented = await inventedNumbers(page, allowedNums);
      if (invented.length) fail(name, w, `numbers on screen not in the fixture: ${invented.slice(0, 8).join(', ')}`);
      else pass(name, w, 'every number traceable to the fixture');

      if (shots && (w === 360 || w === 1440)) {
        await page.screenshot({ path: join(shots, `${name}-${w}.png`), fullPage: true });
        await page.addStyleTag({ content: 'html{filter:grayscale(1)!important}' });
        await page.screenshot({ path: join(shots, `${name}-${w}-gray.png`), fullPage: true });
        await page.addStyleTag({ content: 'html{filter:none!important}' });
      }

      // 7. keyboard (PLAN §6 check 3, red team A11Y-4): the composer is reached early; citation
      //    records are NOT tab stops -- each is reached through a [data-marker] button in the card,
      //    and activating the marker moves focus to its record, which offers "Back to answer".
      if (w === 1440 || w === 360) {
        let composerStop = -1;
        const markersReached = new Set();
        for (let i = 0; i < 60; i++) {
          await page.keyboard.press('Tab');
          const info = await page.evaluate(() => {
            const a = document.activeElement;
            return { composer: !!a?.closest('[data-composer]'), marker: a?.getAttribute?.('data-marker') ?? null };
          });
          if (info.composer && composerStop < 0) composerStop = i;
          if (info.marker) markersReached.add(info.marker);
        }
        if (composerStop < 0 || composerStop > 6) fail(name, w, `composer not reached in the first 6 tab stops (stop ${composerStop})`);
        else pass(name, w, 'composer reached early in tab order');
        const tabbableRecords = await page.$$eval('[data-citation]', els => els.filter(e => e.tabIndex >= 0).length);
        if (tabbableRecords) fail(name, w, `${tabbableRecords} citation record(s) are tab stops that do nothing (A11Y-4)`);
        else pass(name, w, 'citation records are not empty tab stops');
        const refs = await page.$$eval('[data-citation]', els => [...new Set(els.map(e => e.getAttribute('data-citation')))]);
        for (const ref of refs) {
          if (!markersReached.has(ref)) { fail(name, w, `no keyboard-reachable marker for ${ref}`); continue; }
          await page.focus(`[data-marker="${ref}"]`);
          await page.keyboard.press('Enter');
          const landed = await page.evaluate(r => document.activeElement?.closest('[data-citation]')?.getAttribute('data-citation') === r, ref);
          const back = await page.$(`[data-citation="${ref}"] [data-back]`);
          if (!landed) fail(name, w, `marker for ${ref} does not move focus to its record`);
          else if (!back) fail(name, w, `record ${ref} has no "Back to answer" control`);
          else pass(name, w, `marker → record → back for ${ref}`);
        }
      }

      // 7b. every disclosure says whether it is open (red team A11Y-6)
      const noExpanded = await page.$$eval('[data-disclosure]', els => els.filter(e => !e.hasAttribute('aria-expanded')).length);
      if (noExpanded) fail(name, w, `${noExpanded} disclosure(s) without aria-expanded`); else pass(name, w, 'disclosures carry aria-expanded');

      // 7c. structure (red team A11Y-2, A11Y-7): one h1; every group label is a heading
      const struct = await page.evaluate(() => ({
        h1: document.querySelectorAll('h1').length,
        badGroups: [...document.querySelectorAll('[data-group]')].filter(e => !/^H[2-4]$/.test(e.tagName)).length,
      }));
      if (struct.h1 !== 1) fail(name, w, `expected exactly one h1, found ${struct.h1}`);
      else if (struct.badGroups) fail(name, w, `${struct.badGroups} group label(s) are not headings`);
      else pass(name, w, 'one h1; group labels are headings');

      // 7d. confirmed items are in the card, counted by the array (red team L1, DQ1, L3, NG-7)
      if (data.state === 'partial') {
        const n = await page.$$eval('article [data-confirmed-item]', els => els.length);
        const want = (data.confirmed || []).length;
        const cardText = await page.$eval('article', e => e.innerText);
        if (n !== want) fail(name, w, `card renders ${n} confirmed item(s), the response has ${want}`);
        else if (want === 0 && !/Confirmed: none/i.test(cardText)) fail(name, w, 'empty confirmed[] without "Confirmed: none"');
        else pass(name, w, 'confirmed items rendered in the card');
      }

      const supWant = (data.superseded || []).length;
      if (supWant) {
        const supN = await page.$$eval('article [data-superseded-item]', els => els.length);
        if (supN !== supWant) fail(name, w, `card renders ${supN} superseded item(s), the response has ${supWant}`);
        else pass(name, w, 'superseded items rendered');
      }

      // 7e. the model line is always there (red team NG-4)
      const cardAll = await page.$eval('article', e => e.innerText).catch(() => '');
      if (!/No model used|A model was used|Model use: not stated/.test(cardAll)) fail(name, w, 'no model-use line on the card');
      else pass(name, w, 'model use stated');

      // 7f. a follow-up says what it follows (red team NG-8)
      if (data.parent_turn_id && !/Follow-up to turn/.test(cardAll)) fail(name, w, 'follow-up turn without its parent line');
      else if (data.parent_turn_id) pass(name, w, 'parent line shown');

      // 7g. nothing overclaims (red team L5, L10, NG-3)
      // The user's own words are excluded: a question may say anything; the page may not.
      const pageText = await page.evaluate(() => {
        const out = [];
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        while (walker.nextNode()) {
          const el = walker.currentNode.parentElement;
          if (!el || el.closest('[data-f="question"],script,style') || !el.offsetParent) continue;
          out.push(walker.currentNode.textContent);
        }
        return out.join(' ');
      });
      const over = ['still current', 'holds the law as it stands', 'Source link: not recorded'].filter(p => pageText.includes(p));
      if (over.length) fail(name, w, `overclaiming copy on screen: ${over.join(' | ')}`); else pass(name, w, 'no overclaiming copy');

      // 7h. a duty is printed once per turn (red team L8, DQ8)
      if (data.scope_frame) {
        const whats = data.scope_frame.unchecked.map(u => u.what);
        const dupes = await page.evaluate(ws => {
          const card = document.querySelector('article');
          const visible = [...card.querySelectorAll('[data-not-confirmed-item]')].filter(e => e.offsetParent);
          return visible.filter(e => ws.some(w => e.innerText.includes(w))).length;
        }, whats);
        if (dupes) fail(name, w, `${dupes} not-confirmed item(s) repeat a duty the scope frame already names`);
        else pass(name, w, 'each duty printed once');
      }

      // 7i. input borders meet 3:1 (red team A11Y-5, WCAG 1.4.11)
      const ratio = await page.evaluate(() => {
        const lum = c => { const [r, g, b] = c.match(/\d+/g).slice(0, 3).map(Number).map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
        const t = document.querySelector('[data-composer] textarea');
        if (!t) return null;
        let bg = 'rgb(255,255,255)', el = t.parentElement;
        while (el) { const c = getComputedStyle(el).backgroundColor; if (!/rgba\(0, 0, 0, 0\)|transparent/.test(c)) { bg = c; break; } el = el.parentElement; }
        const a = lum(getComputedStyle(t).borderTopColor), b = lum(bg);
        return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
      });
      if (ratio !== null && ratio < 3) fail(name, w, `question field border contrast ${ratio.toFixed(2)}:1 < 3:1`);
      else pass(name, w, 'input border contrast >= 3:1');

      // 7j. Ask does not navigate away, and says what happened (red team NG-1, A11Y-1)
      if (w === 360) {
        const before = page.url();
        await page.fill('[data-composer] textarea', 'a test question');
        await page.click('[data-composer] [type=submit]');
        await page.waitForTimeout(150);
        const after = page.url();
        const status = await page.$eval('[role=status]', e => e.innerText.trim()).catch(() => '');
        const kept = await page.$eval('[data-composer] textarea', e => e.value).catch(() => '');
        if (after !== before) fail(name, w, `pressing Ask navigated to ${after}`);
        else if (!status) fail(name, w, 'pressing Ask announced nothing');
        else if (kept !== 'a test question') fail(name, w, 'pressing Ask discarded the question');
        else pass(name, w, 'Ask stays, keeps the question, and says why nothing was sent');
      }

      // 8. motion: nothing over 200ms, and nothing at all under prefers-reduced-motion
      const motion = await worstMotion(page);
      if (motion > 200) fail(name, w, `motion ${motion}ms exceeds 200ms`);
      else if (w === 320 && motion > 0) fail(name, w, `motion ${motion}ms under prefers-reduced-motion`);
      else pass(name, w, 'motion within limits');

      await ctx.close();
    }
  }
} finally {
  await browser.close();
}

{
  const b2 = await chromium.launch({ executablePath: exe, headless: true });
  try {
    for (const w of [360, 1440]) {
      const ctx = await b2.newContext({ viewport: { width: w, height: 900 } });
      const page = await ctx.newPage();
      await page.route('**/*', r => (/^(file|data):/.test(r.request().url()) ? r.continue() : r.abort()));
      await page.goto(pathToFileURL(resolve(page_)).href, { waitUntil: 'load' });
      await withFonts(page);
      const empty = await page.evaluate(() => ({
        states: document.querySelectorAll('[data-state]').length,
        h1: [...document.querySelectorAll('h1')].map(h => h.innerText.trim()),
        overflow: document.documentElement.scrollWidth > window.innerWidth + 1,
      }));
      if (empty.states) fail('empty', w, 'the empty state renders an answer');
      else if (empty.h1.length !== 1 || !/Companies Act, 2013/.test(empty.h1[0])) fail('empty', w, `empty title missing: ${JSON.stringify(empty.h1)}`);
      else if (empty.overflow) fail('empty', w, 'horizontal overflow');
      else pass('empty', w, 'empty state: title, no answer');
      if (shots) await page.screenshot({ path: join(shots, `empty-${w}.png`), fullPage: true });
      await ctx.close();
    }
  } finally {
    await b2.close();
  }
}

// 13. The three non-answer states (PLAN_13 §4.4, §7.3, §7.11; copy verbatim from §13), both themes.
//     ?state=waiting|cancelled|error. With ?fixture= the page shows the state that fixture's request
//     was in, on load; without one the page is empty until Ask is pressed. None of the three is a
//     server state, so none carries [data-state]; and the service error must never read as an
//     abstention (placedon-claude-legal-3300 AGENTS.md: a transport failure is never rendered as an
//     abstention) -- no abstention class, grey, dashed mark, glyph or state word, and not on paper.
const NA_COPY = {
  waiting: "Waiting for the server's decision.",
  cancelled: 'Cancelled before a result arrived. Nothing is shown.',
  errorHead: 'No result',
  error: 'The service did not return a result, so there is no answer, partial or otherwise. Your question is still in the box.',
  docLine: 'Nothing was changed in your document.',
};
const NA_STATES = ['waiting', 'cancelled', 'error'];
const NA_WIDTHS = [360, 1440];
const NA_SHOTS = new Set(['', 'document_context_2024', 'followup_turnover']);
const TYPED = 'Does this company need a CSR committee?';

// Everything the checks need about the (one) non-answer card and the composer.
async function naFacts(page) {
  return page.evaluate(() => {
    const ABSTAIN = 'rgb(91, 100, 114)';     // --abstain #5b6472
    const PAPER = 'rgb(251, 248, 242)';      // --paper #fbf8f2, the answer's sheet
    const cards = [...document.querySelectorAll('[data-nonanswer]')];
    const card = cards[0] || null;
    const ta = document.querySelector('[data-composer] textarea');
    const ask = document.querySelector('[data-composer] [type=submit]');
    const a = document.activeElement;
    const btns = sel => [...(card ? card.querySelectorAll(sel) : [])]
      .map(b => ({ tag: b.tagName, type: b.getAttribute('type'), text: b.innerText.trim(), tabIndex: b.tabIndex }));
    const qEl = card && card.querySelector('[data-f="question"]');
    const f = {
      n: cards.length,
      kind: card && card.getAttribute('data-nonanswer'),
      tag: card && card.tagName,
      h2: card && card.querySelector('h2') ? card.querySelector('h2').innerText.trim() : null,
      paras: card ? [...card.querySelectorAll('p')].map(p => p.innerText.trim()) : [],
      text: card ? card.innerText : '',
      html: card ? card.innerHTML : '',
      question: qEl ? qEl.innerText.trim() : null,
      states: document.querySelectorAll('[data-state]').length,
      h1: document.querySelectorAll('h1').length,
      box: ta ? ta.value : null,
      boxLocked: !!ta && (ta.readOnly || ta.disabled || ta.getAttribute('aria-disabled') === 'true'),
      askLocked: !!ask && (ask.disabled || ask.getAttribute('aria-disabled') === 'true'),
      focusCancel: !!a && a.hasAttribute('data-cancel'),
      focusAgain: !!a && a.hasAttribute('data-send-again'),
      focusHead: !!card && !!a && a.tagName === 'H2' && card.contains(a),
      cancel: btns('[data-cancel]'),
      again: btns('[data-send-again]'),
      progress: document.querySelectorAll('progress,[role=progressbar],[aria-valuenow],[class*=skeleton],[class*=spinner]').length,
      // A spinner, a skeleton pulse or any client-timed progress is either endless or longer
      // than the 200ms budget worstMotion() enforces; a button's own 140ms focus transition,
      // still in flight because the machine is busy, is neither. Counting only the first kind
      // keeps "the waiting card does nothing by itself" true without depending on the clock.
      running: document.getAnimations ? document.getAnimations().filter(a => {
        const t = a.effect && a.effect.getComputedTiming ? a.effect.getComputedTiming() : null;
        if (!t) return true;
        return t.iterations === Infinity || !(t.activeDuration <= 200);
      }).length : 0,
      overflow: document.documentElement.scrollWidth > window.innerWidth + 1,
    };
    if (!card) return f;
    const all = [card, ...card.querySelectorAll('*')];
    const cls = e => String(e.className && e.className.baseVal !== undefined ? e.className.baseVal : e.className || '');
    f.abstainClass = all.filter(e => /abstain|badge/.test(cls(e))).length;
    f.glyphs = card.querySelectorAll('svg,.glyph,[data-state-heading],[data-state]').length;
    f.dashed = all.filter(e => {
      const cs = getComputedStyle(e);
      return ['Top', 'Right', 'Bottom', 'Left'].some(s => cs[`border${s}Style`] === 'dashed' && parseFloat(cs[`border${s}Width`]) > 0);
    }).length;
    // Not one exact value: any COOL grey near the abstention grey counts, so a colour one unit off
    // (#5c6573, found by the ASK-3 verifier) cannot pass. Warm greys (--grey #6b665f) are excluded
    // by hue (blue channel above red), which is what makes the abstention grey read as abstention.
    const [ar, ag, ab] = ABSTAIN.match(/\d+/g).map(Number);
    const nearAbstain = c => {
      const m = String(c).match(/\d+(\.\d+)?/g);
      if (!m || m.length < 3 || (m.length > 3 && Number(m[3]) === 0)) return false;
      const [r, g, b] = m.slice(0, 3).map(Number);
      return b - r >= 12 && Math.hypot(r - ar, g - ag, b - ab) <= 30;
    };
    f.abstainHue = all.filter(e => {
      const cs = getComputedStyle(e);
      return [cs.color, cs.backgroundColor, cs.borderTopColor, cs.borderRightColor,
              cs.borderBottomColor, cs.borderLeftColor].some(nearAbstain);
    }).length;
    f.onPaper = getComputedStyle(card).backgroundColor === PAPER;
    // Any form of "abstain" and the state glyph characters, not only the four state words.
    f.stateWords = /\b(Answered|Partly answered|Not held)\b|abstain|[■◧◨◩□▣▢]/i.test(card.innerText);
    const lum = c => { const [r, g, b] = c.match(/\d+/g).slice(0, 3).map(Number).map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
    let bg = 'rgb(255, 255, 255)', e = card.parentElement;
    while (e) { const c = getComputedStyle(e).backgroundColor; if (!/rgba\(0, 0, 0, 0\)|transparent/.test(c)) { bg = c; break; } e = e.parentElement; }
    const cs = getComputedStyle(card);
    const x = lum(cs.borderTopColor), y = lum(bg);
    f.border = { style: cs.borderTopStyle, width: parseFloat(cs.borderTopWidth), ratio: (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05) };
    return f;
  });
}

async function tabReaches(page, attr, max = 40) {
  for (let i = 0; i < max; i++) {
    await page.keyboard.press('Tab');
    if (await page.evaluate(a => !!document.activeElement && document.activeElement.hasAttribute(a), attr)) return i + 1;
  }
  return -1;
}

// What every non-answer card must be, wherever it came from.
async function checkNonAnswer(page, S, question, src, w, at) {
  const f = await naFacts(page);
  const copyOk = S === 'waiting' ? f.h2 === NA_COPY.waiting && f.cancel.length === 1 && f.cancel[0].text === 'Cancel'
    : S === 'cancelled' ? f.h2 === NA_COPY.cancelled && f.cancel.length === 0
    : f.h2 === NA_COPY.errorHead && f.paras.includes(NA_COPY.error) && f.again.length === 1 && f.again[0].text === 'Send again';
  if (f.n !== 1 || f.kind !== S) fail(at, w, `expected one [data-nonanswer=${S}], got ${f.n} (${f.kind})`);
  else if (f.tag !== 'ARTICLE' || f.h2 === null) fail(at, w, `the ${S} card is not an article with its own h2`);
  else if (!copyOk) fail(at, w, `the ${S} card does not carry §13's exact copy (h2 ${JSON.stringify(f.h2)})`);
  else pass(at, w, `${S}: §13 copy verbatim, in an article with its own h2`);
  if (!f.n) return;

  if (f.states) fail(at, w, `${f.states} [data-state] on a ${S} page: it is not a server state`);
  else if (f.glyphs) fail(at, w, `${f.glyphs} state glyph(s) in the ${S} card`);
  else pass(at, w, `${S}: no [data-state], no state glyph`);

  if (S === 'error') {
    const bad = [
      f.abstainClass && `${f.abstainClass} abstention/badge class(es)`,
      f.dashed && `${f.dashed} dashed border(s)`,
      f.abstainHue && `${f.abstainHue} element(s) in the abstention grey`,
      f.onPaper && 'drawn on Compliance Note paper, like an answer',
      f.stateWords && 'a state word',
      !(f.border.style === 'solid' && f.border.width >= 1 && f.border.ratio >= 3)
        && `border ${f.border.style} ${f.border.width}px at ${f.border.ratio.toFixed(2)}:1 (needs solid, >= 3:1)`,
    ].filter(Boolean);
    if (bad.length) fail(at, w, `the service error looks like an answer or an abstention: ${bad.join('; ')}`);
    else pass(at, w, 'error: nothing an abstention carries; its own solid border >= 3:1');
  }

  if (f.box !== question) fail(at, w, `the question box holds ${JSON.stringify(f.box)}, not the question`);
  else if (S !== 'error' && f.question !== question) fail(at, w, `the ${S} card shows ${JSON.stringify(f.question)} as the question`);
  else pass(at, w, `${S}: the question is still in the box`);

  const lockedRight = S === 'waiting' ? f.boxLocked && f.askLocked : !f.boxLocked && !f.askLocked;
  if (!lockedRight) fail(at, w, S === 'waiting' ? 'the composer is not disabled while waiting' : `the composer is still disabled on a ${S} card`);
  else pass(at, w, S === 'waiting' ? 'composer disabled while waiting' : `${S}: composer usable again`);

  if (S === 'waiting') {
    await page.waitForTimeout(400);
    const g = await naFacts(page);
    if (f.progress || g.progress || g.running) fail(at, w, `progress indicator or running animation while waiting (${g.progress}/${g.running})`);
    else if (g.html !== f.html) fail(at, w, 'the waiting card changed by itself: client-timed progress');
    else pass(at, w, 'waiting: static -- no spinner, skeleton, timer, stage or animation');
  }

  if (f.overflow) fail(at, w, 'horizontal overflow'); else pass(at, w, `${S}: no overflow`);
  if (f.h1 !== 1) fail(at, w, `expected exactly one h1, found ${f.h1}`); else pass(at, w, `${S}: one h1`);

  const motion = await worstMotion(page);
  if (motion > 200) fail(at, w, `motion ${motion}ms exceeds 200ms`);
  else if (w === 360 && motion > 0) fail(at, w, `motion ${motion}ms under prefers-reduced-motion`);
  else pass(at, w, `${S}: motion within limits`);

  if (src) {
    const doc = src.data.context && src.data.context.kind === 'document';
    const miss = [];
    if (S !== 'error' && doc && !/About the open document · dated/.test(f.text)) miss.push('the document band');
    if (S !== 'error' && src.data.parent_turn_id && !/Follow-up to turn/.test(f.text)) miss.push('the parent line');
    if (S !== 'error' && !/Asked as of/.test(f.text)) miss.push('the stamp');
    if (S === 'error' && doc && !f.paras.includes(NA_COPY.docLine)) miss.push(`"${NA_COPY.docLine}"`);
    const invented = await inventedNumbers(page, fixtureNumbers(src.data));
    if (invented.length) miss.push(`numbers not in the request: ${invented.slice(0, 6).join(', ')}`);
    if (miss.length) fail(at, w, `${S}: request values wrong: ${miss.join('; ')}`);
    else pass(at, w, `${S}: carries the request values the user set, and no others`);
  }
}

// Without a fixture: the page is empty until Ask; Ask brings the card and moves focus (§15).
async function arriveByAsk(page, S, w, at) {
  const f0 = await naFacts(page);
  if (f0.n || f0.states) fail(at, w, 'a card on the empty page before anything was asked');
  else pass(at, w, 'empty until Ask is pressed');
  await page.fill('[data-composer] textarea', TYPED);
  await page.focus('[data-composer] textarea');
  await page.keyboard.press('Enter');
  const f1 = await naFacts(page);
  if (S === 'error') {
    if (f1.kind !== 'error' || !f1.focusHead) { fail(at, w, `Ask did not bring "No result" with focus on its heading (${f1.kind})`); return; }
    await page.keyboard.press('Tab');
    const f2 = await naFacts(page);
    if (!f2.focusAgain || f2.again[0]?.tag !== 'BUTTON') fail(at, w, 'Send again is not a button reached by Tab from the heading');
    else pass(at, w, 'Ask -> "No result", focus on its heading; Send again is the next tab stop');
    return;
  }
  if (f1.kind !== 'waiting' || !f1.focusCancel || f1.cancel[0]?.tag !== 'BUTTON') { fail(at, w, `Ask did not bring the waiting card with focus on its Cancel button (${f1.kind})`); return; }
  await page.focus('[data-composer] textarea');
  await page.keyboard.press('Enter');
  const f2 = await naFacts(page);
  if (f2.n !== 1 || f2.kind !== 'waiting') fail(at, w, 'Enter while waiting sent the question again');
  else pass(at, w, 'Ask -> waiting, focus on Cancel; Enter while waiting sends nothing more');
  if (S !== 'cancelled') { await page.focus('[data-cancel]'); return; }   // where Ask left it
  await page.keyboard.press('Escape');
  const f3 = await naFacts(page);
  if (f3.kind !== 'cancelled' || !f3.focusHead) fail(at, w, 'Esc did not cancel with focus on the card heading');
  else pass(at, w, 'Esc cancels; focus on the cancelled card heading');
}

// With a fixture nothing moved focus on load, so the button must be reachable by Tab.
async function checkReach(page, S, w, at) {
  if (S === 'cancelled') return;
  const attr = S === 'waiting' ? 'data-cancel' : 'data-send-again';
  const name = S === 'waiting' ? 'Cancel' : 'Send again';
  const stop = await tabReaches(page, attr);
  const b = (await naFacts(page))[S === 'waiting' ? 'cancel' : 'again'][0];
  if (stop < 0) fail(at, w, `${name} is not reached by Tab`);
  else if (!b || b.tag !== 'BUTTON' || b.type !== 'button') fail(at, w, `${name} is not a <button type=button>`);
  else pass(at, w, `${name} is a button reached by Tab`);
}

// Focus an element and press Enter on it, as a keyboard user would; false if it is not there.
async function pressOn(page, sel) {
  if (!(await page.$(sel))) return false;
  await page.focus(sel);
  await page.keyboard.press('Enter');
  return true;
}

// What each state's control does.
async function checkTransition(page, S, question, w, at) {
  if (S === 'waiting') {
    if (!(await pressOn(page, '[data-cancel]'))) { fail(at, w, 'no Cancel button to press'); return; }
    const f = await naFacts(page);
    if (f.n !== 1 || f.kind !== 'cancelled' || f.h2 !== NA_COPY.cancelled) fail(at, w, `Cancel did not rewrite the card as cancelled (${f.kind})`);
    else if (!f.focusHead) fail(at, w, 'after Cancel, focus is not on the cancelled card heading');
    else if (f.box !== question || f.boxLocked || f.askLocked || !/Asked as of/.test(f.text)) fail(at, w, 'after Cancel, the question, the composer or the stamp was lost');
    else pass(at, w, 'Cancel -> cancelled copy, stamp kept, focus on its heading, question in the box');
  } else if (S === 'cancelled') {
    await pressOn(page, '[data-composer] textarea');
    const f = await naFacts(page);
    await page.keyboard.press('Escape');
    const g = await naFacts(page);
    if (f.n !== 1 || f.kind !== 'waiting' || !f.focusCancel) fail(at, w, `asking again from a cancelled card did not wait (${f.kind})`);
    else if (g.n !== 1 || g.kind !== 'cancelled' || !g.focusHead || g.box !== question) fail(at, w, 'Esc did not cancel the second wait');
    else pass(at, w, 'asking again waits; Esc cancels; the question stays');
  } else {
    if (!(await pressOn(page, '[data-send-again]'))) { fail(at, w, 'no Send again button to press'); return; }
    const f = await naFacts(page);
    if (f.n !== 1 || f.kind !== 'error' || !f.focusHead || f.box !== question) fail(at, w, `Send again did not leave one "No result" with focus on its heading (${f.n} ${f.kind})`);
    else pass(at, w, 'Send again -> one fresh "No result", focus on its heading, question in the box');
  }
}

{
  const b3 = await chromium.launch({ executablePath: exe, headless: true });
  try {
    for (const S of NA_STATES) {
      for (const src of [null, ...fixtures]) {
        const fx = src ? src.name : '';
        const at = `state=${S}${fx ? ` fixture=${fx}` : ''}`;
        const question = src ? src.data.question : TYPED;
        for (const w of NA_WIDTHS) {
          const ctx = await b3.newContext({ viewport: { width: w, height: 900 }, reducedMotion: w === 360 ? 'reduce' : 'no-preference' });
          const page = await ctx.newPage();
          const external = [], errors = [];
          await page.route('**/*', r => {
            const u = r.request().url();
            if (/^(file|data):/.test(u)) return r.continue();
            external.push(u);
            return r.abort();
          });
          page.on('pageerror', e => errors.push(String(e)));
          const qs = (fx ? `fixture=${encodeURIComponent(fx)}&` : '') + `state=${S}`;
          await page.goto(`${pathToFileURL(resolve(page_)).href}?${qs}`, { waitUntil: 'load' });
          await withFonts(page);
          if (src) {
            await checkNonAnswer(page, S, question, src, w, at);
            await checkReach(page, S, w, at);
          } else {
            await arriveByAsk(page, S, w, at);
            await checkNonAnswer(page, S, question, null, w, at);
          }
          if (shots && NA_SHOTS.has(fx)) {
            await page.screenshot({ path: join(shots, `state-${S}${fx ? `-${fx}` : ''}-${w}.png`), fullPage: true });
          }
          await checkTransition(page, S, question, w, at);
          if (errors.length || external.length) fail(at, w, `page errors or network: ${[...errors, ...external].join(' | ').slice(0, 200)}`);
          else pass(at, w, `${S}: no page errors, no network`);
          await ctx.close();
        }
      }
    }
  } finally {
    await b3.close();
  }
}

// 14. Live mode (D2): the same page served by scripts/serve_ask.py on a free loopback port. Ask
//     sends {question, context} to POST /v1/ask on that origin and renders the SERVER's reply
//     through the fixtures' renderer; while the request is out the page shows the waiting card
//     and Cancel aborts it; a dead server, a non-200 or a reply that is not a placedon.ask/0 turn
//     is the service error, never an abstention. ?fixture= and ?state= keep working over http.
const LIVE_QUESTIONS = [
  // Question-only, so the route answers only what it can read in the words (contract §6 D1):
  // the small-company question names no provision -> partial, found by matching words.
  { slug: 'small-company', q: 'Is this company a small company?', state: 'partial' },
  { slug: 'declared-body', q: 'Do we need to tell the RBI before allotting shares to a foreign investor?', state: 'out_of_scope' },
  { slug: 's173', q: 'What does s.173 require?', state: 'partial' },
];
const LIVE_WIDTHS = [360, 1440];

// A child killed by a signal keeps exitCode null; signalCode says it is gone.
const alive = proc => proc.exitCode === null && proc.signalCode === null;

async function freePort() {
  const { createServer } = await import('node:net');
  return new Promise((res, rej) => {
    const s = createServer();
    s.on('error', rej);
    s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); });
  });
}

// The demo server for the page under test: <repo>/scripts/serve_ask.py serves <repo>/web/assistant.
async function startServer() {
  const { spawn } = await import('node:child_process');
  const repo = resolve(resolve(page_), '..', '..', '..');
  const port = await freePort();
  const proc = spawn('python3', [join(repo, 'scripts', 'serve_ask.py'), '--port', String(port)],
    { cwd: repo, env: { ...process.env, PYTHONPATH: repo }, stdio: ['ignore', 'ignore', 'pipe'] });
  let stderr = '';
  proc.stderr.on('data', d => { stderr += d; });
  const exited = new Promise(r => proc.on('exit', r));
  const origin = `http://127.0.0.1:${port}`;
  for (let i = 0; i < 200; i++) {                      // up to ~20 s for the engine to import
    if (!alive(proc)) break;
    try { if ((await fetch(`${origin}/index.html`)).status === 200) return { origin, proc, exited, stderr: () => stderr }; } catch { /* not up yet */ }
    await new Promise(r => setTimeout(r, 100));
  }
  proc.kill('SIGTERM');
  throw new Error(`serve_ask.py did not come up on ${origin}: ${stderr.slice(0, 300)}`);
}

// A page on the live origin: only that origin is reachable; POST /v1/ask can be held, so the
// waiting state is observed deterministically and released on cue, or answered by the check.
async function livePage(ctx, origin) {
  const page = await ctx.newPage();
  const t = { page, external: [], errors: [], asks: [], held: [], failed: [], hold: false, reply: null };
  page.on('pageerror', e => t.errors.push(String(e)));
  page.on('requestfailed', r => { if (r.url().endsWith('/v1/ask')) t.failed.push(r.failure()?.errorText || 'failed'); });
  await page.route('**/*', async r => {
    const req = r.request();
    const u = req.url();
    if (!u.startsWith(origin + '/')) { t.external.push(u); return r.abort(); }
    if (new URL(u).pathname !== '/v1/ask') return r.continue();
    t.asks.push({ method: req.method(), body: req.postData(), ctype: req.headers()['content-type'] || '' });
    if (t.reply) return r.fulfill(t.reply);
    if (t.hold) { t.held.push(r); return; }
    return r.continue();
  });
  return t;
}

async function release(t) {
  for (const r of t.held.splice(0)) { try { await r.continue(); } catch { /* the page aborted it */ } }
}

const human = iso => { const [y, m, d] = iso.split('-'); return `${d}-${['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][Number(m) - 1]}-${y}`; };

// One question asked through the page, held while the waiting card is checked, then answered
// by the real server; the rendered turn must be that reply's, not a fixture's.
async function liveQuestion(ctx, origin, spec, w, fixtureIds) {
  const at = `live ${spec.slug}`;
  const t = await livePage(ctx, origin);
  const { page } = t;
  await page.goto(`${origin}/`, { waitUntil: 'load' });
  await withFonts(page);
  const note = await page.$eval('[data-concept]', e => e.innerText).catch(() => '');
  if (/Nothing you type is sent/i.test(note) || !/this computer/i.test(note) || !/no model/i.test(note)) fail(at, w, `live concept note is not the live wording: ${JSON.stringify(note)}`);
  else pass(at, w, 'concept note: sent to the engine on this computer only, no model');

  t.hold = true;
  await page.fill('[data-composer] textarea', spec.q);
  await page.focus('[data-composer] textarea');
  await page.keyboard.press('Enter');
  for (let i = 0; i < 100 && !t.held.length; i++) await page.waitForTimeout(50);   // the request reaching the route
  const sent = t.asks[0];
  let body = null;
  try { body = JSON.parse(sent?.body || 'null'); } catch { body = null; }
  const shape = body && JSON.stringify(Object.keys(body).sort()) === '["context","question"]'
    && body.question === spec.q && JSON.stringify(body.context) === '{"kind":"general"}';
  if (t.asks.length !== 1 || sent.method !== 'POST' || !/application\/json/.test(sent.ctype) || !shape) fail(at, w, `Ask did not POST {question, context} once: ${JSON.stringify(t.asks).slice(0, 200)}`);
  else pass(at, w, 'Ask POSTs {question, context:{kind:general}} as JSON to /v1/ask, once');
  const f = await naFacts(page);
  if (f.kind !== 'waiting' || !f.focusCancel || !f.boxLocked || !f.askLocked || f.states) fail(at, w, `no waiting card with focus on Cancel while the request is out (${f.kind})`);
  else pass(at, w, 'waiting card, composer locked, focus on Cancel, while the request is out');

  // No request held means nothing was sent: every check below then fails rather than aborting.
  const replyP = t.held.length ? page.waitForResponse(r => r.url().endsWith('/v1/ask')).catch(() => null) : null;
  t.hold = false;
  await release(t);
  const reply = replyP ? await replyP : null;
  const r = reply ? await reply.json().catch(() => ({})) : {};
  if (reply) await page.waitForSelector('[data-state]', { timeout: 30000 }).catch(() => null);
  const g = await page.evaluate(() => {
    const card = document.querySelector('article[data-state]');
    return {
      states: [...document.querySelectorAll('[data-state]')].map(e => e.getAttribute('data-state')),
      origin: card && card.getAttribute('data-origin'),
      question: card && card.querySelector('[data-f="question"]')?.innerText.trim(),
      stamp: card && card.querySelector('.stamp')?.innerText,
      heading: card && card.querySelector('[data-state-heading]')?.innerText.trim(),
      nonanswer: document.querySelectorAll('[data-nonanswer]').length,
      lawVersion: !!document.querySelector('[data-law-version]'),
      focusQuestion: !!card && document.activeElement === card.querySelector('[data-f="question"]'),
      locked: document.querySelector('[data-composer] textarea').readOnly,
    };
  });
  if (!reply || reply.status() !== 200 || r.schema !== 'placedon.ask/0' || r.state !== spec.state) fail(at, w, `server replied ${reply ? reply.status() : 'nothing'} ${r.state}, expected 200 ${spec.state}`);
  else pass(at, w, `the server answered ${r.state}`);
  if (g.states.length !== 1 || g.states[0] !== r.state || g.origin !== 'live') fail(at, w, `rendered ${JSON.stringify(g.states)} (${g.origin}), not the server's ${r.state}`);
  else if (fixtureIds.has(r.turn_id) || g.question !== spec.q || !g.stamp?.includes(human(r.as_of || '0-1-0'))) fail(at, w, `the rendered turn is not this request's reply (${r.turn_id}, ${JSON.stringify(g.question)}, ${g.stamp})`);
  else pass(at, w, `renders the server's ${r.state} for the typed question, stamped with its as-of, not a fixture`);
  if (!HEADING_WORD[r.state]?.test(g.heading || '') || g.nonanswer || g.locked || !g.focusQuestion) fail(at, w, `after the reply: heading ${JSON.stringify(g.heading)}, ${g.nonanswer} non-answer card(s), locked ${g.locked}, focus on question ${g.focusQuestion}`);
  else pass(at, w, 'state named in words; waiting card gone; composer usable; focus on the question');
  if (['rows', 'confirmed', 'superseded', 'citations'].some(k => (r[k] || []).length) && !g.lawVersion) fail(at, w, 'legal content shown without [data-law-version]');
  else pass(at, w, 'law version wherever legal text is shown');
  const invented = await inventedNumbers(page, fixtureNumbers(r));
  if (invented.length) fail(at, w, `numbers on screen not in the server's reply: ${invented.slice(0, 8).join(', ')}`);
  else pass(at, w, "every number traceable to the server's reply");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  if (overflow) fail(at, w, 'horizontal overflow'); else pass(at, w, 'no overflow');
  if (shots) await page.screenshot({ path: join(shots, `live-${spec.slug}-${w}.png`), fullPage: true });
  if (t.errors.length || t.external.length) fail(at, w, `page errors or network: ${[...t.errors, ...t.external].join(' | ').slice(0, 200)}`);
  else pass(at, w, 'no page errors; nothing left this origin');
  await page.close();
}

// Ask with the reply decided by the check (a 500, a wrong schema, an unknown state) or with the
// server gone: every one is "No result", never an abstention, and the question stays in the box.
async function liveFailure(ctx, origin, w, label, reply, stopServer) {
  const at = `live ${label}`;
  const t = await livePage(ctx, origin);
  const { page } = t;
  await page.goto(`${origin}/`, { waitUntil: 'load' });
  if (stopServer) await stopServer();
  t.reply = reply;
  const q = 'What does s.173 require?';
  await page.fill('[data-composer] textarea', q);
  await page.focus('[data-composer] textarea');
  await page.keyboard.press('Enter');
  await page.waitForSelector('[data-nonanswer="error"]', { timeout: 30000 }).catch(() => null);
  const f = await naFacts(page);
  if (f.kind !== 'error' || f.states || !f.focusHead) fail(at, w, `expected "No result" with focus on its heading, got ${f.kind} (${f.states} state(s))`);
  else pass(at, w, `${label}: the service error, not a state`);
  await checkNonAnswer(page, 'error', q, null, w, at);
  if (shots && w === 1440) await page.screenshot({ path: join(shots, `live-${label.replace(/\W+/g, '-')}-${w}.png`), fullPage: true });
  if (t.errors.length || t.external.length) fail(at, w, `page errors or network: ${[...t.errors, ...t.external].join(' | ').slice(0, 200)}`);
  else pass(at, w, `${label}: no page errors; nothing left this origin`);
  await page.close();
}

{
  const b4 = await chromium.launch({ executablePath: exe, headless: true });
  let srv = null;
  try {
    srv = await startServer();
    const { origin } = srv;
    const fixtureIds = new Set(fixtures.map(f => f.data.turn_id));
    for (const w of LIVE_WIDTHS) {
      const ctx = await b4.newContext({ viewport: { width: w, height: 900 }, reducedMotion: w === 360 ? 'reduce' : 'no-preference' });
      for (const spec of LIVE_QUESTIONS) await liveQuestion(ctx, origin, spec, w, fixtureIds);

      // Cancel aborts the request, and a reply that arrives anyway is never rendered.
      {
        const at = 'live cancel';
        const t = await livePage(ctx, origin);
        const { page } = t;
        await page.goto(`${origin}/`, { waitUntil: 'load' });
        t.hold = true;
        await page.fill('[data-composer] textarea', 'What does s.173 require?');
        await page.focus('[data-composer] textarea');
        await page.keyboard.press('Enter');
        for (let i = 0; i < 100 && !t.held.length; i++) await page.waitForTimeout(50);
        await pressOn(page, '[data-cancel]');
        for (let i = 0; i < 100 && !t.failed.length; i++) await page.waitForTimeout(50);   // the abort reaching the network layer
        await release(t);
        await page.waitForTimeout(300);
        const f = await naFacts(page);
        if (!t.failed.length) fail(at, w, 'Cancel did not abort the request');
        else if (f.kind !== 'cancelled' || f.states || f.box !== 'What does s.173 require?' || f.boxLocked) fail(at, w, `after Cancel: ${f.kind}, ${f.states} state(s), box ${JSON.stringify(f.box)}`);
        else pass(at, w, 'Cancel aborts the request; nothing is rendered from it; the question stays');
        if (t.errors.length || t.external.length) fail(at, w, `page errors or network: ${[...t.errors, ...t.external].join(' | ').slice(0, 200)}`);
        else pass(at, w, 'cancel: no page errors; nothing left this origin');
        await page.close();
      }

      await liveFailure(ctx, origin, w, 'reply 500', { status: 500, contentType: 'application/json', body: '{"error":"engine_failure"}' });
      await liveFailure(ctx, origin, w, 'reply wrong schema', { status: 200, contentType: 'application/json', body: '{"schema":"placedon.ask/1","state":"answered"}' });
      await liveFailure(ctx, origin, w, 'reply unknown state', { status: 200, contentType: 'application/json', body: '{"schema":"placedon.ask/0","state":"abstained"}' });

      // ?fixture= and ?state= still work over http: a saved sample renders, and a stand-in state
      // sends nothing.
      {
        const at = 'live fixture param';
        const fx = fixtures.find(x => x.name === 'answered_small_company');
        const t = await livePage(ctx, origin);
        await t.page.goto(`${origin}/?fixture=${fx.name}`, { waitUntil: 'load' });
        const g = await t.page.evaluate(() => ({
          states: [...document.querySelectorAll('[data-state]')].map(e => e.getAttribute('data-state')),
          origin: document.querySelector('article[data-state]')?.getAttribute('data-origin'),
          note: document.querySelector('[data-concept]')?.innerText || '',
        }));
        if (g.states.join() !== fx.data.state || g.origin !== 'fixture' || t.asks.length || !/saved sample/i.test(g.note)) fail(at, w, `?fixture= over http: ${JSON.stringify(g)}, ${t.asks.length} ask(s)`);
        else pass(at, w, '?fixture= over http renders the saved sample, says so, and sends nothing');
        await t.page.close();
        const s = await livePage(ctx, origin);
        await s.page.goto(`${origin}/?state=waiting`, { waitUntil: 'load' });
        await s.page.fill('[data-composer] textarea', TYPED);
        await s.page.focus('[data-composer] textarea');
        await s.page.keyboard.press('Enter');
        const f = await naFacts(s.page);
        const note = await s.page.$eval('[data-concept]', e => e.innerText).catch(() => '');
        if (f.kind !== 'waiting' || s.asks.length || !/Nothing you type is sent/.test(note)) fail('live state param', w, `?state=waiting over http: ${f.kind}, ${s.asks.length} ask(s), note ${JSON.stringify(note)}`);
        else pass('live state param', w, '?state= over http is still the stand-in: nothing is sent');
        await s.page.close();
      }
      await ctx.close();
    }

    // The server goes down under a loaded page: Ask renders the service error.
    for (const w of LIVE_WIDTHS) {
      const ctx = await b4.newContext({ viewport: { width: w, height: 900 }, reducedMotion: w === 360 ? 'reduce' : 'no-preference' });
      const stop = async () => { if (alive(srv.proc)) { srv.proc.kill('SIGTERM'); await srv.exited; } };
      if (!alive(srv.proc)) srv = await startServer();
      await liveFailure(ctx, srv.origin, w, 'server down', null, stop);
      await ctx.close();
    }
  } catch (e) {
    fail('live', 0, `live mode could not run: ${String(e).slice(0, 300)}`);
  } finally {
    if (srv && alive(srv.proc)) { srv.proc.kill('SIGTERM'); await srv.exited; }
    await b4.close();
  }
}

const failed = results.filter(r => !r.ok);
for (const r of failed) console.log(`FAIL ${r.fx} @${r.w}: ${r.msg}`);
console.log(`ACCEPTANCE ${results.length - failed.length}/${results.length} checks passed across ${fixtures.length} fixtures x ${WIDTHS.length} widths, `
  + `the empty state, ${NA_STATES.length} non-answer states x ${fixtures.length + 1} requests x ${NA_WIDTHS.length} widths, `
  + `and live mode (${LIVE_QUESTIONS.length} questions, cancel, 4 failures, 2 params) x ${LIVE_WIDTHS.length} widths`);
process.exit(failed.length ? 1 : 0);
