import re, sys

def load(p):
    return open(p, encoding='utf-8').read().split('\n')

def clean(lines, drop_patterns):
    out = []
    for ln in lines:
        if ln.startswith('<<<PAGE '):
            continue
        s = ln.strip()
        if any(re.search(p, s, re.I) for p in drop_patterns):
            continue
        out.append(ln.rstrip())
    # collapse >2 blank lines
    res, blank = [], 0
    for ln in out:
        if not ln.strip():
            blank += 1
            if blank > 1:
                continue
        else:
            blank = 0
        res.append(ln)
    return '\n'.join(res).strip() + '\n'

DROP = [
    r'^GUIDANCE NOTE ON MEETINGS OF THE BOARD OF DIRECTORS\s*\d*$',
    r'^\d*\s*GUIDANCE NOTE ON MEETINGS OF THE BOARD OF DIRECTORS$',
    r'^GUIDANCE NOTE ON GENERAL MEETINGS\s*\d*$',
    r'^\d*\s*GUIDANCE NOTE ON GENERAL MEETINGS$',
    r'^ANNEXURES?\s*\d*$',
]

def cut(src, out, start, end, header, dropextra=()):
    lines = load(src)
    body = clean(lines[start-1:end-1], DROP + list(dropextra))
    open(out, 'w', encoding='utf-8').write(header + '\n\n' + body)
    print(f'{out}: {len(body)} chars, lines {start}-{end-1}')

if __name__ == '__main__':
    import json
    for job in json.load(open(sys.argv[1])):
        cut(job['src'], job['out'], job['start'], job['end'], job['header'], job.get('drop', []))
