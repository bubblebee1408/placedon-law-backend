"""
Turn the collected practitioner comments into a structured, honestly-limited evidence base.

These are Tier-E anecdotal signals. They are useful for finding vocabulary, candidate pains and
interview questions. They are not evidence of prevalence, they are not legal authority, and the
count of comments is not a count of people -- which matters more here than usual, because it turns
out one author wrote 62% of them.

Authors are pseudonymised to A01..A16. The mapping is not written to disk. One of them is already
named in EVIDENCE_stale_rule_in_the_wild.md, which was a deliberate choice about a public comment
on a public site; that is not a reason to propagate the name into every derived file.

Run: python3 scripts/build_research_register.py
"""
from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = Path.home() / "PlacedOn/placedon-law-research/data/taxguru_practitioner_comments.json"
OUT = ROOT / "research"
ACCESS_DATE = "2026-08-19"          # when the set was captured; not today's date

# Themes are matched on the practitioner's own vocabulary. A theme fires on a comment; it is never
# counted as a person, and the distinct-author count is carried beside every total for that reason.
THEMES = {
    "deadline_and_due_date": r"due date|deadline|last date|by \w+ \d{1,2}|within \d+ days|extended",
    "form_filing": r"MGT-7|AOC-4|DIR-3|ADT-1|DPT-3|MSME-1|GSTR|ITR|form \d|e-?form",
    "penalty_and_default": r"penalt|late fee|disqualif|deactivat|prosecut|struck off|default",
    "amendment_or_change": r"amend|changed|new act|renumber|substitut|omitted|w\.e\.f|revised",
    "small_company_thresholds": r"small compan|turnover|paid-?up|threshold|crore|lakh",
    "audit_and_auditor": r"auditor|audit|ADT-1|secretarial audit",
    "meetings_and_governance": r"board meeting|AGM|annual general|quorum|resolution|minutes|director",
    "portal_or_process": r"MCA portal|V2|V3|portal|upload|DSC|login|website",
}

# A comment is a LEGAL_CLAIM if it asserts a rule, a duty or a date that a reader might rely on.
_LEGAL_ASSERTION = re.compile(
    r"\b(must|shall|mandatory|required to|has to|is due|by \w+ \d{1,2}, ?20\d\d|within \d+ days)\b",
    re.I)
_WORKAROUND = re.compile(r"\b(we use|i use|manually|spreadsheet|excel|cross-?check|double-?check|"
                         r"we maintain|track(ed)? (in|using))\b", re.I)
_QUESTION = re.compile(r"\?\s*$|^(can|is|are|does|do|what|when|how|which|please clarify)\b", re.I)


def theme_hits(text: str) -> list[str]:
    return [name for name, pat in THEMES.items() if re.search(pat, text, re.I)]


def classify(text: str) -> str:
    if _QUESTION.search(text.strip()):
        return "QUESTION"
    if _WORKAROUND.search(text):
        return "CURRENT_WORKAROUND"
    if _LEGAL_ASSERTION.search(text):
        return "LEGAL_CLAIM"
    return "OPINION"


def first_sentence(text: str, limit: int = 220) -> str:
    flat = re.sub(r"\s+", " ", text).strip()
    m = re.search(r"^(.{40,%d}?[.;])\s" % limit, flat)
    return (m.group(1) if m else flat[:limit]).strip()


def main() -> None:
    if not SRC.is_file():
        raise SystemExit(f"missing {SRC}")
    recs = json.loads(SRC.read_text())
    OUT.mkdir(exist_ok=True)

    authors = sorted({r["author"] for r in recs})
    pseudo = {a: f"A{i:02d}" for i, a in enumerate(authors, 1)}

    sources, claims, signals = [], [], []
    theme_comments: dict[str, list[str]] = defaultdict(list)
    theme_authors: dict[str, set[str]] = defaultdict(set)

    for i, r in enumerate(sorted(recs, key=lambda x: x.get("date", "")), 1):
        sid = f"S{i:03d}"
        aid = pseudo[r["author"]]
        text = r["text"]
        themes = theme_hits(text)
        for t in themes:
            theme_comments[t].append(sid)
            theme_authors[t].add(aid)

        sources.append(dict(
            source_id=sid, source_type="PRACTITIONER_COMMENT", platform="taxguru.in",
            title_or_subject=f"comment on post {r.get('post','?')}",
            publisher_or_author=aid,
            source_url=f"https://taxguru.in/?p={r.get('post','')}#comment-{r.get('id','')}",
            publication_date=(r.get("date") or "")[:10], access_date=ACCESS_DATE,
            jurisdiction="IN", authority_level="E_ANECDOTAL", access_status="PUBLIC",
            summary=first_sentence(text),
            limitations="single public comment; role not verified; no sample; "
                        "not legal authority",
            review_status="EXTRACTED"))

        ctype = classify(text)
        claims.append(dict(
            claim_id=f"C{i:03d}", source_id=sid, claim_text=first_sentence(text),
            claim_type=ctype, evidence_location=f"comment {r.get('id','')}",
            date_scope=(r.get("date") or "")[:10], jurisdiction="IN",
            confidence="LOW",
            corroboration_status="SINGLE_SOURCE",
            legal_authority_status=("REQUIRES_OFFICIAL_VERIFICATION"
                                    if ctype == "LEGAL_CLAIM" else "NOT_A_LEGAL_CLAIM"),
            product_implication="interview prompt only",
            review_notes=("asserts a duty or date a reader might rely on"
                          if ctype == "LEGAL_CLAIM" else "")))

        signals.append(dict(
            signal_id=f"G{i:03d}", source_id=sid, platform="taxguru.in",
            topic="|".join(themes) or "unclassified",
            problem_summary=first_sentence(text, 160),
            workaround="yes" if _WORKAROUND.search(text) else "",
            engagement_if_available="", role_if_stated="",
            anonymization_status="PSEUDONYMISED",
            verification_status="UNVERIFIED"))

    for name, rows in (("sources.csv", sources), ("claims.csv", claims),
                       ("social_signals.csv", signals)):
        p = OUT / name
        with p.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader(); w.writerows(rows)

    # --- the analysis, with the concentration finding leading ---
    by_author = Counter(pseudo[r["author"]] for r in recs)
    top_id, top_n = by_author.most_common(1)[0]
    date_claim_authors = {pseudo[r["author"]] for r in recs if r.get("has_date_claim")}
    legal_claims = [c for c in claims if c["claim_type"] == "LEGAL_CLAIM"]

    md = [
        "# Practitioner comments — structured analysis", "",
        f"42 comments, captured {ACCESS_DATE} from taxguru.in. **Tier E, anecdotal.**", "",
        "## Read this before using any number below", "",
        f"**{top_n} of the 42 comments ({top_n/42*100:.0f}%) were written by one author ({top_id}).**",
        f"There are {len(authors)} distinct authors, not 42. Every count in this file is a count of",
        "COMMENTS; the distinct-author column beside it is what limits the inference.", "",
        f"**All {len(date_claim_authors)} author(s) making date claims is/are the same person** — "
        f"{sorted(date_claim_authors)}. Ten comments carry a date claim and every one is theirs.", "",
        "That person is the same commenter documented in `EVIDENCE_stale_rule_in_the_wild.md`,",
        "which describes the observation as \"the closest thing to a product-market-fit signal this",
        "project has found\". The observation stands — a practising professional did state a",
        "superseded rule publicly. But it is **n=1**, and the apparent breadth of this dataset is",
        "largely one prolific commenter. It is a real anecdote, not a pattern.", "",
        "## Themes", "",
        "| theme | comments | distinct authors | inference this supports |",
        "|---|---:|---:|---|",
    ]
    for t, ids in sorted(theme_comments.items(), key=lambda kv: -len(kv[1])):
        na = len(theme_authors[t])
        infer = ("worth an interview question" if na >= 3 else
                 "one or two voices — not a theme yet")
        md.append(f"| {t} | {len(ids)} | {na} | {infer} |")

    md += ["", "## What this data cannot support", "",
           "- prevalence of any problem among company secretaries;",
           "- frequency, duration or cost of any task;",
           "- willingness to pay;",
           "- the correctness of any legal rule stated in a comment;",
           f"- that {len(legal_claims)} legal claims here are accurate — each needs an official source.",
           "", "## Interview questions generated from unresolved claims", ""]
    qs = [
        "How do you find out that a form or due date has changed?",
        "When a compliance article gives a date, do you verify it against MCA, and how?",
        "Have you ever acted on guidance that turned out to be superseded? What happened?",
        "Which filings do you re-check manually even when software tells you the date?",
        "Where do you look first for a Companies Act question — and what do you not trust?",
    ]
    md += [f"{i}. {q}" for i, q in enumerate(qs, 1)]
    md += ["", "## Recommended next research", "",
           "Do not collect more comments from this source. A second capture would most likely",
           "return more of the same author. The binding constraint is distinct practitioners, and",
           "that is met by interviews, not by scraping."]

    (OUT / "comment_analysis.md").write_text("\n".join(md) + "\n")

    print(f"comments processed   : {len(recs)}")
    print(f"distinct authors     : {len(authors)}  (one wrote {top_n})")
    print(f"legal claims flagged : {len(legal_claims)}  — all require official verification")
    print(f"themes with >=3 distinct authors: "
          f"{sum(1 for t in theme_authors if len(theme_authors[t]) >= 3)}")
    print(f"written              : {', '.join(sorted(p.name for p in OUT.glob('*')))}")


if __name__ == "__main__":
    main()
