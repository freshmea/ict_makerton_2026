"""Check the native-engine P5 renders and the rendered three-page PDF."""
from pathlib import Path
import hashlib
import json
from PIL import Image
import fitz

ROOT = Path(__file__).resolve().parents[1]
GIF = ROOT / 'renders/P5_six_joint_demo.gif'
PDF = ROOT / 'drawings/FWB_v8_P5_RPY_A3.pdf'
frames, durations = [], []
with Image.open(GIF) as im:
    size = list(im.size)
    for i in range(im.n_frames):
        im.seek(i)
        frames.append(hashlib.sha256(im.convert('RGB').tobytes()).hexdigest())
        durations.append(im.info.get('duration', 0))
assert len(frames) == 97 and len(set(frames)) > 12
assert frames[0] == frames[-1], 'Animation did not return to its first neutral image'
assert all(d > 0 for d in durations)
with fitz.open(PDF) as pdf:
    assert len(pdf) == 3
    pages = []
    for i, page in enumerate(pdf):
        assert page.rect.width > page.rect.height
        assert len(page.get_text()) > 200
        png = PDF.with_name(PDF.stem + f'_page{i+1}.png')
        assert png.is_file()
        pages.append({'page': i+1, 'size_pt': list(page.rect)[2:],
                      'render': png.relative_to(ROOT).as_posix(),
                      'sha256': hashlib.sha256(png.read_bytes()).hexdigest()})
report = {
    'revision': 'P5', 'accepted': True,
    'gif': {'path': GIF.relative_to(ROOT).as_posix(), 'size_px': size,
            'frames': len(frames), 'unique_RGB_frames': len(set(frames)),
            'duration_ms': sum(durations), 'first_last_frame_equal': True,
            'renderer': 'SolidCraft native GPU, saved P5 study'},
    'pdf': {'path': PDF.relative_to(ROOT).as_posix(), 'pages': pages,
            'visual_inspection': 'All three rendered pages reviewed: readable Korean, no clipped text or overlapping content.'},
    'desktop_boundary': {'P5_opened_in_desktop': False, 'P5_GUI_angle_change_tested': False,
                         'reason': 'User stopped the earlier P4 desktop-control session with physical Escape. No further computer-use actions were performed.'},
    'limitations': ['Engine renders and static print placement are separate from desktop GUI interaction, slicing and physical hardware tests.']
}
(ROOT / 'evidence/P5_visual_QA.json').write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
print(json.dumps({'gif': report['gif'], 'pdf_pages': len(pages), 'accepted': True}))
