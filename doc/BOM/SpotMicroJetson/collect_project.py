"""Archive public project references without executing upstream robot code."""
from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
import requests, json, re, hashlib, zipfile

ROOT=Path(__file__).resolve().parent
SHA='2235c77a93e86d04dec2e03c6306ba2c06d454ce'
PLAYLIST='https://www.youtube.com/playlist?list=PLK2UKp8KOXe1ZRbSmcO3VvE_TNs66K6lA'
SOURCES=[
 ('road_readme','web/RoadBalance_GitHub.html','https://github.com/Road-Balance/SpotMicroJetson','SpotMicro'),
 ('upstream_docs','web/SpotMicroAI_home.html','https://spotmicroai.readthedocs.io/en/latest/','SpotMicro'),
 ('credits','web/SpotMicroAI_credits.html','https://spotmicroai.readthedocs.io/en/latest/credits/','CLS6336HV'),
 ('assembly','web/SpotMicroAI_assembly.html','https://spotmicroai.readthedocs.io/en/latest/assembly/','SpotMicro'),
 ('korean_build','web/Ductility_20210112_build.html','https://ductility.github.io/2021/01/12/Spot_Micro.html','Spot Micro'),
 ('nvidia_context','web/NVIDIA_meetup.html','https://blogs.nvidia.co.kr/blog/nvidia-jetson-developer-meetup/','SpotMicro'),
 ('original_parts','web/Thingiverse_3445283.html','https://www.thingiverse.com/thing:3445283','Spotmicro'),
 ('updated_parts','web/Thingiverse_3761340.html','https://www.thingiverse.com/thing:3761340','Spot'),
 ('notion_notes','web/Notion_GCamp.html','https://www.notion.so/SpotMicro-for-G-Camp-c541934a4bad4ad48d1e37ab94c10de8','SpotMicro'),
 ('youtube_playlist','web/YouTube_playlist.html',PLAYLIST,'ytInitialData'),
]

def digest(data): return hashlib.sha256(data).hexdigest()

def fetch(item):
    sid,path,url,marker=item
    result=dict(id=sid,url=url,file=path,retrieved_at_utc=datetime.now(timezone.utc).isoformat())
    try:
        r=requests.get(url,timeout=30,headers={'User-Agent':'Mozilla/5.0'})
        result.update(http_status=r.status_code,final_url=r.url)
        r.raise_for_status()
        if marker.lower() not in r.text.lower(): raise ValueError('Expected text missing')
        if sid=='notion_notes' and ('Page not found' in r.text or 'This page could not be found' in r.text):
            raise ValueError('Notion page unavailable')
        path=ROOT/path; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(r.content)
        result.update(status='saved',bytes=len(r.content),sha256=digest(r.content))
        if sid=='youtube_playlist':
            match=re.search(r'(?:var )?ytInitialData\s*=\s*',r.text)
            if not match: raise ValueError('No playlist metadata')
            data=json.JSONDecoder().raw_decode(r.text[match.end():])[0]
            stack=[data]; videos=[]
            while stack:
                obj=stack.pop()
                if isinstance(obj,dict):
                    if 'playlistVideoRenderer' in obj:
                        v=obj['playlistVideoRenderer']
                        title=''.join(t.get('text','') for t in v.get('title',{}).get('runs',[]))
                        idx=v.get('index',{}).get('simpleText','')
                        videos.append(dict(index=idx,title=title,id=v.get('videoId'),url='https://www.youtube.com/watch?v='+v.get('videoId','')))
                    stack.extend(obj.values())
                elif isinstance(obj,list): stack.extend(obj)
            videos.sort(key=lambda v:int(v['index']) if v['index'].isdigit() else 999)
            if videos:
                (ROOT/'youtube_videos.json').write_text(json.dumps(videos,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            else:
                result['note']='HTML shell saved; video list requires browser DOM verification; existing verified list preserved'
            result['videos_listed']=len(videos)
    except Exception as e: result.update(status='failed',error=str(e))
    return result

if __name__=='__main__':
    with ThreadPoolExecutor(max_workers=5) as pool: results=list(pool.map(fetch,SOURCES))
    (ROOT/'web_sources.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for r in results: print(r['id'],r['status'],r.get('videos_listed',''),r.get('error',''))
