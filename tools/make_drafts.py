from pathlib import Path
import json,re,statistics,argparse

ROOT=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser()
ap.add_argument('--full',action='store_true')
args=ap.parse_args()
OUT=ROOT/('tmp/full_draft' if args.full else 'tmp/draft')
OUT.mkdir(exist_ok=True)
PAGES=json.loads((ROOT/'tmp/pages_manifest.json').read_text())
cn='一二三四五六七八九十百〇零'
start=re.compile(r'^(第['+cn+r'\d]+条|[（(]['+cn+r'\d]+[）)]|['+cn+r']+[、．]|\d+[.．、])')
chapter=re.compile(r'^第['+cn+r'\d]+[章节篇]')

for page in PAGES:
    n=page['scan_id']
    raw=json.loads((ROOT/f"tmp/{'ocr_full' if args.full else 'ocr'}/scan_{n:03}.json").read_text())['lines']
    (OUT/f'scan_{n:03}.txt').write_text('\n'.join(f"{l['index']:02} {l['text']}" for l in raw)+'\n')
    lines=[]
    for l in raw:
        s=l['text'].strip();b=l['boundingBox']
        if page['book_page'] is not None:
            if b['y']>.885: continue
            if s==str(page['book_page']) and b['y']<.18: break
            if not args.full and (b['x']>.945 or b['x']+b['width']<.045): continue
        if s:lines.append(l)
    if not lines:
        (OUT/f'scan_{n:03}.md').write_text('')
        continue
    hs=[l['boundingBox']['height'] for l in lines if len(l['text'])>12]
    h=statistics.median(hs) if hs else .025
    paras=[]
    prev=None
    for i,l in enumerate(lines):
        s=l['text'].strip();b=l['boundingBox']
        local=lines[max(0,i-3):min(len(lines),i+4)]
        base=min(v['boundingBox']['x'] for v in local)
        indented=b['x']-base>.034
        isheading=bool(chapter.match(s)) and len(s)<40
        # This is a layout draft only. Every result must be reviewed against the image.
        if isheading:
            prefix='## ' if '篇' in s[:8] else '### '
            paras.append(prefix+s)
        elif page['book_page'] is None:
            paras.append(s)
        elif not paras or prev is None:
            paras.append(s)
        else:
            pb=prev['boundingBox']
            same_row=abs((b['y']+b['height']/2)-(pb['y']+pb['height']/2))<min(b['height'],pb['height'])*.6 and b['x']>pb['x']+pb['width']*.7
            gap=pb['y']-(b['y']+b['height'])
            if same_row:
                paras[-1]+=' '+s
            elif start.match(s) or indented or gap>h*.9 or paras[-1].startswith('#'):
                paras.append(s)
            else:
                sep=' ' if re.search(r'[A-Za-z]$',paras[-1]) and re.match(r'[A-Za-z]',s) else ''
                paras[-1]+=sep+s
        prev=l
    (OUT/f'scan_{n:03}.md').write_text('\n\n'.join(paras)+'\n')
print('159 layout drafts created; not yet verified')
