"""Compatibility entry point: generate corrected v7 P1 joint sheets.
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
