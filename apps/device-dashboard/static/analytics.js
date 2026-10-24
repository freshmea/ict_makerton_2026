(() => {
  'use strict';
  const $=id=>document.getElementById(id);
  const params=new URLSearchParams(location.search);
  const today=()=>new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Seoul'}).format(new Date());
  const state={source:params.get('source')==='real'?'real':'demo',period:['hour','day','month'].includes(params.get('period'))?params.get('period'):'day',
    date:/^\d{4}-\d{2}-\d{2}$/.test(params.get('date')||'')?params.get('date'):today(),hour:Math.max(0,Math.min(23,Number(params.get('hour')||9))),history:'day',expanded:false};
  if(!Number.isFinite(state.hour))state.hour=9;
  let current,sequence=0,controller,timer;
  const colors={present:'#295b46',away:'#c1783c',unknown:'#a5ada0',missing:'#e5e9e0',positive:'#4e795a',calm:'#7b9a9b',strained:'#ac6553',tired:'#c9a45a',mixed:'#8b8191'};
  const percentage=value=>typeof value==='number'?value.toFixed(1)+'%':'—';
  const count=value=>Number(value||0).toLocaleString('ko-KR');
  const text=(id,value)=>{if($(id).textContent!==String(value))$(id).textContent=value;};
  const el=(tag,className,value)=>{const node=document.createElement(tag);if(className)node.className=className;if(value!==undefined)node.textContent=value;return node;};
  const svg=(tag,attributes={})=>{const node=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [key,value] of Object.entries(attributes))node.setAttribute(key,String(value));return node;};
  function svgText(parent,x,y,value,attrs={}){const n=svg('text',{x,y,...attrs});n.textContent=value;parent.append(n);return n;}
  function difference(value){return typeof value==='number'?(value>0?'+':'')+value.toFixed(1)+'%p':'비교 대기';}
  function shift(amount){
    const [year,month,day]=state.date.split('-').map(Number);
    if(state.period==='month'){
      // Temporal when available; offline Safari fallback uses the first calendar day.
      if(typeof Temporal!=='undefined')return {date:Temporal.PlainDate.from(state.date).with({day:1}).add({months:amount}).toString(),hour:state.hour};
      return {date:new Date(Date.UTC(year,month-1+amount,1)).toISOString().slice(0,10),hour:state.hour};
    }
    if(state.period==='day'&&typeof Temporal!=='undefined')return {date:Temporal.PlainDate.from(state.date).add({days:amount}).toString(),hour:state.hour};
    const value=new Date(Date.UTC(year,month-1,day,state.hour));
    if(state.period==='hour')value.setUTCHours(value.getUTCHours()+amount);else value.setUTCDate(value.getUTCDate()+amount);
    return {date:value.toISOString().slice(0,10),hour:value.getUTCHours()};
  }
  function controls(){
    for(const source of ['real','demo'])$('source-'+source).setAttribute('aria-pressed',String(state.source===source));
    document.querySelectorAll('[data-period]').forEach(n=>n.setAttribute('aria-pressed',String(n.dataset.period===state.period)));
    $('date').value=state.date;$('date').max=today();$('hour').value=String(state.hour);$('hour-control').hidden=state.period!=='hour';
    $('next').disabled=shift(1).date>today();
    $('history-day').setAttribute('aria-pressed',String(state.history==='day'));
    $('history-month').setAttribute('aria-pressed',String(state.history==='month'));
  }
  function changeNote(id,value,basis){text(id,`이전 대비 ${difference(value)} · ${basis}`);$(id).className=typeof value==='number'&&value!==0?(value>0?'up':'down'):'';}

  function lineChart(target,rows,title,includeEmotion=false){
    const width=720,height=260,left=43,right=19,top=24,bottom=42;
    const root=svg('svg',{viewBox:`0 0 ${width} ${height}`,role:'img','aria-label':title});
    const desc=svg('desc');desc.textContent='녹색은 재석 중 학습 행동, 황토색은 관측 중 자리비움 비율입니다. '+(includeEmotion?'청회색은 감정 단서가 있는 표본 중 긍정·차분 단서입니다. ':'')+'자료 없는 구간은 연결하지 않습니다.';root.append(desc);
    const x=i=>left+i*(width-left-right)/Math.max(1,rows.length-1), y=v=>height-bottom-v*(height-top-bottom)/100;
    for(const value of [0,25,50,75,100]){root.append(svg('line',{x1:left,y1:y(value),x2:width-right,y2:y(value),stroke:'#e7ebe1','stroke-dasharray':value?'3 5':'0'}));svgText(root,left-9,y(value)+4,String(value),{'text-anchor':'end'});}
    const series=[['study_ratio',colors.present],['away_ratio',colors.away]];
    if(includeEmotion)series.push(['positive_calm_ratio',colors.calm]);
    for(const [key,color] of series){
      let path='',connected=false;
      rows.forEach((r,i)=>{const value=r[key];if(typeof value!=='number'){connected=false;return;}path+=(connected?' L':' M')+x(i).toFixed(2)+' '+y(value).toFixed(2);connected=true;});
      if(path)root.append(svg('path',{d:path,fill:'none',stroke:color,'stroke-width':key==='study_ratio'?2.6:1.8,'stroke-linecap':'round',...(key==='away_ratio'?{'stroke-dasharray':'5 4'}:{})}));
    }
    rows.forEach((r,i)=>{
      if(i%Math.max(1,Math.ceil(rows.length/7))===0||i===rows.length-1)svgText(root,x(i),height-15,r.label,{'text-anchor':i===0?'start':i===rows.length-1?'end':'middle'});
      if(typeof r.study_ratio==='number'){
        const point=svg('circle',{cx:x(i),cy:y(r.study_ratio),r:3.5,fill:colors.present,tabindex:0,'aria-label':`${r.label} 학습 행동 ${percentage(r.study_ratio)}, 자리비움 ${percentage(r.away_ratio)}`});
        const tip=svg('title');tip.textContent=`${r.label} · 학습 행동 ${percentage(r.study_ratio)} · 자리비움 ${percentage(r.away_ratio)}${includeEmotion?' · 긍정·차분 단서 '+percentage(r.positive_calm_ratio):''} · 커버리지 ${percentage(r.coverage)}`;point.append(tip);root.append(point);
      }
    });
    if(!rows.some(r=>typeof r.study_ratio==='number'||typeof r.away_ratio==='number'))svgText(root,360,129,'표시할 관찰 자료가 없습니다.',{'text-anchor':'middle'});
    $(target).replaceChildren(root);
  }

  function smallTable(target,rows){
    const table=el('table'),head=el('thead'),tr=el('tr');
    for(const label of ['구간','학습 행동','자리비움','커버리지']){const th=el('th','',label);th.scope='col';tr.append(th);}head.append(tr);table.append(head);
    const body=el('tbody');for(const row of rows){const item=el('tr'),th=el('th','',row.label);th.scope='row';item.append(th);for(const key of ['study_ratio','away_ratio','coverage'])item.append(el('td','numeric',percentage(row[key])));body.append(item);}table.append(body);$(target).replaceChildren(table);
  }

  function presence(metrics){
    const total=metrics.observed_samples;
    const rows=metrics.presence.filter(r=>r.id!=='missing');
    const root=svg('svg',{viewBox:'0 0 180 180',role:'img','aria-label':'관측된 표본의 자리 상태 비율'});
    root.append(svg('circle',{cx:90,cy:90,r:64,fill:'none',stroke:'#edf0e8','stroke-width':17}));
    const circumference=2*Math.PI*64;let offset=0;
    for(const row of rows){const amount=total?row.count/total:0;const slice=svg('circle',{cx:90,cy:90,r:64,fill:'none',stroke:colors[row.id],'stroke-width':17,'stroke-dasharray':`${amount*circumference} ${circumference}`,'stroke-dashoffset':-offset*circumference,transform:'rotate(-90 90 90)'});const title=svg('title');title.textContent=`${row.label} ${percentage(total?amount*100:null)}`;slice.append(title);root.append(slice);offset+=amount;}
    svgText(root,90,86,percentage(total?metrics.present_samples/total*100:null),{'text-anchor':'middle',fill:'#295b46','font-size':27,'font-family':'Consolas,monospace'});
    svgText(root,90,109,'재석',{'text-anchor':'middle',fill:'#7a837b','font-size':11});
    $('presence-chart').replaceChildren(root);
    const legend=rows.map(row=>{const li=el('li'),dot=svg('svg',{width:8,height:8,'aria-hidden':'true'});dot.append(svg('circle',{cx:4,cy:4,r:4,fill:colors[row.id]}));li.append(dot,el('span','',row.label),el('strong','',percentage(total?row.count/total*100:null)));return li;});$('presence-legend').replaceChildren(...legend);
    const missing=metrics.presence.find(r=>r.id==='missing');text('presence-note',`관측된 표본 기준. 선택 기간의 미수집·누락 ${percentage(missing.ratio)}는 위 커버리지에 별도 표시합니다.`);
  }

  function emotions(metrics){
    const root=svg('svg',{viewBox:'0 0 600 32',role:'img','aria-label':'재석 표본의 감정 키워드 단서 분포'});let start=0;
    root.append(svg('rect',{x:0,y:0,width:600,height:32,fill:'#edf0e8'}));
    const legend=metrics.emotions.map(row=>{
      const width=(row.ratio||0)*6;
      root.append(svg('rect',{x:start,y:0,width,height:32,fill:colors[row.id]}));start+=width;
      const li=el('li'),label=el('span'),dot=svg('svg',{width:8,height:8,'aria-hidden':'true'});dot.append(svg('circle',{cx:4,cy:4,r:4,fill:colors[row.id]}));label.append(dot,document.createTextNode(row.label));li.append(label,el('strong','',percentage(row.ratio)),el('small','',`${count(row.count)} 표본`));return li;
    });
    $('emotion-chart').replaceChildren(root);$('emotion-legend').replaceChildren(...legend);
    text('cue-coverage',metrics.present_samples?`재석 표본 ${count(metrics.present_samples)}개 중 감정 단서가 있는 비율 ${percentage(metrics.emotion_cue_coverage)}. 단서가 없으면 감정 상태를 채워 넣지 않습니다.`:'감정 단서를 분류할 재석 표본이 아직 없습니다.');
  }

  function openReport(period,date,hour=state.hour){state.period=period;state.date=date;state.hour=hour;state.expanded=false;load().then(()=>window.scrollTo({top:0,behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'}));}
  function history(){
    if(!current)return;
    controls();const rows=state.history==='day'?current.daily:current.monthly;
    lineChart('history-chart',rows,state.history==='day'?'14일 학습 행동·자리비움·감정 단서 비교':'12개월 학습 행동·자리비움·감정 단서 비교',true);
    text('history-caption',state.history==='day'?'하루 총평과 전날 대비 변화 · 14일':'월 총평과 지난달 대비 변화 · 12개월');
    const nodes=rows.slice().reverse().map(row=>{
      const tr=el('tr'),th=el('th','',row.label);th.scope='row';tr.append(th,el('td','numeric',percentage(row.study_ratio)));
      tr.append(el('td','numeric '+(row.delta_pp>0?'positive':row.delta_pp<0?'negative':''),difference(row.delta_pp)),el('td','numeric',percentage(row.positive_calm_ratio)),el('td','numeric',percentage(row.coverage)),el('td','summary',row.summary));
      const td=el('td'),button=el('button','report-link','총평 보기 ↗');button.type='button';button.onclick=()=>openReport(state.history,row.date);td.append(button);tr.append(td);return tr;
    });$('history-rows').replaceChildren(...nodes);
  }

  function hourly(){
    if(!current)return;
    const visible=state.expanded?current.hourly:current.source==='demo'?current.hourly.slice(9,15):current.hourly.filter(r=>r.coverage>0).slice(-6);
    const nodes=visible.map(row=>{
      const item=el('article','hour-row');item.append(el('strong','',row.label));const content=el('div');content.append(el('p','',row.summary),el('small','',`학습 행동 ${percentage(row.study_ratio)} · 자리비움 ${percentage(row.away_ratio)} · 커버리지 ${percentage(row.coverage)}`));item.append(content);
      const button=el('button','','↗');button.type='button';button.setAttribute('aria-label',`${row.label} 시간 총평 보기`);button.onclick=()=>openReport('hour',state.date,row.hour);item.append(button);return item;
    });
    if(!nodes.length)nodes.push(el('p','section-copy','기록이 쌓이면 시간별 총평이 이곳에 표시됩니다.'));
    $('hourly-list').replaceChildren(...nodes);$('hourly-more').setAttribute('aria-expanded',String(state.expanded));text('hourly-more',state.expanded?'시간별 총평 접기 ↑':'하루 24시간 모두 보기 ↓');
  }

  function render(data){
    current=data;const report=data.report,m=report.metrics,comparison=report.comparison,demo=data.demo;
    document.querySelectorAll('.data-origin').forEach(n=>{n.textContent=demo?'DEMO':'실제 기록';n.classList.toggle('real',!demo);});
    text('source-pill',demo?'DEMO':'실제 기록');$('source-pill').classList.toggle('real',!demo);
    $('mode-notice').classList.toggle('real',!demo);$('mode-notice').replaceChildren(el('strong','',demo?'DEMO · 가상 기록':'REAL · 실제 관찰 기록'),el('span','',demo?`${data.available_days}일의 가상 기록으로 비교 기능을 체험합니다. 데모의 오늘은 24시간을 채운 예시이며 실제 데이터와 섞이지 않습니다.`:`이 분석 범위에서 ${data.available_days}일의 관찰을 확인했습니다. 기록이 없는 기간과 감정 단서가 없는 표본은 따로 표시합니다.`));
    const labels={hour:'시간',day:'하루',month:'한 달'};const title=state.period==='month'?state.date.slice(0,7).replace('-','년 ')+'월':state.date.replaceAll('-','.');
    text('range-title',`${title}${state.period==='hour'?' '+String(state.hour).padStart(2,'0')+':00':''} · ${labels[state.period]}의 기록`);
    text('range-meta',`${report.partial?'현재까지 · 부분 기간':'완료된 기간'} · KST · 10초 표본`);
    text('edition-month',state.date.slice(0,7).replace('-',' / '));text('edition-day',state.date.slice(-2));text('edition-meta',`${demo?'가상':'실제'} 기록 · ${count(m.observed_samples)} 관측 표본`);
    text('study-value',percentage(m.study_ratio));text('away-value',percentage(m.away_ratio));text('emotion-value',percentage(m.positive_calm_ratio));text('coverage-value',percentage(m.coverage));
    changeNote('study-change',comparison.study_delta_pp,'재석 표본 중');
    text('away-change',`이전 대비 ${difference(comparison.away_delta_pp)} · 미수집 제외`);
    text('emotion-change',m.positive_calm_ratio===null?'추정할 감정 단서가 없습니다.':`단서가 있는 표본 중 · 이전 대비 ${difference(comparison.emotion_delta_pp)}`);
    text('coverage-note',`${count(m.observed_samples)} / ${count(m.expected_samples)}개 구간 관측`);
    text('review-period',labels[state.period]+' 총평');text('review-status',report.partial?'진행 중 · 자동 갱신':'지표 기반 자동 작성');text('review-title',report.summary.headline);
    $('review-paragraphs').replaceChildren(...report.summary.paragraphs.map(p=>el('p','',p)));
    $('review-highlights').replaceChildren(...report.summary.highlights.map(p=>el('li','',p)));
    text('comparison-note',`${comparison.label}과 비교 · ${comparison.start.slice(0,16).replace('T',' ')} ~ ${comparison.through.slice(0,16).replace('T',' ')} KST`);
    text('flow-title',state.period==='hour'?'선택 시간과 앞선 다섯 시간':state.period==='day'?'하루 속 학습 흐름':'날짜별 학습 흐름');
    lineChart('flow-chart',data.series,'선택 기간의 학습 행동과 자리비움 비율');smallTable('flow-data',data.series);
    text('flow-note',`${state.period==='month'?'하루': '한 시간'} 단위 집계. 기록 없는 구간은 선으로 연결하지 않습니다. 학습 행동은 재석, 자리비움은 관측 표본 기준입니다.`);
    presence(m);emotions(m);history();hourly();
    text('generated-at',`생성 ${data.generated_at.slice(0,16).replace('T',' ')} KST · ${demo?'가상 데이터':'실제 기록'}`);
  }

  async function load(){
    clearTimeout(timer);const own=++sequence;if(controller)controller.abort();controller=new AbortController();const requestController=controller;
    const timeout=setTimeout(()=>requestController.abort(),30000);controls();$('report-body').setAttribute('aria-busy','true');text('load-state','기록을 집계하고 총평을 정리하고 있습니다.');$('load-state').classList.remove('error');
    const query=new URLSearchParams({source:state.source,period:state.period,date:state.date,hour:String(state.hour)});
    window.history.replaceState(null,'','/analytics?'+query);
    try{
      const response=await fetch('/api/analytics?'+query,{signal:requestController.signal,cache:'no-store'});const data=await response.json();
      if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'분석 자료를 불러오지 못했습니다.');
      if(own!==sequence)return;render(data);text('load-state',`${data.demo?'데모':'실제'} 분석을 불러왔습니다. 총평은 기록에 따라 자동 갱신됩니다.`);
    }catch(error){if(own!==sequence)return;text('load-state',error.name==='AbortError'?'분석 조회가 지연됩니다. 새로고침으로 다시 시도해 주세요.':error.message);$('load-state').classList.add('error');}
    finally{clearTimeout(timeout);if(own===sequence){$('report-body').setAttribute('aria-busy','false');if(state.source==='real'&&!document.hidden)timer=setTimeout(load,60000);}}
  }

  for(let h=0;h<24;h++){const option=el('option','',String(h).padStart(2,'0')+':00');option.value=String(h);$('hour').append(option);}
  for(const source of ['real','demo'])$('source-'+source).onclick=()=>{state.source=source;state.expanded=false;load();};
  document.querySelectorAll('[data-period]').forEach(n=>n.onclick=()=>{state.period=n.dataset.period;load();});
  $('date').onchange=()=>{if($('date').value){state.date=$('date').value;state.expanded=false;load();}};
  $('hour').onchange=()=>{state.hour=Number($('hour').value);load();};
  for(const [id,amount] of [['previous',-1],['next',1]])$(id).onclick=()=>{Object.assign(state,shift(amount));state.expanded=false;load();};
  $('today').onclick=()=>{state.date=today();load();};$('refresh').onclick=load;
  for(const kind of ['day','month'])$('history-'+kind).onclick=()=>{state.history=kind;history();};
  $('hourly-more').onclick=()=>{state.expanded=!state.expanded;hourly();};
  document.addEventListener('visibilitychange',()=>{clearTimeout(timer);if(!document.hidden&&state.source==='real')load();});
  load();
})();
