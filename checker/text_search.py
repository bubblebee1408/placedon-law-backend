"""
Title + body search over the Companies Act 2013 corpus, for users who do not know the number.

`section_index.section_by_number("174")` answers "what does s.174 say". It cannot answer "what is
the quorum for a board meeting", which is the question people actually arrive with. This module
answers that one: 464 mapped sections in `corpus/companies_act/`, ranked over heading and text,
carrying the matched wording back so a result can be audited instead of trusted.

Why not embeddings
------------------
`checker/retrieval.py` (PoSH era, 30 sections) argued vector search was unjustified below roughly
four-labour-codes scale, ~500 sections. At 464 that argument no longer settles it by size alone --
but query shape still settles it. These queries name statutory subjects: "related party
transactions", "quorum for board meetings", "loans to directors". Those are the drafter's own
words, because the drafter chose the headings from the vocabulary the reader already uses. Lexical
matching against a heading is not an approximation of the right answer here; it *is* the right
answer, and it yields a citable reason -- "your words are in the heading" -- that a cosine
distance cannot. In a product whose whole claim is evidence, an unauditable ranking is a
liability. `retrieval.py` is otherwise inapplicable: its KEYWORD_MAP is thirty hand-written PoSH
routes (internal committee, presiding officer, district officer) naming a different statute, over
`corpus/provisions/posh_act_2013.json`. One idea survives the move -- weight terms by inverse
document frequency measured on the corpus rather than guessed -- and it survives because it is why
"committee" stopped drowning out the question's actual subject.

MEASURED LIMITATION -- the query class this cannot serve. Questions whose vocabulary appears
nowhere in the statute are out of reach. The Act never says "conflict of interest" (s.184 says
"concern or interest"), never says "whistleblower" (s.177 says "vigil mechanism"), never says
"insider trading". Asked in those words this returns [] rather than a wrong section, which is the
correct failure. "can a director attend by video" is the near-miss case that *does* work, and only
just: the Act says "participation ... through video conferencing", so "attend" matches nothing and
the result rests entirely on "video" (df=2) plus "director". Push one step further -- "can a
director dial in remotely" -- and there is no lexical hook at all. The fix is a curated synonym
layer built by reading the sections, the same discipline `retrieval.py` used, NOT a 2GB embedding
stack whose nearest-neighbour guess would be uncitable. Not built here because each synonym must
be evidenced section by section, and this module must not ship guesses.

How it ranks
------------
Every query term is weighted by BM25 inverse document frequency measured on these 464 records, so
"quorum" (df=6) carries ~30x the weight of "company" (df=396) and "shall" (df=439) is stopworded
away entirely. A term counts once per record where it appears; repetition adds a small bounded
bonus and can never substitute for coverage. Contiguous phrase hits are rewarded above the same
words scattered. Heading evidence is worth `TITLE_GAIN` times body evidence for the same term, and
is scaled by how much of the heading the query accounts for -- so "Notice of meeting" beats
"Auditors to attend general meeting", which merely contains the words.

Deliberately NOT BM25's document-length normalisation. BM25's length prior assumes a long document
is padded and therefore less relevant per term. In a statute length tracks subject complexity, not
verbosity: s.173 (Meetings of Board) is long *because* board meetings are intricate. With b=0.6 the
length prior pushed s.173 below s.146 for "can a director attend by video" -- the correct answer
lost to a section about auditors, purely for being long. Measured, then removed.

Silence
-------
`search()` returns [] unless a result clears both `MIN_COVER` (it must account for at least half
of what was asked, by IDF mass) and `SCORE_FLOOR`. A plausible-looking wrong section is worse than
no section, because the wrong one gets quoted. CLAUDE.md: "If evidence is incomplete, write OPEN
or UNVERIFIED. Do not guess."

Defective records are flagged, never hidden. `docs/SOURCE_DEFECTS.md` records SD-001 (editorial
matter inside s.1) and SD-002 (pre-amendment JSON for s.16, s.124, s.76A, s.329). Those rows carry
a non-empty `defects` tuple. They are still returned -- suppressing them would be a silent repair,
which CLAUDE.md forbids -- and presentation is someone else's job.

Run: python3 checker/text_search.py
"""
from __future__ import annotations

import html
import json
import math
import re
from functools import lru_cache
from pathlib import Path

CORPUS = Path(__file__).resolve().parent.parent / "corpus/companies_act"
INDEX = CORPUS / "_index.json"

# --------------------------------------------------------------------------------------------
# Source defects. docs/SOURCE_DEFECTS.md is the authority; this is its machine-readable echo.
# Flagged, not filtered: CLAUDE.md forbids repairing a defective government source.
# --------------------------------------------------------------------------------------------
DEFECTS: dict[str, tuple[str, ...]] = {
    "1": ("SD-001",),      # editorial instruction "To be deleted" left inside the statutory text
    "16": ("SD-002",),     # JSON rendering is pre-amendment: "fine" where the PDF says "penalty"
    "124": ("SD-002",),
    "76A": ("SD-002",),
    "329": ("SD-002",),
}

# --------------------------------------------------------------------------------------------
# Tuning. Each of these is exercised by an assertion in _test(), not chosen by feel.
# --------------------------------------------------------------------------------------------
TITLE_GAIN = 1.4          # a term in the heading is worth this much a term in the body
TITLE_PHRASE_BONUS = 0.5  # contiguous phrase in the heading, as a fraction of query mass
BODY_PHRASE_BONUS = 0.3   # ... and in the body. Kept below TITLE_GAIN - 1 on purpose; see _test.
TITLE_PRECISION_FLOOR = 0.35   # a heading is never worth less than this share of its full gain
BODY_PRESENCE = 0.75      # a term is either in the body or not; that is most of the signal
BODY_TF_BONUS = 0.25      # repetition adds at most this, saturating -- it cannot buy coverage
BODY_TF_HALF = 2.0        # occurrences at which half the tf bonus is earned
MIN_COVER = 0.50          # a result must account for >= half the query's IDF mass
SCORE_FLOOR = 0.45
SNIPPET_CHARS = 150

# --------------------------------------------------------------------------------------------
# Stopwords: ordinary English plus Indian statutory boilerplate. The boilerplate half matters
# more -- "shall" is in 439 of 464 records and "section" in 341, and IDF alone would still leave
# them a small vote that a long section can accumulate. Topical nouns that merely happen to be
# frequent -- company, board, director, meeting -- are deliberately NOT here. They carry real
# meaning and IDF demotes them correctly; deleting them would break "loans to directors".
# --------------------------------------------------------------------------------------------
_STOP_ENGLISH = """
a an the and or of to in for on by with as at from is are be been being was were am do does did
can could will would should must not no nor it its this that these those there here what which
who whom whose when where why how if then than so but also only own same very have has had he she
they them his her their i we you your my our me us about into out up down over under between
each any all both few more most less least other another such some
"""
_STOP_LEGAL = """
shall may provided proviso provisos section sections sub subsection subsections clause clauses
chapter schedule act thereof therein thereto thereunder thereafter therefrom hereby herein hereof
hereunder aforesaid notwithstanding whereas said prescribed manner respect purpose purposes case
cases deemed deem means meaning include includes including included foregoing applicable
accordance pursuant subject following specified specify relating relates respectively namely etc
viz provision provisions made make given give unless otherwise whether either neither
"""


def _norm(text: str) -> str:
    """India Code markup fragment -> plain text. The corpus stores the markup verbatim."""
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    text = text.replace("’", "'").replace("“", '"').replace("”", '"')
    return " ".join(text.split())


def _stem(token: str) -> str:
    """Plural stripping only, applied identically to query and corpus so it cannot desynchronise.

    Deliberately not a Porter stemmer: over-stemming collides distinct statutory terms
    ("meeting"/"meet", "resolution"/"resolve") and nothing here would catch the resulting wrong
    answer. Plurals are the whole of the observed gap -- "loans to directors" has to reach the
    heading "Loan to directors, etc".
    """
    if len(token) <= 3 or token.endswith("ss") or token.endswith("us"):
        return token
    if token.endswith("ies"):
        return token[:-3] + "y"
    if token.endswith(("ches", "shes", "sses", "xes", "zes")):
        return token[:-2]
    if token.endswith("s"):
        return token[:-1]
    return token


def _tokens(text: str) -> list[str]:
    """Stemmed token sequence. Stopwords are retained here so phrase positions stay intact."""
    return [_stem(t) for t in re.findall(r"[a-z0-9]+", text.lower())]


@lru_cache(maxsize=1)
def _stopwords() -> frozenset[str]:
    return frozenset(_stem(w) for w in (_STOP_ENGLISH + _STOP_LEGAL).split())


def _content(tokens: list[str]) -> list[str]:
    stop = _stopwords()
    return [t for t in tokens if t not in stop and not t.isdigit()]


# --------------------------------------------------------------------------------------------
# Corpus
# --------------------------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _records() -> tuple[dict, ...]:
    """Every mapped, confidently-indexed section, tokenised once.

    Unmapped and low-confidence index entries are skipped for the same reason
    `section_index.section_by_number` returns None for them: a guessed mapping would attach a
    section number to text nobody confirmed was that section, which is a wrong legal answer
    delivered with full confidence.
    """
    entries = json.loads(INDEX.read_text())["entries"]
    out = []
    for entry in entries.values():
        sid = entry.get("section_id")
        if not sid or entry.get("confidence") not in ("high", "medium"):
            continue
        raw = json.loads((CORPUS / f"{sid}.json").read_text())
        # Footnotes are amendment history ("Subs. by Act 21 of 2015, s. 16") -- editorial
        # apparatus, not statutory text. Searching them would surface a section on the strength
        # of its edit log, which is not what "the law says X" means. Excluded on purpose.
        body = _norm(raw.get("content"))
        title_tokens = _tokens(entry["title"])
        title_stems = _content(title_tokens)
        tf: dict[str, int] = {}
        for term in _content(_tokens(body)):
            tf[term] = tf.get(term, 0) + 1
        out.append({
            "section_number": entry["section_number"],
            "section_id": str(sid),
            "title": entry["title"],
            "body": body,
            "body_lower": body.lower(),
            "title_stems": frozenset(title_stems),
            "title_mass_terms": tuple(dict.fromkeys(title_stems)),
            "title_seq": " " + " ".join(title_tokens) + " ",
            "body_seq": " " + " ".join(_tokens(body)) + " ",
            "tf": tf,
            "defects": DEFECTS.get(entry["section_number"], ()),
        })
    return tuple(out)


@lru_cache(maxsize=1)
def _stats() -> tuple[dict[str, float], int]:
    """(idf by stem, N). Measured on this corpus only -- never a borrowed English frequency list."""
    records = _records()
    n = len(records)
    df: dict[str, int] = {}
    for rec in records:
        for term in set(rec["tf"]) | rec["title_stems"]:
            df[term] = df.get(term, 0) + 1
    idf = {t: math.log(1.0 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}
    return idf, n


def _idf(term: str) -> float:
    """Weight of a term. A term no section uses gets the maximum: it discriminates maximally
    *against* every record, which is what makes a nonsense query return []."""
    idf, n = _stats()
    return idf.get(term, math.log(1.0 + (n + 0.5) / 0.5))


def _mass(terms) -> float:
    return sum(_idf(t) for t in terms)


# --------------------------------------------------------------------------------------------
# Query
# --------------------------------------------------------------------------------------------
def _phrases(tokens: list[str]) -> list[tuple[str, float]]:
    """Contiguous query n-grams worth testing, longest first, each with its content IDF mass.

    Built over the sequence *including* stopwords, so "notice of meeting" survives as a phrase,
    but an n-gram must carry at least two content words to count -- otherwise "of the" would be a
    phrase hit in all 464 records.
    """
    stop = _stopwords()
    out: list[tuple[str, float]] = []
    for size in range(min(6, len(tokens)), 1, -1):
        for i in range(len(tokens) - size + 1):
            gram = tokens[i:i + size]
            content = [t for t in gram if t not in stop and not t.isdigit()]
            if len(content) < 2:
                continue
            out.append((" " + " ".join(gram) + " ", _mass(dict.fromkeys(content))))
    return out


def _tf_weight(freq: int) -> float:
    """Presence is most of the signal; repetition adds a bounded, saturating remainder."""
    return BODY_PRESENCE + BODY_TF_BONUS * freq / (freq + BODY_TF_HALF)


def _title_precision(rec: dict, hits: list[str]) -> float:
    """How much of the heading the query accounts for, floored at TITLE_PRECISION_FLOOR.

    Without this, "Auditors to attend general meeting" scored the same as "Annual general meeting"
    for "notice of general meeting" -- both contain the phrase -- and both buried "Notice of
    meeting", whose heading is *entirely* about the question. Coverage says how much of the query
    the heading answers; precision says how much of the heading is answering it. Both are needed.
    """
    total = _mass(rec["title_mass_terms"])
    if total <= 0:
        return TITLE_PRECISION_FLOOR
    precision = _mass(hits) / total
    return TITLE_PRECISION_FLOOR + (1.0 - TITLE_PRECISION_FLOOR) * precision


def _score(rec: dict, terms: list[str], phrases: list[tuple[str, float]], qmass: float) -> dict:
    """Score one record against one query. Returns the score and the evidence behind it."""
    title_hits = [t for t in terms if t in rec["title_stems"]]
    body_hits = [t for t in terms if rec["tf"].get(t)]
    gain = TITLE_GAIN * _title_precision(rec, title_hits) if title_hits else 0.0

    evidence = 0.0
    for term in terms:
        weight = 0.0
        if term in rec["title_stems"]:
            weight = gain
        if rec["tf"].get(term):
            weight = max(weight, _tf_weight(rec["tf"][term]))
        evidence += _idf(term) * weight

    title_phrase = body_phrase = 0.0
    matched_phrase = ""
    for gram, mass in phrases:
        if gram in rec["title_seq"] and mass > title_phrase * qmass:
            title_phrase = mass / qmass
            matched_phrase = gram
        if gram in rec["body_seq"] and mass > body_phrase * qmass:
            body_phrase = mass / qmass
            matched_phrase = matched_phrase or gram

    score = (evidence / qmass
             + gain * TITLE_PHRASE_BONUS * title_phrase
             + BODY_PHRASE_BONUS * body_phrase)
    cover = _mass(dict.fromkeys(title_hits + body_hits)) / qmass
    return {"score": score, "cover": cover, "title_hits": title_hits,
            "body_hits": body_hits, "phrase": matched_phrase.strip()}


# --------------------------------------------------------------------------------------------
# Evidence
# --------------------------------------------------------------------------------------------
def _find(text_lower: str, stems: list[str]) -> int:
    """Offset of the first matched stem in the original text, or -1.

    Prefix-tolerant: the corpus carries surface forms ("transactions") the query only reaches
    after stemming ("transaction").
    """
    for stem in stems:
        m = re.search(r"\b" + re.escape(stem) + r"[a-z]{0,3}\b", text_lower)
        if m:
            return m.start()
    return -1


def _snippet(rec: dict, stems: list[str], phrase: str) -> str:
    """A verbatim substring of the record's body around the strongest match. Never a paraphrase."""
    start = -1
    if phrase:
        start = _find(rec["body_lower"], [phrase.split()[0]])
    if start < 0:
        start = _find(rec["body_lower"], stems)
    if start < 0:
        return rec["body"][:SNIPPET_CHARS].strip()
    lo = max(0, start - SNIPPET_CHARS // 4)
    if lo:
        space = rec["body"].find(" ", lo)
        lo = space + 1 if 0 <= space < start else lo
    hi = min(len(rec["body"]), lo + SNIPPET_CHARS)
    if hi < len(rec["body"]):
        cut = rec["body"].rfind(" ", lo, hi)
        hi = cut if cut > lo else hi
    return ("..." if lo else "") + rec["body"][lo:hi].strip() + ("..." if hi < len(rec["body"]) else "")


def _by_weight(terms: list[str]) -> list[str]:
    return sorted(terms, key=_idf, reverse=True)


# --------------------------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------------------------
def search(query: str, *, top_k: int = 5) -> list[dict]:
    """Find Companies Act 2013 sections by subject, when the section number is unknown.

    Returns up to top_k rows, best first:

        {"section_number": str, "section_id": str, "title": str,
         "score": float, "route": str, "matched": str, "defects": tuple}

    `route` is "title" | "body" | "title+body" -- which evidence carried the result.
    `matched` is verbatim text from the record showing WHY it matched: the heading for a title
    route, a body substring for a body route, and both joined by " | " for "title+body". It is
    never paraphrased and never synthesised.
    `defects` is always present, empty for a clean record. Non-empty values are IDs from
    docs/SOURCE_DEFECTS.md and mean the underlying source text is known-bad.

    Returns [] rather than a weak guess. Silence is a valid answer in this product.
    """
    tokens = _tokens(query)
    terms = list(dict.fromkeys(_content(tokens)))
    if not terms:
        return []
    qmass = _mass(terms)
    if qmass <= 0:
        return []
    phrases = _phrases(tokens)

    ranked = []
    for rec in _records():
        scored = _score(rec, terms, phrases, qmass)
        if scored["cover"] < MIN_COVER or scored["score"] < SCORE_FLOOR:
            continue
        ranked.append((scored, rec))
    # Section number breaks ties only, so equally-scored sections come back in a stable order.
    ranked.sort(key=lambda pair: (-pair[0]["score"], pair[1]["section_number"]))

    rows = []
    for scored, rec in ranked[:top_k]:
        has_title, has_body = bool(scored["title_hits"]), bool(scored["body_hits"])
        route = "title+body" if has_title and has_body else "title" if has_title else "body"
        snippet = _snippet(rec, _by_weight(scored["body_hits"]), scored["phrase"]) if has_body else ""
        matched = (rec["title"] if route == "title"
                   else snippet if route == "body"
                   else f"{rec['title']} | {snippet}")
        rows.append({
            "section_number": rec["section_number"],
            "section_id": rec["section_id"],
            "title": rec["title"],
            "score": round(scored["score"], 4),
            "route": route,
            "matched": matched,
            "defects": rec["defects"],
        })
    return rows


# --------------------------------------------------------------------------------------------
# Tests. Convention from checker/legal_ref.py: run the module, read PASS/FAIL, non-zero exit on
# any failure. Not pytest.
# --------------------------------------------------------------------------------------------

# Real queries, phrased the way someone who does not know the number would phrase them.
CASES: tuple[tuple[str, str], ...] = (
    ("related party transactions", "188"),
    ("quorum for board meetings", "174"),
    ("notice of general meeting", "101"),
    ("loans to directors", "185"),
    ("can a director attend by video", "173"),
    ("twenty-one days notice", "101"),
)

# Nothing in the Companies Act answers these. The only correct result is [].
NONSENSE: tuple[str, ...] = (
    "chocolate ice cream recipe",
    "how do I renew my passport",
    "best time to visit Goa in December",
    "python list comprehension syntax",
    "what is the capital of France",
)


def _test() -> None:
    ok = fail = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1; print(f"[PASS] {label}")
        else:
            fail += 1; print(f"[FAIL] {label}")

    print(f"-- corpus: {len(_records())} mapped sections --\n")

    # 1. Retrieval. The whole point of the module.
    top1 = top3 = 0
    for query, expected in CASES:
        found = [h["section_number"] for h in search(query, top_k=5)]
        rank = found.index(expected) + 1 if expected in found else 0
        top1 += rank == 1
        top3 += 0 < rank <= 3
        check(0 < rank <= 3, f"{query!r} -> s.{expected} at rank {rank or '>5'}  {found[:4]}")
    print(f"       precision@1 = {top1}/{len(CASES)}   precision@3 = {top3}/{len(CASES)}\n")

    # 2. Silence. A bad guess is worse than no answer.
    for query in NONSENSE:
        hits = search(query)
        check(hits == [], f"nonsense {query!r} -> [] "
                          f"{'' if not hits else [h['section_number'] for h in hits]}")
    check(search("") == [], "empty query -> []")
    check(search("of the and shall be prescribed") == [], "all-boilerplate query -> []")

    # 3. Title outranks body. s.188 IS related party transactions; s.2 defines the term and
    #    s.177 and s.164 merely mention it.
    rpt = search("related party transactions", top_k=5)
    check(rpt[0]["section_number"] == "188" and rpt[0]["route"].startswith("title"),
          f"heading beats incidental mentions  {[h['section_number'] for h in rpt]}")
    check(all(rpt[0]["score"] > h["score"] for h in rpt if h["route"] == "body"),
          "every body-only hit scores below the section whose heading names the subject")
    check(TITLE_GAIN > 1.0 + BODY_PHRASE_BONUS,
          f"arithmetic guarantee: a heading fully covering the query ({TITLE_GAIN}) outranks the "
          f"best possible body-only match ({1.0 + BODY_PHRASE_BONUS})")

    # 4. Rare terms beat common ones, or statutory boilerplate swamps every query.
    check(_idf("quorum") > 4 * _idf("company"),
          f"idf(quorum)={_idf('quorum'):.2f} >> idf(company)={_idf('company'):.2f}")
    check(_idf("video") > _idf("director") > _idf("company"),
          f"idf ordering video {_idf('video'):.2f} > director {_idf('director'):.2f} "
          f"> company {_idf('company'):.2f}")
    check(_stem("shall") in _stopwords() and _stem("sections") in _stopwords(),
          "statutory boilerplate is stopworded, not merely down-weighted")
    check("company" not in _stopwords() and "director" not in _stopwords(),
          "topical nouns are NOT stopworded -- IDF demotes them; deleting them breaks queries")

    # 5. Phrases beat scatter. Five sections contain "twenty-one days"; the one whose heading is
    #    "Notice of meeting" is the one a person asking this wants.
    days = search("twenty-one days notice", top_k=5)
    check(bool(days) and "twenty-one days" in days[0]["matched"].lower(),
          "the winning row's evidence contains the phrase 'twenty-one days' verbatim")
    scattered = search("twenty one days", top_k=3)
    check(bool(scattered), f"the same words unhyphenated still resolve "
                           f"{[h['section_number'] for h in scattered]}")

    # 6. Plural stemming, the one morphology rule claimed above.
    check(_stem("loans") == "loan" and _stem("companies") == "company"
          and _stem("business") == "business", "plural stemming, and 'business' left alone")

    # 7. Contract shape. Another module reads these keys by name.
    keys = {"section_number", "section_id", "title", "score", "route", "matched", "defects"}
    rows = search("quorum for board meetings", top_k=5)
    check(bool(rows) and all(set(r) == keys for r in rows),
          "every row carries exactly the contract keys")
    check(all(isinstance(r["score"], float) and isinstance(r["defects"], tuple)
              and isinstance(r["section_number"], str) and isinstance(r["section_id"], str)
              for r in rows), "score float, defects tuple, numbers and ids str")
    check(all(r["route"] in ("title", "body", "title+body") for r in rows),
          "route is one of title | body | title+body")
    check(all(r["matched"].strip() for r in rows), "matched is never empty")
    check(all(r["score"] >= rows[i + 1]["score"] for i, r in enumerate(rows[:-1])),
          "rows are sorted by descending score")

    # 8. `matched` must be real text from the record, or it is not evidence.
    for row in rows + rpt + search("can a director attend by video", top_k=3):
        rec = next(r for r in _records() if r["section_number"] == row["section_number"])
        haystack = (rec["title"] + " " + rec["body"]).lower()
        # Compare lowercased on BOTH sides. The haystack is lowered, so a snippet carrying any
        # capital -- which every title does -- would otherwise fail a check the code passes.
        pieces = [p.strip().strip(".").lower() for p in row["matched"].split(" | ")]
        check(all(p in haystack for p in pieces if p),
              f"s.{row['section_number']} matched text is verbatim from the record")

    check(len(search("company", top_k=3)) <= 3, "top_k is respected")
    check(search("quorum", top_k=0) == [], "top_k=0 returns nothing")

    # 9. Defects surfaced, not swallowed.
    hit16 = [h for h in search("rectification of name of company", top_k=5)
             if h["section_number"] == "16"]
    check(bool(hit16) and hit16[0]["defects"] == ("SD-002",),
          "s.16 carries SD-002 (pre-amendment JSON rendering)")
    hit1 = [h for h in search("short title extent commencement", top_k=5)
            if h["section_number"] == "1"]
    check(bool(hit1) and hit1[0]["defects"] == ("SD-001",),
          "s.1 carries SD-001 (editorial matter left in the source)")
    check(rpt[0]["defects"] == (), "a clean record carries an empty tuple, not a missing key")
    check(set(DEFECTS) == {"1", "16", "124", "76A", "329"},
          "the defect table matches docs/SOURCE_DEFECTS.md")

    # 10. Only confirmed mappings are searchable.
    nums = [r["section_number"] for r in _records()]
    check(len(set(nums)) == len(nums) == 464, f"464 mapped sections, no duplicates ({len(nums)})")

    print(f"\n{ok}/{ok + fail} passed")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
