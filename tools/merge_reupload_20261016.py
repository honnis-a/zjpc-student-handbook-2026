"""Merge visually reviewed replacement pages and supplied missing pages."""
from pathlib import Path
import csv, hashlib, json, re

ROOT=Path(__file__).resolve().parents[1]
SUP=ROOT/'tmp/reupload_20261016'
OUT=ROOT/'output'
base=json.loads((ROOT/'tmp/pages_manifest.json').read_text())
sources=json.loads((SUP/'source_manifest.json').read_text())
source_by_book={r['book_page']:r for r in sources}
folders=['review_root','review_first','review_second','review_tail']
blank_reviews=json.loads((SUP/'blanks/review.json').read_text())
blank_by_book={r['book_page']:r for r in blank_reviews}
replacement_reviews=json.loads((SUP/'replacements/review.json').read_text())
assert {r['book_page'] for r in replacement_reviews}=={24,28,78}
assert all(r['entire_page_visually_checked'] and not r['remaining_unclear'] for r in replacement_reviews)
phone_review=json.loads((SUP/'phone_158_review.json').read_text())

def added(book):
    src=source_by_book[book]
    if book==158:
        path=SUP/'phone_158.md';blank=False;rotation=0
    else:
        review=blank_by_book[book]
        assert not review['has_recognition_issue']
        path=Path(review['markdown_path']);blank=review['blank'];rotation=review['rotation_ccw']
    return dict(book_page=book,source=src['source'],filename=src['filename'],side='single',body_path=str(path),blank=blank,rotation_ccw=rotation,base_scan_id=None)

before={3:[1,2],33:[32],73:[72],75:[74],123:[122],125:[124]}
combined=[]
for p in base:
    book=p['book_page']
    for new_book in before.get(book,[]):
        combined.append(added(new_book))
    paths=[ROOT/f'tmp/{f}/scan_{p["scan_id"]:03}.md' for f in folders if (ROOT/f'tmp/{f}/scan_{p["scan_id"]:03}.md').exists()]
    assert len(paths)==1
    row=dict(p,base_scan_id=p['scan_id'],body_path=str(paths[0]),source=str(Path('/Users/nihao/Desktop/学生手册')/p['filename']),blank=False)
    if book in {24,28,78}:
        src=source_by_book[book]
        row.update(body_path=str(SUP/f'replacements/book_{book:03}.md'),source=src['source'],filename=src['filename'],side='single',rotation_ccw=0,replaced_source=p['filename'])
    combined.append(row)
combined.append(added(158))

issues=[]
for entry in phone_review['issues']:
    issues.append(dict(book_page=158,position=entry['location'],reason='数字字形存在歧义，无法高置信度确认，需要重新上传该局部的清晰图片。'))

blocks=[];mapping=[];seen={};duplicates=[]
for n,p in enumerate(combined,1):
    book=p['book_page'];p['scan_id']=n
    body=Path(p['body_path']).read_text().strip()
    assert body or p['blank'],(book,'unverified empty page')
    book_label=f'{book:03}' if book is not None else f"无印刷页码（目录 {p['toc_page']}）"
    side={'single':'单页','left':'左页','right':'右页'}[p['side']]
    fields=[f'Page: {n:03}',f'Book Page: {book_label}',f'Source: {p["filename"]}',f'Side: {side}']
    if p['blank']:fields.append('Blank: true')
    if p.get('replaced_source'):fields.append('Previous Source: '+p['replaced_source'])
    marker='<!-- '+' | '.join(fields)+' -->'
    if book is not None and book in seen:
        first=seen[book]
        body=f'[疑似与扫描第 {first:03} 页（印刷第 {book} 页）重复，请人工确认]\n\n'+body
        duplicates.append(dict(scan_id=n,book_page=book,first_scan_id=first))
    elif book is not None:seen[book]=n
    blocks.append(marker+('\n\n'+body if body else ''))
    mapping.append(dict(scan_page=f'{n:03}',book_page=book if book is not None else f"目录{p['toc_page']}",source_image=p['filename'],side=side,blank=p['blank'],previous_scan_page=p.get('base_scan_id') or '',previous_source_image=p.get('replaced_source','')))

missing=sorted(set(range(1,159))-set(seen))
assert not missing
issue_text='## 需要重新上传的页面\n\n'
if issues:
    issue_text+='\n'.join(f"- 第 {i['book_page']} 页：{i['position']}，{i['reason']}" for i in issues)+'\n'
else:issue_text+='本批次所有页面均可清晰识别。\n'
text='\n\n'.join(blocks)+'\n\n'+issue_text
assert len(combined)==167
assert re.findall(r'^<!-- Page: (\d{3}) \|',text,re.M)==[f'{i:03}' for i in range(1,168)]
assert sum(p['blank'] for p in combined)==6
assert len(duplicates)==6
assert text.count('[疑似与扫描第 ')==6
assert len({p['filename'] for p in combined})==95
assert not re.search(r'\[第 (24|28|78) 页[^\]]*需要重新上传\]',text)
assert '60元/分计' in text
assert '\ufffd' not in text
assert not re.search(r'以下是 OCR 结果|我已经完成整理|根据图片可以看到|这一页主要讲了',text)
for r in sources:
    assert hashlib.sha256(Path(r['source']).read_bytes()).hexdigest()==r['sha256']
for r in json.loads((ROOT/'tmp/source_manifest.json').read_text()):
    assert hashlib.sha256((Path('/Users/nihao/Desktop/学生手册')/r['filename']).read_bytes()).hexdigest()==r['sha256']

(OUT/'学生手册.md').write_text(text)
(OUT/'需要重新上传的页面.md').write_text(issue_text)
with (OUT/'页码对照.csv').open('w',encoding='utf-8-sig',newline='') as stream:
    writer=csv.DictWriter(stream,fieldnames=list(mapping[0]));writer.writeheader();writer.writerows(mapping)
(ROOT/'tmp/combined_pages_manifest.json').write_text(json.dumps(combined,ensure_ascii=False,indent=2))
report=dict(source_images=95,new_source_images=11,page_occurrences=167,unnumbered_contents_pages=3,unique_numbered_pages=158,confirmed_blank_book_pages=[2,32,72,74,122,124],replaced_book_pages=[24,28,78],added_book_pages=[1,2,32,72,74,122,124,158],missing_printed_pages=missing,unclear_printed_pages=sorted({i['book_page'] for i in issues}),duplicate_occurrences=duplicates,all_source_files_unchanged=True,page_markers_contiguous=True,all_pages_visually_reviewed=True,characters=len(text),output_sha256=hashlib.sha256(text.encode()).hexdigest())
(ROOT/'tmp/final_quality_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False,indent=2))
