from pathlib import Path
base=Path(__file__).with_name('build_plan.py')
definitions=base.read_text(encoding='utf8').split("raw=SRC.read_text",1)[0]
definitions=definitions.replace('기존 문제집 기반 코칭으로 구분 [S1]','아이별 기억·양방향 대화 목표 [S1]')
exec(compile(definitions,str(base),'exec'))
from reportlab.platypus import Image
raw=SRC.read_text(encoding='utf8')
def section(a,b): return raw[raw.index(a):raw.index(b)]
def paragraph(label):
 a=raw.index('**'+label+'**')
 return raw[a:raw.index('\n\n',a)]
def chunk(a,b): return parse(section(a,b))
story=[p('1. 팀 소개','h2'),p('개정일 2026-10-18 · 아이 주도 자율학습 동반자 · 제출 검토용 요약본','small')]
story+=chunk('## 1. 팀 소개','## 2. 창업아이템 개요')[1:]
story+=[p('제품 비전','h3'),p('아이를 기억하고 기다리며, 필요할 때만 돕는 피지컬 AI 학습 동반자. 아이가 자기 속도로 생각하고 풀이하는 시간을 충분히 보장한다.'),p('작성 근거','h3'),p('2026-10-12 회의록·현재 사업계획서·2026-10-14 시장조사와 맞춤형 동반자·양방향 대화·인터럽트 요구사항, 아이가 학습을 주도하고 필요한 순간만 도움을 제공하라는 추가 요청을 반영했다. 상세한 요구사항은 Markdown 원본에 수록했다. 모든 기능은 기획·검증 목표이며 구현 완료를 뜻하지 않는다.'),PageBreak()]
story+=[p('2. 창업아이템 개요 | 소개·핵심 기능','h2')]
story+=chunk('### 창업아이템 명칭','**아이를 알아가는 기억과 개인화.**')
story+=[PageBreak()]
story+=[p('창업아이템 개요 | 기억·자연스러운 대화','h2')]
story+=chunk('**아이를 알아가는 기억과 개인화.**','**구현 구조(제안).**')
story+=[p(paragraph('구현 구조(제안).')),p(paragraph('사용 흐름.')),PageBreak()]
story+=[p('창업아이템 개요 | 목표시장·경쟁 제품','h2'),p('목표시장·사업모델','h3'),p('1차 대상은 초등 고학년 가정의 아이·학부모, 2차 대상은 소규모 공부방·지역아동센터다. 기기 판매와 개인 맞춤 음성 대화·기억·학습 요약 구독을 검토한다. 기존 99,000원 기기 가격 가설은 음성·연산 운영비를 반영해 재검토한다. 국내 세부시장 규모·판매량·구매 전환은 미확인이다.'),p('경쟁 제품·서비스 | 기존 공식 자료 확인일 2026-10-16','h3'),Competitors(),p('이미지·상표는 각 권리자 소유. 공식 제품·서비스 출처는 [S1~S4]. 가격은 지역·계약·시점에 따라 달라지며, 이번 개정에서 재조사하지 않았다.','small'),p('공개 유사 구현 StudyGuard AI[S5]·MAK-G[S6]에는 행동 감지·알림·기록 사례가 있다. 제작자 설명을 확인했으며 본 팀 실행 검증은 수행하지 않았다. Focus Friend[S7]는 본문 재확인 제한으로 핵심 비교에서 제외했다. 양방향 음성·장기 기억의 경쟁 성능은 추가 비교가 필요하다.','small'),PageBreak()]
story+=[p('창업아이템 개요 | 차별성·산출물·개발단계','h2')]
story+=chunk('### 경쟁사 대비 차별성','### 산출물 및 개발단계')
story+=[p('산출물 및 개발단계','h3'),p('현재는 기획·구체화 단계다. 핵심 산출물은 마이크·스피커·카메라·네오픽셀·LCD·2 DOF 조명 손을 연결한 실물 1세트, 대기·개입 판단·음성 대화 소스 1식, 아이별 기억 관리 1식, 설계·시험 문서와 발표·영상 각 1식이다. 모바일은 핵심 자율학습 지원 흐름 완성 후 연결한다.'),p(paragraph('MVP 시연(제안).')),p(paragraph('추진 순서.')),p('시험·사업 검증','h3'),p('요청 없는 침묵·독백·풀이, 힌트 후 대기, 중단 요청·인터럽트, 합의한 알림의 미응답, 기억·장애 복구를 각 3회 이상 시험한다. 대화 없는 학습도 성공으로 보고 불필요한 개입률·반복 알림·중단 없이 생각한 시간·자율 풀이 재개를 기록한다. 출력 정지·새 응답 지연은 별도로 측정한다. 아이의 통제감과 보호자의 기록·가격 수용성도 검증한다.'),PageBreak()]
story+=[p('창업아이템 개요 | 제품 시안·시스템·출처','h2'),Image(str(ROOT/'doc/BOM/img/design2-04-fold-wing-v4-korean-flush.png'),width=487,height=487*2/3),p('채택한 디자인: 폴드 윙 버디 v4. 팔당 회전 2 DOF, 고정 손가락·매립형 렌즈. 자율학습 중 고정 조명을 유지하고 요청 시 조사 위치·폭·밝기를 조절한다. 손 흔들기는 합의한 알림에만 사용하며 발사체는 제외했다. AI 콘셉트로 실제 성능은 검증 전이다.','small'),p('개정 시스템 구성','h3'),p('아이의 자율학습·기본 대기 → 명시적 요청/합의 조건 → 개입 판단 → 필요한 기억 조회·짧은 도움 → 자율학습 대기. 도움 중에는 동시 듣기·인터럽트를 유지한다. 카메라는 보조 문맥, 조명은 기본 고정, 모바일은 합의한 요약·알림으로 연결한다.'),p('작성 근거·출처·제출 전 확인','h3')]
sources=raw[raw.index('## 작성 근거 및 제출 전 확인'):]
for line in sources.splitlines()[2:]:
 if line.strip(): story.append(p(line.removeprefix('- '),'small'))
def header(c,doc):
 c.saveState();c.setFillColor(colors.HexColor('#d4d4d4'));c.setStrokeColor(colors.HexColor('#777777'));c.rect(54,780,487,30,fill=1,stroke=1)
 c.setFont('MalgunBold',12);c.setFillColor(colors.HexColor('#1f1f1f'));c.drawCentredString(297.5,790,'[배재대 스마트 ICT 메이커톤] 사업계획서')
 c.setFont('Malgun',8);c.setFillColor(colors.HexColor('#666666'));c.drawString(54,29,'300 Seconds · 2026-10-18 개정 · 검토용 요약본');c.drawRightString(541,29,str(doc.page));c.restoreState()
doc=SimpleDocTemplate(str(OUT),pagesize=(595.28,841.89),leftMargin=54,rightMargin=54.28,topMargin=73,bottomMargin=49,title='300 Seconds 아이 주도 자율학습 동반자 사업계획서',author='300 Seconds')
doc.build(story,onFirstPage=header,onLaterPages=header)
d=pymupdf.open(OUT)
for i,page in enumerate(d):
 page.get_pixmap(matrix=pymupdf.Matrix(1.2,1.2)).save(str(ROOT/f'tmp/pdfs/personal-tutor-{i+1}.png'))
 print('PAGE',i+1,'CHARS',len(page.get_text()))
print('PAGES',len(d))
