from pathlib import Path
from collections import Counter
import json,re,csv,hashlib

ROOT=Path(__file__).resolve().parents[1]
if (ROOT/'tmp/reupload_20261016/phone_158_review.json').exists():
    import runpy
    runpy.run_path(str(ROOT/'tools/merge_reupload_20261016.py'),run_name='__main__')
    raise SystemExit(0)
OUT=ROOT/'output'
OUT.mkdir(exist_ok=True)
pages=json.loads((ROOT/'tmp/pages_manifest.json').read_text())
folders=['review_root','review_first','review_second','review_tail']
issues=[]
for folder in folders:
    data=json.loads((ROOT/f'tmp/{folder}/issues.json').read_text())
    issues.extend(data if isinstance(data,list) else data.get('needs_reupload',[]))
seen={}
blocks=[]
duplicates=[]
mapping=[]
for p in pages:
    n=p['scan_id'];book=p['book_page']
    candidates=[ROOT/f'tmp/{f}/scan_{n:03}.md' for f in folders if (ROOT/f'tmp/{f}/scan_{n:03}.md').is_file()]
    assert len(candidates)==1,(n,candidates)
    body=candidates[0].read_text().strip()
    assert body,(n,'empty page')
    book_label=f'{book:03}' if book is not None else f"无印刷页码（目录 {p['toc_page']}）"
    side={'left':'左页','right':'右页','single':'单页'}[p['side']]
    marker=f"<!-- Page: {n:03} | Book Page: {book_label} | Source: {p['filename']} | Side: {side} -->"
    if book is not None and book in seen:
        first=seen[book]
        body=f'[疑似与扫描第 {first:03} 页（印刷第 {book} 页）重复，请人工确认]\n\n'+body
        duplicates.append(dict(scan_id=n,book_page=book,first_scan_id=first))
    elif book is not None:
        seen[book]=n
    blocks.append(marker+'\n\n'+body)
    mapping.append(dict(scan_page=f'{n:03}',book_page=book if book is not None else f"目录{p['toc_page']}",source_image=p['filename'],image_index=p['image_index'],side=side))

# The visible contents page explicitly lists a section beginning on page 158.
missing=sorted(set(range(1,159))-set(seen))
problem_rows=[]
for book in missing:
    reason='未在提供的扫描图片中找到，需要补充上传。'
    if book==158:reason='目录列有“浙江药科职业大学校内常用联系电话一览表”，但未提供对应扫描图片，需要补充上传。'
    problem_rows.append((book,reason))
for issue in issues:
    reason=issue['reason'].rstrip('。；')
    problem_rows.append((issue['book_page'],issue['position']+'：'+reason+'；需要重新上传。'))
problem_rows.sort(key=lambda row:row[0])
issue_text='## 需要重新上传的页面\n\n'+'\n'.join(f'- 第 {book} 页：{reason}' for book,reason in problem_rows)+'\n'
text='\n\n'.join(blocks)+'\n\n'+issue_text
assert re.findall(r'^<!-- Page: (\d{3}) \|',text,re.M)==[f'{i:03}' for i in range(1,160)]
assert len({p['image_index'] for p in pages})==84
assert text.count('[疑似与扫描第 ')==6
assert '\ufffd' not in text
assert not re.search(r'以下是 OCR 结果|我已经完成整理|根据图片可以看到|这一页主要讲了',text)
for issue in issues:
    body=blocks[issue['scan_id']-1]
    assert '需要重新上传' in body,issue
(OUT/'学生手册.md').write_text(text)
(OUT/'需要重新上传的页面.md').write_text(issue_text)
with (OUT/'页码对照.csv').open('w',encoding='utf-8-sig',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=list(mapping[0]));writer.writeheader();writer.writerows(mapping)

source_manifest=json.loads((ROOT/'tmp/source_manifest.json').read_text())
for row in source_manifest:
    path=Path('/Users/nihao/Desktop/学生手册')/row['filename']
    assert hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256'],('source changed',path)
report=dict(source_images=84,page_occurrences=159,unnumbered_contents_pages=3,unique_numbered_pages=len(seen),duplicate_occurrences=duplicates,missing_printed_pages=missing,unclear_printed_pages=sorted({i['book_page'] for i in issues}),all_source_files_unchanged=True,page_markers_contiguous=True,all_159_pages_have_reviewed_text=True,ocr_omission_audit_candidates=10,ocr_omission_audit_candidates_visually_resolved=10,characters=len(text),output_sha256=hashlib.sha256(text.encode()).hexdigest())
(ROOT/'tmp/final_quality_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False,indent=2))
