import sys, re
def slice_out(src, out, start, end, header):
    lines = open(src, encoding='utf-8').read().split('\n')
    body = [l.rstrip() for l in lines[start-1:end-1] if not l.startswith('<<<PAGE ')]
    res, blank = [], 0
    for l in body:
        if not l.strip():
            blank += 1
            if blank > 1: continue
        else: blank = 0
        res.append(l)
    txt = header + '\n\n' + '\n'.join(res).strip() + '\n'
    open(out,'w',encoding='utf-8').write(txt)
    print(f'{out}: {len(txt)} chars')
if __name__=='__main__':
    slice_out(sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5])
