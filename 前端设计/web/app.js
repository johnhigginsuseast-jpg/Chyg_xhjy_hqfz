'use strict';
const $ = id => document.getElementById(id);
const dateFormat = new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false});
const shortFormat = new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',hour:'2-digit',minute:'2-digit',hour12:false});
const time = value => value == null ? '未记录' : dateFormat.format(new Date(value));
const short = value => shortFormat.format(new Date(value));
const number = value => value == null ? '—' : Number(value).toLocaleString('zh-CN',{maximumFractionDigits:2});
const percent = value => value == null ? '暂无可计分样本' : `${(value*100).toFixed(2)}%`;
const directions = {up:'↑ 上涨',down:'↓ 下跌',flat:'— 平盘'};
const resultNames = {HIT:'命中',MISS:'未命中',FLAT:'平盘',PENDING:'待结算',UNSCORABLE:'无法计分'};
const codes = {WARMUP:'暖机中',WARMUP_COMPLETE:'暖机完成',WAITING_NEW_COMPLETE_BAR:'等待新完整K线',NOMINAL_REST:'休市（常规时段）',STALE_SOURCE:'行情滞后',MISSING_SEQUENCE:'缺失分钟序列',FINALITY_UNKNOWN:'完整性尚未核实',SOURCE_OR_MODEL_BLOCKED:'数据 / 模型校验异常',STALE_OR_BACKFILL:'补回旧行情，不发新预测',LATE:'迟到，未计分',RULE_SKIP:'本锚点规则跳过',PREDICTED:'已发布预测',UNKNOWN:'未知'};
const label = code => codes[code] || (code?.startsWith('HTTP_') ? `行情获取异常 · ${code}` : `未知状态 · ${code || '未记录'}`);
const state = {data:null,lastSuccess:0,error:null,busy:false,queued:false,epoch:0,timer:null,before:[null],page:0,selected:null,returnFocus:null,viewEnd:null,hover:null,chartBars:[],newRecords:false,filters:{from:'',to:'',status:''}};
const put = (id,text) => {const el=$(id);const value=String(text ?? '—');if(el.textContent!==value)el.textContent=value;};

function validate(data) {
  const numeric = v => typeof v==='number' && Number.isFinite(v);
  if(!data?.snapshot || !numeric(data.snapshot.observed_at_ms) || !data.identity || !['LIVE','DEMO','REPLAY'].includes(data.identity.mode) || !data.status || !Array.isArray(data.records) || !Array.isArray(data.trend))throw Error('接口数据结构异常');
  for(const summary of data.statistics ? [data.statistics.cumulative,data.statistics.today] : []) {
    if(!summary || ['scored','HIT','MISS','FLAT','PENDING','UNSCORABLE'].some(k=>!Number.isInteger(summary[k])||summary[k]<0) || !(summary.hit_rate===null || numeric(summary.hit_rate)&&summary.hit_rate>=0&&summary.hit_rate<=1))throw Error('统计字段异常');
  }
  for(const p of [...data.records,data.current_prediction,data.last_prediction,data.detail].filter(Boolean)) {
    if(!/^[a-f0-9]{64}$/.test(p.id) || !numeric(p.p_up) || p.p_up<0 || p.p_up>1 || !directions[p.predicted_direction] || !resultNames[p.result?.status] || !numeric(p.anchor_ms) || !numeric(p.computed_at_ms))throw Error('预测字段异常');
  }
  for(const b of [...(data.market?.bars||[]),data.market?.latest_observed_bar].filter(Boolean)) {
    if(['ts','raw_ts','open','high','low','close','volume'].some(k=>!numeric(b[k])) || b.high<Math.max(b.open,b.close,b.low) || b.low>Math.min(b.open,b.close) || b.volume<0)throw Error('行情字段异常');
  }
  for(const p of data.trend)if(!numeric(p.as_of_ms)||!numeric(p.hit_rate)||p.hit_rate<0||p.hit_rate>1||!Number.isInteger(p.scored))throw Error('趋势字段异常');
}

function query() {
  const q = new URLSearchParams({bars:'600',limit:'50'});
  for(const [key,value] of Object.entries(state.filters))if(value)q.set(key,value);
  if(state.before[state.page])q.set('before',state.before[state.page]);
  if(state.selected)q.set('prediction_id',state.selected);
  return q.toString();
}

async function refresh() {
  state.epoch++;
  if(state.busy){state.queued=true;return;}
  clearTimeout(state.timer);state.busy=true;state.queued=false;
  const epoch=state.epoch, requested=query(), controller=new AbortController();
  const deadline=setTimeout(()=>controller.abort(),5000);
  $('refresh').disabled=true;
  try {
    const response=await fetch(`/api/dashboard?${requested}`,{signal:controller.signal,cache:'no-store'});
    const data=await response.json();
    if(!response.ok) {
      if(response.status===404&&state.selected){closeDetail();state.queued=true;throw Error('所选记录不属于当前快照，正在重新读取');}
      throw Error(`接口错误 ${response.status} · ${data.error||'UNKNOWN'}`);
    }
    validate(data);
    if(epoch!==state.epoch || requested!==query())return;
    const previous=state.data;
    if(previous && previous.identity.deployment===data.identity.deployment && previous.identity.mode===data.identity.mode && data.snapshot.observed_at_ms<previous.snapshot.observed_at_ms)return;
    if(previous && (previous.identity.deployment!==data.identity.deployment || previous.identity.mode!==data.identity.mode)){state.viewEnd=null;state.hover=null;state.before=[null];state.page=0;}
    if(state.page===0)state.newRecords=false;
    else if(previous?.last_prediction?.id!==data.last_prediction?.id)state.newRecords=true;
    state.data=data;state.lastSuccess=Date.now();state.error=null;render(data);
  } catch(error) {
    if(epoch===state.epoch)state.error=error.name==='AbortError'?'页面请求超过5秒，正在重试':error.name==='SyntaxError'?'接口返回数据格式异常，正在重试':error.name==='TypeError'?'页面连接中断，正在重试':error.message||'页面连接中断，正在重试';
  } finally {
    clearTimeout(deadline);state.busy=false;$('refresh').disabled=false;freshness();
    state.timer=setTimeout(refresh,state.queued?0:3000);
  }
}

function freshness() {
  const d=state.data, expired=!!state.lastSuccess&&Date.now()-state.lastSuccess>10000, cached=!!state.error||expired;
  document.body.classList.toggle('cached',cached);
  $('connection').classList.toggle('error',cached||!d&&!!state.error);
  if(state.error)put('connection',state.error+(d?(expired?'；上次快照已过期，仅作历史查看。':'；保留上次快照，仅作历史查看。'):document.body.dataset.mode==='DEMO'?'；演示接口不可用，没有提供真实数据。':'；没有切换到演示数据。'));
  else if(d)put('connection',cached?'页面快照已过期，仅作历史查看。':`页面已连接 · ${d.identity.mode==='DEMO'?'演示快照':'真实账本只读快照'} · 3秒刷新；采集进程状态仍需独立证据。`);
  put('page-state',cached?(d?(expired?'连接异常 / 缓存过期':'连接异常 / 缓存'):'连接异常'):d?'已连接':'加载中');
  put('page-time',state.lastSuccess?`成功刷新 ${time(state.lastSuccess)}`:'尚未成功刷新');
  if(!d)return;
  const elapsed=Date.now()-state.lastSuccess;
  const recent=!cached&&d.status.poll_recent&&d.snapshot.observed_at_ms+elapsed-(d.status.last_poll_ms||0)<=15000;
  put('feed-state',recent?(d.status.last_poll_success?'最近获取成功':'获取 / 处理异常'):'未知 · 轮询记录过期');
  put('market-state',recent?label(d.status.code):`上次：${label(d.status.code)}`);
  $('market-state').className=recent&&['STALE_SOURCE','MISSING_SEQUENCE','SOURCE_OR_MODEL_BLOCKED'].includes(d.status.code)?'amber':'';
  if(cached)put('prediction-kind','历史快照 · 非当前信号');
}

function render(d) {
  const id=d.identity;
  document.body.dataset.mode=id.mode;document.body.dataset.snapshot=d.snapshot.id;
  document.title=(id.mode==='DEMO'?'演示数据 · ':'')+'行情研究监控';
  $('demo-banner').hidden=id.mode!=='DEMO';
  put('mode',id.mode==='DEMO'?'DEMO · 演示数据':id.mode==='LIVE'?'LIVE · 真实账本':'REPLAY · 回放数据');
  put('instrument',`${id.name} · ${id.symbol}`);put('process','未知');
  put('source',id.source);put('model',id.model_version);put('deployment',id.deployment);
  put('success-time',time(d.status.last_success_ms));put('cutoff',time(d.snapshot.data_as_of_ms));
  put('poll-time',d.status.last_poll_ms?`最后轮询 ${time(d.status.last_poll_ms)}`:'尚无完整轮询');
  put('stop-time',d.status.last_stop_event?`${time(d.status.last_stop_event.at_ms)} · 历史记录`:'未记录；不代表仍在运行');
  put('snapshot-label',d.snapshot.data_as_of_ms?'同一业务截面 · Asia/Shanghai':'尚无完整快照');
  const b=d.market?.latest_observed_bar;
  put('quote',b?number(b.close):'—');put('quote-note',b?(b.complete?'源K线收盘 · 已确认完整':'最后观察源K线 · 尚未确认完整'):'源原始价格');
  put('bar-times',b?`源K线开始 ${time(b.raw_ts)} / 结束标签 ${short(b.ts)}`:'源K线时间：—');
  put('complete-time',`最后完整K线：${time(d.market?.last_complete_ms)}`);
  put('bar-received',`该行版本获取：${time(b?.received_ms)}`);
  const age=b?Math.max(0,(d.snapshot.observed_at_ms-b.ts)/1000):null;
  put('data-age',age===null?'无行情时间':`结束标签距快照 ${number(age)} 秒；获取时间另列`);
  put('units',`量额均为源原始数值 · ${id.units} · 不填补休市分钟`);
  renderPrediction(d);renderStats(d);renderRecords(d);drawCandles();drawTrend(d.trend);
  if(d.detail&&$('detail').open)renderDetail(d.detail);
}

function renderPrediction(d) {
  const current=d.current_prediction, p=current||d.last_prediction;
  const context=d.prediction_context;
  put('prediction-kind',current?'当前有效根预测':p?'最近历史预测':'无当前预测');
  $('prediction-state').className='prediction-state'+(current?' '+p.predicted_direction:'');
  if(context==='RULE_SKIP')put('prediction-state','本锚点规则跳过');
  else if(p)put('prediction-state',`${directions[p.predicted_direction]}${p.signal==='wait'?' · 低置信度等待':''}`);
  else put('prediction-state',context==='PREDICTED'?'暂无预测记录':label(context));
  const show=p&&context!=='RULE_SKIP';
  put('probability',show?percent(p.p_up):'—');$('probability-meter').hidden=!show;
  if(show)$('probability-meter').value=p.p_up;
  put('prediction-note',current?(p.signal==='wait'?'等待是行动标签，原方向仍计入可计分主统计。':'仅代表原模型的本次输出，不代表已验证有效。'):context==='RULE_SKIP'?'跳过没有概率；原预测只能在下方历史记录查看。':p?`当前无有效新预测；以下为最近记录，${resultNames[p.result.status]}。`:'没有可展示的预测，不生成示例概率。');
  put('prediction-anchor',show?time(p.anchor_ms):'—');put('prediction-published',show?time(p.publication?.published_at_ms):'—');
  put('prediction-computed',show?time(p.computed_at_ms):'—');put('prediction-target',show&&p.result.target_ms?time(p.result.target_ms):'待确认 · 下一有效K线');
  $('latest-detail').hidden=!p;$('latest-detail').dataset.id=p?.id||'';
}

function renderStats(d) {
  const c=d.statistics?.cumulative, today=d.statistics?.today;
  for(const [id,key] of [['scored','scored'],['hits','HIT'],['misses','MISS'],['flats','FLAT'],['pending','PENDING'],['unscorable','UNSCORABLE']])put(id,c?number(c[key]):'—');
  for(const [id,s] of [['rate',c],['today-rate',today]]) {
    put(id,s?percent(s.hit_rate):'尚无完整快照');$(id).classList.toggle('no-sample',!s||s.hit_rate===null);
  }
  put('wilson',c?.wilson95?`95% Wilson：${percent(c.wilson95[0])} — ${percent(c.wilson95[1])}`:'95% Wilson 区间：暂无');
  put('sample-note',!c?'尚无完整快照':c.effect_sample_insufficient?`效果样本不足 · n=${number(c.scored)}，未达500`:`已计分样本 n=${number(c.scored)}，不代表预测优势`);
  put('today-note',d.statistics?`${d.statistics.today_date} 发布归属 · 已计分 ${number(today.scored)}`:'按上海日期的发布归属统计');
}

const svgNode = (tag,attrs={},text) => {const n=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,v]of Object.entries(attrs))n.setAttribute(k,v);if(text!==undefined)n.textContent=text;return n;};
function drawCandles() {
  const all=[...(state.data?.market?.bars||[])], latest=state.data?.market?.latest_observed_bar;
  if(latest&&!latest.complete)all.push(latest);
  const count=Number($('range').value);
  const eligible=state.viewEnd===null?all:all.filter(b=>b.ts<=state.viewEnd);
  const bars=eligible.slice(-count);state.chartBars=bars;
  $('candles').toggleAttribute('hidden',!bars.length);$('chart-empty').hidden=!!bars.length;
  if(!bars.length)return;
  const width=Math.max(280,$('candles').getBoundingClientRect().width),plotWidth=width-80;
  state.chartWidth=plotWidth;$('candles').setAttribute('viewBox',`0 0 ${width} 340`);
  const lo=Math.min(...bars.map(b=>b.low)),hi=Math.max(...bars.map(b=>b.high)),pad=Math.max((hi-lo)*.08,.1);
  const y=p=>20+(hi+pad-p)/(hi-lo+2*pad)*205, step=plotWidth/bars.length;
  const maxVolume=Math.max(1,...bars.map(b=>b.volume)),g=$('chart-content'),nodes=[];
  for(let i=0;i<5;i++){const value=hi+pad-(hi-lo+2*pad)*i/4,py=y(value);nodes.push(svgNode('line',{x1:20,x2:20+plotWidth,y1:py,y2:py,class:'grid'}),svgNode('text',{x:width-48,y:py+4},number(value)));}
  nodes.push(svgNode('line',{x1:20,x2:20+plotWidth,y1:247,y2:247,class:'grid'}),svgNode('text',{x:width-48,y:267},'原始量'));
  bars.forEach((b,i)=>{const x=20+(i+.5)*step,w=Math.max(.8,step*.6),cls=b.close>b.open?'candle-up':b.close<b.open?'candle-down':'candle-flat';
    nodes.push(svgNode('line',{x1:x,x2:x,y1:y(b.high),y2:y(b.low),class:cls}));
    nodes.push(svgNode('rect',{x:x-w/2,y:Math.min(y(b.open),y(b.close)),width:w,height:Math.max(1,Math.abs(y(b.open)-y(b.close))),class:cls+(b.complete?'':' forming')}));
    nodes.push(svgNode('rect',{x:x-w/2,y:312-b.volume/maxVolume*55,width:w,height:Math.max(.5,b.volume/maxVolume*55),class:cls+' volume'}));
    if(i===0||i===bars.length-1||i%Math.max(1,Math.floor(bars.length/4))===0)nodes.push(svgNode('text',{x,y:333,'text-anchor':'middle'},short(b.raw_ts)));
  });
  g.replaceChildren(...nodes);drawHover();$('chart-latest').setAttribute('aria-pressed',String(state.viewEnd===null));
}

function drawHover() {
  const bars=state.chartBars,i=bars.findIndex(b=>b.ts===state.hover),g=$('chart-hover');
  if(i<0){g.replaceChildren();return;}
  const b=bars[i],x=20+(i+.5)*state.chartWidth/bars.length;
  g.replaceChildren(svgNode('line',{x1:x,x2:x,y1:15,y2:315,class:'crosshair'}));
  put('hover-info',`${time(b.raw_ts)} · ${b.complete?'已完整':'未确认完整'} · 开 ${number(b.open)} / 高 ${number(b.high)} / 低 ${number(b.low)} / 收 ${number(b.close)} / 原始量 ${number(b.volume)}`);
}

function drawTrend(points) {
  const enough=points.length>=2;$('trend').toggleAttribute('hidden',!enough);$('trend-empty').hidden=enough;
  if(!enough)return;
  const width=Math.max(280,$('trend').getBoundingClientRect().width);$('trend').setAttribute('viewBox',`0 0 ${width} 180`);
  const nodes=[];for(const [rate,y]of [[1,15],[.5,80],[0,145]])nodes.push(svgNode('line',{x1:35,x2:width-15,y1:y,y2:y,class:'grid'}),svgNode('text',{x:0,y:y+4},`${rate*100}%`));
  const coords=points.map((p,i)=>[35+i*(width-50)/(points.length-1),145-p.hit_rate*130]);
  nodes.push(svgNode('polyline',{points:coords.map(p=>p.join(',')).join(' '),class:'trend-line'}));
  points.forEach((p,i)=>{const dot=svgNode('circle',{cx:coords[i][0],cy:coords[i][1],r:2.8,class:'trend-dot'});dot.append(svgNode('title',{},`${time(p.as_of_ms)} · ${percent(p.hit_rate)} · n=${p.scored}`));nodes.push(dot);});
  nodes.push(svgNode('text',{x:35,y:173},short(points[0].as_of_ms)),svgNode('text',{x:width-15,y:173,'text-anchor':'end'},short(points.at(-1).as_of_ms)));$('trend').replaceChildren(...nodes);
}

function renderRecords(d) {
  const body=$('records'), oldRows=[...body.children];
  const anchor=oldRows.find(r=>r.getBoundingClientRect().top>=0), top=anchor?.getBoundingClientRect().top;
  const byId=new Map(oldRows.map(r=>[r.dataset.id,r])), keep=new Set();
  d.records.forEach((p,index)=>{
    let row=byId.get(p.id);
    if(!row){row=document.createElement('tr');row.dataset.id=p.id;for(let i=0;i<8;i++)row.append(document.createElement('td'));const button=document.createElement('button');button.textContent='查看';button.dataset.id=p.id;button.addEventListener('click',()=>openDetail(p.id,button));row.children[7].append(button);}
    const values=[time(p.display_time_ms)+(p.publication?'':' · 未发布'),directions[p.predicted_direction]+(p.signal==='wait'?' · 等待':''),percent(p.p_up),time(p.anchor_ms),p.result.target_ms?time(p.result.target_ms):'待确认',directions[p.actual_direction]||'待确认',resultNames[p.result.status]+(p.result.revision>1?` · 修订${p.result.revision}`:'')];
    values.forEach((v,i)=>{if(row.children[i].textContent!==v)row.children[i].textContent=v;});
    row.children[1].className=p.predicted_direction;row.children[5].className=p.actual_direction||'';
    row.children[6].className='result-'+p.result.status;
    if(body.children[index]!==row)body.insertBefore(row,body.children[index]||null);keep.add(p.id);
  });
  for(const row of oldRows)if(!keep.has(row.dataset.id))row.remove();
  if(anchor?.isConnected&&top>=0&&window.scrollY>0)window.scrollBy(0,anchor.getBoundingClientRect().top-top);
  $('records-empty').hidden=!!d.records.length;put('page-label',`第 ${state.page+1} 页 · 本页 ${d.records.length} 条`);
  put('history-note',state.newRecords?'有新预测，可点“回到最新”':'筛选不改变全局统计');
  $('previous').disabled=state.page===0;$('next').disabled=!d.next_before;
}

function renderDetail(p) {
  const values=[['预测ID',p.id],['原方向 / 行动',`${directions[p.predicted_direction]} / ${p.signal}`],['上涨 / 下跌概率',`${percent(p.p_up)} / ${percent(p.p_down)}`],['基准收盘',number(p.base_close)],['计算时刻',time(p.computed_at_ms)],['实际发布时间',time(p.publication?.published_at_ms)],['发布资格',p.publication?(p.publication.eligible?'有合格回执':'不合格回执，无法计分'):'无发布回执'],['锚点',time(p.anchor_ms)],['目标有效K线',p.result.target_ms?time(p.result.target_ms):'待确认'],['目标收盘',number(p.result.target_close)],['实际方向',directions[p.actual_direction]||'待确认'],['结果 / 修订',`${resultNames[p.result.status]} / ${p.result.revision||'未记录'}`],['原因',p.result.reason||'未记录'],['目标发布时已开盘',p.result.target_started_at_publication==null?'未记录':p.result.target_started_at_publication?'是':'否'],['输入摘要',p.input_sha256]];
  const content=$('detail-body'),dl=document.createElement('dl');
  for(const [name,value]of values){const div=document.createElement('div'),dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=name;dd.textContent=value;div.append(dt,dd);dl.append(div);}
  const pre=document.createElement('pre');pre.textContent=p.trace?JSON.stringify(p.trace,null,2):'MODEL_INPUT：未记录';
  const scroll=$('detail').scrollTop,signature=JSON.stringify(p);
  if(content.dataset.signature!==signature){content.replaceChildren(dl,pre);content.dataset.signature=signature;$('detail').scrollTop=scroll;}
}

function openDetail(id,button) {state.selected=id;state.returnFocus=button;$('detail-body').textContent='正在读取同一截面的详情…';delete $('detail-body').dataset.signature;if(!$('detail').open)$('detail').showModal();refresh();}
function closeDetail(){state.selected=null;if($('detail').open)$('detail').close();state.returnFocus?.focus();}
$('detail').addEventListener('close',()=>{state.selected=null;});
$('close-detail').addEventListener('click',closeDetail);$('latest-detail').addEventListener('click',event=>openDetail(event.currentTarget.dataset.id,event.currentTarget));
$('refresh').addEventListener('click',refresh);
$('filters').addEventListener('submit',event=>{event.preventDefault();state.filters={from:$('from').value,to:$('to').value,status:$('result-filter').value};state.before=[null];state.page=0;refresh();});
$('reset-filters').addEventListener('click',()=>{$('filters').reset();state.filters={from:'',to:'',status:''};state.before=[null];state.page=0;refresh();});
$('next').addEventListener('click',()=>{if(state.data?.next_before){state.before[++state.page]=state.data.next_before;refresh();}});
$('previous').addEventListener('click',()=>{if(state.page){state.page--;refresh();}});
$('history-latest').addEventListener('click',()=>{state.before=[null];state.page=0;refresh();});
$('range').addEventListener('change',drawCandles);
$('chart-latest').addEventListener('click',()=>{state.viewEnd=null;state.hover=null;drawCandles();});
for(const [id,sign]of [['older',-1],['newer',1]])$(id).addEventListener('click',()=>{const bars=state.data?.market?.bars||[];if(!bars.length)return;const at=state.viewEnd===null?bars.length-1:Math.max(0,bars.findIndex(b=>b.ts>=state.viewEnd));state.viewEnd=bars[Math.max(0,Math.min(bars.length-1,at+sign*Math.max(10,Number($('range').value)/4)))].ts;drawCandles();});
$('candles').addEventListener('pointermove',event=>{if(!state.chartBars.length)return;const rect=$('candles').getBoundingClientRect(),x=event.clientX-rect.left;const i=Math.max(0,Math.min(state.chartBars.length-1,Math.floor((x-20)/state.chartWidth*state.chartBars.length)));state.hover=state.chartBars[i].ts;if(state.viewEnd===null)state.viewEnd=state.chartBars.at(-1).ts;drawHover();});
window.addEventListener('resize',()=>{drawCandles();if(state.data)drawTrend(state.data.trend);});
setInterval(freshness,1000);refresh();
