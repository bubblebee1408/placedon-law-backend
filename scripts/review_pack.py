"""
Generate the lawyer review pack.

BACKLOG H-2 has been sitting as "find an employment lawyer, ~15-25 hours". That is a vague ask
and vague asks do not get done. This narrows it to something a junior employment lawyer or a
final-year NLU student can finish in an evening, by observing something checkable:

**The product cites six sections.** s.2, s.4, s.6, s.19, s.21, s.26. Every claim the checker,
the IC-order generator, and the Q&A engine currently make rests on those. The remaining 24
sections are ingested but nothing depends on them yet — verifying them is real work with no
current payoff.

So the pack is tiered. Tier 1 unlocks the product. Tier 2 is what retrieval can route to.
Tier 3 is everything else, and is explicitly marked as *not needed yet*.

Each Tier 1 entry shows the verbatim text beside the specific claim we derived from it, so the
reviewer is checking a reading rather than reading a statute cold.

Run: python3 scripts/review_pack.py  →  corpus/review_pack.html
"""
from __future__ import annotations

import html
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
CORPUS = ROOT / "corpus/provisions/posh_act_2013.json"
OUT = ROOT / "corpus/review_pack.html"

# What we assert from each section, in our own words, for the reviewer to accept or reject.
CLAIMS: dict[int, list[str]] = {
    2: ["We read the 'unorganised sector' definition — \"the number of such workers is less "
        "than ten\" — as one of the two places the ten-worker figure appears, neither of which "
        "is s.4."],
    4: ["s.4(1) imposes the duty on <em>every employer of a workplace</em>, with no headcount "
        "threshold stated. <strong>We do not cite s.4 for the ten-employee rule.</strong>",
        "The Presiding Officer must be a woman employed at a senior level, from amongst the "
        "employees.",
        "Not less than two further members from amongst the employees.",
        "One member from an NGO or association committed to the cause of women.",
        "At least one-half of those nominated must be women — <strong>we count the Presiding "
        "Officer toward this; see Question 4.</strong>",
        "Term not exceeding three years.",
        "A separate Internal Committee at every administrative unit or office where these are "
        "at different places."],
    6: ["We treat s.6(1) — Local Committee for establishments that have not constituted an IC "
        "\"due to having less than ten workers\" — as <strong>the actual source</strong> of the "
        "ten-worker figure, and we label it an inference rather than a rule."],
    19: ["The employer must display the penal consequences of sexual harassment and the order "
         "constituting the Internal Committee at a conspicuous place at the workplace."],
    21: ["An annual report goes to the District Officer. <strong>The deadline is fixed by that "
         "officer, not nationally</strong> — so we decline to state a date where we do not hold "
         "the district's notification. See Question 3."],
    26: ["Failure to constitute an Internal Committee is punishable by a fine which may extend "
         "to fifty thousand rupees. We quote ₹50,000 and nothing beyond it."],
}

QUESTIONS = [
    ("Does the s.4 duty attach below ten workers?",
     "s.4(1) says \"every employer of a workplace shall\" and states no threshold. The "
     "ten-worker figure appears in s.2 (defining unorganised sector) and s.6(1) (Local "
     "Committee for establishments with fewer than ten workers). Every secondary source we "
     "checked states it as though s.4 contained it. <strong>This is the question that decides "
     "what we tell a nine-person company.</strong>"),
    ("Do contract workers count toward that figure?",
     "We currently decline to answer this and say so. If there is a settled position we will "
     "encode it; if there is not, we would rather keep declining."),
    ("Is the annual-return deadline genuinely district-set?",
     "Gurugram's District Officer notified 28 February. Most sources say 31 January as though "
     "it were national. We abstain for districts whose notification we do not hold — including "
     "Bengaluru Urban. Is that the right reading of s.21/22?"),
    ("Does the one-half-women proviso count the Presiding Officer?",
     "The proviso sits under clause (c), after (a) names the Presiding Officer separately. We "
     "take the stricter reading — counting everyone — and say so in the generated order. A "
     "narrower reading counting only (b) and (c) is arguable."),
    ("May we reproduce this statutory text verbatim in a commercial product?",
     "We store the sections verbatim from India Code and show them to users with citations. "
     "Crown copyright under the Copyright Act 1957, and GODL-India, both apply somewhere in "
     "here. We have not established which."),
]

CSS = """
body{font:16px/1.6 Georgia,serif;max-width:52rem;margin:0 auto;padding:3rem 1.5rem;color:#16150f}
h1{font-size:2rem;line-height:1.2;margin:0 0 .5rem}
h2{font-size:1.3rem;margin:2.5rem 0 .75rem;border-top:1px solid #ddd;padding-top:1.5rem}
h3{font-size:1.05rem;margin:1.75rem 0 .4rem}
.lede{color:#555;font-size:1.05rem}
.q{background:#f8f2e4;border-left:3px solid #8a6410;padding:1rem 1.2rem;margin:1rem 0}
.q b{display:block;margin-bottom:.3rem}
.tier{background:#eef2f7;border-left:3px solid #3d4c66;padding:.9rem 1.2rem;margin:1.5rem 0}
.text{background:#faf8f4;border:1px solid #e0dbd0;padding:1rem 1.2rem;font-size:.92rem;
  white-space:pre-wrap;max-height:22rem;overflow:auto}
.claim{margin:.5rem 0 .5rem 1.2rem}
.signoff{border:1px solid #ccc;padding:.75rem 1rem;margin:.9rem 0 0;font-family:system-ui;
  font-size:.9rem;color:#444}
.signoff span{display:inline-block;min-width:12rem;border-bottom:1px solid #999;margin-left:.4rem}
code{font-family:ui-monospace,monospace;font-size:.9em;background:#f0ede6;padding:.1em .35em}
@media print{.text{max-height:none}h2{page-break-before:always}}
"""


def main() -> int:
    data = json.loads(CORPUS.read_text())
    provisions = {p["section_number"]: p for p in data["provisions"]}
    inst = data["instrument"]

    tier1 = sorted(CLAIMS)
    from checker.retrieval import KEYWORD_MAP  # noqa: PLC0415
    routed = sorted({n for v in KEYWORD_MAP.values() for n in v})
    tier2 = [n for n in routed if n not in CLAIMS]
    tier3 = [n for n in sorted(provisions) if n not in routed]

    out: list[str] = [
        "<!doctype html><meta charset=utf-8>",
        f"<title>placedon — PoSH review pack</title><style>{CSS}</style>",
        "<h1>PoSH Act 2013 — verification pack</h1>",
        f"<p class=lede>Prepared {date.today():%d %B %Y} for review by an employment lawyer. "
        f"Source: <code>{html.escape(inst['source_url'])}</code>, sha256 "
        f"<code>{inst['source_sha256'][:16]}…</code>, {inst['source_pages']} pages, "
        f"stamped &ldquo;{html.escape(inst['source_version_note'])}&rdquo;.</p>",

        "<div class=tier><b>What we are asking for.</b> Not a full reading of the Act. "
        f"The product currently cites <strong>{len(tier1)} sections</strong>. Verifying those "
        "unlocks everything it claims; until then it declines every question and says why. "
        "Each entry below shows the verbatim text beside the specific reading we derived from "
        "it — so this is checking a reading, not reading a statute cold.</div>",

        "<h2>Five questions, in priority order</h2>",
    ]

    for i, (q, detail) in enumerate(QUESTIONS, 1):
        out.append(f"<div class=q><b>{i}. {html.escape(q)}</b>{detail}</div>")

    out.append(f"<h2>Tier 1 — the {len(tier1)} sections the product relies on</h2>")
    out.append("<p class=lede>Everything the checker, the IC-order generator, and the Q&amp;A "
               "engine assert rests on these. This is the work that unlocks the product.</p>")

    for n in tier1:
        p = provisions[n]
        out.append(f"<h3>{html.escape(p['citation'])} — {html.escape(p['heading'])}</h3>")
        if p["amendment_markers"]:
            out.append(f"<p><em>Carries amendment markers {p['amendment_markers']} — please "
                       f"confirm this is the text currently in force.</em></p>")
        out.append("<p><strong>What we assert from it:</strong></p><ul>")
        out += [f"<li class=claim>{c}</li>" for c in CLAIMS[n]]
        out.append("</ul>")
        out.append(f"<p><strong>Verbatim text</strong> (page {p['page_from']}–{p['page_to']}):</p>")
        out.append(f"<div class=text>{html.escape(p['text_display'])}</div>")
        out.append("<div class=signoff>Reading accepted / corrected (circle one). "
                   "Correction:<span></span><br>Reviewer:<span></span> Date:<span></span></div>")

    out.append(f"<h2>Tier 2 — {len(tier2)} sections reachable by search, not yet relied on</h2>")
    out.append("<p class=lede>Retrieval can route a question to these, so they will be quoted "
               "back to users once verification opens the answer path. Lower priority than "
               "Tier 1, higher than Tier 3.</p><ul>")
    out += [f"<li>{html.escape(provisions[n]['citation'])} — "
            f"{html.escape(provisions[n]['heading'])}</li>" for n in tier2]
    out.append("</ul>")

    out.append(f"<h2>Tier 3 — {len(tier3)} sections ingested, nothing depends on them</h2>")
    out.append("<p class=lede><strong>Please do not spend time on these.</strong> They are held "
               "verbatim for completeness. Verifying them has no payoff until something cites "
               "them.</p><ul>")
    out += [f"<li>{html.escape(provisions[n]['citation'])} — "
            f"{html.escape(provisions[n]['heading'])}</li>" for n in tier3]
    out.append("</ul>")

    OUT.write_text("\n".join(out), encoding="utf-8")
    print(f"Tier 1 (unlocks the product): {len(tier1)} sections — "
          f"{', '.join(provisions[n]['citation'] for n in tier1)}")
    print(f"Tier 2 (reachable by search): {len(tier2)}")
    print(f"Tier 3 (not needed yet):      {len(tier3)}")
    print(f"\n→ {OUT.relative_to(ROOT)}  ({OUT.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
