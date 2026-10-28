"""Bounded, local excerpt retrieval for explicitly attached conversation documents.

This module never calls a model and never decides a legal status. Offsets count Unicode
code points in the stored extracted text, not PDF bytes or pages. Uploaded content is
returned only as quoted data; even text that resembles an instruction stays verbatim.
"""
from __future__ import annotations

import bisect
import functools
import hashlib
import math
import re
import unicodedata
from collections import Counter
from typing import Literal, NotRequired, TypedDict

from gateway.english_stem import stem as _porter2

MAX_DOCUMENT_CHARS = 200_000
MAX_TOTAL_CHARS = 500_000
MAX_DOCUMENT_BYTES = MAX_DOCUMENT_CHARS * 4
MAX_TOTAL_BYTES = MAX_TOTAL_CHARS * 4
MAX_PASSAGES = 8
MAX_PASSAGE_CHARS = 1200
MAX_DOCUMENTS = 20

# Question-mode ranking (RETRIEVAL_LOOP DECISION §2). Module-level so the evaluation harness
# can override them; a reader never sees a score.
K1 = 1.2            # BM25 term-frequency saturation (Robertson & Zaragoza 2009)
B = 0.4             # BM25 length normalisation (tuned on CUAD dev 0-50: +0.021 MRR over 0.75)
ALPHA = 0.6         # keep passages scoring at least ALPHA x this query's top score (dev-tuned)
COMMON_SHARE = 0.5  # a term in more than this share of passages is "common"
W_HISTORY = 0.5     # weight of previous-question terms in a follow-up (Lin et al. 2020, weight ours)
STEMMING = True
HISTORY_LIMITATION = 'This question was read together with your previous question in this conversation.'


class EvidencePassage(TypedDict):
    id: str
    document_id: str
    name: str
    sha256: str
    start: int
    end: int
    text: str
    page: int | None


class EvidenceDocument(TypedDict):
    document_id: str
    name: str
    sha256: str | None
    status: Literal['SEARCHED', 'UNAVAILABLE', 'LIMIT_EXCEEDED', 'NOT_SEARCHED']
    reason: str | None
    total_chars: int | None
    total_passages: int
    shown_passages: int
    excerpt_chars: int
    excerpt_coverage_ratio: float | None


class DocumentEvidence(TypedDict):
    schema: Literal['document_evidence.v1']
    mode: Literal['question', 'overview']
    status: Literal['EXCERPTS_FOUND', 'NO_MATCH', 'UNAVAILABLE', 'NOT_SEARCHED']
    query: str
    searched_document_ids: list[str]
    documents: list[EvidenceDocument]
    passages: list[EvidencePassage]
    limitations: list[str]
    # Present only when this follow-up was read together with the previous user question.
    history_query: NotRequired[str]


_OVERVIEW = re.compile(r'^\s*(?:(?:please|can you|could you|give me)\s+)*(?:summari[sz]e\b|give\s+(?:me\s+)?(?:a\s+)?(?:summary|overview)\b)', re.I)
_STOP = frozenset('a an the is are was were be being been to of and or for in on at as by '
                  'with from that this these those it its my our your their what which '
                  'where when how who why can could would should does do did please '
                  'tell me find show say says about document documents file files '
                  'attached attachment agreement contract clause section '
                  'shall such herein hereof hereto hereunder thereof therein thereto will also '
                  'any there whether related regarding concerning'.split())
# A follow-up that leans on the previous question: "And how long is that?", "What about ...".
_FOLLOW_UP = re.compile(r'^\s*(?:and|also|so|then|what about|how about|what if|is that|is it|does that|'
                        r'does it|do they|can (?:it|that|they)|and if)\b', re.I)


# A PDF's pages arrive SEPARATED by form feeds: N pages, N-1 breaks (the frontend reads
# it page by page). Unlike pdftotext, which ends every page with one, a trailing \f here
# means the last page had no text layer. Text with none -- a .docx, a .txt -- has no pages.
PAGE_BREAK = '\f'
PAGES_FROM_BREAKS = 'Page numbers come from the page breaks in the uploaded text layer; a page that had no text layer is not in it.'
PAGES_UNKNOWN = 'Offsets count Unicode characters in extracted text, not original PDF pages or bytes.'


def page_of(text: str, offset: int) -> int | None:
    """The 1-indexed page `offset` falls on, or None when the text carries no pages."""
    if PAGE_BREAK not in text:
        return None
    return text.count(PAGE_BREAK, 0, offset) + 1


def is_overview(query: str) -> bool:
    return bool(_OVERVIEW.search(query))


@functools.lru_cache(maxsize=65536)
def _index_form(word: str) -> str:
    """The form a word is matched by: NFC, then Porter2 for plain English words only."""
    word = unicodedata.normalize('NFC', word)
    if STEMMING and word.isascii() and word.isalpha():
        return _porter2(word)
    return word


def _tokens(text: str) -> list[str]:
    """Index tokens with repeats kept (BM25 needs term frequency). Never used for offsets."""
    words, token = [], []
    for char in text.casefold() + ' ':
        if char.isalnum() or unicodedata.category(char).startswith('M'):
            token.append(char)
        elif token:
            word = ''.join(token)
            if len(word) > 1 and word not in _STOP:
                words.append(_index_form(word))
            token.clear()
    return words


def _rank(searched, weights: dict[str, float], df: Counter, n: int, avgdl: float):
    """Pass 2: BM25-score every passage; keep the best MAX_PASSAGES as (rank, passage, terms)."""
    terms = sorted(weights)  # fixed summation order: bit-identical scores across runs
    idf = {t: math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5)) for t in terms}
    candidates = []
    for position, did, raw, row, sha in searched:
        for ordinal, (start, end) in enumerate(_spans(raw)):
            tf = Counter(_tokens(raw[start:end]))
            matched = [t for t in terms if t in tf]
            if not matched:
                continue
            norm = K1 * (1 - B + B * sum(tf.values()) / avgdl) if avgdl else K1
            score = sum(weights[t] * idf[t] * tf[t] * (K1 + 1) / (tf[t] + norm) for t in matched)
            if score <= 0:
                continue
            rank = (-score, ordinal, position)
            if len(candidates) == MAX_PASSAGES and rank >= candidates[-1][:3]:
                continue
            passage: EvidencePassage = {'id': f'doc-{position + 1}-{start}-{end}',
                'document_id': did, 'name': row['name'], 'sha256': sha,
                'start': start, 'end': end, 'text': raw[start:end], 'page': page_of(raw, start)}
            if len(candidates) == MAX_PASSAGES:
                candidates.pop()
            bisect.insort(candidates, (*rank, passage, frozenset(matched)),
                          key=lambda candidate: candidate[:3])
    return candidates


def _all_common(weights, candidates, df: Counter, n: int) -> bool:
    """True when every query term that matched anything appears in most passages."""
    matched = {t for c in candidates for t in c[4] if weights.get(t) == 1.0}
    return bool(matched) and all(df[t] > n * COMMON_SHARE for t in matched)


def _question_passages(query: str, searched, previous_query: str | None):
    """BM25 over this call's passages, then a cut relative to the top score (DECISION §2.3-2.5).

    Returns (passages, history_used). Scores never leave this function.
    """
    df, n, total = Counter(), 0, 0
    for _, _, raw, row, _ in searched:                 # pass 1: statistics only
        for start, end in _spans(raw):
            toks = _tokens(raw[start:end])
            n += 1
            total += len(toks)
            df.update(set(toks))
            row['total_passages'] += 1
    avgdl = total / n if n else 0.0
    weights = {t: 1.0 for t in set(_tokens(query))}
    candidates = _rank(searched, weights, df, n, avgdl) if weights else []
    history = False
    if previous_query and (_FOLLOW_UP.match(query) or not weights or not candidates
                           or _all_common(weights, candidates, df, n)):
        extra = {t: W_HISTORY for t in set(_tokens(previous_query)) - weights.keys()}
        if extra:
            weights = {**weights, **extra}
            candidates = _rank(searched, weights, df, n, avgdl)
            history = True
    if not candidates:
        return [], history
    # A rare-term guard was specified too; on CUAD dev it changed nothing the relative cut
    # did not already do, so it was removed (EVAL_retrieval.md, Phase 1).
    top = -candidates[0][0]
    kept = [c for i, c in enumerate(candidates) if i == 0 or -c[0] >= ALPHA * top]
    return [c[3] for c in kept], history


def _spans(text: str):
    """Keep exact source offsets while splitting paragraphs and capping long spans."""
    def paragraphs():
        start = 0
        # A page break is a hard boundary: no passage, and so no quote, spans two pages.
        for separator in re.finditer(r'\n[ \t\r]*\n|\f', text):
            yield start, separator.start()
            start = separator.end()
        yield start, len(text)

    for start, end in paragraphs():
        while start < end:
            stop = min(start + MAX_PASSAGE_CHARS, end)
            if stop < end:
                boundary = text.rfind(' ', start + MAX_PASSAGE_CHARS // 2, stop)
                if boundary > start:
                    stop = boundary
            left, right = start, stop
            while left < right and text[left].isspace():
                left += 1
            while right > left and text[right - 1].isspace():
                right -= 1
            if left < right:
                yield left, right
            start = stop
            while start < end and text[start].isspace():
                start += 1


def collect(query: str, documents: dict, *, enabled: bool = True,
            previous_query: str | None = None) -> DocumentEvidence:
    """Rank lexical matches locally; a match establishes presence, never legal truth.

    `previous_query` is the previous USER question in this conversation (never an answer);
    it is used only when this question leans on it, and the result then says so.
    """
    overview = is_overview(query)
    result: DocumentEvidence = {
        'schema': 'document_evidence.v1', 'mode': 'overview' if overview else 'question',
        'status': 'NOT_SEARCHED', 'query': query, 'searched_document_ids': [],
        'documents': [], 'passages': [], 'limitations': [
            'These are exact excerpts from stored extracted text, not verified legal authority.',
            'Keyword matching can miss relevant wording; no match does not establish absence.',
            PAGES_UNKNOWN,
            'Only selected documents were searched. Held law, the web and other files were not searched.',
            'Excerpts are saved conversation snapshots. Deleting a vault document does not remove excerpts already saved in a conversation.',
        ],
    }
    if overview:
        result['limitations'].append('Distributed excerpts are not a complete summary; terms, exceptions and schedules between excerpts may be omitted.')
    overview_documents = []
    searched = []
    total_chars = 0
    for position, (did, doc) in enumerate(documents.items()):
        raw = doc.get('text')
        row: EvidenceDocument = {'document_id': did, 'name': str(doc.get('name') or did)[:512],
            'sha256': None, 'status': 'NOT_SEARCHED', 'reason': None, 'total_chars': None,
            'total_passages': 0, 'shown_passages': 0, 'excerpt_chars': 0, 'excerpt_coverage_ratio': None}
        result['documents'].append(row)
        if not enabled:
            row['reason'] = 'Document sources are not selected. Enable your documents to search these attachments.'
            continue
        if position >= MAX_DOCUMENTS or doc.get('limit_exceeded'):
            row.update(status='LIMIT_EXCEEDED', reason='The selected document exceeds this turn’s reading limit.')
            continue
        if doc.get('cannot_read') or not isinstance(raw, str) or not raw.strip():
            row.update(status='UNAVAILABLE', reason=str(doc.get('cannot_read') or 'Readable document text is unavailable.'))
            continue
        if len(raw) > MAX_DOCUMENT_CHARS or total_chars + len(raw) > MAX_TOTAL_CHARS:
            row.update(status='LIMIT_EXCEEDED', reason='The selected document exceeds this turn’s reading limit.')
            continue
        total_chars += len(raw)
        sha = hashlib.sha256(raw.encode('utf-8')).hexdigest()
        row.update(status='SEARCHED', sha256=sha, total_chars=len(raw))
        result['searched_document_ids'].append(did)
        if overview:
            row['total_passages'] = sum(1 for _ in _spans(raw))
            overview_documents.append((position, did, raw, row))
            continue
        searched.append((position, did, raw, row, sha))
    if searched:
        # Ranking orders excerpts only. It is never a confidence or legal verdict.
        result['passages'], history = _question_passages(query, searched, previous_query)
        if history:
            result['history_query'] = str(previous_query)[:500]
            result['limitations'].append(HISTORY_LIMITATION)
    if overview:
        # Fair round-robin budget, then evenly spaced source spans per document.
        # Counts and at most eight selected offsets stay resident; no full span list.
        allocations = [0] * len(overview_documents)
        for _ in range(MAX_PASSAGES):
            eligible = [i for i, item in enumerate(overview_documents)
                        if allocations[i] < item[3]['total_passages']]
            if not eligible:
                break
            index = min(eligible, key=lambda i: (allocations[i], i))
            allocations[index] += 1
        for (position, did, raw, row), count in zip(overview_documents, allocations):
            if not count:
                continue
            total = row['total_passages']
            selected = {0} if count == 1 else {
                j * (total - 1) // (count - 1) for j in range(count)}
            for ordinal, (start, end) in enumerate(_spans(raw)):
                if ordinal in selected:
                    result['passages'].append({'id': f'doc-{position + 1}-{start}-{end}',
                        'document_id': did, 'name': row['name'], 'sha256': row['sha256'],
                        'start': start, 'end': end, 'text': raw[start:end],
                        'page': page_of(raw, start)})
    for row in result['documents']:
        selected = [p for p in result['passages'] if p['document_id'] == row['document_id']]
        row['shown_passages'] = len(selected)
        row['excerpt_chars'] = sum(p['end'] - p['start'] for p in selected)
        if row['status'] == 'SEARCHED':
            row['excerpt_coverage_ratio'] = row['excerpt_chars'] / row['total_chars']
    for doc in documents.values():
        if doc.get('partial') and not doc.get('cannot_read'):
            result['limitations'].append(f"{str(doc.get('name') or 'A document')[:200]}: {doc['partial']}")
    result['partial_documents'] = [str(doc.get('name') or did)[:200] for did, doc in documents.items()
                                   if doc.get('partial') and not doc.get('cannot_read')]
    if any(PAGE_BREAK in str(doc.get('text') or '') for doc in documents.values()):
        result['limitations'][2] = PAGES_FROM_BREAKS
    if not enabled:
        result['limitations'][3] = 'No source was searched because document sources are not selected.'
    elif not result['searched_document_ids']:
        result['status'] = 'UNAVAILABLE'
    else:
        result['status'] = 'EXCERPTS_FOUND' if result['passages'] else 'NO_MATCH'
    return result


def description(evidence: DocumentEvidence) -> str:
    partial = evidence.get('partial_documents') or []
    if partial and evidence['status'] in ('NO_MATCH', 'EXCERPTS_FOUND'):
        return (_description(evidence) + ' ' + ', '.join(partial)
                + ' had pages with no text layer; those pages were not searched.')
    return _description(evidence)


def _description(evidence: DocumentEvidence) -> str:
    if evidence['status'] == 'NOT_SEARCHED':
        return 'Your attachments were not searched. Enable your documents in Sources, then ask again.'
    if evidence['status'] == 'UNAVAILABLE':
        return 'I could not read the selected documents. Check the file status or select a smaller readable file.'
    if evidence['status'] == 'NO_MATCH':
        return 'I found no keyword matches in the readable selected documents. Try the exact wording or inspect the document; this does not mean the information is absent.'
    if evidence['mode'] == 'overview':
        return 'Here are excerpts sampled across your readable selected documents. This is a limited preview, not a complete summary or legal review.'
    return 'Here are matching excerpts from your readable selected documents. Read the surrounding text before drawing a conclusion; these excerpts have not been checked against law.'
