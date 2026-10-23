"""A3 reference sheets for existing P0 test coupons, not production release.
Geometry on sheet 1 is 1:1 in millimetres. Sheet 2 is a conceptual section.
Only writes FWB_DETAIL_reference_A3.pdf and its two rendered page PNGs.
"""
from pathlib import Path
import math
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor, white
import fitz

HERE=Path(__file__).resolve().parent
OUT=HERE.parent/'drawings'
OUT.mkdir(exist_ok=True)
pdfmetrics.registerFont(TTFont('MG',r'C:/Windows/Fonts/malgun.ttf'))
pdfmetrics.registerFont(TTFont('MGB',r'C:/Windows/Fonts/malgunbd.ttf'))
PDF=OUT/'FWB_DETAIL_reference_A3.pdf'
C=canvas.Canvas(str(PDF),pagesize=(420*mm,297*mm))
C.setTitle('Fold Wing Buddy v6 P0 - 끼움 시험편 및 관절 참고도')
C.setAuthor('300 Seconds project - sourced P0 reference')
INK='#202a31'; MUTED='#5d6870'; BLUE='#2f6888'; GREEN='#60704d'; AMBER='#9c5d22'

def line(x1,y1,x2,y2,color=INK,width=.3,dash=None):
    C.setStrokeColor(HexColor(color));C.setLineWidth(width*mm)
    C.setDash(dash or []);C.line(x1*mm,y1*mm,x2*mm,y2*mm);C.setDash([])

def txt(x,y,s,size=9,bold=False,color=INK,align='left',rotate=0):
    C.saveState();C.translate(x*mm,y*mm);C.rotate(rotate)
    C.setFillColor(HexColor(color));C.setFont('MGB' if bold else 'MG',size)
    if align=='center':C.drawCentredString(0,0,s)
    elif align=='right':C.drawRightString(0,0,s)
    else:C.drawString(0,0,s)
    C.restoreState()

def rect(x,y,w,h,fill=None,stroke=INK,width=.35):
    C.setLineWidth(width*mm);C.setStrokeColor(HexColor(stroke) if stroke else white)
    C.setFillColor(HexColor(fill) if fill else white)
    C.rect(x*mm,y*mm,w*mm,h*mm,stroke=bool(stroke),fill=bool(fill))

def circle(x,y,r,fill=None,stroke=INK,width=.3):
    C.setLineWidth(width*mm);C.setStrokeColor(HexColor(stroke) if stroke else white)
    C.setFillColor(HexColor(fill) if fill else white)
    C.circle(x*mm,y*mm,r*mm,stroke=bool(stroke),fill=bool(fill))

def cross(x,y,r=3):
    line(x-r,y,x+r,y,MUTED,.12,[3,1,1,1]);line(x,y-r,x,y+r,MUTED,.12,[3,1,1,1])

def arrow(x,y,angle,color=INK):
    a=math.radians(angle);L=1.7;W=.65
    p=C.beginPath();p.moveTo(x*mm,y*mm)
    for sign in [-1,1]:
        p.lineTo((x-L*math.cos(a)+sign*W*math.sin(a))*mm,(y-L*math.sin(a)-sign*W*math.cos(a))*mm)
    p.close();C.setFillColor(HexColor(color));C.drawPath(p,fill=1,stroke=0)

def dh(x1,x2,yy,ref,text):
    line(x1,ref,x1,yy+2,MUTED,.14);line(x2,ref,x2,yy+2,MUTED,.14)
    line(x1,yy,x2,yy,INK,.16);arrow(x1,yy,180);arrow(x2,yy,0)
    txt((x1+x2)/2,yy+1.8,text,8,align='center')

def dv(y1,y2,xx,ref,text):
    line(ref,y1,xx+2,y1,MUTED,.14);line(ref,y2,xx+2,y2,MUTED,.14)
    line(xx,y1,xx,y2,INK,.16);arrow(xx,y1,-90);arrow(xx,y2,90)
    txt(xx-2,(y1+y2)/2,text,8,align='center',rotate=90)

def leader(points,label,size=8.5,color=BLUE,align='left'):
    for a,b in zip(points,points[1:]):line(*a,*b,color,.18)
    circle(*points[0],.45,fill=color,stroke=None)
    x,y=points[-1];txt(x,y+1.6,label,size,color=color,align=align)

def header(title,sub,page):
    rect(12,12,396,273,stroke='#aab3b9',width=.2)
    txt(19,274,'300 SECONDS / FOLD WING BUDDY v6',15,True)
    txt(19,265,title,11,True)
    txt(19,258,sub,8.5,color=MUTED)
    txt(402,274,'P0  참고도',13,True,AMBER,'right')
    txt(402,265,f'FWB-DETAIL-001 | {page}/2',9,align='right')
    line(19,252,401,252,'#aab3b9',.2)
    line(19,22,401,22,'#aab3b9',.2)
    txt(19,16,'2026-10-23 | mm | 실물 측정·출력·조립 검증 미실시 | 최종 제작 승인: 미정',8)
    txt(401,16,'A3 가로 420 × 297 | 인쇄 100% / 페이지 맞춤 해제',8,align='right')

def source(x,y,label,url):
    txt(x,y,label,7.5,color=BLUE)
    C.linkURL(url,(x*mm,(y-1)*mm,(x+180)*mm,(y+3)*mm),relative=0,thickness=0)

header('끼움 시험편 치수도', '도형 축척 1:1. 아래 값은 새 시험편의 설계값이며, 보유 부품의 확정 공차가 아니다.',1)
txt(23,240,'A. CLS6336HV 서보 장착 시험편',11,True)
txt(23,233,'외형 60 × 35 × 4 / 평면도 1:1',8.5,color=MUTED)
txt(216,240,'B. F625ZZ 베어링 끼움 시험편',11,True)
txt(216,233,'외형 94 × 30 × 6 / 평면도 1:1',8.5,color=MUTED)

# Servo coupon: exact geometry and hole locations from joint_test_parts.py.
sx,sy=83,198
rect(sx-30,sy-17.5,60,35,fill='#edf0e8')
rect(sx-20.65,sy-10.5,41.3,21,fill='#ffffff')
for dx in [-24.75,24.75]:
    for dy in [-5,5]:circle(sx+dx,sy+dy,1.7,fill='#ffffff');cross(sx+dx,sy+dy,2.6)
line(sx-34,sy,sx+34,sy,MUTED,.13,[4,1,1,1]);line(sx,sy-21,sx,sy+21,MUTED,.13,[4,1,1,1])
dh(sx-30,sx+30,225.5,sy+17.5,'60')
dh(sx-24.75,sx+24.75,218.8,sy+5,'49.5')
dh(sx-20.65,sx+20.65,171.5,sy-10.5,'41.3 開口'.replace('開口','개구'))
dv(sy-17.5,sy+17.5,43,sx-30,'35')
dv(sy-10.5,sy+10.5,126,sx+20.65,'21.0')
dv(sy-5,sy+5,137,sx+24.75,'10')
leader([(sx+24.75,sy-5),(155,184),(155,171)],'4 × Ø3.4 관통',8.5)
txt(24,156,'A-A  중앙 개구를 지나는 단면 / 1:1',9,True)
line(sx-33,sy,sx-35,sy,BLUE,.3);txt(sx-39,sy+1,'A',8,True,BLUE)
line(sx+33,sy,sx+35,sy,BLUE,.3);txt(sx+36,sy+1,'A',8,True,BLUE)
z=141
rect(sx-30,z,9.35,4,fill='#d8dfce');rect(sx+20.65,z,9.35,4,fill='#d8dfce')
dv(z,z+4,126,sx+30,'4')
txt(23,125,'공급자 참고값: 몸체 40.5 × 20.2, 홈 중심 49.5 × 10.',8.5)
txt(23,118,'개구는 전체 +0.8, 즉 한쪽 0.4 여유를 더했다.',8.5)
txt(23,111,'홈 지름·귀 두께·축 위치·혼 홀은 현품 실측 후 확정한다.',8.5)
txt(23,104,'개구 끝과 체결 홀 사이 명목 최소 육두께: 2.4.',8.5)

# Four body bores, each with an identical 18.2 x 1.2 counterbore.
bx,by=299,198
rect(bx-47,by-15,94,30,fill='#e7eff4')
ds=[15.9,16.,16.1,16.3]
for dx,d in zip([-33,-11,11,33],ds):
    circle(bx+dx,by,9.1,stroke=BLUE,width=.25)
    circle(bx+dx,by,d/2,fill='#ffffff');cross(bx+dx,by,3)
    txt(bx+dx,by+18,f'Ø{d:.1f}',8.5,align='center')
    line(bx+dx,by+14,bx+dx,by+15.5,BLUE,.15)
line(bx-50,by,bx+50,by,MUTED,.13,[4,1,1,1])
dh(bx-47,bx+47,227.5,by+15,'94')
dv(by-15,by+15,241,bx-47,'30')
for a,b,t in zip([-47,-33,-11,11,33],[-33,-11,11,33,47],['14','22','22','22','14']):
    dh(bx+a,bx+b,175.5,by-15,t)
txt(216,163,'4 × Ø18.2 카운터보어 / 깊이 1.2 (상면 기준)',8.8,True,BLUE)
txt(216,156,'B-B  구멍 중심선을 지나는 단면 / 1:1',9,True)
z=140
rect(bx-47,z,94,6,fill='#d8e5ee')
for dx,d in zip([-33,-11,11,33],ds):
    x=bx+dx
    rect(x-d/2,z-.2,d,6.4,fill='#ffffff',stroke=None)
    rect(x-9.1,z+4.8,18.2,1.4,fill='#ffffff',stroke=None)
    for sign in [-1,1]:
        line(x+sign*d/2,z,x+sign*d/2,z+4.8)
        line(x+sign*d/2,z+4.8,x+sign*9.1,z+4.8)
        line(x+sign*9.1,z+4.8,x+sign*9.1,z+6)
dv(z,z+6,241,bx-47,'6')
leader([(bx+33+8.7,z+5.4),(366,148),(366,155)],'1.2 깊이',8.5)
txt(216,125,'몸체 Ø16 기준 직경 차이: -0.1 / 0 / +0.1 / +0.3.',8.5)
txt(216,118,'원본 SpotMicro의 Ø16.3은 한쪽 약 0.15 여유이다.',8.5)
txt(216,111,'이 시험편의 깊이 1.2는 원본 깊이 1과 다르다.',8.5)
txt(216,104,'관통공은 끼움 비교용이며 축방향 고정턱은 검증하지 않는다.',8.5)

rect(20,68,380,25,fill='#f5f1e9',stroke='#cfb68d',width=.2)
txt(25,83,'시험 순서',9.5,True,AMBER)
txt(53,83,'동일 PLA·노즐·레이어·출력 방향으로 시험편을 먼저 출력한다.',9)
txt(25,75,'실제 서보·베어링과 비교해 끼움값을 고른 뒤 본체에 반영한다. 강제 압입, 축방향 체결과 가동 하중은 별도 검증한다.',8.5)
line(25,54,75,54,INK,.3);line(25,52.5,25,55.5);line(75,52.5,75,55.5)
txt(50,58,'인쇄 확인용 50 mm',8,align='center')
txt(95,54,'1:1은 PDF 페이지 배율 기준. STL 자체에는 단위 메타데이터가 없으므로 슬라이서에서 mm를 확인한다.',8)
source(23,39,'출처: CLS6336HV 공급자 기구도 (원본 이미지 / 클릭)', 'https://ueeshop.ly200-cdn.com/u_file/UPBE/UPBE325/2507/30/photo/CLS6336HV-EN.jpg')
source(216,39,'출처: JTEKT / Koyo F625 ZZ 제조사 규격 (클릭)', 'https://koyo.jtekt.co.jp/en/products/detail/?pno=F625+ZZ')
txt(23,30,'형상 대응: reference/joint_test_parts/servo_fit_trial.step 및 F625ZZ_bearing_fit_trial.step',8,color=MUTED)
C.showPage()

header('관절 단면 구성과 원본 베어링 자리', '개념 단면 / 축척 없음. 원본에서 참고한 원리와 새 적용안을 구분하며, 최종 조립 치수도는 아니다.',2)
txt(23,239,'구동측은 현품 혼으로 연결하고, 반대쪽은 같은 축선의 F625ZZ로 지지한다.',11,True)
txt(23,231,'금속 혼·허브·정밀축은 신규 선정/설계 대상이다. 사진의 보유품으로 확인된 항목이 아니다.',9,color=AMBER)

# Concept section: axial arrangement deliberately NTS; coloured parts show function.
cy=185
rect(128,140,7,70,fill='#cfd6dc');rect(300,140,7,70,fill='#cfd6dc')
rect(128,140,179,7,fill='#cfd6dc')
rect(69,164,53,44,fill='#e3e6e9')
txt(95.5,192,'CLS6336HV',10,True,align='center')
txt(95.5,183,'서보',10,align='center')
rect(118,202,17,4,fill='#c5cdd3');rect(118,165,17,4,fill='#c5cdd3')
rect(122,182,22,6,fill='#8796a2')
rect(128,180.5,7,9,fill='#ffffff',stroke=None)
rect(122,182,22,6,fill='#8796a2')
rect(145,168,5,34,fill='#b4c2cc')
rect(154,168,7,34,fill='#b5c99f')
rect(161,175,130,20,fill='#d7e1c8')
for yy in [173,197]:line(144,yy,161,yy,INK,.5)
rect(283,182.5,42,5,fill='#8e9da6')
# Bearing body and flange, split at bore to show inner ring/spindle path.
rect(300,177,5,16,fill='#b9d8e8',stroke=BLUE)
rect(299,176,1,18,fill='#9bc2d8',stroke=BLUE)
rect(299,182.5,6,5,fill='#ffffff',stroke=None)
for yy in [179.5,190.5]:circle(302.5,yy,1.15,fill='#f5fafd',stroke=BLUE,width=.15)
for yy in [181,187.5]:rect(305,yy,6,1.5,fill='#b9b4a0')
rect(312,179,3,12,fill='#bfae90')
rect(312,182.5,3,5,fill='#ffffff',stroke=None)
rect(283,182.5,42,5,fill='#8e9da6')
line(58,cy,338,cy,BLUE,.18,[5,1,1,1])
txt(339,cy-1,'共軸'.replace('共軸','동일 축선'),8,color=BLUE)

leader([(98,207),(98,218),(44,218)],'서보 본체 + 고정 귀',8.8)
leader([(147,200),(170,218),(170,218)],'탈착 가능한 현품 금속 혼',8.8)
leader([(218,195),(218,212),(241,212)],'회전 허브 / 이동측 링크',8.8)
leader([(301.5,192),(332,215),(332,218)],'F625ZZ 반대편 지지',8.8)
leader([(131,157),(102,151),(69,151)],'고정 포크 (회전하지 않음)',8.8)
leader([(287,183),(272,160),(235,160)],'Ø5 정밀 축 / 어깨축 (미선정)',8.8)
leader([(308,188.5),(347,199),(347,202)],'내륜용 간격재',8.5)
leader([(313.5,179),(340,156),(340,151)],'축 이탈 방지부 / 체결 방식 미정',8.5)
txt(151,134,'혼 PCD·두께·중심 나사, 축 중심 오프셋, 포크 간격은 실측 후 확정.',9,color=AMBER)

line(23,126,398,126,'#aab3b9',.2)
txt(23,115,'원본 L_arm_cover.stl에서 재구성한 베어링 자리',10,True)
txt(23,107,'원본 STL 명목 형상이며, 실물 측정이나 출력 공차가 아니다.',8.5,color=MUTED)
txt(23,94,'플랜지 자리',9,True);txt(62,94,'Ø18.2 × 깊이 1',10,True,BLUE)
txt(23,85,'몸체 자리',9,True);txt(62,85,'Ø16.3 × 깊이 4',10,True,BLUE)
txt(23,76,'전체 수납 깊이',9,True);txt(62,76,'5',10,True)
txt(23,65,'Ø16.3 - Ø16 = 직경 여유 0.3 / 한쪽 여유 약 0.15.',8.5)
txt(23,57,'새 시험편은 깊이 1.2를 사용하므로 원본 자리를 그대로 복사한 것이 아니다.',8.2)

txt(216,115,'F625ZZ 공칭 규격과 체결 원칙',10,True)
txt(216,104,'내경 5 / 외경 16 / 전체 폭 5 / 플랜지 외경 18 / 두께 1.',9)
txt(216,94,'외륜은 포크에 지지하고, 회전축과 내륜의 체결 경로를 구분한다.',8.5)
txt(216,84,'간격재·와셔가 외륜 또는 실드까지 눌러 회전을 막으면 안 된다.',8.5)
txt(216,74,'M5 나사산은 정밀 축과 다르다. 축 공차·길이·이탈 방지를 확정한다.',8.5)
txt(216,64,'지지축과 서보 축을 동축으로 맞추고, 전선 굽힘과 전체 가동 간섭을 확인한다.',8.3)
txt(216,55,'최종 혼 어댑터·회전 허브·간격재·축 길이 및 하중 검증: 미정.',8.5,True,AMBER)

source(23,39,'원본: Road-Balance/SpotMicroJetson / 커밋 2235c77... (클릭)', 'https://github.com/Road-Balance/SpotMicroJetson/tree/2235c77a93e86d04dec2e03c6306ba2c06d454ce')
source(216,39,'조립 원리: SpotMicroAI assembly / JTEKT F625 ZZ (클릭)', 'https://spotmicroai.readthedocs.io/en/latest/assembly/')
txt(23,30,'수치 근거: reference/SpotMicro_original_bearing_seat.json | 제작 적용: 고정 포크 + 교체식 혼/허브 + 반대편 베어링',8,color=MUTED)
C.save()

doc=fitz.open(PDF)
assert len(doc)==2
for i,p in enumerate(doc):
    name='FWB_DETAIL_reference_A3.png' if i==0 else 'FWB_DETAIL_reference_A3_page2.png'
    p.get_pixmap(matrix=fitz.Matrix(1.7,1.7)).save(OUT/name)
    assert len(p.get_text())>800
print(PDF)
print('Two A3 pages rendered; sheet 1 coupons are scale 1:1, sheet 2 is NTS.')
