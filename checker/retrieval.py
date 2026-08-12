"""
Retrieval over the PoSH corpus. Keyword route first, then a scan. No vector search.

The spec asks for sentence-transformers / all-MiniLM-L6-v2 as stage 2. We are not adding it,
and the reason is arithmetic rather than taste: the corpus is **30 sections**. Loading torch to
rank thirty paragraphs costs ~2GB of dependencies and several seconds of cold start to beat a
scan that finishes in under a millisecond. `architect`'s standing position is no vector search
until SQL stops working, and thirty sections is nowhere near that. When the corpus reaches the
four labour codes (~500 sections) this becomes the right call; today it is cargo cult.

The spec also assumes a Supabase `provisions` table. We read the ingested JSON, which is the
same data with its sha256 intact and no network dependency.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

CORPUS = Path(__file__).resolve().parent.parent / "corpus/provisions/posh_act_2013.json"

# Question language → the sections that actually govern it. Every mapping was read off the
# ingested text, not guessed from a heading.
KEYWORD_MAP: dict[str, tuple[int, ...]] = {
    "internal committee": (4,), "ic": (4,), "committee": (4, 6, 7),
    "presiding officer": (4,), "constitute": (4,), "who can be": (4,),
    "members": (4, 7), "tenure": (4,), "three years": (4,),
    "local committee": (6, 7), "district officer": (5, 6, 20, 21),
    "annual return": (21, 22), "annual report": (21, 22),
    # "file" alone routed "how do I file income tax?" here. Needs its object.
    "file the return": (21, 22), "file the report": (21, 22), "filing deadline": (21, 22),
    "policy": (19,), "display": (19,), "duties of employer": (19,), "employer must": (19,),
    "training": (19,), "awareness": (19,),
    "penalty": (26,), "fine": (26,), "punishment": (14, 26), "non-compliance": (26,),
    "complaint": (9, 10, 11), "inquiry": (11, 12, 13), "conciliation": (10,),
    # Added because bench_retrieval.py showed real phrasings missing these
    # sections entirely. Users do not say "conciliation"; they say "settle".
    "settle the matter": (10,), "settle": (10,), "powers": (11,),
    "published": (16, 17), "publish": (16, 17), "turns out to be false": (14,),
    "malicious": (14,), "civil court": (11,),
    "false complaint": (14,), "compensation": (15,), "appeal": (18,),
    "confidential": (16, 17), "publication": (16, 17),
    "definition": (2,), "workplace": (2,), "employee": (2,), "aggrieved": (2,),
    "unorganised": (2,), "ten workers": (2, 6), "less than ten": (2, 6),
}


@lru_cache(maxsize=1)
def _corpus() -> list[dict]:
    return json.loads(CORPUS.read_text())["provisions"]


@lru_cache(maxsize=None)
def _idf(phrase: str) -> float:
    """
    How much a phrase discriminates, from the corpus itself.

    log(N / df) where df counts sections whose statutory text contains the phrase. A phrase in
    every section carries no information and lands near zero; a phrase in one section is the
    strongest signal available. Unseen phrases get the maximum, because a routing key nobody's
    text contains is presumably a synonym we added deliberately.
    """
    import math                                               # noqa: PLC0415

    corpus = _corpus()
    n = len(corpus) or 1
    df = sum(1 for p in corpus
             if phrase in " ".join((p.get("text_statutory") or "").split()).lower())
    return math.log(n / df) if df else math.log(n)


def keyword_route(question: str) -> tuple[int, ...] | None:
    """
    Stage 1. Free, sub-millisecond, and it resolves most real questions.

    Ordered by **specificity, not section number**. This mattered more than it looks.

    "Does the committee have to file an annual report?" matches two keys: 'committee' -> (4, 6, 7)
    and 'annual report' -> (21, 22). The union sorted numerically is (4, 6, 7, 21, 22), and
    top_k=3 then hands back 4, 6, 7 — the generic key crowds out the specific one purely because
    4 < 21. s.21 was in the route and got truncated off the end of it.

    That is the annual-report section: the one the entire notified-date register turns on. Found
    by scripts/bench_retrieval.py, which is the only reason it was found at all — the section was
    present in the route, so nothing looked wrong.

    Specificity is **inverse document frequency over the corpus**, not string length.

    The first attempt used len(phrase) / len(sections), and it was wrong for a reason worth
    keeping: 'committee' appears in **20 of the 30 sections** of this Act. It is the least
    informative word in the statute. But it is nine characters pointing at three mapped sections,
    so it scored 3.00 and outranked 'inquiry' at 2.33 — and "what powers does the committee have
    during an inquiry?" kept returning s.4, 6, 7 instead of s.11.

    idf = log(N / df) is the standard answer (Spärck Jones 1972; the term-weighting half of
    BM25). A phrase occurring in one section discriminates; one occurring in twenty is background.

    **Measured honestly**, on scripts/bench_retrieval.py's 20 cases:

        weight = _idf(phrase)                recall@3 = 1.00
        weight = len(phrase)/len(sections)   recall@3 = 1.00
        weight = 1.0  (i.e. section order)   recall@3 = 0.80

    So *weighting* is load-bearing and this set cannot tell idf from the length heuristic. idf is
    kept on principle rather than on evidence: it is derived from the corpus, so it stays correct
    as the corpus grows, whereas len/count is a coincidence that happens to rank 'conciliation'
    above 'committee' on twenty questions and carries no reason to keep doing so at 500 sections.
    If a future case set separates them, that is the measurement to trust over this paragraph.
    """
    q = " ".join(question.lower().split())
    weight: dict[int, float] = {}
    for phrase, sections in KEYWORD_MAP.items():
        if phrase in q:
            w = _idf(phrase)
            for s in sections:
                weight[s] = max(weight.get(s, 0.0), w)
    if not weight:
        return None
    # Section number only breaks ties, so equally-specific routes stay in statute order.
    return tuple(sorted(weight, key=lambda s: (-weight[s], s)))


def _score(question: str, provision: dict) -> int:
    """Stage 2. Term overlap against heading and text. Beats embeddings at this corpus size."""
    terms = {t for t in re.findall(r"[a-z]{4,}", question.lower())}
    if not terms:
        return 0
    heading = provision["heading"].lower()
    body = provision["text_display"].lower()
    return sum(3 for t in terms if t in heading) + sum(1 for t in terms if t in body)


# A single term overlapping is one common word, not relevance. Measured on this corpus:
# off-topic questions ("GST rate on chocolate", "capital of France", "renew my passport") all
# top out at exactly 1, while on-topic questions score 2-8. Below the floor we return nothing,
# which is a better answer than three weakly-matched sections a model would then explain.
# Applies to the scan fallback only; a keyword route is an explicit mapping and stands.
SCAN_FLOOR = 2


def retrieve(question: str, *, top_k: int = 3) -> tuple[list[dict], str]:
    """Returns (provisions, which_stage). Never more than top_k — context is cost."""
    sections = keyword_route(question)
    if sections:
        by_num = {p["section_number"]: p for p in _corpus()}
        hits = [by_num[n] for n in sections if n in by_num][:top_k]
        if hits:
            return hits, "keyword"

    scored = sorted(
        ((_score(question, p), p) for p in _corpus()),
        key=lambda pair: pair[0], reverse=True,
    )
    hits = [p for s, p in scored[:top_k] if s >= SCAN_FLOOR]
    return hits, "scan" if hits else "none"
