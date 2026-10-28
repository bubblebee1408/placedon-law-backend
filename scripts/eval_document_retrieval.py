"""Evaluate document excerpt retrieval (gateway.document_evidence.collect) on CUAD + a synthetic suite.

    PYTHONPATH=. python3 scripts/eval_document_retrieval.py                  # dev split (CUAD 0-50)
    PYTHONPATH=. python3 scripts/eval_document_retrieval.py --json out.json
    PYTHONPATH=. python3 scripts/eval_document_retrieval.py --impl mymod:collect   # candidate side by side
    PYTHONPATH=. python3 scripts/eval_document_retrieval.py --set ALPHA=0.4 --set STEMMING=False

Non-circular split (runbook .claude/loops/RETRIEVAL_LOOP.md): tune on contracts 0-50 (dev);
contracts 51-101 (heldout) are reported ONCE, after the algorithm is frozen.

Relevance is span overlap: a passage [start, end) is relevant when it overlaps any CUAD gold
answer span [answer_start, answer_start + len(text)). Gold comes from CUAD's lawyer annotations,
never from the retriever's own output. Deterministic: no randomness, fixed iteration order.
"""
from __future__ import annotations

import argparse
import ast
import importlib
import inspect
import json
import re
import sys
import time
from pathlib import Path

CUAD = Path(__file__).resolve().parent.parent / 'corpus' / 'benchmark' / 'cuad' / 'test.json'
DEV, HELDOUT = range(0, 51), range(51, 102)
KS = (1, 3, 8)
_TEMPLATE = re.compile(r'related to "(?P<cat>.+?)".*?Details:\s*(?P<details>.*)$', re.S)


def load_impl(spec: str, overrides: list[str] = ()):
    module_name, _, func = spec.partition(':')
    module = importlib.import_module(module_name)
    for item in overrides:
        name, sep, value = item.partition('=')
        if not sep or not hasattr(module, name):
            raise SystemExit(f'--set {item!r}: {module_name} has no constant {name!r}')
        setattr(module, name, ast.literal_eval(value))
    if overrides and hasattr(module, '_index_form'):
        module._index_form.cache_clear()  # STEMMING is read inside an lru_cache
    return getattr(module, func or 'collect')


def queries(question: str) -> dict[str, str]:
    m = _TEMPLATE.search(question)
    if not m:
        raise ValueError(f'unexpected CUAD question template: {question[:80]!r}')
    cat, details = m['cat'].strip(), m['details'].strip()
    return {'long': f'What does the contract say about {cat}? {details}', 'short': cat}


def overlaps(p: dict, gold: list[tuple[int, int]]) -> bool:
    return any(p['start'] < g_end and g_start < p['end'] for g_start, g_end in gold)


def score(passages: list[dict], gold: list[tuple[int, int]], status: str = 'EXCERPTS_FOUND') -> dict:
    rel = [overlaps(p, gold) for p in passages]
    first = next((i for i, r in enumerate(rel) if r), None)
    row = {f'r@{k}': float(first is not None and first < k) for k in KS}
    row.update(mrr=0.0 if first is None else 1.0 / (first + 1),
               precision=(sum(rel) / len(rel)) if rel else 0.0,
               shown=float(len(passages)), empty=float(status == 'NO_MATCH'),
               # UNAVAILABLE / LIMIT: the document was never searched (e.g. > MAX_DOCUMENT_CHARS).
               unsearched=float(status not in ('EXCERPTS_FOUND', 'NO_MATCH')))
    return row


def mean(rows: list[dict]) -> dict:
    if not rows:
        return {}
    return {k: sum(r[k] for r in rows) / len(rows) for k in rows[0]}


def eval_cuad(collect, indices: range) -> dict:
    data = json.loads(CUAD.read_text(encoding='utf-8'))['data']
    rows = {'long': [], 'short': []}
    per_query = []
    by_cat: dict[str, dict[str, list]] = {}
    failures = []
    t0 = time.perf_counter()
    for i in indices:
        entry = data[i]
        para = entry['paragraphs'][0]
        context = para['context']
        for qa in para['qas']:
            if not qa['answers']:
                continue
            gold = [(a['answer_start'], a['answer_start'] + len(a['text'])) for a in qa['answers']]
            cat = _TEMPLATE.search(qa['question'])['cat']
            for variant, query in queries(qa['question']).items():
                got = collect(query, {'c': {'text': context, 'name': entry['title']}})
                row = score(got['passages'], gold, got['status'])
                rows[variant].append(row)
                top = got['passages'][0] if got['passages'] else None
                per_query.append({'contract': i, 'category': cat, 'variant': variant, 'query': query,
                    'top1': None if top is None else [top['start'], top['end']],
                    'top1_text': None if top is None else top['text'][:200], 'r@1': row['r@1'],
                    'mrr': row['mrr'], 'unsearched': row['unsearched'], 'n_gold': len(gold),
                    'gold_covered': sum(any(overlaps(p, [g]) for p in got['passages']) for g in gold)})
                by_cat.setdefault(cat, {'long': [], 'short': []})[variant].append(row)
                if row['r@1'] == 0.0:
                    top = got['passages'][0] if got['passages'] else None
                    failures.append({'contract': i, 'title': entry['title'], 'category': cat,
                        'variant': variant, 'query': query, 'status': got['status'],
                        'shown': len(got['passages']), 'rank_of_first_relevant':
                            None if row['mrr'] == 0 else round(1 / row['mrr']),
                        'top_passage': None if top is None else top['text'][:300],
                        'gold': [context[s:e][:300] for s, e in gold[:2]]})
    return {'contracts': len(indices), 'answerable_questions': len(rows['long']),
            'wall_seconds': round(time.perf_counter() - t0, 2),
            'long': mean(rows['long']), 'short': mean(rows['short']),
            # Excludes questions whose contract exceeds MAX_DOCUMENT_CHARS (never searched).
            'long_searched': mean([r for r in rows['long'] if not r['unsearched']]),
            'short_searched': mean([r for r in rows['short'] if not r['unsearched']]),
            'searched_questions': sum(1 for r in rows['long'] if not r['unsearched']),
            'by_category': {c: {v: mean(r) | {'n': len(r)} for v, r in d.items()}
                            for c, d in sorted(by_cat.items())},
            'failures_at_1': failures, 'per_query': per_query}


# --- SYNTHETIC SUITE: hand-built, no real client data. Reproduces the 2026-10-28 bug. ---
_FILLER = ('Administrative schedule {n}. The reporting period for this schedule is the calendar '
           'quarter. Contact details for each period are kept by the account manager. Records for '
           'the period are retained in the shared folder.')
_PAGES = [_FILLER.format(n=n) for n in range(1, 9)]
_PAGES[2] = ('Fees. The Client shall pay a monthly fee of INR 50,000. Payment is due within fifteen '
             'days of the invoice date for each period.')
_PAGES[5] = "Termination. Either party may terminate this Agreement by giving sixty days' written notice."
# Trap for the semantic-gap cases (DECISION §8): a filler page that says "end" (added 2026-10-28, L5).
_PAGES[7] += ' Folder access lapses at the end of each quarter.'
SYNTHETIC_TEXT = '\f'.join(_PAGES)
_TERM_Q = 'What does the termination clause say?'
# (name, question, prior user questions oldest first, gold page, pass rule)
# pass rule 'gold': top on gold AND every shown page is gold; 'gold_or_none': NO_MATCH also passes.
SYNTHETIC_CASES = [
    ('notice-period', 'What notice period does the termination clause require?', [], 6, 'gold'),
    ('fee-and-due', 'How much is the monthly fee and when is payment due?', [], 3, 'gold'),
    ('semantic-gap', 'When can a party end the agreement early?', [], 6, 'gold'),
    ('semantic-gap-2', 'When may this be brought to an end before it expires?', [], 6, 'gold_or_none'),
    ('followup-termination', 'And how long is that?', [_TERM_Q], 6, 'gold'),
    ('followup-fee', 'And what if it is paid late?', ['How much is the monthly fee?'], 3, 'gold'),
    ('followup-no-cue', 'How long is that?', [_TERM_Q], 6, 'gold'),
    # Third turn depends on the FIRST; phase 1 reads one previous question only (M = 1): expected FAIL.
    ('followup-chain-3', 'And can that be waived?', [_TERM_Q, 'And how long is that?'], 6, 'gold'),
]


def run_synthetic_case(collect, query: str, gold_page: int, rule: str, **kwargs) -> dict:
    got = collect(query, {'s': {'text': SYNTHETIC_TEXT, 'name': 'synthetic-8-page.txt'}}, **kwargs)
    pages = [p['page'] for p in got['passages']]
    top_ok = bool(pages) and pages[0] == gold_page
    ok = top_ok and set(pages) == {gold_page}
    return {'query': query, 'status': got['status'], 'pages_shown': pages,
            'history_query': got.get('history_query'), 'top_on_gold': top_ok,
            'pass': ok or (rule == 'gold_or_none' and got['status'] == 'NO_MATCH')}


def eval_synthetic(collect) -> list[dict]:
    has_history = 'previous_query' in inspect.signature(collect).parameters
    out = []
    for name, question, priors, page, rule in SYNTHETIC_CASES:
        base = {'case': name, 'gold_page': page, 'rule': rule}
        if not priors:
            out.append({**base, 'mode': 'alone', **run_synthetic_case(collect, question, page, rule)})
            continue
        out.append({**base, 'mode': 'second-alone', **run_synthetic_case(collect, question, page, rule)})
        if has_history:
            out.append({**base, 'mode': 'previous_query', **run_synthetic_case(
                collect, question, page, rule, previous_query=priors[-1])})
        out.append({**base, 'mode': 'prepend-all', **run_synthetic_case(
            collect, ' '.join([*priors, question]), page, rule)})
    return out


def print_report(cuad: dict | None, synth: list[dict], split: str, impl: str) -> None:
    print(f'impl={impl} split={split}')
    if cuad:
        print(f"CUAD contracts={cuad['contracts']} answerable={cuad['answerable_questions']} "
              f"wall={cuad['wall_seconds']}s")
        head = ('variant', 'R@1', 'R@3', 'R@8', 'MRR', 'prec', 'shown', 'empty', 'unsrch')
        print('  '.join(f'{h:>7}' for h in head))
        for v in ('long', 'short', 'long_searched', 'short_searched'):
            m = cuad[v]
            print('  '.join([f'{v.replace("_searched", "*"):>7}'] + [f'{m[k]:7.3f}' for k in
                  ('r@1', 'r@3', 'r@8', 'mrr', 'precision')] + [f"{m['shown']:7.2f}", f"{m['empty']:7.3f}", f"{m['unsearched']:7.3f}"]))
        print(f"  (* = searched only: {cuad['searched_questions']} questions, over-limit contracts excluded)")
    print('SYNTHETIC (hand-built, not real data)')
    for r in synth:
        print(f"  {'PASS' if r['pass'] else 'FAIL'}  {r['case']:<21} {r['mode']:<14} gold=p{r['gold_page']} "
              f"shown={len(r['pages_shown'])} pages={r['pages_shown']}")


def _self_check() -> None:
    gold = [(10, 20)]
    s = score([{'start': 0, 'end': 5}, {'start': 15, 'end': 30}], gold)
    assert s['r@1'] == 0 and s['r@3'] == 1 and s['mrr'] == 0.5 and s['precision'] == 0.5
    assert score([], gold, 'NO_MATCH')['empty'] == 1 and score([], gold)['precision'] == 0
    assert score([], gold, 'UNAVAILABLE')['unsearched'] == 1
    assert not overlaps({'start': 20, 'end': 25}, gold)  # half-open: touching is not overlap
    assert queries('... related to "Governing Law" that should be ... Details: Which law?') == {
        'long': 'What does the contract say about Governing Law? Which law?', 'short': 'Governing Law'}
    assert SYNTHETIC_TEXT.count('\f') == 7


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--split', choices=('dev', 'heldout', 'all'), default='dev')
    ap.add_argument('--json', dest='json_out')
    ap.add_argument('--impl', default='gateway.document_evidence:collect')
    ap.add_argument('--synthetic-only', action='store_true')
    ap.add_argument('--set', dest='overrides', action='append', default=[], metavar='NAME=value',
                    help='override a module constant of the --impl module (repeatable)')
    args = ap.parse_args(argv)
    _self_check()
    if args.split in ('heldout', 'all'):
        print('WARNING: held-out contracts 51-101 are for the ONE final verdict after the '
              'algorithm is frozen. Do not tune on these numbers.', file=sys.stderr)
    collect = load_impl(args.impl, args.overrides)
    indices = {'dev': DEV, 'heldout': HELDOUT, 'all': range(0, 102)}[args.split]
    cuad = None if args.synthetic_only else eval_cuad(collect, indices)
    synth = eval_synthetic(collect)
    print_report(cuad, synth, args.split, args.impl)
    if args.json_out:
        Path(args.json_out).write_text(json.dumps({'impl': args.impl, 'split': args.split,
            'overrides': args.overrides,
            'cuad': cuad, 'synthetic': synth}, indent=1, ensure_ascii=False), encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
