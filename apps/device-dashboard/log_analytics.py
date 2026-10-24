"""KST rollups and explainable reports. Demo aggregates never enter the real DB."""
import asyncio
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import json
import math
import random
import threading
import time

KST = timezone(timedelta(hours=9))
VERSION = 'learning-log-v1-keyword'
PRESENCE = [('present','재석'),('away','자리비움'),('unknown','판단 불가'),('missing','미수집·누락')]
EMOTIONS = [('positive','긍정·활력 단서'),('calm','차분·안정 단서'),('strained','긴장·어려움 단서'),
            ('tired','피로·휴식 단서'),('mixed','복합 단서'),('unknown','감정 단서 없음')]
STUDY = {'reading','writing','typing'}
PERSON_ACTIONS = STUDY | {'phone_use','looking_away','eating_drinking','handling_objects','person_present'}
EMOTION_WORDS = {
    'positive':('미소','웃음','웃고','웃는','즐거','기쁜','기뻐','신나','긍정','행복','의욕'),
    'calm':('차분','편안','안정된','평온','침착'),
    'strained':('짜증','화난','불안','긴장','답답','좌절','초조','당황','울음','눈물','찡그'),
    'tired':('하품','졸림','졸린','졸려','피곤','지친','피로','눈 비비','눈을 비비','꾸벅','휴식')}


def month_add(value, amount):
    year, month = divmod(value.year*12+value.month-1+amount,12)
    return value.replace(year=year,month=month+1,day=1,hour=0,minute=0,second=0,microsecond=0)


def bounds(period, day, hour=0):
    start = datetime.strptime(day,'%Y-%m-%d').replace(tzinfo=KST)
    if period == 'hour':
        start = start.replace(hour=hour); end = start+timedelta(hours=1); previous = start-timedelta(hours=1)
    elif period == 'day':
        end = start+timedelta(days=1); previous = start-timedelta(days=1)
    elif period == 'month':
        start = start.replace(day=1); end = month_add(start,1); previous = month_add(start,-1)
    else:raise ValueError('invalid_period')
    return start.timestamp(),end.timestamp(),previous.timestamp()


def stamp(value):return datetime.fromtimestamp(value,KST).isoformat()
def day_text(value):return datetime.fromtimestamp(value,KST).strftime('%Y-%m-%d')
def ratio(n,d):return round(n/d*100,1) if d else None


def blank(expected=0):
    return {'expected':expected,'observed':0,'present':0,'away':0,'unknown':0,'study':0,'other':0,
            'emotions':{k:0 for k,_ in EMOTIONS},'keywords':{},'raw_rows':0,'duplicates':0}


def combine(parts):
    total=blank();words=Counter()
    for item in parts:
        for key in ('expected','observed','present','away','unknown','study','other','raw_rows','duplicates'):
            total[key]+=item.get(key,0)
        for key in total['emotions']:total['emotions'][key]+=item['emotions'].get(key,0)
        words.update(item.get('keywords',{}))
    total['keywords']=dict(words.most_common(12))
    return total


def emotion_cue(rows):
    """Only explicit textual cues. No facial/emotional classifier or neutral-by-default guess."""
    groups=set()
    for row in rows:
        phrases=list(row.get('keywords',[]))+[row.get('description','')]
        for phrase in phrases:
            text=' '.join(str(phrase).casefold().split())
            for group,words in EMOTION_WORDS.items():
                for word in words:
                    at=text.find(word)
                    if at<0:continue
                    tail=text[at+len(word):at+len(word)+14].replace(' ','')
                    if any(term in tail[:10] for term in ('없','않','아니','보이지','불명','판단불가')):continue
                    groups.add(group)
    return next(iter(groups)) if len(groups)==1 else 'mixed' if groups else 'unknown'


def aggregate_rows(rows,start,end):
    expected=max(0,math.ceil((end-start)/10));result=blank(expected)
    batches=defaultdict(list);slots=defaultdict(dict)
    for row in rows:batches[row['batch_id']].append(row)
    for batch in batches.values():
        captured=max(r['captured'] for r in batch)
        if not start<=captured<end:continue
        slot=int((captured-start)//10)
        for original in batch:
            row=dict(original)
            for name in ('keywords','actions'):
                row[name]=json.loads(row.get(name+'_json') or '[]')
            old=slots[slot].get(row['camera'])
            if old is None or (row['captured'],row['id'])>(old['captured'],old['id']):slots[slot][row['camera']]=row
    words=Counter()
    for cameras in slots.values():
        result['raw_rows']+=len(cameras)
        result['duplicates']+=sum(r['status']=='duplicate' for r in cameras.values())
        successful=[r for r in cameras.values() if r['status'] in ('success','duplicate')]
        if not successful:continue
        result['observed']+=1
        usable=[r for r in successful if r.get('confidence') is not None and r['confidence']>=.5 and r['actions']]
        if not usable:
            result['unknown']+=1
            continue
        actions={a for r in usable for a in r['actions']}
        if actions & PERSON_ACTIONS:
            result['present']+=1
            if actions & STUDY:result['study']+=1
            else:result['other']+=1
            result['emotions'][emotion_cue(usable)]+=1
        elif 'seat_empty' in actions:result['away']+=1
        else:result['unknown']+=1
        words.update({str(k)[:60] for r in usable for k in r['keywords'][:8]})
    result['keywords']=dict(words.most_common(12))
    return result


def metrics(stats):
    known=stats['present']-stats['emotions']['unknown']
    return {'expected_samples':stats['expected'],'observed_samples':stats['observed'],
        'present_samples':stats['present'],'study_samples':stats['study'],
        'study_ratio':ratio(stats['study'],stats['present']),
        'away_ratio':ratio(stats['away'],stats['observed']),
        'coverage':ratio(stats['observed'],stats['expected']),
        'positive_calm_ratio':ratio(stats['emotions']['positive']+stats['emotions']['calm'],known),
        'emotion_cue_coverage':ratio(known,stats['present']),
        'presence':[{'id':k,'label':label,'count':stats.get(k,stats['expected']-stats['observed']) if k!='missing' else stats['expected']-stats['observed'],
                     'ratio':ratio(stats.get(k,0) if k!='missing' else stats['expected']-stats['observed'],stats['expected'])} for k,label in PRESENCE],
        'emotions':[{'id':k,'label':label,'count':stats['emotions'][k],
                     'ratio':ratio(stats['emotions'][k],stats['present'])} for k,label in EMOTIONS],
        'keywords':[{'word':k,'count':v} for k,v in stats['keywords'].items()],
        'raw_camera_rows':stats['raw_rows'],'duplicate_camera_rows':stats['duplicates']}


def delta(current,previous,key):
    a,b=current.get(key),previous.get(key)
    return round(a-b,1) if a is not None and b is not None else None


def narrative(current,previous,period):
    change=delta(current,previous,'study_ratio')
    minimum=12 if period=='hour' else 60
    enough=current['present_samples']>=minimum
    if not enough or previous['present_samples']<minimum:change=None
    if not current['observed_samples']:
        return {'assessment':'empty','headline':'아직 이 구간의 관찰이 없습니다.','paragraphs':[
            '수집된 기록이 생기면 자리 상태와 보이는 학습 행동을 함께 정리합니다.',
            '자료가 없는 구간은 자리비움이나 낮은 학습 상태로 평가하지 않습니다.'],'highlights':['데이터 수집 후 자동으로 총평을 작성합니다.']}
    pct=current['study_ratio']
    first=(f"재석 표본 중 {pct:.1f}%에서 읽기·필기·키보드 입력 같은 학습 행동이 보였습니다." if pct is not None else
           '학습 행동 비율을 계산할 재석 표본이 아직 없습니다.')
    if not enough:headline='조금 더 기록을 모아 흐름을 살펴봐요.';assessment='insufficient'
    elif change is None:headline='이 기간의 학습 흐름을 기록했어요.';assessment='baseline'
    elif change>=3:headline='학습 행동이 더 자주 관찰됐어요.';assessment='increasing'
    elif change<=-3:headline='이전 구간과 다른 흐름이 보였어요.';assessment='decreasing'
    else:headline='이전 구간과 비슷한 흐름을 이어갔어요.';assessment='steady'
    second=(f"이전 비교 구간보다 학습 행동 비율이 {abs(change):.1f}%p {'높았습니다' if change>=0 else '낮았습니다'}." if change is not None else
            '비교에 필요한 재석 표본이 부족해 증감 평가는 보류합니다.')
    highlights=[f"자리비움은 관찰된 표본의 {current['away_ratio']:.1f}%입니다." if current['away_ratio'] is not None else '자리 상태 근거가 부족합니다.']
    if current['positive_calm_ratio'] is not None:
        highlights.append(f"감정 단서가 있는 표본 중 긍정·차분 단서는 {current['positive_calm_ratio']:.1f}%입니다.")
    else:highlights.append('감정 관련 단어가 없어 감정 단서 평가는 보류합니다.')
    highlights.append(f"선택 기간의 데이터 커버리지는 {current['coverage'] or 0:.1f}%입니다. 미수집·판단 불가도 함께 확인해 주세요.")
    if current['keywords']:highlights.append('자주 보인 키워드: '+', '.join(w['word'] for w in current['keywords'][:3]))
    return {'assessment':assessment,'headline':headline,'paragraphs':[first,second],
            'highlights':highlights,'caution':'10초 표본에 보인 행동·문구의 분석이며 내적 집중력이나 실제 감정을 측정한 값은 아닙니다.'}


@lru_cache(maxsize=1)
def demo_hours(today):
    end=datetime.strptime(today,'%Y-%m-%d').replace(tzinfo=KST)+timedelta(days=1)
    current=month_add(end-timedelta(days=1),-11);hours={}
    while current<end:
        rng=random.Random('study-demo-'+current.isoformat())
        h=current.hour;weekend=current.weekday()>=5
        active=(9<=h<12 or 14<=h<18 or 19<=h<21) if not weekend else (10<=h<12 or 15<=h<18)
        rate=0 if h<7 or h>=23 else (.87 if active else .14 if 8<=h<23 else .02)+rng.uniform(-.035,.035)
        stats=blank(360);stats['observed']=360-rng.randint(2,15)
        stats['present']=max(0,min(stats['observed'],round(stats['observed']*rate)))
        stats['unknown']=rng.randint(0,4)
        stats['away']=stats['observed']-stats['present']-stats['unknown']
        if stats['away']<0:stats['unknown']+=stats['away'];stats['away']=0
        progress=min(.18,max(0,((current.year-2025)*12+current.month-10)*.013))
        learning=.59+progress+(.05 if 9<=h<12 else -.08 if h>=20 else 0)+rng.uniform(-.09,.09)
        if current.day%9==0:learning-=.12
        stats['study']=round(stats['present']*max(.1,min(.94,learning)))
        stats['other']=stats['present']-stats['study']
        n=stats['present'];remaining=n
        shares=[('positive',.21+progress*.3),('calm',.36+progress*.1),
                ('strained',.13-progress*.15),('tired',.14 if h>=18 else .08),('mixed',.045)]
        for key,share in shares:
            count=min(remaining,max(0,round(n*(share+rng.uniform(-.025,.025)))))
            stats['emotions'][key]=count;remaining-=count
        stats['emotions']['unknown']=remaining
        stats['keywords']={'책':stats['study']//2,'필기':stats['study']//3,'문제 풀이':stats['study']//4,
                           '휴식':stats['other']//2,'음료':stats['other']//4}
        stats['raw_rows']=stats['observed']*2;stats['duplicates']=round(stats['raw_rows']*.41)
        hours[int(current.timestamp())]=stats
        current+=timedelta(hours=1)
    return hours


class Analytics:
    def __init__(self,store):
        self.store=store;self.lock=threading.RLock();self.closing=False;self.task=None
        with store.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS analytics_hours(
                start INTEGER PRIMARY KEY,version TEXT NOT NULL,stats_json TEXT NOT NULL,finalized INTEGER NOT NULL,computed REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS analytics_reports(
                period TEXT NOT NULL,start INTEGER NOT NULL,version TEXT NOT NULL,report_json TEXT NOT NULL,computed REAL NOT NULL,
                PRIMARY KEY(period,start));''')

    def _rows(self,start,end):
        with self.store.connect() as db:
            return [dict(r) for r in db.execute('''SELECT o.id,o.batch_id,o.camera,o.captured,o.status,
                COALESCE(o.description,d.description) AS description,
                COALESCE(o.keywords_json,d.keywords_json) AS keywords_json,
                COALESCE(o.actions_json,d.actions_json) AS actions_json,
                COALESCE(o.confidence,d.confidence) AS confidence
                FROM observations o LEFT JOIN observations d ON d.id=o.duplicate_of
                WHERE o.captured>=? AND o.captured<? ORDER BY o.captured,o.id''',(start-2,end+2))]

    def refresh(self,now=None):
        now=time.time() if now is None else now
        with self.lock:
            with self.store.connect() as db:
                first=db.execute('SELECT captured FROM observations ORDER BY captured LIMIT 1').fetchone()
                cached={r['start']:r for r in db.execute('SELECT start,version,finalized FROM analytics_hours')}
            if not first:return
            start=int(first[0]//3600)*3600;changed=[]
            while start<now and not self.closing:
                old=cached.get(start)
                if not old or old['version']!=VERSION or not old['finalized']:
                    end=min(start+3600,now)
                    stats=aggregate_rows(self._rows(start,end),start,end)
                    with self.store.connect() as db:
                        db.execute('INSERT OR REPLACE INTO analytics_hours VALUES (?,?,?,?,?)',
                            (start,VERSION,json.dumps(stats,ensure_ascii=False),int(start+3720<=now),now))
                    changed.append(start)
                start+=3600
            if changed:
                hours=self._cached_hours(month_add(datetime.fromtimestamp(min(changed),KST),-1).timestamp(),now)
                periods={(kind,bounds(kind,day_text(at),datetime.fromtimestamp(at,KST).hour)[0])
                         for at in changed for kind in ('hour','day','month')}
                for kind,at in periods:
                    report=self._report(hours,kind,day_text(at),datetime.fromtimestamp(at,KST).hour,now,real=True)
                    self._save_report(kind,at,report,now)

    def _cached_hours(self,start,end):
        with self.store.connect() as db:
            return {r['start']:json.loads(r['stats_json']) for r in db.execute(
                'SELECT start,stats_json FROM analytics_hours WHERE start>=? AND start<? AND version=?',(int(start//3600)*3600,end,VERSION))}

    @staticmethod
    def _sum(hours,start,end):
        if end<=start:return blank()
        parts=[];at=int(start//3600)*3600
        while at<end:
            span=max(0,min(at+3600,end)-max(at,start));expected=math.ceil(span/10)
            item=hours.get(at)
            if item is None:parts.append(blank(expected))
            elif start<=at and at+3600<=end:parts.append(item)
            else:
                # Stored partial current-hour aggregates end at the same live boundary.
                # Aligned report windows use whole hours; elapsed comparisons may clip a prior hour.
                factor=min(1,expected/max(1,item['expected']));piece=blank(expected)
                for key in ('observed','present','away','unknown','study','other','raw_rows','duplicates'):
                    piece[key]=round(item[key]*factor)
                piece['emotions']={k:round(v*factor) for k,v in item['emotions'].items()}
                # Keep rounding identities exact for percentages.
                piece['unknown']=max(0,piece['observed']-piece['present']-piece['away'])
                piece['other']=max(0,piece['present']-piece['study'])
                remainder=piece['present']-sum(piece['emotions'].values())
                piece['emotions']['unknown']+=remainder
                piece['keywords']={k:round(v*factor) for k,v in item['keywords'].items()}
                parts.append(piece)
            at+=3600
        return combine(parts)

    def _range(self,hours,start,end,real=False):
        if real and end>start and end%3600:
            boundary=max(start,int(end//3600)*3600)
            return combine([self._sum(hours,start,boundary),aggregate_rows(self._rows(boundary,end),boundary,end)])
        return self._sum(hours,start,end)

    def _report(self,hours,period,day,hour,now,real=False):
        start,end,previous=bounds(period,day,hour)
        until=max(start,min(end,now));partial=until<end
        previous_end=min(start,previous+(until-start)) if partial else start
        current=metrics(self._range(hours,start,until,real));old=metrics(self._range(hours,previous,previous_end,real))
        minimum=12 if period=='hour' else 60
        study_ready=min(current['present_samples'],old['present_samples'])>=minimum
        away_ready=min(current['observed_samples'],old['observed_samples'])>=minimum
        emotion_ready=min(current['present_samples']*(current['emotion_cue_coverage'] or 0)/100,
                          old['present_samples']*(old['emotion_cue_coverage'] or 0)/100)>=12
        return {'period':period,'start':stamp(start),'end':stamp(end),'through':stamp(until),
            'partial':partial,'metrics':current,'previous':old,
            'comparison':{'start':stamp(previous),'through':stamp(previous_end),
                'label':'이전 기간의 같은 경과 구간' if partial else '이전 전체 기간',
                'estimated_partial_hour':False,
                'study_delta_pp':delta(current,old,'study_ratio') if study_ready else None,
                'away_delta_pp':delta(current,old,'away_ratio') if away_ready else None,
                'emotion_delta_pp':delta(current,old,'positive_calm_ratio') if emotion_ready else None},
            'summary':narrative(current,old,period)}

    def _save_report(self,period,start,report,now):
        with self.store.connect() as db:
            db.execute('INSERT OR REPLACE INTO analytics_reports VALUES (?,?,?,?,?)',
                       (period,start,VERSION,json.dumps(report,ensure_ascii=False),now))

    def view(self,source='demo',period='day',day=None,hour=9,now=None):
        now=time.time() if now is None else now;today=day_text(now)
        day=day or today
        chosen=datetime.strptime(day,'%Y-%m-%d').replace(tzinfo=KST)
        if chosen.date()>datetime.fromtimestamp(now,KST).date() or chosen.year<2000:raise ValueError('date_out_of_range')
        if source=='demo':
            hours=demo_hours(today);clock=(datetime.strptime(today,'%Y-%m-%d').replace(tzinfo=KST)+timedelta(days=1)).timestamp()
        elif source=='real':
            self.refresh(now);clock=now
            hours=self._cached_hours(month_add(chosen,-12).timestamp(),min(now,month_add(chosen,1).timestamp()))
        else:raise ValueError('invalid_source')
        report=self._report(hours,period,day,hour,clock,real=source=='real')
        start,end,_=bounds(period,day,hour)
        series=[]
        step=3600 if period in ('hour','day') else 86400
        at=start-5*3600 if period=='hour' else start
        while at<end:
            stop=min(at+step,end,clock)
            stat=self._range(hours,at,max(at,stop),real=source=='real')
            value=metrics(stat)
            label=datetime.fromtimestamp(at,KST).strftime('%H:%M' if period!='month' else '%m/%d')
            series.append({'label':label,'at':stamp(at),'study_ratio':value['study_ratio'],
                           'away_ratio':value['away_ratio'],'coverage':value['coverage']})
            at+=step
        def history(kind,count):
            rows=[]
            for back in reversed(range(count)):
                date=chosen-timedelta(days=back) if kind=='day' else month_add(chosen,-back)
                r=self._report(hours,kind,date.strftime('%Y-%m-%d'),0,clock,real=source=='real')
                rows.append({'date':date.strftime('%Y-%m-%d'),'label':date.strftime('%m/%d' if kind=='day' else '%Y.%m'),
                    'study_ratio':r['metrics']['study_ratio'],'away_ratio':r['metrics']['away_ratio'],
                    'positive_calm_ratio':r['metrics']['positive_calm_ratio'],'coverage':r['metrics']['coverage'],
                    'delta_pp':r['comparison']['study_delta_pp'],'headline':r['summary']['headline'],
                    'summary':' '.join(r['summary']['paragraphs'])})
            return rows
        hourly=[]
        for h in range(24):
            r=self._report(hours,'hour',day,h,clock,real=source=='real')
            hourly.append({'hour':h,'label':'%02d:00'%h,'study_ratio':r['metrics']['study_ratio'],
                'away_ratio':r['metrics']['away_ratio'],'coverage':r['metrics']['coverage'],
                'summary':' '.join(r['summary']['paragraphs'])})
        if source=='real':self._save_report(period,start,report,now)
        recorded_days=len({day_text(k) for k,v in hours.items() if v['observed']})
        return {'source':source,'demo':source=='demo','version':VERSION,'timezone':'Asia/Seoul',
            'today':today,'generated_at':stamp(now),'available_days':recorded_days,
            'report':report,'series':series,'daily':history('day',14),'monthly':history('month',12),'hourly':hourly,
            'definitions':{'sample_seconds':10,'study':'재석 10초 표본 중 읽기·필기·키보드 입력이 보인 비율',
                'presence':'선택 기간의 10초 구간 비율. 두 카메라는 하나의 구간으로 합칩니다.',
                'emotion':'재석 표본의 관찰 문구·키워드 추정. 사람의 실제 감정을 확정하지 않습니다.',
                'coverage':'선택 기간 중 관찰 결과가 남아 있는 구간의 비율',
                'comparison':'진행 중인 기간은 이전 기간의 같은 경과 구간과 비교합니다. 실제 부분 시간도 원표본으로 계산합니다.'}}

    def start(self):self.task=asyncio.create_task(self.maintain())

    async def maintain(self):
        while not self.closing:
            try:await asyncio.get_running_loop().run_in_executor(None,self.refresh)
            except Exception:pass
            await asyncio.sleep(60)

    async def close(self):
        self.closing=True
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task,return_exceptions=True)
