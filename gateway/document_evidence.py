"""Bounded, local excerpt retrieval for explicitly attached conversation documents.

This module never calls a model and never decides a legal status. Offsets count Unicode
code points in the stored extracted text, not PDF bytes or pages. Uploaded content is
returned only as quoted data; even text that resembles an instruction stays verbatim.
"""
from __future__ import annotations

import bisect
import hashlib
import math
import re
import unicodedata
from typing import Literal, TypedDict

MAX_DOCUMENT_CHARS = 200_000
MAX_TOTAL_CHARS = 500_000
MAX_DOCUMENT_BYTES = MAX_DOCUMENT_CHARS * 4
MAX_TOTAL_BYTES = MAX_TOTAL_CHARS * 4
MAX_PASSAGES = 8
MAX_PASSAGE_CHARS = 1200
MAX_DOCUMENTS = 20


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


_OVERVIEW = re.compile(r'^\s*(?:(?:please|can you|could you|give me)\s+)*(?:summari[sz]e\b|give\s+(?:me\s+)?(?:a\s+)?(?:summary|overview)\b)', re.I)
_STOP = frozenset('a an the is are was were be being been to of and or for in on at as by '
                  'with from that this these those it its my our your their what which '
                  'where when how who why can could would should does do did please '
                  'tell me find show say says about document documents file files '
                  'attached attachment agreement contract clause section'.split())


# A PDF's pages arrive joined by form feeds (the frontend reads it page by page, as
# pdftotext does). Text with none -- a .docx, a .txt -- has no pages, and says so.
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


def _terms(text: str) -> set[str]:
    # Python's \w drops combining marks, splitting Indian-script words into letters.
    words, token = set(), []
    for char in text.casefold() + ' ':
        if char.isalnum() or unicodedata.category(char).startswith('M'):
            token.append(char)
        elif token:
            word = ''.join(token)
            if len(word) > 1 and word not in _STOP:
                words.add(word)
            token.clear()
    return words


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


def collect(query: str, documents: dict, *, enabled: bool = True) -> DocumentEvidence:
    """Rank lexical matches locally; a match establishes presence, never legal truth."""
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
    candidates = []
    overview_documents = []
    total_chars = 0
    query_terms = _terms(query)
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
        for ordinal, (start, end) in enumerate(_spans(raw)):
            row['total_passages'] += 1
            snippet = raw[start:end]
            terms = _terms(snippet)
            overlap = len(query_terms & terms)
            if not overview and not overlap:
                continue
            # Ranking orders excerpts only. It is never a confidence or legal verdict.
            score = overlap / math.sqrt(max(1, len(terms)))
            rank = (-score, ordinal, position)
            if len(candidates) == MAX_PASSAGES and rank >= candidates[-1][:3]:
                continue
            passage: EvidencePassage = {'id': f'doc-{position + 1}-{start}-{end}',
                'document_id': did, 'name': row['name'], 'sha256': sha,
                'start': start, 'end': end, 'text': snippet, 'page': page_of(raw, start)}
            # Only the eight best records stay resident, even for hundreds of thousands
            # of tiny paragraphs. Ranking is identical to the previous stable full sort.
            if len(candidates) == MAX_PASSAGES:
                candidates.pop()
            bisect.insort(candidates, (*rank, passage), key=lambda candidate: candidate[:3])
    result['passages'] = [item[3] for item in candidates]
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
    if evidence['status'] == 'NOT_SEARCHED':
        return 'Your attachments were not searched. Enable your documents in Sources, then ask again.'
    if evidence['status'] == 'UNAVAILABLE':
        return 'I could not read the selected documents. Check the file status or select a smaller readable file.'
    if evidence['status'] == 'NO_MATCH':
        return 'I found no keyword matches in the readable selected documents. Try the exact wording or inspect the document; this does not mean the information is absent.'
    if evidence['mode'] == 'overview':
        return 'Here are excerpts sampled across your readable selected documents. This is a limited preview, not a complete summary or legal review.'
    return 'Here are matching excerpts from your readable selected documents. Read the surrounding text before drawing a conclusion; these excerpts have not been checked against law.'
