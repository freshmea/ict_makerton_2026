"""Two A3 reference/detail sheets. Native PDF geometry, rendered PNG QA.
Source cross sections are read from original_joint_sections.json.
P1 diagrams show the same nominal design parameters as build_v7.py, but are
annotated section schematics; they are not hidden-line CAD projections.
"""
from pathlib import Path
import json, math
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor, Color, white
import fitz
HERE=Path(__file__).resolve().parent
OUT=HERE.parent/'drawings';OUT.mkdir(exist_ok=True)
FONT='Malgun'
pdfmetrics.registerFont(TTFont(FONT,'C:/Windows/Fonts/malgun.ttf'))
MM=72/25.4
PATH=OUT/'FWB_JOINT_P1_reference_A3.pdf'
c=canvas.Canvas(str(PATH),pagesize=(420*MM,297*MM))
c.setTitle('Fold Wing Buddy v7 P1 - embedded servo joint and SpotMicro source audit')
INK='#24352d';FIXED='#c5d0ad';MOVING='#e4d8bb';SERVO='#3f4548';HORN='#cc9047';BEARING='#7f9da7'

def line(x1,y1,x2,y2,color=INK,lw=.5,dash=None):
    c.setStrokeColor(HexColor(color));c.setLineWidth(lw)
    c.setDash(dash or [])
    c.line(x1*MM,y1*MM,x2*MM,y2*MM);c.setDash([])
def rect(x,y,w,h,fill=None,stroke=INK,lw=.5):
    c.setStrokeColor(HexColor(stroke));c.setLineWidth(lw)
    if fill:c.setFillColor(HexColor(fill))
    c.rect(x*MM,y*MM,w*MM,h*MM,stroke=1,fill=bool(fill))
def circle(x,y,r,fill=None,stroke=INK,lw=.5):
    c.setStrokeColor(HexColor(stroke));c.setLineWidth(lw)
    if fill:c.setFillColor(HexColor(fill))
    c.circle(x*MM,y*MM,r*MM,stroke=1,fill=bool(fill))
def text(x,y,s,size=9,color=INK):
    c.setFont(FONT,size);c.setFillColor(HexColor(color));c.drawString(x*MM,y*MM,s)
def rows(x,y,lines,size=9,leading=5.5):
    for s in lines:text(x,y,s,size);y-=leading
def dim(x1,y1,x2,y2,label,above=1.5):
    line(x1,y1,x2,y2,lw=.35)
    a=math.atan2(y2-y1,x2-x1);t=1.7
    for x,y,s in [(x1,y1,1),(x2,y2,-1)]:
        for da in [-.5,.5]:line(x,y,x+s*t*math.cos(a+da),y+s*t*math.sin(a+da),lw=.35)
    text((x1+x2)/2-5,(y1+y2)/2+above,label,8)
def lead(x1,y1,x2,y2,s,size=8):
    line(x1,y1,x2,y2,lw=.4);circle(x1,y1,.45,INK);text(x2+1,y2,s,size)
def page(title,no):
    rect(8,8,404,281,stroke='#869284',lw=.4)
    text(16,279,title,17)
    text(16,271,'FOLD WING BUDDY / v7 P1 / 2026-10-23 / 단위 mm / 조립·실측 전 검토용',9)
    line(16,267,404,267,color='#869284')
    line(16,20,404,20,color='#869284')
    text(16,13,'FWB_JOINT_P1 | 원본 근거와 새 설계값 구분 | 출력 배율로 치수를 재지 말고 기입값 사용',8)
    text(377,13,str(no)+' / 2',8)

data=json.loads((HERE/'original_joint_sections.json').read_text(encoding='utf-8'))
records=data['records']
page('관절 구조 재분석 - 원본 혼 포켓과 반대편 베어링',1)
text(18,255,'A. CLS 수정 STEP에 있는 실제 혼 포획 형상',12)
text(18,248,'O_shoulder_cls_grooved_modi.stp / Y=2.5 단면 / 6갈래 별형',9)
src=next(r for r in records if 'O_shoulder' in r['source_path'])
sec=next(s for s in src['sections'] if s['plane_y_mm']==2.5)
sx,sy,scale=23,139,1.5
for loop in sec['loops']:
    points=loop['xz_points_mm'];p=c.beginPath();p.moveTo((sx+points[0][0]*scale)*MM,(sy+points[0][1]*scale)*MM)
    for x,z in points[1:]:p.lineTo((sx+x*scale)*MM,(sy+z*scale)*MM)
    c.setStrokeColor(HexColor(INK));c.setLineWidth(.65);c.drawPath(p)
for center in [16,94]:
    x=sx+center*scale;z=sy+26*scale
    line(x-19,z,x+19,z,'#748373',.35,[3,2]);line(x,z-25,x,z+25,'#748373',.35,[3,2])
dim(sx+16*scale,134,sx+94*scale,134,'78.0')
rows(20,125,[
    '포켓 깊이: Y=2.3~5.0 → 2.7',
    '포켓 XZ 외형: 약 28.976 × 32.600',
    '축선 중심: (16,26), (94,26) / 중심 통과부 약 Ø9',
    '이 CLS STEP은 6갈래이다. 구형 L_arm은 한쪽 팔 혼 자리이다.',
    'v7의 4갈래 십자는 사용자의 요청에 따른 교환형 시험 설계다.'
],9,6)
text(20,89,'C. 원본처럼 유지할 회전 전달·지지 관계',12)
rows(20,79,[
    '고정측: 서보 케이스 + 내부 코어 + 반대편 지지축',
    '구동측: 서보 혼 + 감싸는 앞판/뒷판 + 연결 브리지',
    '구동측 뒷판의 베어링 외륜 ↔ 고정측 지지축의 내륜',
    '서보 출력축과 베어링 중심은 같은 축선에 놓인다.',
    '서보 케이스는 코어 안으로 수납하고 짧은 출력부만 앞판에 연결한다.'
],9,6)
rows(20,40,['원본 출처: Road-Balance/SpotMicroJetson @ 2235c77a93e86d04dec2e03c6306ba2c06d454ce',
            '원본 STL/STEP 버전을 혼합해 검증된 어셈블리로 간주하지 않는다.'],7.2,5)

text(220,255,'B. L_arm_cover.stl에서 읽은 베어링 자리',12)
text(220,248,'모델 단면 기준 / 축 방향 Y / 반대편 커버 안의 단차 구멍',9)
# Native axial section of original cover, graph has Y horizontal, radial vertical.
ox,oy,k=241,193,4
def orig_rect(y0,y1,r0,r1,fill):rect(ox+(y0-40)*k,oy+r0*k,(y1-y0)*k,(r1-r0)*k,fill)
for sgn in [-1,1]:
    if sgn==1:
        orig_rect(40,41,9.1,12,MOVING);orig_rect(41,45,8.15,12,MOVING)
    else:
        orig_rect(40,41,-12,-9.1,MOVING);orig_rect(41,45,-12,-8.15,MOVING)
line(229,oy,298,oy,'#748373',.5,[4,2])
dim(ox,134,ox+k,134,'1.0');dim(ox+k,126,ox+5*k,126,'4.0')
lead(ox+3*k,oy+8.15*k,302,224,'몸체 수납공 Ø16.3',9)
lead(ox+.5*k,oy+9.1*k,302,210,'플랜지 자리 Ø18.2',9)
rows(302,198,['전체 수납 깊이 5.0', '축 중심 XZ:', '(1.17473, 124.92493)', 'Y40~41 / Y41~45'],9,6)
rows(220,76,[
    'F625ZZ 공칭: 내경 5 / 외경 16 / 폭 5 / 플랜지 Ø18×1',
    '원본의 직경 여유는 새 출력물에서도 맞는지 시험해야 한다.',
    '메시 원 맞춤 수치는 명목 CAD 형상이며 실제 출력 정밀도가 아니다.',
    '재현 근거: reference/original_joint_sections.json 및 원본 보존 파일',
    '가이드: spotmicroai.readthedocs.io/en/latest/assembly/'
],8.5,6)
c.showPage()

page('수정 관절 - 서보를 축 둘레 코어 안에 수납',2)
text(18,255,'D. 축 방향 단면 개념도 (새 P1 명목값, 축척 2:1)',12)
text(18,248,'수평=Y(회전축 방향), 수직=X / 두 앞뒤 판은 브리지로 연결되어 함께 회전',9)
ox,oy,k=30,150,2.0
def pos(y,x):return (ox+y*k,oy+x*k)
def qr(y0,y1,x0,x1,fill,stroke=INK):rect(*pos(y0,x0),(y1-y0)*k,(x1-x0)*k,fill,stroke)
# Fixed round barrel section, cavity, embedded servo, short shaft.
qr(13,67,-40,40,FIXED)
qr(16,64,-37,37,'#f9fbf6')
qr(18,62,-10.9,30.4,'#f9fbf6')
qr(20,60,-10.5,30,SERVO)
qr(10.5,20,-3,3,HORN)
# Moving end caps and bridge outside fixed core.
qr(6,12,-45,45,MOVING);qr(68,74,-45,45,MOVING)
qr(8,72,-49,-41,MOVING)
# Front horn recess (new four-arm adapter cross section).
qr(9.3,12,-15,15,'#fbf7eb')
qr(9.7,11.9,-14.8,14.8,HORN)
qr(6,12,-2.65,2.65,'#fafafa')
qr(10.5,20,-3,3,HORN)
# Back bearing: body69..73, flange73..74. Shaft fixed66..76.
for a,b in [(-8.15,8.15)]:qr(68,73,a,b,'#ffffff')
qr(73,74,-9.1,9.1,'#ffffff')
qr(69,73,-8,8,BEARING);qr(73,74,-9,9,BEARING)
qr(63,77,-2.45,2.45,FIXED);qr(62,64,-4,4,FIXED)
line(*pos(0,0),*pos(82,0),'#71806e',.5,[4,2])
text(ox+1,oy+3,'동일 회전축',8)
# leader targets carefully spaced.
lead(*pos(42,30),194,224,'서보 몸체 40.5×40×20.2',8)
lead(*pos(15,37),194,212,'고정 코어 Ø80 × 길이54',8)
lead(*pos(10,19),194,200,'앞판 Y6~12 / 혼 자리 깊이2.7',8)
lead(*pos(71,7),194,188,'F625ZZ, 몸체Y69~73 / 플랜지73~74',7.7)
lead(*pos(75,1.7),194,176,'지지축 Ø4.9 Y63~77 / 턱 Ø8',8)
lead(*pos(39,-45),194,164,'앞뒤 판을 연결하는 외곽 브리지',8)
dim(*pos(13,47),*pos(67,47),'54.0')
dim(*pos(6,-56),*pos(74,-56),'68.0')
rows(20,29,['서보 케이스는 Y20~60, 수납공은 Y18~62. 긴 허브가 서보를 바깥에서 연결하지 않는다.',
            '반대편 축·스페이서·나사 머리·외륜 간섭과 축방향 이탈 방지 구조는 실측 후 확정한다.'],8,5.5)

# End view actual new trial cross geometry.
cx,cy,sk=337,205,1.1
circle(cx,cy,45*sk,MOVING);circle(cx,cy,40*sk,None,'#71806e',.4)
poly=[(-3.2,-15),(3.2,-15),(3.2,-3.2),(15,-3.2),(15,3.2),(3.2,3.2),(3.2,15),(-3.2,15),(-3.2,3.2),(-15,3.2),(-15,-3.2),(-3.2,-3.2)]
p=c.beginPath();p.moveTo((cx+poly[0][0]*sk)*MM,(cy+poly[0][1]*sk)*MM)
for x,z in poly[1:]:p.lineTo((cx+x*sk)*MM,(cy+z*sk)*MM)
p.close();c.setFillColor(HexColor('#fbf7eb'));c.setStrokeColor(HexColor(INK));c.drawPath(p,fill=1)
circle(cx,cy,2.65*sk,'#ffffff')
line(cx-52,cy,cx+52,cy,'#71806e',.35,[3,2]);line(cx,cy-52,cx,cy+52,'#71806e',.35,[3,2])
text(291,145,'E. 새 교환형 4갈래 혼 자리',11)
rows(291,135,['전체 span 30 / 팔 폭 6.4 / 깊이 2.7',
              '중심 통과공 Ø5.3 / 앞판 Y9.3~12',
              '표시 혼: span29.6 / 팔폭6 / 두께2.2',
              '위 값은 새 시험 설계이며 보유 혼 실측 필요'],8.5,6)
rect(288,60,110,44,'#f3f5ec','#869284')
rows(292,95,['최종 제작 전 확인',
             '• 케이스 기준 출력축 위치 +9.75: 미확정',
             '• 혼 스플라인·십자 치수·나사: 미확정',
             '• Ø5 지지축 공차·스페이서·체결: 미확정',
             '• 관절 회전 중 배선과 외장 충돌: 미검증'],8.1,6)
c.showPage();c.save()
doc=fitz.open(PATH)
for i,p in enumerate(doc):p.get_pixmap(matrix=fitz.Matrix(1.65,1.65)).save(OUT/f'FWB_JOINT_P1_reference_A3_page{i+1}.png')
assert len(doc)==2
print(str(PATH));print('Rendered 2 pages')
