"""Collect mechanical source evidence only; no physical dimensions were measured."""
from pathlib import Path
import datetime, hashlib, json, shutil
import requests
import fitz

ROOT = Path(__file__).resolve().parent
BOM = ROOT.parents[1]
UTC = lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
sources = []

def remote(sid, name, url, provenance, claims, caveats):
    entry = dict(id=sid, url=url, provenance=provenance, fetched_at_utc=UTC(), claims=claims, caveats=caveats)
    try:
        r = requests.get(url, timeout=35)
        entry.update(http_status=r.status_code, final_url=r.url, content_type=r.headers.get('content-type'))
        r.raise_for_status()
        if name.endswith('.pdf') and not r.content.startswith(b'%PDF'):
            raise ValueError('Response is not a PDF; no document saved')
        if 'nvidia.com/login' in r.url:
            raise ValueError('Official download requires login; not obtained')
        p = ROOT/name
        p.write_bytes(r.content)
        entry.update(path=name, bytes=len(r.content), sha256=hashlib.sha256(r.content).hexdigest(), status='saved')
        if name.endswith('.pdf'):
            d = fitz.open(p)
            entry['pages'] = len(d)
            if len(d) == 1:
                d[0].get_pixmap(matrix=fitz.Matrix(2,2)).save(p.with_suffix('.png'))
    except Exception as ex:
        entry.update(status='unavailable', error=str(ex))
    sources.append(entry)

def copied(sid, name, existing, url, provenance, claims, caveats):
    p = ROOT/name
    shutil.copyfile(BOM/existing,p)
    data=p.read_bytes()
    sources.append(dict(id=sid,path=name,url=url,provenance=provenance,status='copied_from_previously_saved_source',source_path='../../'+existing,
        copied_at_utc=UTC(),bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),claims=claims,caveats=caveats))

for tag,kind in [('MD01','2'),('MD02','3-standard'),('MD03','3-wide')]:
    name=f'camera-module-{kind}-mechanical-drawing.pdf'
    remote(tag,name,'https://datasheets.raspberrypi.com/camera/'+name,'manufacturer mechanical drawing',
           ['PCB outline 25 x 23.862 mm','4 x diameter 2.2 mm mounting holes','mounting grid 21 x 12.5 mm derived from explicit dimensions'],
           ['No as-built camera measured','Hole coordinate origin depends on camera rotation; use PDF datum rather than copying arbitrary top-left coordinates','Module 3 lens and height differ from Module 2; Standard and Wide are not mechanically identical'])

remote('MD04','CLS6336HV_vendor_dimensions.jpg','https://ueeshop.ly200-cdn.com/u_file/UPBE/UPBE325/2507/30/photo/CLS6336HV-EN.jpg',
       'seller-hosted branded mechanical figure; not signed manufacturer CAD',
       ['40.5 x 20.2 mm body footprint','40 mm vertical callout','29 mm from base to underside of mounting flange','49.5 x 10 mm mounting notch center grid'],
       ['40 mm dimension terminates at apparent shaft-tip plane in side figure; do not assume 40 mm housing-only height','Output shaft X offset, spline diameter, notch diameter, flange thickness and full flange span not dimensioned','25T spline is textual seller specification; use supplied metal/plastic horn rather than printing spline','Other sellers report width 20.5 mm; actual servo must be measured'])
copied('MD05','CLS6336HV_BeGreatRC_source.html','web/CLS6336HV_BeGreatRC.html','https://begreatrc.com/products/jx-servo-cls6336hv-35kg-aluminium-shell-metal-gear-high-voltage-coreless-digital-servo-968','seller product page',['40.5 x 20.2 x 40 mm nominal','25 tooth spline','63 g nominal'],['Not manufacturer engineering drawing','No manufacturing tolerance'])
copied('MD06','Britz_BA-R9_manual.jpg','manuals/Britz_BA-R9_manual.jpg','https://www.britz.co.kr/common/download.php?fullpath=product/19_f&filename=BA-R9%20SoundBar_manual.jpg','manufacturer manual',['400(W) x 73(D) x 68(H) mm','50 mm x 2 acoustic units'],['Enclosure keepout only','No teardown, internal driver screw pattern, PCB or knob dimensions supplied','Do not shrink this intact speaker into a small head enclosure'])
copied('MD07','Britz_BA-R9_source.html','web/Britz_BA-R9_official.html','https://www.britz.co.kr/product/view.html?p_no=19','manufacturer product page',['Product identity BA-R9'],['Dimensions checked visually against MD06 manual'])
copied('MD08','SunFounder_TS0185_source.html','web/SunFounder_PCA9685_product.html','https://www.sunfounder.com/products/pca9685-servo-driver','manufacturer product page',['SKU TS0185 identity'],['No mechanical drawing or hole spacing located','74 x 32 mm belongs to a different SunFounder shield and is not applied to TS0185','Common Adafruit/clone 62.5 x 25.4 dimensions not proven for this board'])
remote('MD09','NVIDIA_Nano_launch_size.html','https://nvidianews.nvidia.com/news/nvidia-announces-jetson-nano-99-tiny-yet-mighty-nvidia-cuda-x-ai-computer-that-runs-all-ai-models','manufacturer announcement',
       ['Developer Kit size 100 x 80 mm'],['2019 launch article, not exact B01 mounting drawing','Does not establish as-built heat-sink height or port offsets'])
remote('MD10','NVIDIA_B01_carrier_specification.pdf','https://developer.nvidia.com/jetson-nano-developer-kit-carrier-board-p3449-b01-specification','manufacturer engineering document download',[],['Download requires NVIDIA login; not obtained','B01 board revision on actual item remains unconfirmed'])
remote('MD11','NVIDIA_B01_STEP.zip','https://developer.nvidia.com/jetson-nano-developer-kit-b01-3d-cad-step-model','manufacturer engineering CAD download',[],['Download requires NVIDIA login; not obtained'])
remote('MD12','NVIDIA_download_catalog.json','https://developer.nvidia.com/embedded/downloads.json','manufacturer download catalog',
       ['Carrier spec P3449 B01 v1.1, date 2020/01/15','Developer Kit STEP P3450 Rev 100, date 2020/01/15'],['Catalog is index evidence only; unavailable document contents were not inferred'])
remote('MD13','RPi_camera_module_3_product.html','https://www.raspberrypi.com/products/camera-module-3/','manufacturer product page',
       ['25 x 24 x 11.5 mm Standard nominal','12.4 mm Wide nominal height'],['Product dimensions are rounded and may use different datum from side drawing 11.3 / 12 mm'])
copied('MD14','Camera_Module_3_product_brief.pdf','datasheets/Camera_Module_3_product_brief.pdf','https://datasheets.raspberrypi.com/camera/camera-module-3-product-brief.pdf','manufacturer product brief',
       ['25 x 24 x 11.5 mm Standard nominal','12.4 mm Wide nominal height'],['Nominal envelope differs slightly from side drawing callouts; retain larger product envelope for preliminary keepout'])

manifest=dict(verified_on_korea_date='2026-10-23',units='mm',physical_measurements_performed=False,
    classification_policy={'manufacturer_drawing':'Published engineering dimensions, still verify actual model and revision','vendor_nominal':'Provisional fit reference, no tolerances or guarantee','derived':'Arithmetic from explicit drawing dimensions, not measured','unknown':'Do not fabricate mating holes, spline, or assembly fit'},sources=sources)
(ROOT/'dimensions_sources.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps([{'id':s['id'],'status':s['status'],'path':s.get('path'),'bytes':s.get('bytes')} for s in sources],ensure_ascii=False,indent=2))
