"""A3 review sheets made from SolidCraft model renders and measured print data."""
from pathlib import Path
import json
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader
import fitz

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'drawings'
OUT.mkdir(exist_ok=True)
pdfmetrics.registerFont(TTFont('Malgun','C:/Windows/Fonts/malgun.ttf'))
pdfmetrics.registerFont(TTFont('MalgunBold','C:/Windows/Fonts/malgunbd.ttf'))
W,H=landscape(A3)
C=canvas.Canvas(str(OUT/'FWB_v8_P2_A3.pdf'),pagesize=(W,H))
C.setTitle('Fold Wing Buddy v8 P2 - SolidCraft 3D and X1 Carbon print review')
INK='#27352e'; GREEN='#68724d'; LIGHT='#e7e9df'; GREY='#606b65'


def text(x,y,s,size=10,bold=False,color=INK):
    C.setFillColor(color);C.setFont('MalgunBold' if bold else 'Malgun',size)
    C.drawString(x*mm,y*mm,s)


def rule(x1,y1,x2,y2,color=LIGHT,width=0.6):
    C.setStrokeColor(color);C.setLineWidth(width)
    C.line(x1*mm,y1*mm,x2*mm,y2*mm)


def header(num,title,subtitle):
    text(16,279,'FOLD WING BUDDY',23,True)
    text(16,268,title,14,True)
    text(16,259,subtitle,9,color=GREY)
    text(346,280,'v8 / P2',16,True)
    text(346,270,'2026-10-23',10)
    rule(16,254,404,254,GREEN,1.2)
    rule(16,16,404,16)
    text(16,10,'검토·끼움 시험용  |  단위 mm  |  화면 맞춤 축척  |  실물 출력·하중·전체 가동 범위 미검증',8,color=GREY)
    text(380,10,f'{num} / 3',9)


def image(name,x,y,w,h):
    C.drawImage(ImageReader(str(ROOT/'renders'/name)),x*mm,y*mm,w*mm,h*mm,
                preserveAspectRatio=True,anchor='c',mask='auto')


def rows(x,y,data,lineheight=8,size=9):
    for label,value in data:
        text(x,y,label,size,True)
        text(x+48,y,value,size)
        y-=lineheight


header(1,'SolidCraft 3D 조립 검토','실제 .solidcraft 모델 렌더. AI 외관 참고 이미지가 아닌 CAD 형상이다.')
image('P2_iso.png',16,78,240,171)
text(20,242,'3D 등각 투상',10,True)
image('P2_front.png',266,177,136,77)
text(270,242,'전면',10,True)
image('P2_top.png',266,122,136,50)
text(270,166,'평면',10,True)
image('P2_right.png',310,25,75,96)
text(270,111,'측면',10,True)
rows(23,70,[('베이스','640 × 200 × 100 / 폭 방향 3분할'),
             ('트레이 1개','약 213.33 × 200 × 96'),
             ('현재 정지 높이','360 / 손목 축 높이 315'),
             ('편집 원본','cad/fold_wing_v8_P2.solidcraft'),
             ('새 피처','연결판·바닥 체결부, 손·혼 홈·베어링 자리·분할 정렬핀')],8.5,10)
text(23,23,'기존 머리·팔은 가져온 기준 형상을 유지하며, 새 손은 안정적인 네이티브 피처로 재작성했다.',9,color=GREY)
C.showPage()

header(2,'분할 베이스와 체결 상세','접착은 베이스 맞댐선의 선택 보강. 정렬과 체결은 핀·볼트·너트로 수행한다.')
image('P2_base_splices_top.png',16,126,270,125)
text(20,243,'뚜껑을 숨긴 실제 베이스 내부 / 연결판 4개',10,True)
image('P2_splice_detail.png',295,107,105,76)
text(298,177,'실제 네이티브 연결판',10,True)

# Top-view schematic with exact dimensions of the native splice.
ox,oy,sc=326,209,1.13
C.setFillColor(LIGHT);C.setStrokeColor(GREEN)
C.rect((ox-24*sc)*mm,(oy-22*sc)*mm,48*sc*mm,44*sc*mm,fill=1)
for dx in [-12,12]:
    for dy in [-14,14]:
        px,py=ox+dx*sc,oy+dy*sc
        C.setFillColor('#ffffff')
        C.rect((px-2.9*sc)*mm,(py-2.9*sc)*mm,5.8*sc*mm,5.8*sc*mm,fill=1)
        C.circle(px*mm,py*mm,1.7*sc*mm,fill=0)
for dx in [-8,8]:
    C.setDash(2,2);C.circle((ox+dx*sc)*mm,oy*mm,2*sc*mm,fill=0);C.setDash()
text(315,238,'48',10,True)
text(356,208,'44',10,True)
text(296,185,'Ø3.4 × 4 / 사각 너트 포켓 5.8 × 5.8',8.5)
rows(22,115,[('연결판','48 × 44 × 8, 아래 핀 돌출 2 (전체 높이 10)'),
              ('볼트 피치','X 방향 24 / Y 방향 28'),
              ('너트 포켓','M3 DIN 562 사각 너트 / 깊이 2.2'),
              ('볼트 / 수량','M3×10 낮은 버튼 머리 / 16개 + 사각 너트 16개'),
              ('바닥 머리 홈','6.4 × 6.4, 깊이 2.2'),
              ('핀 / 소켓','Ø4 / Ø4.4, 소켓 깊이 2.3'),
              ('스피커 하부','연결판 상단 Z12, BA-R9 하단 Z16, 정적 여유 4'),
              ('전원·배터리','미확정 예약 공간 바닥 Z14, 연결판 위 여유 2')],10,10)
text(295,96,'조립 순서',11,True)
for yy,s in [(86,'① 트레이 3개를 640 폭에 맞춰 정렬'),(76,'② 안쪽에서 연결판의 핀을 끼움'),(66,'③ 사각 너트를 위쪽 포켓에 삽입'),(56,'④ 아래에서 M3×10 볼트를 체결'),(46,'⑤ 실물 부품·배선 여유 확인'),(36,'⑥ 뚜껑은 자체 구멍으로 분리 체결')]:
    text(295,yy,s,9)
text(22,25,'시험 공차다. 먼저 소형 연결판과 실물 볼트·너트를 맞춰 보고 큰 외장을 출력한다.',9,color=GREY)
C.showPage()

m=json.loads((ROOT/'print/manifest.json').read_text(encoding='utf-8'))
header(3,'X1 Carbon 출력 방향과 단일 부품 배치','256 × 256 베드 / 프로파일 높이 250 / 앞 왼쪽 18 × 28 제외 / 브림 5 예약')
text(18,243,'각 칸은 별도 출력판이다. 외곽선은 형상의 경계상자다.',9)
for i,p in enumerate(m['parts']):
    col,row=i%5,i//5; x=18+col*39;y=203-row*42;ss=35/256
    C.setFillColor('#f5f6f0');C.setStrokeColor('#bdc5b9')
    C.rect(x*mm,y*mm,35*mm,35*mm,fill=1)
    C.setFillColor('#d9978a');C.rect(x*mm,y*mm,18*ss*mm,28*ss*mm,fill=1)
    lo,hi=p['plate_bbox_mm'];br=p['brim_bbox_xy_mm']
    C.setFillColor('#68724d');C.setStrokeColor(GREEN)
    C.rect((x+lo[0]*ss)*mm,(y+lo[1]*ss)*mm,(hi[0]-lo[0])*ss*mm,(hi[1]-lo[1])*ss*mm,fill=1)
    C.setDash(1,1);C.setStrokeColor('#65716b')
    C.rect((x+br[0][0]*ss)*mm,(y+br[0][1]*ss)*mm,(br[1][0]-br[0][0])*ss*mm,(br[1][1]-br[0][1])*ss*mm,fill=0)
    C.setDash();text(x,y-4,str(i+1).zfill(2),7,True)
text(221,243,'번호 / 부품 / 출력 경계상자 X × Y × Z',9,True)
for i,p in enumerate(m['parts']):
    dims=' × '.join(f'{v:.1f}' for v in p['oriented_bbox_mm'])
    yy=233-i*8.2
    text(221,yy,f'{i+1:02d}  {p["part"]}',7.7,True)
    text(221,yy-3.6,dims+' mm'+(' / 4개 출력' if p['part']=='HAND_DOWEL_4x6' else ''),7.4,color=GREY)
text(18,25,'3MF는 모델·위치만 포함한다. 재료·서포트·공정 프리셋과 G-code는 포함하지 않는다.',9,color=GREY)
C.save()

doc=fitz.open(OUT/'FWB_v8_P2_A3.pdf')
for i,page in enumerate(doc):
    page.get_pixmap(matrix=fitz.Matrix(1.35,1.35),alpha=False).save(OUT/f'FWB_v8_P2_A3_page{i+1}.png')
print('A3 PDF and review PNG pages written')
