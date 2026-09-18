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
      const invented = [...new Set(screenNums.filter(x => !allowedNums.has(x) && !allowedNums.has(x.replace(/\.$/, ''))))];
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
      const motion = await page.evaluate(() => {
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

const failed = results.filter(r => !r.ok);
for (const r of failed) console.log(`FAIL ${r.fx} @${r.w}: ${r.msg}`);
console.log(`ACCEPTANCE ${results.length - failed.length}/${results.length} checks passed across ${fixtures.length} fixtures x ${WIDTHS.length} widths`);
process.exit(failed.length ? 1 : 0);
