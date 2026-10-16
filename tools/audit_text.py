from pathlib import Path
import json,re,difflib
ROOT=Path(__file__).resolve().parents[1]
pages=json.loads((ROOT/'tmp/pages_manifest.json').read_text())
folders=['review_root','review_first','review_second','review_tail']
norm=lambda s:re.sub(r'[^\u3400-\u9fffA-Za-z0-9]','',s)
flags=[]
missing=[]
for p in pages:
    n=p['scan_id']
    paths=[ROOT/f'tmp/{f}/scan_{n:03}.md' for f in folders if (ROOT/f'tmp/{f}/scan_{n:03}.md').is_file()]
    if not paths:
        missing.append(n);continue
    if len(paths)>1:raise ValueError(f'duplicate reviewed output {n}')
    t=norm(paths[0].read_text())
    # Spot substantial OCR lines omitted from the reviewed output. This audit
    # identifies candidates only; image review decides whether they are real.
    for engine in ['ocr','ocr_full']:
        raw=json.loads((ROOT/f'tmp/{engine}/scan_{n:03}.json').read_text())['lines']
        for l in raw:
            s=norm(l['text']);b=l['boundingBox']
            if len(s)<12 or b['y']<.09 or b['y']>.88 or l['confidence']<.9:continue
            if s in t:continue
            match=difflib.SequenceMatcher(None,s,t,autojunk=False).find_longest_match()
            if match.size/len(s)<.55:
                flags.append(dict(scan=n,book=p['book_page'],engine=engine,index=l['index'],text=l['text'],longest_fraction=round(match.size/len(s),2)))
(ROOT/'tmp/text_audit.json').write_text(json.dumps(dict(missing=missing,flags=flags),ensure_ascii=False,indent=2))
print('missing reviewed:',missing,'flagged lines:',len(flags))
for f in flags:print(json.dumps(f,ensure_ascii=False))
