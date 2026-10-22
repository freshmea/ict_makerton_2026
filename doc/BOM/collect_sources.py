"""Download the curated BOM references; record failures without disguising them as files."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from datetime import datetime, timezone
import requests
import fitz

ROOT = Path(__file__).resolve().parent
# id, filename, authority, URL, expected content marker
SOURCES = [
 ('S01','datasheets/PCA9685_NXP.pdf','manufacturer','https://www.nxp.com/docs/en/data-sheet/PCA9685.pdf','PCA9685'),
 ('S02','datasheets/LM2596_TI.pdf','manufacturer','https://www.ti.com/lit/ds/symlink/lm2596.pdf','LM2596'),
 ('S03','datasheets/Camera_Module_3_product_brief.pdf','manufacturer','https://datasheets.raspberrypi.com/camera/camera-module-3-product-brief.pdf','Camera Module 3'),
 ('S04','manuals/Jetson_Nano_Developer_Kit_User_Guide.pdf','manufacturer','https://developer.download.nvidia.com/embedded/L4T/r32-2_Release_v1.0/Jetson_Nano_Developer_Kit_User_Guide.pdf','Jetson'),
 ('S05','web/SunFounder_PCA9685_product.html','manufacturer','https://www.sunfounder.com/products/pca9685-servo-driver','PCA9685'),
 ('S06','web/SunFounder_PCA9685_wiki.html','manufacturer','https://wiki.sunfounder.cc/index.php?title=PCA9685_16_Channel_12_Bit_PWM_Servo_Driver','PCA9685'),
 ('S07','web/Camera_Module_2_product.html','manufacturer','https://www.raspberrypi.com/products/camera-module-v2/','IMX219'),
 ('S08','web/Camera_Module_3_product.html','manufacturer','https://www.raspberrypi.com/products/camera-module-3/','IMX708'),
 ('S09','web/Raspberry_Pi_camera_documentation.html','manufacturer','https://www.raspberrypi.com/documentation/accessories/camera.html','Camera Module'),
 ('S10','web/Jetson_Nano_get_started.html','manufacturer','https://developer.nvidia.com/embedded/learn/get-started-jetson-nano-devkit','Jetson Nano'),
 ('S11','web/Jetson_Nano_power_NVIDIA.html','manufacturer-forum','https://forums.developer.nvidia.com/t/power-supply-considerations-for-jetson-nano-developer-kit/71637','power'),
 ('S12','web/Jetson_GPIO_README.txt','manufacturer','https://raw.githubusercontent.com/NVIDIA/jetson-gpio/master/README.md','GPIO'),
 ('S13','web/CLS6336HV_HobbyKing.html','retailer-reference-only','https://hobbyking.com/en_us/jx-cls6336hv-high-voltage-coreless-metal-gear-high-torque-servo-35-6kg-0-11sec-63g.html','CLS6336HV'),
 ('S14','web/CLS6336HV_BeGreatRC.html','retailer-reference-only','https://begreatrc.com/products/jx-servo-cls6336hv-35kg-aluminium-shell-metal-gear-high-voltage-coreless-digital-servo-968','CLS6336HV'),
 ('S15','manuals/LiPo_general_safety_Spektrum.pdf','other-manufacturer-general-reference','https://my.spektrumrc.com/ProdInfo/Files/SMART%20Batteries%20Safety%20Sheet%20Update%20Manual-MULTI.pdf','Lithium'),
 ('S16','web/Adapter_KC_SafetyKorea.html','government','https://www.safetykorea.kr/search/searchPop?certNum=SU10726-20002&menu=search','ZC024'),
 ('S17','web/Adapter_RRA_registration.html','government','https://www.rra.go.kr/ko/license/A_b_popup_keyno.do?key_no=R-R-Zcp-ZC024AHL120','ZC024'),
 ('S18','web/SKY_HOLIC_home.html','brand-site-unverified-product','https://www.sky-holic.com/','sky'),
 ('S19','web/NVIDIA_first_picture_camera.html','manufacturer','https://developer.nvidia.com/embedded/learn/tutorials/first-picture-csi-usb-camera','IMX219'),
 ('S20','web/NVIDIA_Nano_IMX708_support.html','manufacturer-forum','https://forums.developer.nvidia.com/t/jetson-nano-no-available-cameras/246747','IMX708'),
 ('S21','web/Balancer_Guard_V_Devicemart.html','retailer-product-identification','https://www.devicemart.co.kr/goods/view?no=9878','Balancer Guard V'),
 ('S22','web/Balancer_Guard_V_firsthand_review.html','firsthand-historical-review-not-manufacturer-manual','https://teamsi.co.kr/board/board.html?code=cockpit1_data1&lock=N&num1=999941&num2=00000&page=2&type=v','Balancer Guard'),
 ('S23', 'web/Britz_BA-R9_official.html', 'manufacturer', 'https://www.britz.co.kr/product/view.html?p_no=19', 'BA-R9'),
 ('S24', 'manuals/Britz_BA-R9_manual.jpg', 'manufacturer', 'https://www.britz.co.kr/common/download.php?fullpath=product/19_f&filename=BA-R9%20SoundBar_manual.jpg', None),
 ('S25', 'datasheets/WS2812B_V5_reference.pdf', 'manufacturer-document-via-module-vendor-reference-only', 'https://seengreat.com/upload/file/85/WS2812B.PDF', 'WS2812B'),
 ('S26', 'manuals/Adafruit_NeoPixel_Uberguide.pdf', 'other-manufacturer-general-reference', 'https://cdn-learn.adafruit.com/downloads/pdf/adafruit-neopixel-uberguide.pdf', 'NeoPixel'),
 ('S27', 'web/Adafruit_NeoPixel_best_practices.html', 'other-manufacturer-general-reference', 'https://learn.adafruit.com/adafruit-neopixel-uberguide/best-practices', 'NeoPixel'),
 ('S28', 'web/UGREEN_30143_candidate_reference.html', 'regional-brand-site-candidate-not-identified-unit', 'https://ugreen.com.tr/urun/ugreen-usb-harici-3-5mm-stereo-ses-karti-beyaz/', '30143'),
 ('S29', 'datasheets/MAX7219_MAX7221_Analog_Devices.pdf', 'manufacturer', 'https://www.analog.com/media/en/technical-documentation/data-sheets/MAX7219-MAX7221.pdf', 'MAX7219'),
 ('S30', 'web/MAX7219_Analog_Devices_product.html', 'manufacturer', 'https://www.analog.com/en/products/max7219.html', 'MAX7219'),
 ('S31', 'datasheets/TTP223_BA6_V2_1_Tontek_reference.pdf', 'manufacturer-candidate-not-identified-unit', 'https://www.tontek.com.tw/uploads/product/243/TTP223-BA6_V2.1_EN.pdf', 'TTP223'),
 ('S32', 'web/Tontek_TTP223_BA6_candidate.html', 'manufacturer-candidate-not-identified-unit', 'https://www.tontek.com.tw/product/product2?idx=243&lang=en', 'TTP223'),
]

def fetch(item):
    sid, name, authority, url, marker = item
    result = dict(id=sid, file=name, authority=authority, url=url, retrieved_at_utc=datetime.now(timezone.utc).isoformat())
    try:
        r = requests.get(url, timeout=45, headers={'User-Agent':'Mozilla/5.0 BOM reference archive'})
        result.update(http_status=r.status_code, final_url=r.url, content_type=r.headers.get('Content-Type',''))
        r.raise_for_status()
        data = r.content
        if name.endswith('.pdf'):
            if not data.startswith(b'%PDF-'):
                raise ValueError('Response is not a PDF')
            doc = fitz.open(stream=data, filetype='pdf')
            txt = ''.join(p.get_text() for p in doc)
            result['pages'] = len(doc)
            if marker.lower() not in txt.lower():
                raise ValueError('PDF expected text missing: '+marker)
        elif name.endswith('.jpg'):
            from PIL import Image
            from io import BytesIO
            Image.open(BytesIO(data)).verify()
        else:
            if marker.lower() not in r.text.lower():
                raise ValueError('Expected content marker missing: '+marker)
        dest = ROOT / name
        if dest.exists() and dest.read_bytes() != data:
            raise FileExistsError('Existing different file preserved: '+name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        result.update(status='saved', bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    except Exception as e:
        result.update(status='failed', error=str(e))
    return result

if __name__ == '__main__':
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(fetch, SOURCES))
    (ROOT/'sources.json').write_text(json.dumps(results, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    for r in results:
        print(r['id'], r['status'], r.get('bytes',0), r.get('error',''))
