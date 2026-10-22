"""Prepare a bounded reference snapshot from the downloaded upstream ZIP."""
from pathlib import Path
import zipfile, hashlib, json, shutil
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parent
SHA='2235c77a93e86d04dec2e03c6306ba2c06d454ce'
source=ROOT/'Road-Balance_SpotMicroJetson_2235c77.zip'
target=ROOT/'Road-Balance_SpotMicroJetson_2235c77_reference.zip'
images={'Readme_Parts2.jpg','Readme_assemble.jpg','SpotMicroAI_electronics.png','jetsonNano_connected_1.jpg','SpotMicroAI_jetson.jpg'}
records=[]
original=dict(url='https://codeload.github.com/Road-Balance/SpotMicroJetson/zip/'+SHA,commit=SHA,bytes=source.stat().st_size,sha256=hashlib.sha256(source.read_bytes()).hexdigest())
with zipfile.ZipFile(source) as upstream, zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as filtered:
    prefix=upstream.namelist()[0]
    assert prefix.endswith('/') and prefix.startswith('SpotMicroJetson-')
    keep_extracted=set()
    for entry in upstream.infolist():
        if entry.is_dir(): continue
        name=entry.filename[len(prefix):]
        rel=Path(name)
        assert not rel.is_absolute() and '..' not in rel.parts
        # Demo animations, fonts, and generated interpreter caches are not needed for reference.
        if rel.suffix.lower() in {'.gif','.ttf','.pyc'} or '__pycache__' in rel.parts:
            continue
        data=upstream.read(entry)
        filtered.writestr(entry.filename,data)
        records.append(dict(path=name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
        if rel.suffix.lower() in {'.md','.py','.txt','.ipynb','.yaml','.yml','.xml','.sh'} or rel.name=='LICENSE' or rel.name in images:
            dest=ROOT/'repo'/rel
            assert (ROOT/'repo').resolve() in dest.resolve().parents
            dest.parent.mkdir(parents=True,exist_ok=True); dest.write_bytes(data)
            keep_extracted.add(dest.resolve())
    # Remove only files created by this turn's initial extraction and omitted from the selected view.
    for entry in upstream.infolist():
        if entry.is_dir(): continue
        name=entry.filename[len(prefix):]
        dest=ROOT/'repo'/name
        assert (ROOT/'repo').resolve() in dest.resolve().parents
        if dest.exists() and dest.resolve() not in keep_extracted:
            assert dest.read_bytes()==upstream.read(entry)
            dest.unlink()
with zipfile.ZipFile(target) as check:
    assert check.testzip() is None
    assert len(check.infolist())==len(records)
out=dict(collected_at_utc=datetime.now(timezone.utc).isoformat(),repository='https://github.com/Road-Balance/SpotMicroJetson',commit=SHA,original_download=original,snapshot=dict(file=target.name,bytes=target.stat().st_size,sha256=hashlib.sha256(target.read_bytes()).hexdigest(),zip_crc_verified=True),omitted_extensions=['.gif','.ttf','.pyc'],files=records)
(ROOT/'repository_snapshot.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
source.unlink() # newly downloaded temporary full archive; validated reference snapshot is retained
captions=[
 ('12_power','AUtIKKJltyg','youtube-AUtIKKJltyg-89f04d1e-7cef-4d61-9972-3728a92c2214.txt'),
 ('15_servo_specs','StFKgFmMEK0','youtube-StFKgFmMEK0-7f3572de-03ed-472f-98ce-034458370cc7.txt'),
 ('16_servo_control','Az8Ae3zJoPo','youtube-Az8Ae3zJoPo-ffaca876-432b-4743-b7d2-c6076c3cff8c.txt'),
 ('18_calibration','pvS29mRDxEc','youtube-pvS29mRDxEc-8fc4b89b-af16-4b3f-8717-12f788a894f1.txt'),
]
caption_records=[]
for label,video,name in captions:
    src=Path('C:/Users/ADMINI~1/AppData/Local/Temp/browser-use/exports')/name
    data=src.read_bytes(); assert b'Captions: auto-generated' in data
    dest=ROOT/'transcripts'/(label+'.txt'); dest.parent.mkdir(exist_ok=True); dest.write_bytes(data)
    caption_records.append(dict(file=dest.relative_to(ROOT).as_posix(),video_id=video,url='https://www.youtube.com/watch?v='+video,language='ko',auto_generated=True,sha256=hashlib.sha256(data).hexdigest(),bytes=len(data)))
(ROOT/'transcripts'/'sources.json').write_text(json.dumps(caption_records,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(snapshot_bytes=target.stat().st_size,snapshot_files=len(records),transcripts=len(caption_records))))
