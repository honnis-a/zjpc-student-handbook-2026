from pathlib import Path
from PIL import Image, ImageOps
import json

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path('/Users/nihao/Desktop/学生手册')
rows = json.loads((ROOT/'tmp/map_first/mapping.json').read_text()) + json.loads((ROOT/'tmp/map_second/mapping.json').read_text())
out = ROOT/'tmp/pages'
out.mkdir(parents=True, exist_ok=True)
pages=[]
toc=0
for row in rows:
    im=ImageOps.exif_transpose(Image.open(SOURCE/row['filename'])).convert('RGB')
    if row['rotation_ccw']:
        im=im.rotate(row['rotation_ccw'], expand=True)
    books=row['book_pages']
    if books is None:
        books=[None] * (2 if row['image_index']==2 else 1)
    for j, book in enumerate(books):
        scan=len(pages)+1
        if book is None:
            toc+=1
        if len(books)==2:
            # Keep a narrow gutter overlap so skewed lines are not cut off.
            bounds=(0,0,round(im.width*.515),im.height) if j==0 else (round(im.width*.485),0,im.width,im.height)
            page=im.crop(bounds)
        else:
            bounds=(0,0,im.width,im.height)
            page=im
        path=out/f'scan_{scan:03}.jpg'
        page.save(path,quality=98,subsampling=0)
        pages.append(dict(scan_id=scan,image_index=row['image_index'],filename=row['filename'],book_page=book,toc_page=toc if book is None else None,side=('left' if j==0 else 'right') if len(books)==2 else 'single',rotation_ccw=row['rotation_ccw'],crop_box=list(bounds),image_path=str(path),notes=row['notes']))
(ROOT/'tmp/pages_manifest.json').write_text(json.dumps(pages,ensure_ascii=False,indent=2))
present={p['book_page'] for p in pages if p['book_page'] is not None}
missing=sorted(set(range(1,max(present)+1))-present)
print('page occurrences:',len(pages),'toc:',toc,'unique numbered pages:',len(present),'missing in 1..157:',missing)
