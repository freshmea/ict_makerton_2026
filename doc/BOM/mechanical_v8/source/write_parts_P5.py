"""Generate the P5-only parts list from completed geometry and print manifests."""
from pathlib import Path
import hashlib,json

ROOT=Path(__file__).resolve().parents[1]
P5=ROOT/'P5'

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def desc(name):
    if name=='HAND_DOWEL_4x6':return '손 전후 정렬용 느슨한 핀, 양손 각2개'
    if 'ROLL_YOKE_PALM_FRONT' in name:return '안쪽 Roll 캡·후방 요크·앞 손바닥 일체'
    if 'ROLL_PALM_REAR' in name:return '뒤 손바닥·목 서비스 분할'
    if 'ROLL_BEARING_CAP' in name:return '마지막에 닫는 X동축 베어링 캡·연결 귀'
    if 'SHOULDER_YAW_TURRET' in name:return 'J1 회전판·J2 고정 어깨 하우징'
    if 'CURVED_ARM_CORE' in name:return 'P5 팔: Ø88 어깨 캡·브리지와 X축 손목 고정 코어'
    if 'PILL_BASE_TRAY' in name:return '3분할 베이스 트레이'
    if 'PILL_BASE_LID' in name:return '3분할 베이스 서비스 뚜껑'
    if 'SEAM_SPLICE' in name:return '베이스 전후 접합판·정렬키·M3 좌석'
    if 'ROUND_YAW_COLLAR' in name:return 'J1 베이스 칼라'
    if 'PEBBLE_HEAD' in name:return '페블 머리 전후 외장'
    if 'CAPSULE_VISOR' in name:return '얼굴 베젤'
    if 'PHONE_CRADLE' in name:return '휴대폰 받침'
    return 'P5 출력 부품'

def main():
    geometry=json.loads((ROOT/'source/geometry_P5_parts.json').read_text(encoding='utf-8'))
    manifest=json.loads((P5/'print/manifest.json').read_text(encoding='utf-8'))
    records=manifest['parts'];byname={p['part']:p for p in records}
    expected={p['name'] for p in geometry}|{'HAND_DOWEL_4x6'}
    assert set(byname)==expected and len(byname)==len(records)
    assert manifest['input_dir'].replace('\\','/').endswith('P5/stl')
    assert manifest['all_static_checks_pass'] and not manifest['slicing_performed'] and not manifest['physical_print_verified']
    checks=[]
    for row in records:
        assert row['watertight'] and row['connected_components']==1
        assert row['quantity']==(4 if row['part']=='HAND_DOWEL_4x6' else 1)
        for field,key in [('source_stl','source_sha256'),('oriented_stl','oriented_stl_sha256'),('model_3mf','model_3mf_sha256')]:
            path=ROOT/row[field]
            assert path.is_file() and sha(path)==row[key],str(path)
        assert (P5/'cad'/(row['part']+'.step')).is_file()
        checks.append({'part':row['part'],'quantity':row['quantity'],'three_export_hashes_match':True})
    qty=sum(p['quantity'] for p in records)
    height=max(p['oriented_bbox_mm'][2] for p in records)
    lines=['# P5 RPY 전용 출력 부품 목록','',f'2026-10-23 · mm · **{len(records)}종, 총 {qty}개 출력**. `HAND_DOWEL_4x6`만 4개, 나머지는 각 1개다.','',
      '기준은 [P5 형상 부품 목록](../source/geometry_P5_parts.json)과 [출력 manifest](print/manifest.json)다. 두 목록의 부품 집합, 각 부품의 원형 STL·방향 STL·3MF 입력 해시, 단일 폐합 메시와 수량을 대조했다. 서보·혼·베어링·금속 지지축 표시 바디는 출력 수량에 포함하지 않는다.','',
      '**P5 폴더의 파일만 사용한다.** 같은 이름의 P2/P4 팔도 형상이 다르며 P4의 Y축 손목과 혼용하지 않는다. 아래 치수는 방향 적용 STL의 경계상자 X×Y×Z다. 실제 출력 성공·서포트·공정 검증을 뜻하지 않는다.','',
      '수정 팔4종은 최초 직접 STL의 비폐합을 같은 STEP의 OCP 재테셀레이션으로 보완했다. 왼앞 팔은 미세 누락 삼각형1개를 추가 수선했으며 네이티브·STEP 원본은 바꾸지 않았다. 아래 표는 최종 배포 메시 기준이다. [재생성·원표면 비교 근거](../source/P5_geometry_files/arm_tessellation.json), [최종 출력 전수검사](../source/P5_geometry_files/print_geometry_QA.json)와 [상세 이력](PRINT_ASSEMBLY.md#출력-메시-검사와-확인-범위)을 확인한다.','',
      '| 부품 | 수량 | 출력 경계상자 mm | 역할 | P5 파일 |','| --- | ---: | --- | --- | --- |']
    order=[p['name'] for p in geometry]+['HAND_DOWEL_4x6']
    for name in order:
        row=byname[name];dims='×'.join(f'{v:.2f}' for v in row['oriented_bbox_mm'])
        files=f'[STEP](cad/{name}.step) · [출력 STL](print/oriented_stl/{name}.stl) · [3MF](print/single_part_3mf/{name}.3mf)'
        role=desc(name)
        lines.append(f'| {name} | {row["quantity"]} | {dims} | {role} | {files} |')
    lines += ['',f'정적 출력 배치의 최대 높이는 약 **{height:.2f} mm**다. X1 Carbon 기본 프로파일 높이250mm, 앞 왼쪽18×28mm 제외 영역, 가장자리1mm와 브림5mm 예약을 검사했다. [배치 그림](print/bed_overview.svg)과 [P5 출력·조립 안내](PRINT_ASSEMBLY.md)를 함께 확인한다.','',
      '자동 방향 후보(`automatic_review_required`)의 코어 내부·케이스 레일·손 요크·서비스 개구·너트 홈은 서포트와 제거 경로를 슬라이서에서 재검토한다. `3MF`는 단일 모델·좌표만 포함하며 재료/공정 프리셋·실제 브림·서포트·G-code는 없다.','',
      '실제 슬라이싱·출력, 수축, 재료 강도, 현품 끼움·체결·하중 시험은 미검증이다. CAD 6축 RPY 구동과 실제 하드웨어 구동도 별개다.','']
    (P5/'PARTS.md').write_text('\n'.join(lines),encoding='utf-8')
    evidence={'revision':'P5','print_designs':len(records),'print_quantity':qty,'largest_print_height_mm':height,'source_geometry_set_matches_manifest':True,'checks':checks,'static_manifest_pass':True,'slicing_performed':False,'physical_print_verified':False}
    (ROOT/'source/P5_files').mkdir(exist_ok=True)
    (ROOT/'source/P5_files/print_list_checks.json').write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in evidence.items() if k!='checks'}))

if __name__=='__main__':main()
