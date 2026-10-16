import urllib.request, json, concurrent.futures
from pathlib import Path
from PIL import Image
root=Path(__file__).resolve().parents[2]
out=root/'doc/계획서/assets/competitors'
out.mkdir(parents=True,exist_ok=True)
assets=[
 {'id':'miko3','name':'Miko 3','type':'공식 제품 사진','page':'https://miko.ai/products/miko-3','url':'https://miko.ai/cdn/shop/files/miko-red_1_88c13e0f-d894-4ab1-a7a9-d85d83f6ddad.png?v=1763631213&width=1000'},
 {'id':'smartall','name':'웅진스마트올 초등','type':'공식 제품 대표 이미지','page':'https://www.wjthinkbig.com/prod/subjectDetail.do?subjectId=S0000068','url':'https://online-cloud.wjthinkbig.com/contents/product/18fd3071-a1b9-44e8-a99d-ea5cba95ef9a.jpg'},
 {'id':'forest','name':'Forest','type':'공식 앱 아이콘','page':'https://forestapp.cc/','url':'https://forestapp.cc/assets/forest_icon_512-CSz_KJjV.png'},
 {'id':'focusmate','name':'Focusmate','type':'공식 로고','page':'https://www.focusmate.com/pricing/','url':'https://focusmate.wpenginepowered.com/wp-content/uploads/2021/12/cropped-1-11-18-Focusmate-logo-purple-Avenir-next-2-1.png'},
]
def fetch(a):
 path=out/(a['id']+Path(a['url'].split('?')[0]).suffix)
 req=urllib.request.Request(a['url'],headers={'User-Agent':'Mozilla/5.0'})
 path.write_bytes(urllib.request.urlopen(req,timeout=40).read())
 im=Image.open(path); im.verify()
 a['file']=path.name;a['checked']='2026-10-16';a['rights']='각 브랜드 및 원권리자. 경쟁 제품 식별·분석용으로 원본 비율 유지. 제휴·추천을 의미하지 않음.'
 print(a['id'],Image.open(path).size)
 return a
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
 result=list(ex.map(fetch,assets))
(out/'sources.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
