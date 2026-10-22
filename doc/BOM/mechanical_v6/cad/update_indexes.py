from pathlib import Path
import json
r=Path(__file__).resolve().parents[1]
v=json.loads((r/'cad/validation.json').read_text('utf-8'))
t='# v6 P0 출력 형상 목록\n\n단위 mm. 아래 17개는 배치·외장 시험 형상이며 최종 조립 보증이 아니다. 먼저 서보·베어링 끼움 시험편을 출력한다. 치수는 좌표축 정렬 경계상자이며 출력 방향은 별도로 정한다.\n\n| 부품 | X × Y × Z 외형 | STEP | STL |\n| --- | --- | --- | --- |\n'
for p in v['parts']:
    n=p['part'];dims=' × '.join(f'{x:.3f}' for x in p['bbox_mm'])
    t+=f'| {n} | {dims} | [STEP](cad/{n}.step) | [STL](stl/{n}.stl) |\n'
t+='\n관절의 혼 어댑터·지지축·고정 캡과 PCB 브래킷 등은 실측 전이며 이 목록에 완성 부품으로 포함하지 않았다.\n'
(r/'PARTS.md').write_text(t,encoding='utf-8')
p=r.parent/'README.md';t=p.read_text('utf-8');anchor='- [재료 목록과 사용 전 확인 사항]'
if 'mechanical_v6/README.md' not in t:
    t=t.replace(anchor,'- [v6 치수 기반 CAD·3면도·관절 분석](mechanical_v6/README.md): 공식/판매처 치수, SpotMicro 원본 STEP/STL, SolidCraft MCP 분석, P0 도면·STEP·STL·끼움 시험편.\n'+anchor,1)
p.write_text(t,encoding='utf-8')
p=r.parent/'design sample2.md';t=p.read_text('utf-8');a='## 생성 기록'
section='''## 04번 v6 — 치수 기반 CAD와 출력 검토

[![v6 외관 참고](mechanical_v6/renders/v6_appearance_concept.png)](mechanical_v6/renders/v6_appearance_concept.png)

BA-R9 완제품 400×73×68 mm, JX 서보 판매처 기구도, 카메라 공식 기구도와 SpotMicro 관절 STEP/STL을 대조했다. SolidCraft MCP로 원본 관절 3개를 별도 세션에서 분석했다.

[전면·측면·평면도 PDF](mechanical_v6/drawings/FWB_ASM_001_orthographic_A3.pdf)와 [CAD STEP](mechanical_v6/cad/fold_wing_v6_P0_assembly.step)은 같은 형상에서 생성했다. 베이스 설계값은 640×200×100 mm, 현재 자세 전체 높이는 337 mm이며 베이스는 3분할했다. 이는 시제품의 설계값으로 현품 실측값이 아니다. [원본 CAD 렌더](mechanical_v6/renders/v6_CAD_isometric.png)가 기하 기준이며 위 AI 외관 참고 이미지는 미세 형상이 다를 수 있다.

[전체 자료와 출력 순서](mechanical_v6/README.md), [SpotMicro 관절 분석](mechanical_v6/reference/joint_reference.md), [SolidCraft MCP 실제 결과](mechanical_v6/reference/solidcraft/README.md)를 참조한다. **P0 배치·끼움 검토용**이며 혼 어댑터·지지축·PCB 체결부는 실측 전이므로 최종 조립용 제작도로 확정하지 않았다. 출력 형상 17개와 먼저 출력할 작은 시험편 2개를 구분했다.

'''
if '## 04번 v6' not in t:t=t.replace(a,section+a,1)
p.write_text(t,encoding='utf-8')
p=r.parent/'재료 목록.md';t=p.read_text('utf-8');a='## 핵심 자료 요약'
s='''## 기구 설계와 추가 필요 부품

[v6 CAD·3면도·출력 검토](mechanical_v6/README.md)를 추가했다. 보유품 수량은 사진 기준을 유지한다. 팔 4축의 반대편 지지에 **F625ZZ 4개 사용을 계획**하며 보유 여부는 미확인이다. 서보 혼·Ø5 지지축·스페이서·볼트/너트와 매트릭스 추가 1개도 준비·확인 대상이다. 규격 미정인 체결부를 확정 구매 목록으로 보지 않는다.

'''
if '## 기구 설계와 추가 필요 부품' not in t:t=t.replace(a,s+a,1)
p.write_text(t,encoding='utf-8')
print('Linked mechanical package and parts inventory.')
print('Package bytes:',sum(p.stat().st_size for p in r.rglob('*') if p.is_file()))
