"""
Generate the lawyer review pack.

BACKLOG H-2 has been sitting as "find an employment lawyer, ~15-25 hours". That is a vague ask
and vague asks do not get done. This narrows it to something a junior employment lawyer or a
final-year NLU student can finish in an evening, by observing something checkable:

**Tier 1 is computed, not chosen.** An earlier version of this file hard-coded six sections —
s.2, s.4, s.6, s.19, s.21, s.26 — as "the sections the product relies on". Rehearsing the
verification end-to-end disproved that: with all six verified, the flagship question *"Do I need
an Internal Committee?"* still abstained, because retrieval routes it to s.4, s.6 **and s.7**,
and `verifier.should_abstain` blocks a packet if *any* provision in it is unverified. Six
verified sections bought an answer to one question out of twelve.

So Tier 1 is now derived: run every question the product is actually built to answer through
`retrieval.retrieve()` and take the closure. That comes to 12 sections. The number moves on its
own if KEYWORD_MAP changes, which is the point — a hand-maintained list drifts silently and
this one cannot.

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
    ("Do contract workers count toward the ten? The Act appears to answer this and we think it "
     "does not.",
     "<strong>s.2(f)</strong> defines \"employee\" to expressly include &ldquo;a co-worker, a "
     "<strong>contract worker</strong>, probationer, trainee, apprentice or called by any other "
     "such name&rdquo;. Read alone, that settles it. But the ten-person figure does not come "
     "from s.2(f). It comes from <strong>s.2(p)</strong>, which defines the unorganised sector "
     "as one where &ldquo;the number of such <strong>workers</strong> is less than ten&rdquo; — "
     "and <em>&ldquo;worker&rdquo; is not a defined term anywhere in this Act</em>. So the "
     "question is whether the s.2(f) set and the s.2(p) set are the same. We decline to answer "
     "it and say so on the page. <strong>If they are the same, our abstention is unnecessarily "
     "cautious and we should drop it. If they are not, most tools in this market are giving "
     "wrong answers.</strong>"),
    ("Is the annual-return deadline genuinely district-set?",
     "Gurugram's District Officer notified 28 February. Most sources say 31 January as though "
     "it were national. We abstain for districts whose notification we do not hold — including "
     "Bengaluru Urban. Is that the right reading of s.21/22?"),
    ("Does the one-half-women proviso count the Presiding Officer?",
     "The proviso sits under clause (c), after (a) names the Presiding Officer separately. We "
     "take the stricter reading — counting everyone — and say so in the generated order. A "
     "narrower reading counting only (b) and (c) is arguable."),
    ("Does Rule 8A require an IC statement from small companies and OPCs?",
     "Rule 8(5)(x) of the Companies (Accounts) Rules requires a Board's Report statement on IC "
     "constitution — and since G.S.R. 357(E) (14 July 2025) also the count of complaints "
     "received, disposed, and pending over ninety days. Rule 8(6) says Rule 8 does not apply to "
     "a One Person Company or a Small Company. The full text of Rule 8A we found lists clauses "
     "(a) to (j) with <strong>no IC clause</strong>, but two secondary sources state that small "
     "companies must give the statement anyway. <strong>This decides whether we can say anything "
     "at all to a small company about its Board's Report</strong>, and it has the same shape as "
     "the s.4 threshold problem in Question 1 — everyone repeats it, and we cannot find it in "
     "the provision."),
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


# The questions the product is actually built to answer. Tier 1 is whatever retrieval needs to
# answer these — not a list anyone maintains by hand.
CORE_QUESTIONS = [
    "Do I need an Internal Committee?",
    "Who can be on the IC?",
    "What is the tenure of IC members?",
    "What is the penalty for not having an IC?",
    "Do I need a PoSH policy?",
    "What must the employer display?",
    "When is the annual return due?",
    "What is a workplace under the Act?",
    "What if we have fewer than ten employees?",
    "Who is the district officer?",
    "How do I file a complaint?",
    "What happens after a complaint is filed?",
]


def required_sections() -> set[int]:
    """
    Every section that must be verified before the product stops abstaining.

    Two closures, applied in order.

    **Retrieval closure.** `verifier.should_abstain` rejects a packet if ANY provision in it is
    unverified, so the unit of verification is the retrieved packet, not the cited section.
    Verifying s.4 alone does not answer "do I need an IC?" — that packet also carries s.6 and
    s.7. This is what took the pack from a hand-written 6 to 12.

    **Dependency closure.** Sections rest on one another, and the statute says so in its own
    words: s.26's penalty attaches to failing the duty "under sub-section (1) of section 4", so
    a verified s.26 over an unverified s.4 still leaves the penalty claim on unverified ground.
    `provision_graph` extracts those edges from the text. Taking the fixed point adds s.13, s.15
    and s.16 — 12 becomes 15.

    **This over-approximates, deliberately.** The graph finds every cross-reference, and not
    every one is load-bearing for what we actually assert: s.4 mentions s.16 only to say a
    Presiding Officer who contravenes it shall be removed, and we make no claim about removal.
    Over-approximating costs the reviewer three more sections in one sitting. Under-approximating
    costs a customer an answer resting on ground nobody checked. The asymmetry decides it.
    """
    from checker.provision_graph import ProvisionGraph  # noqa: PLC0415
    from checker.retrieval import retrieve              # noqa: PLC0415

    need = {p["section_number"] for q in CORE_QUESTIONS for p in retrieve(q)[0]}

    provisions = json.loads(CORPUS.read_text())["provisions"]
    for _ in range(8):                                   # fixed point; converges in 2 today
        simulated = [{**p, "verified_by": "pending" if p["section_number"] in need else None}
                     for p in provisions]
        graph = ProvisionGraph(simulated)
        extra = {b for n in need for b in graph.blocked_by(n)} - need
        if not extra:
            break
        need |= extra
    return need


def main() -> int:
    data = json.loads(CORPUS.read_text())
    provisions = {p["section_number"]: p for p in data["provisions"]}

    # Clauses we rely on, grouped by parent. Where these exist the pack prints THEM rather than
    # the whole section — s.2 is 5,570 characters of every definition in the Act, and four
    # clauses of it are load-bearing. Printing the blob was asking a reviewer to find the
    # relevant paragraphs themselves, which is work we can do for them.
    subs_by_section: dict[int, list[dict]] = {}
    for sub in data.get("subsections", []):
        subs_by_section.setdefault(sub["section_number"], []).append(sub)
    inst = data["instrument"]

    tier1 = sorted(required_sections())

    # Three reasons a section is in Tier 1, and a reviewer's evening is better spent if the pack
    # says which. Verifying the PDF by hand showed s.16 is pulled in only by s.4(5) — removal of
    # a member who breaches confidentiality — and we make no claim about removal. The dependency
    # is real; it is simply not load-bearing for anything we assert.
    from checker.provision_graph import ProvisionGraph  # noqa: PLC0415
    from checker.retrieval import retrieve as _retrieve  # noqa: PLC0415
    graph = ProvisionGraph()
    retrieved = {p["section_number"] for q in CORE_QUESTIONS for p in _retrieve(q)[0]}
    dependency_only = sorted(set(tier1) - retrieved)
    from checker.retrieval import KEYWORD_MAP  # noqa: PLC0415
    routed = sorted({n for v in KEYWORD_MAP.values() for n in v})
    tier2 = [n for n in routed if n not in tier1]
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
        f"<strong>{len(tier1)} sections.</strong> That is every section retrieval must produce "
        f"to answer the {len(CORE_QUESTIONS)} questions the product is built for — verified as a "
        "set, because one unverified section in a packet makes the whole answer abstain. Until "
        "then it declines every question and says why. "
        "Each entry below shows the verbatim text beside the specific reading we derived from "
        "it — so this is checking a reading, not reading a statute cold.</div>",

        "<h2>Five questions, in priority order</h2>",
    ]

    for i, (q, detail) in enumerate(QUESTIONS, 1):
        out.append(f"<div class=q><b>{i}. {html.escape(q)}</b>{detail}</div>")

    out.append(f"<h2>Tier 1 — the {len(tier1)} sections that unlock the product</h2>")
    out.append(f"<p class=lede>Derived, not chosen — by running each of the "
               f"{len(CORE_QUESTIONS)} questions above through our retrieval, then closing over "
               "the dependencies the statute declares in its own cross-references.</p>")
    out.append("<div class=tier><b>Not all of these need equal attention.</b><br>"
               f"<strong>{len(CLAIMS)} sections</strong> carry a specific reading of ours, "
               "printed beside the text. Those are the work.<br>"
               f"<strong>{len(tier1) - len(CLAIMS) - len(dependency_only)} sections</strong> we "
               "only quote back to users — we need to know they are in force and that quoting "
               "them is not misleading.<br>"
               f"<strong>{len(dependency_only)} sections</strong> are here purely because "
               "sections we rely on cross-refer to them. Lowest priority; in at least one case "
               "the reference is in a sub-clause we make no claim about."
               "</div><p class=lede>The questions: "
               + "; ".join(html.escape(q) for q in CORE_QUESTIONS) + "</p>")

    for n in tier1:
        p = provisions[n]
        if n in dependency_only:
            pullers = sorted(x for x in retrieved if n in graph.dependencies(x))
            out.append(f"<h3>{html.escape(p['citation'])} — {html.escape(p['heading'])}</h3>")
            out.append("<p><strong>Lowest priority — check this last, or not at all.</strong> "
                       "We assert nothing from this section and retrieval never returns it. It "
                       "is here only because sections we DO rely on cross-refer to it, so a "
                       "claim citing them technically rests on it: "
                       f"{', '.join(html.escape(provisions[x]['citation']) for x in pullers)}. "
                       "In at least one case the reference sits in a sub-clause we make no claim "
                       "about — s.4(5), removal of a member who contravenes s.16. "
                       "<em>Is it enough that this section is in force?</em></p>")
            for x in pullers[:2]:
                q = graph.evidence_for(n, x)
                if q:
                    out.append(f"<p class=lede>Pulled in by {html.escape(provisions[x]['citation'])}: "
                               f"&ldquo;&hellip;{html.escape(q[-120:])}&hellip;&rdquo;</p>")
            # Opening words only. Printing 3,600 characters of text while telling the reviewer
            # to skip it was contradictory, and it was the largest remaining block in the pack.
            # The full text is in the corpus if they want it; what they need here is enough to
            # identify the section and decide it is in force.
            opening = " ".join(p["text_statutory"].split())[:340]
            out.append(f"<div class=text>{html.escape(opening)}…</div>")
            out.append(f"<p class=lede>Opening words only — the full section runs "
                       f"{len(' '.join(p['text_statutory'].split())):,} characters and is in "
                       f"<code>corpus/provisions/posh_act_2013.json</code> if you want it.</p>")
            out.append("<div class=signoff>In force / problem noted (circle one). "
                       "Note:<span></span><br>Reviewer:<span></span> Date:<span></span></div>")
            continue
        if n not in CLAIMS:
            out.append(f"<h3>{html.escape(p['citation'])} — {html.escape(p['heading'])}</h3>")
            out.append("<p><strong>We assert nothing from this section.</strong> Retrieval pulls "
                       "it in as supporting context for the questions listed above, so its text "
                       "gets quoted back to a user. We only need to know: <em>is this the text "
                       "currently in force, and is quoting it alongside the others misleading in "
                       "any way?</em></p>")
            out.append(f"<div class=text>{html.escape(p['text_display'])}</div>")
            out.append("<div class=signoff>In force and not misleading / problem noted (circle "
                       "one). Note:<span></span><br>Reviewer:<span></span> "
                       "Date:<span></span></div>")
            continue
        out.append(f"<h3>{html.escape(p['citation'])} — {html.escape(p['heading'])}</h3>")
        if p["amendment_markers"]:
            out.append(f"<p><em>Carries amendment markers {p['amendment_markers']} — please "
                       f"confirm this is the text currently in force.</em></p>")
        out.append("<p><strong>What we assert from it:</strong></p><ul>")
        out += [f"<li class=claim>{c}</li>" for c in CLAIMS[n]]
        out.append("</ul>")
        clauses = subs_by_section.get(n)
        if clauses:
            full = len(" ".join(p["text_statutory"].split()))
            shown = sum(c["char_count"] for c in clauses)
            out.append(f"<p><strong>Verbatim text — the {len(clauses)} clauses we rely on</strong> "
                       f"(page {p['page_from']}–{p['page_to']}). The full section runs "
                       f"{full:,} characters; these are the {shown:,} that carry our claims. "
                       f"Each is a verbatim slice, confirmed against the India Code PDF.</p>")
            for c in clauses:
                out.append(f"<p class=lede><strong>{html.escape(c['citation'])}</strong></p>")
                out.append(f"<div class=text>{html.escape(c['text_statutory'])}</div>")
        else:
            out.append(f"<p><strong>Verbatim text</strong> "
                       f"(page {p['page_from']}–{p['page_to']}):</p>")
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
