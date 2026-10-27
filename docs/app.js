const $ = s => document.querySelector(s);
const escape = v => String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let selected='recognition_toggle',selectedAction='recognition_start',data,mode='raw';
let durationMode='all',durationPage=0;
const identityReady=fetch('/api/device').then(r=>r.json());
const names={transcript_tab:'转写 Tab',summary_tab:'摘要 Tab',recognition_toggle:'识别按钮',content_save:'保存'};
function status(text,error=false){if(error) console.error(text)}
let requestId=0,appliedStart='',appliedEnd='',replaying=false,replayToken=0;
function validRange(){
  const start=$('#range-start').value,end=$('#range-end').value;
  return !!(start&&end&&start<=end&&end<=data.today);
}
async function refresh(){
  const id=++requestId,start=appliedStart,end=appliedEnd;
  const query=start?`?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`:'';
  const res=await fetch('/api/stats'+query),next=await res.json();
  if(id!==requestId)return;
  if(!res.ok){$('#range-error').textContent=next.error||'日期范围无效';$('#raw-view').hidden=true;$('#insights-view').hidden=true;$('#heat-overlay').hidden=true;return}
  applyMode();
  if(!start){appliedStart=next.range.start;appliedEnd=next.range.end;$('#range-start').value=appliedStart;$('#range-end').value=appliedEnd;}
  $('#range-start').max=next.today;$('#range-end').max=next.today;
  const changed=!data||data.total_events!==next.total_events||data.range.start!==next.range.start||data.range.end!==next.range.end||JSON.stringify(data.trajectories)!==JSON.stringify(next.trajectories)||JSON.stringify(data.dashboard)!==JSON.stringify(next.dashboard)||next.recognition_runs.some(r=>r.status!=='ended');
  data=next;status('监测中');if(changed)render();
}
function closeRange(){ $('#range-popover').hidden=true;$('#range-toggle').setAttribute('aria-expanded','false');$('#range-error').textContent=''; }
$('#range-toggle').addEventListener('click',()=>{if(!$('#range-popover').hidden){closeRange();return}$('#range-start').value=appliedStart;$('#range-end').value=appliedEnd;$('#range-popover').hidden=false;$('#range-toggle').setAttribute('aria-expanded','true')});
$('#range-cancel').addEventListener('click',closeRange);
$('#range-apply').addEventListener('click',()=>{if(!validRange()){$('#range-error').textContent='请选择有效日期，开始不能晚于截止且不能晚于今天。';return}appliedStart=$('#range-start').value;appliedEnd=$('#range-end').value;closeRange();refresh().catch(()=>status('读取失败',true))});
document.addEventListener('click',e=>{if(!e.target.closest('.range-controls'))closeRange()});
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeRange()});

function durationRow(){
  const summary=AnalysisMetrics.durationSummary(data);
  return {id:'recognition_end',name:'识别时长',average_ms:summary.average_ms,stats:{period_clicks:summary.count,period_users:summary.users,click_times:[],click_records:summary.device_ids.map(device_id=>({device_id}))}};
}
function durationDetails(open){
  const summary=AnalysisMetrics.durationSummary(data),records=AnalysisMetrics.recognitionRecords(data),pageSize=10;
  durationPage=Math.max(0,Math.min(durationPage,Math.ceil(records.length/pageSize)-1));
  const shown=durationMode==='top'?summary.runs.slice(0,5):records.slice(durationPage*pageSize,(durationPage+1)*pageSize);
  const stamp=t=>t?escape(t.slice(0,10)+' '+t.slice(11,19)):'—';
  const states={ended:'已结束',running:'进行中',unconfirmed:'结束未确认'};
  return `<tr class="duration-detail-row"><td colspan="6"><details id="duration-details" ${open?'open':''}><summary>识别原始明细 · ${durationMode==='top'?'最长5次':'全部记录（'+records.length+'条）'}</summary><div class="duration-detail-controls"><button data-duration-view="all" aria-pressed="${durationMode==='all'}">全部记录（${records.length}）</button><button data-duration-view="top" aria-pressed="${durationMode==='top'}">最长5次</button></div><small class="coverage">${durationMode==='top'?'仅已结束，按时长降序':'已结束按结束日期、未结束按最后观测日期筛选；按开始时间倒序'}；每行一次识别。未结束仅显示已观测时长下限。</small><div class="record-table-wrap"><table class="run-table raw-run-table"><thead><tr><th>用户 / 识别过程 / 轨迹</th><th>时长</th><th>开始时间</th><th>结束时间</th><th>结束方式</th><th>状态</th></tr></thead><tbody>${shown.map(run=>`<tr data-run-id="${escape(run.recognition_id)}"><td><code>用户 ${escape(run.device_id)}</code><small class="event-code">识别 ${escape(run.recognition_id)}</small><small class="event-code">轨迹 ${escape(run.trajectory_id||'—')}</small></td><td>${run.status==='ended'?'':'≥'}${(run.duration_ms/1000).toFixed(2)}秒</td><td>${stamp(run.started_at)}</td><td>${stamp(run.ended_at)}</td><td>${run.end_reason==='manual'?'点击关闭':run.end_reason==='exit'?'退出功能':'—'}</td><td>${states[run.status]}</td></tr>`).join('')||'<tr><td colspan="6">暂无识别记录</td></tr>'}</tbody></table></div>${durationMode==='all'&&records.length>pageSize?`<div class="duration-pagination"><button data-duration-page="prev" ${durationPage===0?'disabled':''}>上一页</button><span>${durationPage+1} / ${Math.ceil(records.length/pageSize)}</span><button data-duration-page="next" ${(durationPage+1)*pageSize>=records.length?'disabled':''}>下一页</button></div>`:''}</details></td></tr>`;
}
function render(){
  if(!data)return;
  $('#date').textContent=data.range.start===data.range.end?(data.range.start===data.today?'今天 · ':'')+data.range.start:`${data.range.start} — ${data.range.end}`;
  renderTrajectories();renderDashboard();drawOverlay();
  const eventIds={transcript_tab:'voice.transcript.open',summary_tab:'voice.summary.open',recognition_start:'voice.recognition.start',recognition_stop:'voice.recognition.stop',content_save:'voice.content.save',recognition_end:'voice.recognition.end'};
  const recognition=data.components.recognition_toggle;
  const rows=Object.entries(names).filter(([id])=>id!=='recognition_toggle').map(([id,name])=>({id,name,stats:data.components[id]}));
  for(const [action,name] of [['recognition_start','识别 · 启动'],['recognition_stop','识别 · 关闭']])rows.push({id:'recognition_toggle',action,name,stats:recognition.actions[action]});
  rows.push(durationRow());
  const durationOpen=$('#duration-details')?.open;
  $('#metrics').innerHTML=rows.map(row=>{
    const c=row.stats,last=c.click_times[0],isDuration=row.id==='recognition_end';
    const active=selected===row.id&&(!row.action||selectedAction===row.action);
    const seconds=isDuration&&row.average_ms!=null?`平均每次 ${(row.average_ms/1000).toFixed(2)} 秒`:'—';
    return `<tr data-event="${row.id}"><td class="${active?'active':''}">${row.name}<small class="event-code">${row.action?eventIds[row.action]:eventIds[row.id]}</small></td><td class="user-ids">${[...new Set(c.click_records.map(r=>r.device_id))].map(id=>`<code>${escape(id)}</code>`).join('')||'—'}</td><td class="duration-value">${seconds}</td><td>${c.period_clicks}</td><td>${c.period_users}</td><td${isDuration?' title="时长事件不适用最近点击"':''}>${!isDuration&&last?escape(data.range.days>1?last.slice(5,10)+' '+last.slice(11,19):last.slice(11,19)):'—'}</td></tr>${isDuration?durationDetails(durationOpen):''}`;
  }).join('');
  document.querySelectorAll('[data-duration-view]').forEach(button=>button.addEventListener('click',()=>{durationMode=button.dataset.durationView;durationPage=0;render()}));
  document.querySelectorAll('[data-duration-page]').forEach(button=>button.addEventListener('click',()=>{durationPage+=button.dataset.durationPage==='next'?1:-1;render()}));
}

const frame=$('#product-frame'),mirror=$('#heat-frame');
$('#debug-toggle').addEventListener('click',()=>{const open=$('#debug-panel').hidden;$('#debug-panel').hidden=!open;$('.workspace').classList.toggle('debug-collapsed',!open);$('#debug-toggle').setAttribute('aria-expanded',String(open));$('#debug-toggle').textContent=open?'收起调试产品':'展开调试产品';if(open&&!frame.getAttribute('src'))frame.src='./product.html';});
mirror.src='./product.html?preview=1';
let mirroredHTML='';
function syncMirror(){
  if(replaying)return;
  const doc=frame.contentDocument;if(!doc?.body)return;
  const copy=doc.documentElement.cloneNode(true);copy.querySelectorAll('script').forEach(el=>el.remove());
  const html='<!doctype html>'+copy.outerHTML;
  if(html===mirroredHTML){drawOverlay();return}
  mirroredHTML=html;mirror.srcdoc=html;
}
mirror.addEventListener('load',drawOverlay);
async function connectProduct(){
  if(!frame.getAttribute('src'))return;
  await identityReady;
  const doc=frame.contentDocument;
  if(!doc||doc.getElementById('tool-tracker'))return;
  new ResizeObserver(syncMirror).observe(doc.documentElement);
  new MutationObserver(syncMirror).observe(doc.body,{subtree:true,attributes:true,childList:true});
  frame.contentWindow.addEventListener('scroll',()=>{if(mirror.contentWindow)mirror.contentWindow.scrollTo(frame.contentWindow.scrollX,frame.contentWindow.scrollY);drawOverlay()});
  syncMirror();
  const sdk=doc.createElement('script');sdk.id='tool-tracker';sdk.src='./tracker.js';doc.body.append(sdk);
}
frame.addEventListener('load',connectProduct);
if(frame.getAttribute('src')&&frame.contentDocument?.readyState==='complete')connectProduct();
window.addEventListener('message',event=>{
  if(event.origin!==location.origin||event.source!==frame.contentWindow)return;
  if(event.data?.type==='trail:uploaded')refresh().catch(()=>status('读取失败',true));
  if(event.data?.type==='trail:error')status('上报失败 · 事件已暂存',true);
});
refresh().catch(()=>status('连接中断',true));
setInterval(()=>refresh().catch(()=>status('本地服务连接中断',true)),3000);

function drawOverlay(){
  const layer=$('#heat-overlay');layer.hidden=mode!=='raw'||replaying||!$('#show-heat').checked;
  const doc=mirror.contentDocument;if(!doc?.body||!data)return;
  const selectors={transcript_tab:'#transcript-tab',summary_tab:'#summary-tab',recognition_toggle:'#recognize',content_save:'#save-content'};
  const max=Math.max(1,...Object.keys(names).map(id=>data.components[id].period_clicks));
  layer.innerHTML=Object.entries(selectors).map(([id,selector])=>{
    const el=doc.querySelector(selector);if(!el)return '';
    const r=el.getBoundingClientRect(),count=data.components[id].period_clicks;
    if(!r.width||!r.height)return '';
    const radius=mirror.contentWindow.getComputedStyle(el).borderRadius;
    return `<button type="button" aria-label="查看${names[id]}数据" data-inspect="${id}" class="heat-spot" style="left:${r.left}px;top:${r.top}px;width:${r.width}px;height:${r.height}px;border-radius:${radius};background:rgba(235,102,26,${count ? .12 + .58 * count / max : 0})">${count?`<span>${count}次</span>`:''}</button>`;
  }).join('');
  layer.querySelectorAll('[data-inspect]').forEach(b=>b.addEventListener('click',()=>{selected=b.dataset.inspect;render()}));
}
$('#show-heat').addEventListener('change',drawOverlay);
new ResizeObserver(drawOverlay).observe(mirror);


function renderTrajectories(){
  const panel=$('#trajectory-panel');
  const totals=data.trajectory_totals;
  const rows=data.trajectory_groups.map(g=>({route:g.steps,steps:g.step_count,count:g.count,users:g.users,status:'已结束',records:g.records}));
  rows.sort((a,b)=>b.count-a.count);
  panel.innerHTML=`<h3>轨迹记录</h3><p class="coverage">按进入日期 · 已结束 ${totals.ended} 次</p><div class="record-table-wrap"><table class="trace-table"><thead><tr><th>操作顺序</th><th>步数</th><th>次数</th><th>人数</th><th>状态</th><th>操作</th></tr></thead><tbody>${rows.map(r=>`<tr><td><span class="trajectory-route">${r.route.map(escape).join(' → ')}</span></td><td>${r.steps}</td><td>${r.count}</td><td>${r.users}</td><td>${r.status}</td><td><button class="replay-button" data-replay="${escape(r.records[0].trajectory_id)}">逆向演示</button></td></tr>`).join('')||'<tr><td colspan="6">暂无轨迹记录</td></tr>'}</tbody></table></div>`;
  panel.querySelectorAll('[data-replay]').forEach(b=>b.addEventListener('click',()=>startReplay(b.dataset.replay)));
}
function applyMode(){
  $('#raw-view').hidden=mode!=='raw';$('#insights-view').hidden=mode!=='insights';$('#dashboard-view').hidden=mode!=='dashboard';
  $('.heat-control').hidden=mode!=='raw';
  $('#monitor-preview').hidden=mode==='dashboard';
  $('.work-panels').hidden=mode==='dashboard';
  $('.analysis-panel').hidden=mode==='dashboard';
  $('#preview-title').textContent=mode==='insights'?'回放预览':'页面预览';
  $('.range-controls').hidden=mode==='dashboard';
  for(const [id,value] of [['raw-tab','raw'],['insights-tab','insights'],['dashboard-tab','dashboard']]){const active=mode===value;$('#'+id).setAttribute('aria-selected',String(active));$('#'+id).tabIndex=active?0:-1;}
}
for(const [id,value] of [['raw-tab','raw'],['insights-tab','insights'],['dashboard-tab','dashboard']]){
  $('#'+id).addEventListener('click',()=>{mode=value;if(mode!=='insights')stopReplay();applyMode();if(data){drawOverlay()}});
  $('#'+id).addEventListener('keydown',event=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){event.preventDefault();const ids=['raw-tab','insights-tab','dashboard-tab'],index=ids.indexOf(id),next=event.key==='Home'?ids[0]:event.key==='End'?ids[2]:ids[(index+(event.key==='ArrowRight'?1:-1)+ids.length)%ids.length];$('#'+next).focus();$('#'+next).click()}});
}

async function startReplay(id){
  const trace=data.trajectories.find(t=>t.trajectory_id===id&&t.status==='ended');if(!trace)return;
  const token=++replayToken;replaying=true;drawOverlay();
  const progress=$('#replay-status');progress.hidden=false;progress.textContent='准备演示…';
  mirror.removeAttribute('srcdoc');
  await new Promise(resolve=>{mirror.onload=()=>{mirror.onload=null;resolve()};mirror.src='./product.html?replay='+token});
  if(token!==replayToken)return;
  const doc=mirror.contentDocument;
  const map={'voice.transcript.open':'#transcript-tab','voice.summary.open':'#summary-tab','voice.recognition.start':'#recognize','voice.recognition.stop':'#recognize','voice.content.save':'#save-content'};
  const steps=trace.steps.filter(s=>map[s.event_id]);
  for(let i=0;i<steps.length;i++){
    if(token!==replayToken)return;
    const step=steps[i],el=doc.querySelector(map[step.event_id]);
    if(!el||el.hidden||!el.getClientRects().length){progress.textContent=`第 ${i+1}/${steps.length} 步：${step.label} · 当前界面无法演示`;return}
    progress.textContent=`第 ${i+1}/${steps.length} 步：${step.label}`;
    el.style.outline='3px solid #ec7a30';el.style.outlineOffset='3px';
    await new Promise(r=>setTimeout(r,700));if(token!==replayToken)return;
    el.click();await new Promise(r=>setTimeout(r,500));el.style.outline='';el.style.outlineOffset='';
  }
  progress.textContent=steps.length?'演示完成 · '+steps.length+' 步':'进入后直接退出，无操作步骤';
}
function stopReplay(){if(!replaying)return;++replayToken;replaying=false;$('#replay-status').hidden=true;mirror.removeAttribute('srcdoc');mirroredHTML='';if(frame.getAttribute('src'))syncMirror();else mirror.src='./product.html?preview=1';drawOverlay()}

function renderDashboard(){
  const panel=$('#dashboard-content'),d=data.dashboard;
  if(!d){panel.innerHTML='<p class="empty">看板数据尚不可用，请重启本地服务。</p>';return}
  const fmt=v=>v==null?'—':v.toLocaleString(),days=d.recent_daily;
  const count=(v,partial)=>v==null?'—':(partial?'≥ ':'')+fmt(v);
  function chart(key,title,unit){
    const max=Math.max(1,...days.map(day=>day[key]||0)),ceiling=Math.max(4,Math.ceil(max/4)*4),x=i=>55+i*110,y=v=>165-v/ceiling*120;
    let segments=[],segment=[];days.forEach((day,i)=>{if(day[key]==null){if(segment.length)segments.push(segment);segment=[]}else segment.push(`${x(i)},${y(day[key])}`)});if(segment.length)segments.push(segment);
    const grid=Array.from({length:5},(_,i)=>{const value=ceiling*(4-i)/4,yy=45+i*30;return `<line x1="55" y1="${yy}" x2="715" y2="${yy}" stroke="#e4eaf3" stroke-dasharray="3 3"/><text x="43" y="${yy+4}" text-anchor="end">${value}</text>`}).join('');
    const dates=days.map((day,i)=>`<text x="${x(i)}" y="190" text-anchor="middle">${escape(day.date.slice(5).replace('-','/'))}</text>`).join('');
    const points=days.map((day,i)=>day[key]==null?'':`<circle cx="${x(i)}" cy="${y(day[key])}" r="4.5" fill="#345ddb" stroke="white" stroke-width="2"/><text x="${x(i)}" y="${y(day[key])-10}" text-anchor="middle" class="chart-value">${key==='visits'&&day.visits_partial?'≥':''}${day[key]}</text>`).join('');
    const paths=segments.map(points=>`<polyline points="${points.join(' ')}" fill="none" stroke="#345ddb" stroke-width="2.5"/>`).join('');
    return `<section class="dashboard-chart"><div class="chart-title"><div><h4>${title}</h4><span>${escape(days[0].date)} — ${escape(days[6].date)}</span></div><span>${unit}</span></div><svg viewBox="0 0 770 205" role="img" aria-label="${title}：${days.map(day=>day.date+' '+count(day[key],key==='visits'&&day.visits_partial)).join('，')}">${grid}${paths}${points}${dates}</svg></section>`;
  }
  panel.innerHTML=`<div class="dashboard-date">${escape(data.today)} <span>当日数据</span></div><div class="dashboard-cards"><div><small>今日日活</small><strong>${fmt(d.today_active)}</strong><span>当日活跃用户</span></div><div><small>今日新增</small><strong>${fmt(d.today_first_observed)}</strong><span>当日首次观测</span></div><div><small>年度累计用户</small><strong>${fmt(d.year_active)}</strong><span>${escape(data.today.slice(0,4))}.01.01 至今 · 活跃去重</span></div><div><small>今日访问次数</small><strong>${count(d.today_visits,days[6].visits_partial)}</strong><span>按进入日统计</span></div><div><small>今日人均访问次数</small><strong>${count(d.today_visits_per_user,days[6].visits_partial)}</strong><span>今日访问次数 ÷ 日活</span></div><div><small>年度累计访问次数</small><strong>${count(d.year_visits,d.year_visits_partial)}</strong><span>${escape(data.today.slice(0,4))}.01.01 至今</span></div></div><div class="dashboard-charts">${chart('active','近 7 日日活趋势','人数')}${chart('visits','近 7 日访问次数趋势','次数')}</div><p class="dashboard-note">匿名浏览器标识去重；新增为已有历史中的首次观测。访问按有轨迹标识的进入记录计数，包含尚未确认结束的访问；旧记录缺少标识时结果可能不完整（≥）。— 表示无可用记录，不视为零。${d.coverage_start?'最早记录：'+escape(d.coverage_start.slice(0,10))+'。':''}</p>`;
}
