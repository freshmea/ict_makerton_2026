#!/usr/bin/env python3
"""Synthetic local component check, separate from human Korean accuracy."""
import argparse,json,os,subprocess,tempfile,time
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--skip-asr',action='store_true');a=p.parse_args()
    worker=Path(__file__).resolve().parents[1]/'workers/local_ai.py';checks=[]
    with tempfile.TemporaryDirectory(prefix='local-ai-') as tmp:
        root=Path(tmp);fontpath=subprocess.check_output(['fc-match','sans:lang=ko','-f','%{file}']).decode().strip()
        image=Image.new('RGB',(1280,720),'white');d=ImageDraw.Draw(image);font=ImageFont.truetype(fontpath,48)
        d.text((60,100),'수학 공부\n문제의 조건을 먼저 찾아보자.\n3 + 4 = ?',font=font,fill='black',spacing=30);image.save(root/'ocr.png')
        def call(q):
            start=time.monotonic();r=subprocess.run(['/opt/300seconds/ai/venv/bin/python',str(worker)],input=(json.dumps(q)+'\n').encode(),stdout=subprocess.PIPE,timeout=40,env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',OMP_THREAD_LIMIT='1'))
            v=json.loads(r.stdout);assert v['ok'],v;checks.append({'op':q['op'],'wall_ms':round((time.monotonic()-start)*1000),'result':v['data']});print(json.dumps(checks[-1],ensure_ascii=False),flush=True);return v['data']
        o=call({'op':'ocr','image':str(root/'ocr.png'),'roi':[0,0,1280,720]});assert '수학' in o['text'] and o['confidence']>.7,o
        sample='문제에서 주어진 조건을 먼저 찾아볼까?';call({'op':'tts','backend':'espeak','text':sample,'wav':str(root/'tts.wav'),'pcm':str(root/'tts.s16')})
        call({'op':'prepare_wav','wav':str(root/'tts.wav'),'pcm':str(root/'decoded.s16')})
        if not a.skip_asr:
            r=call({'op':'asr','wav':str(root/'tts.wav')});checks[-1]['expected_synthetic_text']=sample;checks[-1]['exact_transcript_match']=r['text'].replace(' ','')==sample.replace(' ','').replace('?','')
    result={'component_execution_pass':True,'synthetic_input':True,'human_speech_accuracy_verified':False,'cloud_calls':0,'raw_audio_saved':False,'checks':checks}
    Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
