"""Three A3 sheets: native six-servo assembly, joints and orthographic views."""
from pathlib import Path
import json
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A3,landscape
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import fitz
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'drawings/FWB_v8_P4_6DOF_A3.pdf'
pdfmetrics.registerFont(TTFont('Malgun','C:/Windows/Fonts/malgun.ttf'))
pdfmetrics.registerFont(TTFont('MalgunBold','C:/Windows/Fonts/malgunbd.ttf'))
C=canvas.Canvas(str(OUT),pagesize=landscape(A3))
C.setTitle('Fold Wing Buddy P4 - six servos / three DOF per arm')
def text(x,y,s,size=10,bold=False,color='#27352e'):
    C.setFillColor(color);C.setFont('MalgunBold' if bold else 'Malgun',size);C.drawString(x*mm,y*mm,s)
def line(y):
    C.setStrokeColor('#c9cec1');C.line(16*mm,y*mm,404*mm,y*mm)
def picture(name,x,y,w,h,zoom=1):
    C.saveState();p=C.beginPath();p.rect(x*mm,y*mm,w*mm,h*mm);C.clipPath(p,stroke=0,fill=0)
    C.drawImage(ImageReader(str(ROOT/'renders'/name)),(x-w*(zoom-1)/2)*mm,(y-h*(zoom-1)/2)*mm,w*zoom*mm,h*zoom*mm,preserveAspectRatio=True,anchor='c',mask='auto')
    C.restoreState()
def header(sub,page):
    text(16,280,'FOLD WING BUDDY / 6 SERVOS',23,True)
    text(16,268,sub,13,True);text(354,280,'v8 / P4',15,True);text(354,268,f'{page} / 3',10);line(259)
def footer(page):
    line(15);text(17,9,f'2026-10-23 | mm | P4 {page}/3 | 원본: fold_wing_v8_P4_6servo.solidcraft | 상세: source/ASSEMBLY_JOINTS_P4.md',8)

header('좌우 팔 각각 3회전축 / 실제 SolidCraft 형상 / 이전 4서보 설계 수정',1)
picture('P4_neutral.png',16,109,238,145,1.2)
text(20,242,'전체 조립 - 여섯 축 모두 중립 0°',10,True)
picture('P4_six_servos_front.png',259,126,144,114,1.45)
text(264,242,'외장을 숨긴 실제 서보 6개 배치',10,True)
text(267,140,'상단: 손목 2 / 중단: 어깨 2 / 하단: Yaw 2',9)
text(258,122,'Ground → J1 Yaw → J2 어깨 → J3 손목',10,True)
text(258,111,'J1을 돌리면 J2·J3가, J2는 J3가 따라간다.',9)
cols=[17,102,176,248,306]
for x,s in zip(cols,['회전 조인트','부모 → 자식','중립 원점 XYZ (mm)','중립 축','임시 CAD 범위 / 데모 +10,-10,0 step']):text(x,97,s,8.5,True)
line(92)
rows=[]
for side,sgn,label in [('L',-1,'좌'),('R',1,'우')]:
    i=0 if side=='L' else 3
    for j,(suffix,chain,xyz,axis) in enumerate([
      ('J1_YAW',f'몸체 → {label} 터렛',f'{sgn*275}, 40, 130','+Z'),
      ('J2_SHOULDER_PITCH',f'{label} 터렛 → {label} 팔',f'{sgn*275}, 40, 180','local +Y'),
      ('J3_WRIST_PITCH',f'{label} 팔 → {label} 손',f'{sgn*220}, 40, 315','local +Y')]):
        start=(i+j)*20;rows.append([side+'_'+suffix,chain,xyz,axis,f'±15° / {start+5}, {start+10}, {start+15}'])
for i,row in enumerate(rows):
    y=84-i*9
    for x,s in zip(cols,row):text(x,y,s,8.5,x==17)
    line(y-3)
text(17,23,'각도는 오른손 법칙. ±15°는 CAD 시연 제한이며 실제 서보 허용각·연속 충돌 없음·토크 검증을 뜻하지 않는다.',9)
footer(1);C.showPage()

header('직렬 구동 체인 / 조립 접근 / X1 Carbon 출력과 원본 수정',2)
picture('P4_left_chain_detail.png',16,95,205,157,1.4)
text(19,242,'좌측 3단 체인 - 실제 CAD 부품',10,True)
text(229,242,'고정·회전 관계와 조립 순서',12,True)
paragraphs=[
'1. 베이스와 Yaw 서보 케이스를 고정한다. Yaw 혼에 터렛을 연결한다.',
'2. 터렛의 어깨 코어에 추가 서보를 넣고 케이스를 고정한다.',
'3. 어깨 혼과 앞 회전 캡을 연결하고, 뒤 동축 베어링으로 받친다.',
'4. 앞·뒤 캡과 상단 브리지를 곡선 팔의 두 반쪽에 연결한다.',
'5. 곡선 팔 끝에 손목 서보를 고정하고 기존 손 커버에 혼을 체결한다.',
'6. J1/J2/J3 케이스는 부모에, 혼·출력축은 자식에 속한다.',
'7. 각 모터 케이블은 부모를 따라 고정하고 회전부에 여유 루프를 둔다.',
'혼 홈·축 오프셋·베어링 유지·볼트 길이·케이블 여유는 현품 시험 필요.'
]
for i,s in enumerate(paragraphs):text(229,227-i*11,s,8.8)
text(229,137,'SolidCraft 구동 및 원본 편집',12,True)
for i,s in enumerate([
'열기: cad/fold_wing_v8_P4_6servo.solidcraft',
'조립 → 관절 구동 → L/R_J1, J2, J3 선택 → +10° → 0°',
'조립 → 운동 연구 → P4_SIX_JOINT_DEMO → step 0~120',
'source/build_geometry_P4.py + build_motion_P4.py로 재생성한다.',
'새 어깨 형상은 네이티브 피처이며 기존 팔·머리의 STEP 기반은 유지한다.'
]):text(229,124-i*9,s,8.8)
line(80)
manifest=json.loads((ROOT/'P4/print/manifest.json').read_text(encoding='utf-8'))
text(17,70,'X1 Carbon 출력 분할',12,True)
text(17,58,f'베이스 640 mm는 3분할, 전후 외장과 어깨 부품은 별도 출력. 출력 형상 {len(manifest["parts"])}종.',10)
text(17,46,'P4/print/single_part_3mf: 부품별 배치. 256×256 mm, 높이 250 mm 및 배제 영역·브림 여유 검사.',10)
text(17,34,'3MF는 모델·배치 데이터다. 재료·서포트·벽수·슬라이싱·실물 끼움은 출력 전 Bambu Studio에서 확인한다.',9)
text(17,23,'전체 큰 출력 전 혼·베어링·회전 커버를 시험 출력한다. 모터는 단순 외형 영역이며 실측된 제조 형상은 아니다.',9)
footer(2);C.showPage()
header('P4 실제 3D 모델의 정면·평면·우측면 / 여섯 축 중립 자세',3)
picture('P4_front.png',16,128,245,122,1.65)
text(20,242,'정면 FRONT',11,True)
picture('P4_top.png',16,24,245,99,1.65)
text(20,118,'평면 TOP',11,True)
picture('P4_right.png',270,85,132,161,1.65)
text(274,242,'우측면 RIGHT',11,True)
text(273,77,'베이스: 640 × 200 × 100 mm',10,True)
text(273,65,'J1 → J2: 수직 50 mm',10)
text(273,53,'J2 → J3: ΔX 55 / ΔZ 135 mm',10)
text(273,41,'축간 거리: √(55²+135²) = 145.77 mm',9)
text(273,28,'각 뷰는 별도 화면 맞춤. 수치·가공은 CAD 기준.',8.5)
footer(3);C.save()
pdf=fitz.open(OUT)
for i,page in enumerate(pdf):page.get_pixmap(matrix=fitz.Matrix(1.3,1.3),alpha=False).save(OUT.with_name(OUT.stem+f'_page{i+1}.png'))
print(OUT)
