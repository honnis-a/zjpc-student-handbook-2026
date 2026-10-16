from pathlib import Path
from PIL import Image,ImageOps
from concurrent.futures import ThreadPoolExecutor,as_completed
import json
from vision_ocr import recognize

ROOT=Path(__file__).resolve().parents[1]
pages=json.loads((ROOT/'tmp/pages_manifest.json').read_text())
groups={}
for p in pages:groups.setdefault(p['image_index'],[]).append(p)
OUT=ROOT/'tmp/ocr_full'
OUT.mkdir(exist_ok=True)
WIDE=ROOT/'tmp/pages_wide'
WIDE.mkdir(exist_ok=True)

def process(group):
    p=group[0]
    im=ImageOps.exif_transpose(Image.open(Path('/Users/nihao/Desktop/学生手册')/p['filename'])).convert('RGB')
    if p['rotation_ccw']:im=im.rotate(p['rotation_ccw'],expand=True)
    full=OUT/f"image_{p['image_index']:03}.jpg"
    im.save(full,quality=98,subsampling=0)
    lines=recognize(full)
    (OUT/f"image_{p['image_index']:03}.json").write_text(json.dumps(lines,ensure_ascii=False,indent=2))
    for page in group:
        selected=[]
        for l in lines:
            b=l['boundingBox']
            center=b['x']+b['width']/2
            if len(group)==1 or ((center<.5)==(page['side']=='left')):
                item=json.loads(json.dumps(l))
                if len(group)==2:
                    item['boundingBox']['x']=(b['x']-(0 if page['side']=='left' else .5))*2
                    item['boundingBox']['width']=b['width']*2
                selected.append(item)
        record=dict(scan_id=page['scan_id'],book_page=page['book_page'],lines=selected,status='ok',usesLanguageCorrection=False,recognitionLevel='accurate',source=str(full),source_kind='original_full_image')
        (OUT/f"scan_{page['scan_id']:03}.json").write_text(json.dumps(record,ensure_ascii=False,indent=2))
        if len(group)==2:
            bounds=(0,0,round(im.width*.60),im.height) if page['side']=='left' else (round(im.width*.40),0,im.width,im.height)
            wide=im.crop(bounds)
        else:wide=im
        wide.save(WIDE/f"scan_{page['scan_id']:03}.jpg",quality=98,subsampling=0)
    return p['image_index']

with ThreadPoolExecutor(max_workers=2) as pool:
    for i,f in enumerate(as_completed([pool.submit(process,g) for g in groups.values()]),1):
        f.result()
        if i%10==0 or i==len(groups):print(i,'/',len(groups),flush=True)
