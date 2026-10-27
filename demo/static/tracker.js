// 工具采集组件，独立于产品业务逻辑。
(async()=>{
  if(window.__trailTracker)return;window.__trailTracker=true;
  const uuid=()=>crypto.randomUUID();
  const identity=await (await fetch('/api/device')).json(),user=identity.device_id;
  let session=uuid(),sequence=0,journeyClock=performance.now(),journeyStart=new Date().toISOString(),closed=false;
  // 每条待发送记录单独持久化；多标签页并发不会覆盖彼此的队列。
  const key='trail-event-outbox-v3:';
  let syncing=false,active=null;
  const pending=()=>Object.keys(localStorage).filter(k=>k.startsWith(key)).map(k=>JSON.parse(localStorage.getItem(k))).filter(Boolean);
  for(const [storage,oldKey] of [[localStorage,'trail-device-outbox-v2'],[sessionStorage,'trail-trajectory-outbox-v1']]){
    const old=JSON.parse(storage.getItem(oldKey)||'[]');
    for(const record of old)localStorage.setItem(key+record.id,JSON.stringify(record));
    storage.removeItem(oldKey);
  }
  function notify(type){if(parent!==window)parent.postMessage({type},location.origin)}
  async function flush(){
    if(syncing)return;syncing=true;
    try{
      for(const record of pending()){
        const res=await fetch('/api/events',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(record)});
        if(!res.ok)throw Error();localStorage.removeItem(key+record.id);
      }
      notify('trail:uploaded');
    }catch{notify('trail:error')}finally{syncing=false}
  }
  function capture(type,component='',action='',event_id,extra={},send=true){
    const record={id:uuid(),event_id,user,session,trajectory_id:session,trajectory_seq:sequence++,page_id:document.querySelector('#summary-tab')?.getAttribute('aria-selected')==='true'?'summary':'transcript',type,component,action,occurred_at:new Date().toISOString(),...extra};
    localStorage.setItem(key+record.id,JSON.stringify(record));if(send)flush();return record;
  }
  function elapsed(run){return Math.max(0,Math.round(performance.now()-run.clock))}
  function runFields(run){return {recognition_id:run.id,started_at:run.started_at}}
  function finish(reason,send=true){
    if(!active)return;
    const run=active;active=null;
    return capture('recognition_end','recognition_toggle','','voice.recognition.end',{
      ...runFields(run),ended_at:new Date().toISOString(),duration_ms:elapsed(run),end_reason:reason
    },send);
  }
  try{
    const res=await fetch('/api/plan');if(!res.ok)throw Error();const plan=await res.json();
    document.addEventListener('click',event=>{
      if(!(event.target instanceof Element))return;
      const item=plan.components.find(c=>event.target.closest(c.selector));if(!item)return;
      if(!item.transitions){capture(item.event,item.id,'',item.event_id);return}
      const element=event.target.closest(item.selector);
      // 冒泡至document时，产品自己的按钮处理已完成，按目标状态记录转换。
      const transition=item.transitions.events.find(t=>t.to===element.getAttribute(item.transitions.attribute));if(!transition)return;
      const clock=performance.now(),at=new Date().toISOString();
      if(transition.id==='recognition_start'){
        if(!active)active={id:uuid(),started_at:at,clock};
        capture(item.event,item.id,transition.id,transition.event_id,{...runFields(active),occurred_at:at});
      }else{
        capture(item.event,item.id,transition.id,transition.event_id,active?runFields(active):{});
        finish('manual');
      }
    });
    capture(plan.page.event,'','',plan.page.event_id,{started_at:journeyStart});
    setInterval(()=>{if(pending().length)flush()},3000);
    setInterval(()=>{
      if(!closed)capture('session_active','','','voice.session.active');
      if(active)capture('recognition_active','recognition_toggle','','voice.recognition.active',{...runFields(active),duration_ms:elapsed(active)});
    },5000);
    window.addEventListener('pagehide',()=>{
      if(closed)return;closed=true;
      finish('exit',false);
      capture('session_end','','','voice.session.end',{started_at:journeyStart,ended_at:new Date().toISOString(),duration_ms:Math.max(0,Math.round(performance.now()-journeyClock)),end_reason:'exit'},false);
      // 每条都保留在待发送队列中，收到确认才移除；退出后重试由记录ID去重。
      for(const record of pending())navigator.sendBeacon('/api/events',new Blob([JSON.stringify(record)],{type:'application/json'}));
    });
    window.addEventListener('pageshow',event=>{
      if(!event.persisted)return;
      session=uuid();sequence=0;journeyClock=performance.now();journeyStart=new Date().toISOString();closed=false;
      capture(plan.page.event,'','',plan.page.event_id,{started_at:journeyStart});
      // BFCache恢复后产品开关仍开启，重新关联持续识别过程。
      if(document.querySelector('#recognize')?.getAttribute('aria-pressed')==='true'){
        active={id:uuid(),started_at:journeyStart,clock:journeyClock};
        capture('recognition_active','recognition_toggle','','voice.recognition.active',{...runFields(active),duration_ms:0});
      }
    });
  }catch{notify('trail:error')}
})();
