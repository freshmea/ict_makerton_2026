"""A3 assembly-motion settings sheet from the actual native P3 model render."""
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import fitz

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'drawings/FWB_v8_P3_joint_settings_A3.pdf'
pdfmetrics.registerFont(TTFont('Malgun','C:/Windows/Fonts/malgun.ttf'))
pdfmetrics.registerFont(TTFont('MalgunBold','C:/Windows/Fonts/malgunbd.ttf'))
W,H=landscape(A3)
C=canvas.Canvas(str(OUT),pagesize=(W,H))
C.setTitle('Fold Wing Buddy P3 - revolute joints and assembly settings')

def text(x,y,s,size=10,bold=False,color='#27352e'):
    C.setFillColor(color);C.setFont('MalgunBold' if bold else 'Malgun',size)
    C.drawString(x*mm,y*mm,s)

def line(x1,y1,x2,y2):
    C.setStrokeColor('#c9cec1');C.line(x1*mm,y1*mm,x2*mm,y2*mm)

def image(name,x,y,w,h):
    C.drawImage(ImageReader(str(ROOT/'renders'/name)),x*mm,y*mm,w*mm,h*mm,
        preserveAspectRatio=True,anchor='c',mask='auto')

text(16,279,'FOLD WING BUDDY',23,True)
text(16,268,'P3 회전 조인트 / 고정·회전 묶음 / 동작 설정',14,True)
text(345,280,'v8 / P3',16,True);text(345,269,'2026-10-23',10)
line(16,259,404,259)
text(16,250,'P2는 강체 연결만 있던 정지 모델이다. P3는 Ground + 회전 조인트 4개 + 운동 연구 5개를 저장한다.',10)
image('P3_neutral.png',16,106,227,143)
text(20,239,'실제 SolidCraft P3 중립 자세 (네 축 0°)',10,True)

text(253,237,'SolidCraft에서 직접 움직이기',12,True)
for y,s in [(224,'① cad/fold_wing_v8_P3_motion.solidcraft 열기'),
            (212,'② 상단 조립 → 관절 구동'),
            (200,'③ L_J1_YAW 선택 → +10° → 0°'),
            (188,'④ L_J2_PITCH 선택 → +10° → 0°'),
            (176,'⑤ 조립 → 운동 연구 → P3_FOUR_JOINT_DEMO'),
            (164,'⑥ step 0~80을 재생 / 마지막은 0° 복귀')]:
    text(253,y,s,10)
text(253,148,'고정과 회전의 연결',11,True)
text(253,136,'몸체 Ground → J1(+Z) → 팔 → J2(+Y) → 손',10,True)
text(253,124,'서보 케이스·코어·지지축은 팔에 고정한다.',9)
text(253,114,'혼·출력축·손 전후 커버는 손과 함께 회전한다.',9)
text(253,104,'Yaw를 돌리면 자식 J2 축·원점도 함께 이동한다.',9)

cols=[17,72,127,183,250,324]
for x,s in zip(cols,['회전 조인트','부모 → 자식','초기 원점 XYZ (mm)','초기 회전축','저장 / 임시 CAD 제한','데모 +10 / -10 / 0 step']):
    text(x,89,s,8.5,True)
line(16,85,404,85)
data=[('L_J1_YAW','몸체 → 왼팔','-275, 40, 130','+Z / 0,0,1','0° / -15°~+15°','5 / 10 / 15'),
      ('L_J2_PITCH','왼팔 → 왼손','-220, 40, 315','+Y / 0,1,0','0° / -15°~+15°','25 / 30 / 35'),
      ('R_J1_YAW','몸체 → 오른팔','275, 40, 130','+Z / 0,0,1','0° / -15°~+15°','45 / 50 / 55'),
      ('R_J2_PITCH','오른팔 → 오른손','220, 40, 315','+Y / 0,1,0','0° / -15°~+15°','65 / 70 / 75')]
for i,row in enumerate(data):
    y=77-i*11
    for x,s in zip(cols,row):text(x,y,s,9,bold=(x==cols[0]))
    line(16,y-4,404,y-4)
text(17,28,'명령 검색 S → motion.play {"study":"P3_FOUR_JOINT_DEMO","step":0} 으로 모든 축을 중립 복귀.',9)
text(17,20,'각도는 오른손 법칙. ±15°는 CAD 시연 제한이며 실물 서보 범위·충돌·토크·출력품 시험을 뜻하지 않는다.',9)
line(16,15,404,15)
text(17,9,'설정 상세: source/ASSEMBLY_JOINTS_P3.md  |  동작 원본: .solidcraft  |  STEP/STL은 조인트 구동 원본이 아니다.',8)
C.save()
pdf=fitz.open(OUT)
pdf[0].get_pixmap(matrix=fitz.Matrix(1.4,1.4),alpha=False).save(OUT.with_suffix('.png'))
print(OUT)
