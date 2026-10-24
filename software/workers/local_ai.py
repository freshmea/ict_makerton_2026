#!/usr/bin/env python3
"""Isolated ML adapter. One bounded JSON request/result; Rust owns devices and policy."""
import audioop
import csv
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import wave

# Nano's preinstalled NumPy/OpenBLAS can select unsupported instructions on
# import. Pin its generic ARMv8 path before NumPy/OpenCV is loaded; this also
# applies when the worker is launched by systemd rather than a login shell.
os.environ['OPENBLAS_CORETYPE'] = 'ARMV8'

def run(q):
    mode = q['op']
    if mode == 'asr':
        from vosk import Model, KaldiRecognizer, SetLogLevel
        SetLogLevel(-1)
        with wave.open(q['wav'], 'rb') as f:
            if f.getnchannels() != 1 or f.getsampwidth() != 2 or f.getnframes() > f.getframerate()*15:
                raise ValueError('ASR requires bounded mono S16 wave')
            pcm = f.readframes(f.getnframes())
            pcm = audioop.ratecv(pcm, 2, 1, f.getframerate(), 16000, None)[0]
        rec = KaldiRecognizer(Model(os.environ.get('NANO_VOSK_MODEL', '/opt/300seconds/models/vosk-model-small-ko-0.22')), 16000)
        rec.SetWords(True)
        results = []
        for offset in range(0, len(pcm), 8000):
            if rec.AcceptWaveform(pcm[offset:offset+8000]):
                results.append(json.loads(rec.Result()))
        results.append(json.loads(rec.FinalResult()))
        words = [w for r in results for w in r.get('result', [])]
        text = ' '.join(r.get('text', '') for r in results).strip()
        return {'text':text, 'confidence':sum(w['conf'] for w in words)/len(words) if words else 0,
                'backend':'vosk-small-ko-0.22-cpu', 'language':'ko', 'empty':not bool(text)}
    if mode in ('tts','prepare_wav'):
        text = q.get('text','')
        if mode=='tts' and (not text.strip() or len(text) > 240):
            raise ValueError('TTS text limit')
        backend='typecast' if mode=='prepare_wav' else q.get('backend',os.environ.get('NANO_TTS_BACKEND','supertonic'))
        if mode=='prepare_wav':
            pass # Validated WAV is converted locally; no credential or network.
        elif backend == 'supertonic':
            import sherpa_onnx
            import numpy as np
            r=Path(os.environ.get('NANO_SUPERTONIC_MODEL','/opt/300seconds/models/sherpa-onnx-supertonic-3-tts-int8-2026-05-11'))
            tts=sherpa_onnx.OfflineTts(sherpa_onnx.OfflineTtsConfig(model=sherpa_onnx.OfflineTtsModelConfig(
                supertonic=sherpa_onnx.OfflineTtsSupertonicModelConfig(
                    duration_predictor=str(r/'duration_predictor.int8.onnx'),text_encoder=str(r/'text_encoder.int8.onnx'),
                    vector_estimator=str(r/'vector_estimator.int8.onnx'),vocoder=str(r/'vocoder.int8.onnx'),
                    tts_json=str(r/'tts.json'),unicode_indexer=str(r/'unicode_indexer.bin'),voice_style=str(r/'voice.bin')),
                num_threads=2,provider='cpu',debug=False)))
            config=sherpa_onnx.GenerationConfig();config.sid=0;config.num_steps=4;config.speed=1.0;config.extra={'lang':'ko'}
            audio=tts.generate(text,config)
            if len(audio.samples)>audio.sample_rate*30:raise ValueError('neural TTS duration limit')
            pcm=(np.clip(audio.samples,-1,1)*32767).astype('<i2').tobytes()
            with wave.open(q['wav'],'wb') as f:
                f.setnchannels(1);f.setsampwidth(2);f.setframerate(audio.sample_rate);f.writeframes(pcm)
        elif backend == 'espeak':
            # Explicit diagnostic fallback only; human Korean quality failed.
            p = subprocess.run(['espeak-ng','-v','ko','-s','155','--stdin','-w',q['wav']],
                               input=text.encode('utf8'),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=12)
            if p.returncode:raise ValueError('Korean TTS failed')
        else:raise ValueError('unsupported TTS backend')
        with wave.open(q['wav'],'rb') as f:
            if f.getnchannels()!=1 or f.getsampwidth()!=2 or f.getnframes()>f.getframerate()*30:
                raise ValueError('TTS format/duration invalid')
            pcm=audioop.ratecv(f.readframes(f.getnframes()),2,1,f.getframerate(),48000,None)[0]
        Path(q['pcm']).write_bytes(pcm)
        return {'backend':backend+'-ko-cpu','rate':48000,'samples':len(pcm)//2,'disclosure':'합성 음성'}
    if mode == 'ocr':
        import cv2
        cv2.setNumThreads(1)
        image=cv2.imread(q['image'])
        if image is None:
            raise ValueError('invalid problem snapshot')
        x,y,w,h=map(int,q['roi'])
        if min(x,y)<0 or min(w,h)<32 or x+w>image.shape[1] or y+h>image.shape[0]:
            raise ValueError('ROI outside snapshot')
        crop=image[y:y+h,x:x+w]
        rotation=int(q.get('rotation',0))
        if rotation not in (0,90,180,270):
            raise ValueError('rotation must be 0,90,180,270')
        if rotation:
            import numpy as np
            crop=np.rot90(crop,rotation//90).copy()
        gray=cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY)
        blur=float(cv2.Laplacian(gray,cv2.CV_64F).var())
        mean=float(gray.mean())
        contrast=float(gray.std())
        # A white page with dark text has a high mean; reject flat exposure, not paper.
        if blur<12 or mean<10 or contrast<8:
            return {'text':'','confidence':0,'confirmed':False,'needs_confirmation':True,'quality':{'laplacian':blur,'luma':mean,'contrast':contrast},'reason':'blur_or_exposure'}
        scale=min(2.0,max(1.0,1280/gray.shape[1]))
        if scale>1:gray=cv2.resize(gray,None,fx=scale,fy=scale,interpolation=cv2.INTER_LINEAR)
        image_bytes=cv2.imencode('.png',gray)[1].tobytes()
        p=subprocess.run(['tesseract','stdin','stdout','-l','kor+eng','--psm','6','tsv'],input=image_bytes,
                         stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=12,env=dict(os.environ,OMP_THREAD_LIMIT='1'))
        if p.returncode:
            raise ValueError('OCR engine failed')
        rows=list(csv.DictReader(io.StringIO(p.stdout.decode('utf8')),delimiter='\t'))
        words=[r for r in rows if r.get('text','').strip() and float(r['conf'])>=0]
        conf=sum(float(r['conf'])*len(r['text']) for r in words)/max(1,sum(len(r['text']) for r in words))/100
        return {'text':' '.join(r['text'] for r in words)[:2048], 'confidence':conf,
                'confirmed':False,'needs_confirmation':True,'backend':'tesseract-kor-eng-cpu',
                'quality':{'laplacian':blur,'luma':mean},'roi':[x,y,w,h],'rotation':rotation}
    raise ValueError('unknown adapter operation')

if __name__ == '__main__':
    try:
        line=sys.stdin.buffer.readline(65537)
        if len(line)>65536: raise ValueError('request too large')
        print(json.dumps({'ok':True,'data':run(json.loads(line))},ensure_ascii=False),flush=True)
    except Exception as exc:
        print(json.dumps({'ok':False,'error':str(exc)[:300]},ensure_ascii=False),flush=True)
        sys.exit(1)
