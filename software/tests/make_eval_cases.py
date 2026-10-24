#!/usr/bin/env python3
"""200 synthetic review candidates. Labels are authored expectations, not measured model accuracy."""
import json,random
from pathlib import Path
requests=['첫 단계 힌트 하나 줘','정답 말고 어디서 시작할지 도와줘','이 문장 뜻을 힌트로 알려줘','이 문제에서 조건을 찾도록 도와줘','어떤 식을 세워야 할지 힌트 줘']
waiting=['잠깐 기다려','혼자 생각할게','조용히 있어 줘','응 알겠어','아직 말하지 마']
ambiguous=['음 이거','저기 그거 있잖아','잘 모르겠는데','이게 뭐였지','어...']
ending=['오늘 공부는 끝낼래','이제 종료해 줘','그만 공부할래','공부 끝','마칠래']
def cases():
    result=[]
    for action,texts in [('offer_hint',requests),('wait',waiting),('clarify',ambiguous),('end_session',ending)]:
        for i in range(50):
            result.append({'id':f'{action}-{i:02d}','text':texts[i%5]+(['','!',' .',' 부탁해','\n'][i//5%5]),'expected':action,'help_requested':True,'vision':'unknown' if i%3 else 'occluded','split':['authoring','calibration','holdout'][i%3],'synthetic':True,'human_reviewed':False})
    random.Random(300).shuffle(result);return result
if __name__=='__main__':
    p=Path(__file__).with_name('decision-candidates.jsonl');p.write_text(''.join(json.dumps(c,ensure_ascii=False)+'\n' for c in cases()),encoding='utf8');print(p,len(cases()))
