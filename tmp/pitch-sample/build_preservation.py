from pathlib import Path
import json, re, hashlib
import pymupdf as fitz
from PIL import Image, ImageOps, ImageDraw

root=Path(__file__).resolve().parent
dest=root.parents[1]/'doc'/'계획서'/'샘플자료'
states=json.loads((root/'states.json').read_text(encoding='utf-8'))
pdf=fitz.open()
thumbs=[]
texts=[]
for i,state in enumerate(states,1):
    assert f'{i} / 36' in state, (i,state)
    src=Image.open(root/f'slide-{i:02}.png').convert('RGB')
    assert src.size==(1032,884), src.size
    # The observed Pitch viewport places its 16:9 slide between y=120 and y=700.
    slide=src.crop((0,120,1032,700))
    out=root/f'page-{i:02}.png'
    slide.save(out)
    page=pdf.new_page(width=1032,height=580)
    page.insert_image(page.rect,filename=str(out))
    lines=[re.sub(r'^.*? text ','',line) for line in state.splitlines() if ' text ' in line]
    lines=[x for x in lines if x not in [str(i),f'{i} / 36','Want to make a presentation like this one?', 'Start with a fully customizable template, create a beautiful deck in minutes, then easily share it with anyone.']]
    texts.append(f'## 슬라이드 {i:02}\n\n'+'\n\n'.join(lines))
    tile=Image.new('RGB',(268,174),'white')
    tile.paste(slide.resize((258,145)),(5,20))
    ImageDraw.Draw(tile).text((5,3),str(i),fill='black')
    thumbs.append(tile)
pdf.set_metadata({'title':'[케이토픽] 강원대학교_창업중심대학_발표평가','subject':'Pitch shared-view visual preservation, captured 2026-10-18; 36 slides; not native PDF export','creator':'Original Pitch slide screenshots assembled without content edits'})
target=dest/'Pitch_케이토픽_창업중심대학_발표평가_원본화면보존.pdf'
pdf.save(target,deflate=True)
(dest/'Pitch_케이토픽_슬라이드별_추출텍스트.md').write_text('# 케이토픽 발표자료 슬라이드별 추출 텍스트\n\n출처: https://pitch.com/v/__-45fz97/37aebdcb-269a-4ce7-963a-8077af32395a\n\n수집일: 2026-10-18 (KST). 화면 접근성 텍스트를 페이지별로 보존했다. 도표·이미지 속 글자와 공간적 배치는 누락될 수 있으므로 PDF 화면과 함께 확인한다. 추출 순서는 시각적 읽기 순서와 다를 수 있다. 원문 주장에 대한 독립 검증은 수행하지 않았다.\n\n'+'\n\n'.join(texts)+'\n',encoding='utf-8')
for start in [0,18]:
    sheet=Image.new('RGB',(268*3,174*6),'#dddddd')
    for j,tile in enumerate(thumbs[start:start+18]): sheet.paste(tile,((j%3)*268,(j//3)*174))
    sheet.save(root/f'contact-{start+1:02}.jpg')
print(json.dumps({'pages':len(pdf),'bytes':target.stat().st_size,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()},ensure_ascii=True))
