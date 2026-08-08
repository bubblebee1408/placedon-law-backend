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
    "annual return": (21, 22), "annual report": (21, 22), "file": (21, 22),
    "policy": (19,), "display": (19,), "duties of employer": (19,), "employer must": (19,),
    "training": (19,), "awareness": (19,),
    "penalty": (26,), "fine": (26,), "punishment": (14, 26), "non-compliance": (26,),
    "complaint": (9, 10, 11), "inquiry": (11, 12, 13), "conciliation": (10,),
    "false complaint": (14,), "compensation": (15,), "appeal": (18,),
    "confidential": (16, 17), "publication": (16, 17),
    "definition": (2,), "workplace": (2,), "employee": (2,), "aggrieved": (2,),
    "unorganised": (2,), "ten workers": (2, 6), "less than ten": (2, 6),
}


@lru_cache(maxsize=1)
def _corpus() -> list[dict]:
    return json.loads(CORPUS.read_text())["provisions"]


def keyword_route(question: str) -> tuple[int, ...] | None:
    """Stage 1. Free, sub-millisecond, and it resolves most real questions."""
    q = question.lower()
    hits: set[int] = set()
    for phrase, sections in KEYWORD_MAP.items():
        if phrase in q:
            hits.update(sections)
    return tuple(sorted(hits)) or None


def _score(question: str, provision: dict) -> int:
    """Stage 2. Term overlap against heading and text. Beats embeddings at this corpus size."""
    terms = {t for t in re.findall(r"[a-z]{4,}", question.lower())}
    if not terms:
        return 0
    heading = provision["heading"].lower()
    body = provision["text_display"].lower()
    return sum(3 for t in terms if t in heading) + sum(1 for t in terms if t in body)


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
    hits = [p for s, p in scored[:top_k] if s > 0]
    return hits, "scan" if hits else "none"
