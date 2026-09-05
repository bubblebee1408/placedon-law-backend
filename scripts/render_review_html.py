#!/usr/bin/env python3
"""Render the fixture review table as a reviewable page. Writes no gold label.

The page is an instrument, not a report: a reviewer works down it marking each
proposal, so status has to read at a glance — hence the pills and the qualifier
chips. Generated from checker.review_table so it cannot drift from the
accounting it displays.
"""
import html
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from checker.review_table import build, ACCEPT, MISSING, PRESERVED, NOT_APPLICABLE

OUT = Path("docs/fixture_review.html")

CSS = """
:root {
  --ground: #F5F6F8;
  --surface: #FFFFFF;
  --surface-sunk: #EFF1F4;
  --ink: #14171D;
  --ink-soft: #4A515E;
  --ink-faint: #767E8C;
  --rule: #DDE1E7;
  --rule-strong: #C3C9D2;
  --accent: #24407A;
  --accent-soft: #E7ECF6;
  --good: #1F6F4A;
  --good-soft: #E3F0E9;
  --warn: #8A6410;
  --warn-soft: #F6EEDC;
  --bad: #A33232;
  --bad-soft: #F7E7E7;
  --serif: "Iowan Old Style", "Palatino Linotype", Palatino, "Book Antiqua",
           Georgia, serif;
  --sans: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  --mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --ground: #0F1216;
    --surface: #171B21;
    --surface-sunk: #1E232B;
    --ink: #E7EAEF;
    --ink-soft: #AAB2BF;
    --ink-faint: #7C8593;
    --rule: #2A303A;
    --rule-strong: #3A424E;
    --accent: #8FAEE8;
    --accent-soft: #1B2436;
    --good: #6FC79A;
    --good-soft: #14241C;
    --warn: #D9AF5C;
    --warn-soft: #241D0F;
    --bad: #E08585;
    --bad-soft: #2A1618;
  }
}
:root[data-theme="dark"] {
  --ground: #0F1216;
  --surface: #171B21;
  --surface-sunk: #1E232B;
  --ink: #E7EAEF;
  --ink-soft: #AAB2BF;
  --ink-faint: #7C8593;
  --rule: #2A303A;
  --rule-strong: #3A424E;
  --accent: #8FAEE8;
  --accent-soft: #1B2436;
  --good: #6FC79A;
  --good-soft: #14241C;
  --warn: #D9AF5C;
  --warn-soft: #241D0F;
  --bad: #E08585;
  --bad-soft: #2A1618;
}

* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--ground);
  color: var(--ink);
  font-family: var(--sans);
  font-size: 16px;
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
}
.wrap {
  max-width: 62rem;
  margin: 0 auto;
  padding: clamp(2rem, 1rem + 4vw, 4.5rem) clamp(1rem, 0.5rem + 2vw, 2rem) 6rem;
  display: flex;
  flex-direction: column;
  gap: 2.5rem;
}

header { display: flex; flex-direction: column; gap: 1rem; }
.eyebrow {
  font-family: var(--mono);
  font-size: 0.72rem;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--accent);
}
h1 {
  font-family: var(--serif);
  font-size: clamp(1.9rem, 1.3rem + 2.4vw, 3rem);
  line-height: 1.12;
  font-weight: 600;
  margin: 0;
  text-wrap: balance;
  letter-spacing: -0.01em;
}
.standfirst {
  font-size: 1.05rem;
  color: var(--ink-soft);
  max-width: 60ch;
  margin: 0;
}
.notice {
  border-left: 3px solid var(--accent);
  background: var(--accent-soft);
  padding: 0.85rem 1.1rem;
  border-radius: 0 4px 4px 0;
  font-size: 0.95rem;
  color: var(--ink);
}
.notice strong { font-weight: 650; }

h2 {
  font-family: var(--serif);
  font-size: 1.35rem;
  font-weight: 600;
  margin: 0 0 0.75rem;
  letter-spacing: -0.005em;
}

.scroll { overflow-x: auto; }
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9rem;
  font-variant-numeric: tabular-nums;
}
thead th {
  text-align: left;
  font-family: var(--mono);
  font-size: 0.68rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ink-faint);
  font-weight: 500;
  padding: 0 0.75rem 0.5rem;
  border-bottom: 1px solid var(--rule-strong);
  white-space: nowrap;
}
tbody td {
  padding: 0.6rem 0.75rem;
  border-bottom: 1px solid var(--rule);
  vertical-align: top;
}
tbody tr:last-child td { border-bottom: none; }
.ledger { background: var(--surface); border: 1px solid var(--rule); border-radius: 6px; }
.ledger table { margin: 0; }
.ledger thead th:first-child, .ledger tbody td:first-child { padding-left: 1.1rem; }
.ledger thead th { padding-top: 1rem; }

code, .mono { font-family: var(--mono); font-size: 0.85em; }
td code { color: var(--ink-soft); }

.pill {
  display: inline-block;
  font-family: var(--mono);
  font-size: 0.68rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  padding: 0.2rem 0.5rem;
  border-radius: 3px;
  white-space: nowrap;
  font-weight: 500;
}
.pill--accept { background: var(--good-soft); color: var(--good); }
.pill--send   { background: var(--warn-soft); color: var(--warn); }
.pill--reject { background: var(--bad-soft);  color: var(--bad); }

.chip {
  display: inline-block;
  font-family: var(--mono);
  font-size: 0.66rem;
  letter-spacing: 0.06em;
  padding: 0.12rem 0.4rem;
  border-radius: 3px;
  white-space: nowrap;
}
.chip--preserved { background: var(--good-soft); color: var(--good); }
.chip--missing   { background: var(--bad-soft);  color: var(--bad); }
.chip--na        { background: var(--surface-sunk); color: var(--ink-faint); }

.cards { display: flex; flex-direction: column; gap: 1.5rem; }
.card {
  background: var(--surface);
  border: 1px solid var(--rule);
  border-radius: 6px;
  overflow: hidden;
}
.card--send { border-left: 4px solid var(--warn); }
.card--accept { border-left: 4px solid var(--good); }

.card-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.5rem 0.9rem;
  padding: 1.1rem 1.4rem;
  border-bottom: 1px solid var(--rule);
  background: var(--surface-sunk);
}
.card-num {
  font-family: var(--mono);
  font-size: 0.8rem;
  color: var(--ink-faint);
}
.card-id { font-family: var(--mono); font-size: 0.92rem; font-weight: 600; }
.card-prov { font-family: var(--serif); font-size: 1rem; color: var(--ink-soft); }
.card-head .pill { margin-left: auto; }

.card-body {
  padding: 1.4rem;
  display: flex;
  flex-direction: column;
  gap: 1.4rem;
}

.label {
  font-family: var(--mono);
  font-size: 0.66rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--ink-faint);
  margin: 0 0 0.4rem;
}

.claims { display: grid; grid-template-columns: 1fr 1fr; gap: 1.2rem; }
@media (max-width: 40rem) { .claims { grid-template-columns: 1fr; } }
.claim p { margin: 0; font-size: 0.95rem; }
.claim--was p { color: var(--ink-faint); text-decoration-color: var(--rule-strong); }
.claim--now p { color: var(--ink); }

.premise {
  background: var(--surface-sunk);
  border: 1px solid var(--rule);
  border-radius: 4px;
  padding: 0.9rem 1.1rem;
  font-family: var(--serif);
  font-size: 0.92rem;
  line-height: 1.65;
  color: var(--ink-soft);
  max-height: 15rem;
  overflow-y: auto;
}

.warnbox {
  border-left: 3px solid var(--warn);
  background: var(--warn-soft);
  padding: 0.75rem 1rem;
  border-radius: 0 4px 4px 0;
  font-size: 0.88rem;
  color: var(--ink);
}
.warnbox ul { margin: 0.4rem 0 0; padding-left: 1.1rem; }
.warnbox li + li { margin-top: 0.35rem; }

.rec {
  border-top: 1px solid var(--rule);
  padding: 1rem 1.4rem;
  font-size: 0.92rem;
  color: var(--ink-soft);
  background: var(--surface-sunk);
}
.rec strong { color: var(--ink); font-weight: 650; }

footer {
  border-top: 1px solid var(--rule);
  padding-top: 1.5rem;
  font-size: 0.88rem;
  color: var(--ink-faint);
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}
a { color: var(--accent); }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
@media (prefers-reduced-motion: reduce) {
  * { animation: none !important; transition: none !important; }
}
"""


def esc(s: str) -> str:
    return html.escape(str(s), quote=False)


def pill(action: str) -> str:
    cls = {"ACCEPT": "accept", "SEND BACK": "send", "REJECT": "reject"}[action]
    return f'<span class="pill pill--{cls}">{esc(action)}</span>'


def chip(status: str) -> str:
    cls = {PRESERVED: "preserved", MISSING: "missing", NOT_APPLICABLE: "na"}[status]
    return f'<span class="chip chip--{cls}">{esc(status)}</span>'


def render() -> str:
    rows = build()
    n_accept = sum(1 for r in rows if r.recommendation == ACCEPT)
    n_back = len(rows) - n_accept

    P = ['<title>Fixture review — 11 proposals</title>',
         f"<style>{CSS}</style>", '<div class="wrap">', "<header>",
         '<p class="eyebrow">Benchmark governance · Companies Act 2013</p>',
         "<h1>Eleven fixture proposals, awaiting review</h1>",
         '<p class="standfirst">Candidate replacements for benchmark fixtures '
         'invalidated under the fail-closed convention. Each states a real '
         'quantity-to-obligation binding that the original asserted without the '
         'qualifier the provision attaches to it.</p>',
         '<div class="notice"><strong>Nothing here has been applied.</strong> '
         'No gold label has been changed. The recommendation on each card is a '
         'reading of the accounting beneath it, not a decision — a reviewer '
         'rules on every row.</div>', "</header>",
         "<section>",
         f"<h2>Decision ledger — {n_accept} to accept, {n_back} to send back</h2>",
         '<div class="ledger scroll"><table><thead><tr>',
         "<th>#</th><th>Proposal</th><th>Provision</th><th>Recommendation</th>",
         "<th>Qualifiers still missing</th><th>Near-duplicate</th>",
         "</tr></thead><tbody>"]

    for i, r in enumerate(rows, 1):
        miss = " ".join(f"<code>{esc(q.kind)}</code>" for q in r.missing) or "—"
        dup = " ".join(f"<code>{esc(x)}</code>" for x in r.near_duplicates) or "—"
        P.append(f"<tr><td>{i}</td><td><code>{esc(r.proposal_id)}</code></td>"
                 f"<td>s.{esc(r.section)}({esc(r.subsection)})</td>"
                 f"<td>{pill(r.recommendation)}</td><td>{miss}</td><td>{dup}</td></tr>")
    P += ["</tbody></table></div></section>", '<section class="cards">']

    for i, r in enumerate(rows, 1):
        cls = "accept" if r.recommendation == ACCEPT else "send"
        P += [f'<article class="card card--{cls}">',
              '<div class="card-head">',
              f'<span class="card-num">{i}</span>',
              f'<span class="card-id">{esc(r.proposal_id)}</span>',
              f'<span class="card-prov">Section {esc(r.section)}'
              f'({esc(r.subsection)})</span>',
              pill(r.recommendation), "</div>",
              '<div class="card-body">',
              '<div class="claims">',
              '<div class="claim claim--was">',
              f'<p class="label">Original claim · supersedes {esc(r.supersedes)}</p>',
              f"<p>{esc(r.original_claim)}</p></div>",
              '<div class="claim claim--now">',
              '<p class="label">Proposed replacement</p>',
              f"<p>{esc(r.replacement_claim)}</p></div>", "</div>",
              "<div>",
              '<p class="label">Supporting premise — served text, verbatim, '
              'not repaired</p>',
              f'<div class="premise">{esc(r.supporting_premise)}</div></div>',
              "<div>", '<p class="label">Qualifier accounting</p>',
              '<div class="scroll"><table><thead><tr>',
              "<th>Kind</th><th>Trigger in source</th><th>Status</th><th>Note</th>",
              "</tr></thead><tbody>"]
        for q in r.qualifiers:
            P.append(f"<tr><td><code>{esc(q.kind)}</code></td>"
                     f"<td>{esc(q.trigger)}</td><td>{chip(q.status)}</td>"
                     f"<td>{esc(q.why)}</td></tr>")
        P += ["</tbody></table></div></div>"]

        if r.near_duplicates:
            P.append('<div class="warnbox"><strong>Near-duplicate</strong> of '
                     + ", ".join(f"<code>{esc(x)}</code>" for x in r.near_duplicates)
                     + ". Two fixtures asserting one proposition carry one "
                       "item's worth of signal.</div>")
        if r.transcription_warnings:
            P.append('<div class="warnbox"><strong>Source transcription '
                     "warnings</strong><ul>"
                     + "".join(f"<li>{esc(w)}</li>" for w in r.transcription_warnings)
                     + "</ul></div>")
        P += ["</div>",
              f'<div class="rec"><strong>{esc(r.recommendation)}.</strong> '
              f"{esc(r.reason)}</div>", "</article>"]

    P += ["</section>", "<footer>",
          "<p>Generated from <code>checker/review_table.py</code>, which holds no "
          "gold-label field and cannot write one. Premises are reproduced from the "
          "India Code API text as served, including the transcription defects "
          "recorded as SD-004 — a defective government source is flagged, never "
          "repaired.</p>",
          "<p>Passing the release gate is not evidence that grounding is solved. "
          "The benchmark remains 80 pairs across five sections, most mechanically "
          "constructed from the same corpus the checker reads.</p>",
          "</footer>", "</div>"]
    return "\n".join(P)


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(), encoding="utf-8")
    print(f"wrote {OUT}")
