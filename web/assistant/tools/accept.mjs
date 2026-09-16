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
//   [data-citation]                    one per citation / confirmed ref; keyboard-reachable
//   [data-source-panel]                the source panel; reachable by keyboard
//   [data-composer]                    the question input; reached early in the tab order and before
//                                      any citation (the pane's own tab strip legitimately precedes it)
//   [data-law-version]                 the section-text as-of ("Text as ingested …")
//   [data-chrome]                      a label the response did not supply (exempt from check 6)
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
// The design's state words are Answered / Partly answered / Not held.
const HEADING_WORD = {
  answered: /answered/i,
  partial: /in part|partly|partial|not confirmed/i,
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
      if ((data.citations || data.confirmed || []).some(x => x.ref)) {
        if (!(await page.$('[data-law-version]'))) fail(name, w, 'citations shown without [data-law-version]');
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

      // 7. keyboard: PLAN §6 check 3 asks for a COMPLETE path — composer reached early and before any
      //    citation; every citation reachable; the source panel reachable.
      if (w === 1440 || w === 360) {
        let composerStop = -1, firstCitationStop = -1;
        const reached = new Set();
        let panelReachable = false;
        for (let i = 0; i < 80; i++) {
          await page.keyboard.press('Tab');
          const info = await page.evaluate(() => {
            const a = document.activeElement;
            return {
              cit: a?.closest('[data-citation]')?.getAttribute('data-citation') ?? null,
              panel: !!a?.closest('[data-source-panel]'),
              composer: !!a?.closest('[data-composer]'),
            };
          });
          if (info.composer && composerStop < 0) composerStop = i;
          if (info.cit) { reached.add(info.cit); if (firstCitationStop < 0) firstCitationStop = i; }
          if (info.panel) panelReachable = true;
        }
        const citCount = await page.$$eval('[data-citation]', els => new Set(els.map(e => e.getAttribute('data-citation'))).size);
        if (composerStop < 0 || composerStop > 6) fail(name, w, `composer not reached in the first 6 tab stops (stop ${composerStop})`);
        else if (firstCitationStop >= 0 && firstCitationStop < composerStop) fail(name, w, 'a citation is reached before the composer');
        else pass(name, w, 'composer reached early in tab order');
        if (citCount && reached.size < citCount) fail(name, w, `keyboard reached ${reached.size} of ${citCount} citations`);
        else pass(name, w, 'all citations keyboard-reachable');
        if (citCount && !panelReachable) fail(name, w, 'source panel not reachable by keyboard');
        else pass(name, w, 'source panel reachable');
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

      if (shots && (w === 360 || w === 1440)) {
        await page.screenshot({ path: join(shots, `${name}-${w}.png`), fullPage: true });
        await page.addStyleTag({ content: 'html{filter:grayscale(1)!important}' });
        await page.screenshot({ path: join(shots, `${name}-${w}-gray.png`), fullPage: true });
      }
      await ctx.close();
    }
  }
} finally {
  await browser.close();
}

const failed = results.filter(r => !r.ok);
for (const r of failed) console.log(`FAIL ${r.fx} @${r.w}: ${r.msg}`);
console.log(`ACCEPTANCE ${results.length - failed.length}/${results.length} checks passed across ${fixtures.length} fixtures x ${WIDTHS.length} widths`);
process.exit(failed.length ? 1 : 0);
