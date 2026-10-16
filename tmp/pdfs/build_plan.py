from pathlib import Path
import re
from xml.sax.saxutils import escape
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Flowable
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
import pymupdf

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / 'doc/계획서/300_Seconds_사업계획서.md'
OUT = ROOT / 'output/pdf/300_Seconds_사업계획서.pdf'
pdfmetrics.registerFont(TTFont('Malgun', 'C:/Windows/Fonts/malgun.ttf'))
pdfmetrics.registerFont(TTFont('MalgunBold', 'C:/Windows/Fonts/malgunbd.ttf'))
pdfmetrics.registerFontFamily('Malgun', normal='Malgun', bold='MalgunBold')
styles = {
 'body': ParagraphStyle('body', fontName='Malgun', fontSize=8.6, leading=12, wordWrap='CJK', spaceAfter=5),
 'h2': ParagraphStyle('h2', fontName='MalgunBold', fontSize=13, leading=19, spaceBefore=7, spaceAfter=10, keepWithNext=True),
 'h3': ParagraphStyle('h3', fontName='MalgunBold', fontSize=11, leading=16, spaceBefore=9, spaceAfter=7, keepWithNext=True),
 'cell': ParagraphStyle('cell', fontName='Malgun', fontSize=7.8, leading=10.8, wordWrap='CJK'),
 'small': ParagraphStyle('small', fontName='Malgun', fontSize=7.5, leading=10.3, wordWrap='CJK', textColor=colors.HexColor('#555555'), spaceAfter=4),
}
def fmt(t):
 t = escape(t)
 t = re.sub(r'\[([^\]]+)\]\((https?://[^\s)]+)\)', r'<link href="\2" color="#285a88">\1</link>', t)
 t = re.sub(r'\[([^\]]+)\]\((?!https?://)[^\n]*?\)', r'\1', t)
 return re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', t)
def p(t,style='body'): return Paragraph(fmt(t),styles[style])
def table(rows):
 n=len(rows[0]); widths={2:[104,383],3:[90,110,287],4:[37,60,65,325],5:[30,48,55,212,142]}[n]
 if n==3 and '구분' in rows[0][0]: widths=[42,126,319]
 if n==3 and '비교' in rows[0][0]: widths=[108,166,213]
 if n==3 and '산출물' in rows[0][0]: widths=[135,121,231]
 if n==3 and '고객군' in rows[0][0]: widths=[90,207,190]
 t=Table([[p(c,'cell') for c in row] for row in rows],colWidths=widths,repeatRows=1,hAlign='LEFT')
 t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e4e4e4')),('GRID',(0,0),(-1,-1),0.5,colors.HexColor('#999999')),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7)]))
 return t
def parse(text):
 lines=text.strip().splitlines(); result=[]; i=0
 while i<len(lines):
  line=lines[i].strip()
  if not line: i+=1; continue
  if line.startswith('|'):
   rows=[]
   while i<len(lines) and lines[i].strip().startswith('|'):
    row=[v.strip() for v in lines[i].strip().strip('|').split('|')]
    if not all(re.match(r'^:?-+:?$',c) for c in row): rows.append(row)
    i+=1
   result += [table(rows),Spacer(1,9)]; continue
  if line.startswith('### '): result.append(p(line[4:],'h3'))
  elif line.startswith('## '): result.append(p(line[3:],'h2'))
  elif line.startswith('> '): result.append(p(line[2:],'small'))
  elif line.startswith('- '): result.append(p('• '+line[2:],'small'))
  else: result.append(p(line))
  i+=1
 return result

class Diagram(Flowable):
 def __init__(self,kind): Flowable.__init__(self); self.kind=kind; self.width=487; self.height=205 if kind=='device' else 190
 def draw(self):
  c=self.canv
  def txt(x,y,t,size=9,bold=False): c.setFillColor(colors.HexColor('#222222')); c.setFont('MalgunBold' if bold else 'Malgun',size); c.drawString(x,y,t)
  def box(x,y,w,h,label):
   c.setFillColor(colors.HexColor('#f1f2f4'));c.setStrokeColor(colors.HexColor('#6d747c'));c.roundRect(x,y,w,h,6,fill=1,stroke=1);txt(x+9,y+h/2-3,label,8.5)
  def arrow(x1,y1,x2,y2):
   c.setStrokeColor(colors.HexColor('#6d747c'));c.line(x1,y1,x2,y2);c.line(x2,y2,x2-5,y2+3);c.line(x2,y2,x2-5,y2-3)
  if self.kind=='device':
   c.setFillColor(colors.HexColor('#e5e7eb'));c.setStrokeColor(colors.HexColor('#707780'));c.roundRect(130,28,193,45,12,fill=1)
   c.setFillColor(colors.HexColor('#333c4b'));c.roundRect(177,65,88,125,8,fill=1)
   c.setFillColor(colors.white);c.roundRect(183,76,76,101,3,fill=1)
   txt(192,151,'학습 목표',9,True);txt(192,130,'단어 10개',9);txt(192,109,'세션 진행 중',8)
   c.setFillColor(colors.HexColor('#6d83a6'));c.circle(222,184,3,fill=1)
   c.setStrokeColor(colors.HexColor('#688aab'));c.setLineWidth(4);c.line(146,45,307,45);c.setLineWidth(1)
   txt(15,177,'카메라 입력부');c.line(100,180,214,184)
   txt(324,140,'스마트폰 거치부');c.line(317,143,267,143)
   txt(335,58,'네오픽셀 상태 표시');c.line(327,61,302,45)
   txt(15,116,'스피커·서보');c.line(103,120,161,62)
   txt(325,22,'발사 모듈: 별도 표적');c.line(321,25,305,32)
   txt(15,27,'탁상형 본체');c.line(97,31,130,44)
   txt(125,6,'외형 제안 · 실제 제품 사진 및 확정 설계 아님',8)
  else:
   box(0,133,135,40,'목표·세션 설정');box(176,133,135,40,'카메라 입력');box(352,133,135,40,'상태 분석')
   arrow(135,153,174,153);arrow(311,153,350,153)
   box(352,61,135,40,'네오픽셀·즉각 피드백');box(176,61,135,40,'세션 기록·요약')
   c.line(420,133,420,103);c.line(420,103,417,109);c.line(420,103,423,109)
   c.line(352,81,313,81);c.line(313,81,318,84);c.line(313,81,318,78)
   txt(2,83,'연산 장치·제어 보드',9,True);txt(2,65,'모델·통신 방식은 미정',8)
   box(0,5,487,32,'확장: 휴대폰 상태 알림·원격 현황 조회 / AI 튜터·앱 제어')

class Competitors(Flowable):
 def __init__(self): Flowable.__init__(self);self.width=487;self.height=429
 def draw(self):
  c=self.canv
  cards=[('miko3.png','Miko 3','교육 로봇 · US$299','카메라·교육 콘텐츠·보호자 앱','기존 문제집 기반 코칭으로 구분 [S1]','https://miko.ai/products/miko-3'),('smartall.jpg','웅진스마트올 초등','AI 맞춤학습 · 월 79,000원~','초등 전과목 콘텐츠·패드학습','콘텐츠를 보완하는 기기로 접근 [S2]','https://www.wjthinkbig.com/prod/subjectDetail.do?subjectId=S0000068'),('focusmate.png','Focusmate','Plus · 월 US$8/12','온라인 파트너와 공동 집중','연 결제 월 환산 $8 / 월 결제 $12 [S3]','https://www.focusmate.com/pricing/'),('forest.png','Forest','집중·습관 앱','나무 성장으로 집중의 보상 제공','동기부여·시각적 보상 설계 참고 [S4]','https://forestapp.cc/')]
  for i,(fn,name,price,desc,insight,url) in enumerate(cards):
   x=(i%2)*249;y=224 if i<2 else 7
   c.setStrokeColor(colors.HexColor('#b1b5bc'));c.setFillColor(colors.HexColor('#fafafa'));c.roundRect(x,y,238,209,5,fill=1)
   ir=ImageReader(str(ROOT/'doc/계획서/assets/competitors'/fn));iw,ih=ir.getSize();scale=min(205/iw,105/ih)
   c.drawImage(ir,x+119-iw*scale/2,y+95+(105-ih*scale)/2,width=iw*scale,height=ih*scale,mask='auto')
   c.setFillColor(colors.HexColor('#222222'));c.setFont('MalgunBold',10);c.drawString(x+10,y+80,name)
   c.setFont('MalgunBold',8.2);c.drawString(x+10,y+63,price)
   c.setFont('Malgun',8);c.drawString(x+10,y+46,desc);c.drawString(x+10,y+28,insight)
   c.setFillColor(colors.HexColor('#285a88'));c.setFont('Malgun',7);c.drawString(x+10,y+12,'공식 이미지·서비스 출처 ↗');c.linkURL(url,(x+8,y+8,x+227,y+25),relative=1)

raw=SRC.read_text(encoding='utf-8')
team=raw[raw.index('## 1.'):raw.index('## 2.')]
intro=raw[raw.index('### 창업아이템 명칭'):raw.index('### 진출 목표시장')]
market=raw[raw.index('### 진출 목표시장'):raw.index('### 경쟁 제품 및 서비스 조사')]
competitor_notes=raw[raw.index('**직접 유사 구현.**'):raw.index('### 경쟁사 대비 차별성')]
diff=raw[raw.index('### 경쟁사 대비 차별성'):raw.index('### 산출물 및 개발단계')]
outputs=raw[raw.index('### 산출물 및 개발단계'):raw.index('### 이미지')]
sources=raw[raw.index('## 작성 근거 및 제출 전 확인'):]
story=[]
story += [p('1. 팀 소개','h2'),p('팀명 300 Seconds | 개정일 2026-10-16 | 시장조사·핵심 기능 반영','small')]
story += parse(team.split('\n',1)[1])
story += [Spacer(1,15),p('작성 기준','h3'),p('2026-10-12 회의록·현재 README와 사용자가 제공한 2026-10-14 시장조사를 바탕으로 개정했다. 경쟁사 공식 자료는 2026-10-16 재확인했다. 네오픽셀과 발사체·스피커·서보 피드백은 사용자의 추가 요청을 반영했다. 기능·사업화·검증 항목은 계획이며 구현 완료를 의미하지 않는다.','small'),PageBreak()]
story += [p('2. 창업아이템 개요','h2')]+parse(intro)+[PageBreak()]
story += [p('창업아이템 개요 | 목표시장·사업화','h2')]+parse(market)+[PageBreak()]
story += [p('창업아이템 개요 | 경쟁 제품·서비스','h2'),p('공식 제품 사진·로고 4종 | 확인일 2026-10-16 | 원본 비율 유지','small'),Competitors(),p('상표·이미지는 각 권리자 소유. 비교·식별용 수록이며 제휴를 의미하지 않는다. 가격은 지역·결제·계약에 따라 변동. Forest 요금은 플랫폼·플랜별 확인.','small')]+parse(competitor_notes)+[PageBreak()]
story += [p('창업아이템 개요 | 차별성·개발계획','h2')]+parse(diff)+parse(outputs)+[PageBreak()]
story += [p('창업아이템 개요 | 이미지·출처','h2'),p('오브제형 AI 학습 코치 외관 개념도','h3'),Diagram('device'),p('외형·부품 위치는 제안 도식. 실제 제작 사진이 아니다. 충전 기능·전원 구성은 별도 검토한다.','small'),p('학습 상태 기반 피드백 구성도','h3'),Diagram('system')]
story += [p('작성 근거 및 제출 전 확인','h3')]
for line in sources.splitlines()[2:]:
 if line.strip(): story.append(p(line.removeprefix('- '),'small'))
def header(c,doc):
 c.saveState();c.setFillColor(colors.HexColor('#d4d4d4'));c.setStrokeColor(colors.HexColor('#777777'));c.rect(54,780,487,30,fill=1,stroke=1)
 c.setFont('MalgunBold',12);c.setFillColor(colors.HexColor('#1f1f1f'));c.drawCentredString(297.5,790,'[배재대 스마트 ICT 메이커톤] 사업계획서')
 c.setFont('Malgun',8);c.setFillColor(colors.HexColor('#666666'));c.drawString(54,29,'300 Seconds · 검토용 초안');c.drawRightString(541,29,str(doc.page));c.restoreState()
doc=SimpleDocTemplate(str(OUT),pagesize=(595.28,841.89),leftMargin=54,rightMargin=54.28,topMargin=73,bottomMargin=49,title='300 Seconds 사업계획서',author='300 Seconds')
doc.build(story,onFirstPage=header,onLaterPages=header)
pdf=pymupdf.open(OUT)
for i,page in enumerate(pdf):
 page.get_pixmap(matrix=pymupdf.Matrix(1.2,1.2)).save(str(ROOT/f'tmp/pdfs/plan-{i+1}.png'))
 print(i+1,len(page.get_text()),page.get_text()[:65].replace('\n',' / '))
print('PDF',OUT,'PAGES',len(pdf))
