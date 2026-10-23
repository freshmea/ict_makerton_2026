"""Record current P1 artifacts and update the old joint-sheet entry point.
Does not change CAD geometry or regenerate the model.
"""
from pathlib import Path
import hashlib, json, re
from datetime import datetime, timezone
import fitz
import sys

ROOT = Path(__file__).resolve().parent
v6 = ROOT.parent / 'mechanical_v6'
data_path = ROOT / 'cad' / 'validation.json'
data = json.loads(data_path.read_text(encoding='utf-8'))
for row in data['parts']:
    row['notes'] = row['notes'].replace('P0 dimensional trial', 'P1 dimensional trial').replace('Motor inside base;', 'Motor inside base/collar;')
data_path.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')

labels = {
    'PILL_BASE_TRAY': '둥근 베이스 트레이',
    'PILL_BASE_LID': '둥근 베이스 뚜껑',
    'SEAM_PLATE': '베이스 연결판',
    'PEBBLE_HEAD_FRONT': '페블 머리 전면',
    'PEBBLE_HEAD_REAR': '페블 머리 후면',
    'CAPSULE_VISOR': '캡슐형 얼굴 베젤',
    'ROUNDED_PHONE': '둥근 휴대폰 받침',
    'ROUND_YAW': '원형 Yaw 수납 칼라',
    'CURVED_ARM_CORE_FRONT': '곡선 팔·고정 코어 전면',
    'CURVED_ARM_CORE_REAR': '곡선 팔·고정 코어 후면',
    'WRAP_HAND_FRONT': '감싸는 손·혼 홈 앞 커버',
    'WRAP_HAND_REAR': '감싸는 손·베어링 뒤 커버',
}
table = ['# v7 P1 출력 형상 목록', '',
         '현재 STL은 22개다. 단위 mm, 배율 100%. 모든 끼움·축방향 체결을 확정한 최종 조립품은 아니다. [검토 범위](README.md)를 먼저 확인한다.', '',
         '| 부품 / STL | 용도 | 경계상자 X×Y×Z (mm) |',
         '| --- | --- | --- |']
for row in data['parts']:
    name = row['part']
    label = next((v for k, v in labels.items() if k in name), 'P1 출력 형상')
    bbox = '×'.join(f'{n:.2f}' for n in row['bbox_mm'])
    table.append(f'| [{name}](stl/{name}.stl) | {label} | {bbox} |')
table += ['', 'CAD 좌표의 각 개별 STEP와 출력용 STL은 위치가 다르다. STL은 각 부품을 양의 좌표로 옮긴 파일이며 조립 위치의 기준은 전체 STEP다.', '',
          '폐기한 별도 Yaw 혼판 2개는 팔과 일체화했으므로 목록에서 제외했다. `history/retired_separate_rotors`에 보존된 파일은 현재 출력 대상이 아니다.', '',
          'SolidCraft는 WRAP_HAND 앞뒤 4개에 열린 바디 가져오기 경고를 반환했다. STL 폐합 검사와 별개다. [기록](reference/solidcraft/README.md).', '']
(ROOT / 'PARTS.md').write_text('\n'.join(table), encoding='utf-8')

compat = '''"""Compatibility entry point: generate corrected v7 P1 joint sheets.
The superseded external-servo P0 generator is preserved in history/P0_external_servo.
"""
from pathlib import Path
import runpy, shutil

V6 = Path(__file__).resolve().parents[1]
V7 = V6.parent / 'mechanical_v7'
runpy.run_path(str(V7 / 'reference' / 'generate_joint_detail.py'), run_name='__main__')
for source, target in [
    ('FWB_JOINT_P1_reference_A3.pdf', 'FWB_DETAIL_reference_A3.pdf'),
    ('FWB_JOINT_P1_reference_A3_page1.png', 'FWB_DETAIL_reference_A3.png'),
    ('FWB_JOINT_P1_reference_A3_page2.png', 'FWB_DETAIL_reference_A3_page2.png'),
]:
    shutil.copy2(V7 / 'drawings' / source, V6 / 'drawings' / target)
print('Updated v6 joint-sheet paths from v7 P1.')
'''
(v6 / 'dimensions' / 'build_detail_sheets.py').write_text(compat, encoding='utf-8')

expected = {r['part'] + '.stl' for r in data['parts']}
actual = {p.name for p in (ROOT / 'stl').glob('*.stl')}
assert actual == expected, (actual - expected, expected - actual)
assert len(actual) == 22
assert all(r['valid'] and r['watertight'] for r in data['parts'])
assert all(r['intersection_mm3'] < 1e-6 for r in data['static_checks'])

pdfs = []
for p in sorted((ROOT / 'drawings').glob('*.pdf')):
    with fitz.open(p) as pdf:
        pdfs.append(dict(file=p.relative_to(ROOT).as_posix(), pages=len(pdf),
                        page_mm=[[round(page.rect.width / 72 * 25.4, 2), round(page.rect.height / 72 * 25.4, 2)] for page in pdf]))

same = []
for oldname, newname in [('FWB_DETAIL_reference_A3.pdf', 'FWB_JOINT_P1_reference_A3.pdf'),
                         ('FWB_DETAIL_reference_A3.png', 'FWB_JOINT_P1_reference_A3_page1.png'),
                         ('FWB_DETAIL_reference_A3_page2.png', 'FWB_JOINT_P1_reference_A3_page2.png')]:
    a = (v6 / 'drawings' / oldname).read_bytes()
    b = (ROOT / 'drawings' / newname).read_bytes()
    assert a == b, oldname
    same.append(oldname)

broken = []
for p in [ROOT / 'README.md', ROOT / 'PARTS.md', ROOT.parent / 'README.md', ROOT.parent / 'design sample2.md']:
    for link in re.findall(r'\]\(([^)]+)\)', p.read_text(encoding='utf-8')):
        from urllib.parse import unquote
        if not link.startswith(('http:', 'https:', '#')):
            resolved = p.parent / unquote(link.split('#', 1)[0])
            if not resolved.exists() and resolved != ROOT / 'verification.json':
                broken.append(dict(file=str(p), link=link))
assert not broken, broken

files = []
for p in sorted(ROOT.rglob('*')):
    if p.is_file() and not {'__pycache__', 'history', 'solidcraft_repair'} & set(p.relative_to(ROOT).parts) and p.name != 'verification.json':
        raw = p.read_bytes()
        files.append(dict(file=p.relative_to(ROOT).as_posix(), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
out = dict(verified_at_utc=datetime.now(timezone.utc).isoformat(), revision='P1', printed_parts=22,
           static_pairs=len(data['static_checks']), static_intersection_max_mm3=max(r['intersection_mm3'] for r in data['static_checks']),
           checks_from_model_generation=str((ROOT / 'cad' / 'validation.json').relative_to(ROOT)),
           motion_check='not performed', hardware_fit='not measured', release='PENDING',
           pdfs=pdfs, v6_replaced_with_identical_P1=same, broken_links=broken,
           SolidCraft_import='47 bodies; 4 open-body warnings on wrap hand parts; unresolved', files=files)
(ROOT / 'verification.json').write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({k: v for k, v in out.items() if k != 'files'}, ensure_ascii=False, indent=2))
