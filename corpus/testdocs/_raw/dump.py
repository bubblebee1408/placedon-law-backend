import sys
from pypdf import PdfReader
f=sys.argv[1]; out=sys.argv[2]
r=PdfReader(f)
with open(out,'w',encoding='utf-8') as fh:
    for i,p in enumerate(r.pages):
        try: t=p.extract_text() or ''
        except Exception as e: t='[EXTRACT ERROR %s]'%e
        fh.write('\n<<<PAGE %d>>>\n'%(i+1)+t)
print('done',f,len(r.pages))
