// Pure derived views over /api/stats. Never add sample/fallback observations.
const AnalysisMetrics={
  event(data,key,measure){
    if(key==='recognition_end'){
      const runs=data.recognition_runs.filter(r=>r.status==='ended');
      return {count:runs.length,users:new Set(runs.map(r=>r.device_id)).size,rows:data.recognition_daily.map(day=>({date:day.date,value:measure==='clicks'?day.ended:day.ended==null?null:new Set(runs.filter(r=>r.ended_at.slice(0,10)===day.date).map(r=>r.device_id)).size}))};
    }
    const stats=key.startsWith('recognition_')?data.components.recognition_toggle.actions[key]:data.components[key];
    return {count:stats.period_clicks,users:stats.period_users,rows:stats.trend.map(d=>({date:d.date,value:d[measure]}))};
  },
  recognitionRecords(data){
    return data.recognition_runs.slice().sort((a,b)=>b.started_at.localeCompare(a.started_at)||a.recognition_id.localeCompare(b.recognition_id));
  },
  durationSummary(data){
    const runs=data.recognition_runs.filter(r=>r.status==='ended').slice().sort((a,b)=>b.duration_ms-a.duration_ms||b.ended_at.localeCompare(a.ended_at)||a.recognition_id.localeCompare(b.recognition_id));
    const ids=[...new Set(runs.map(r=>r.device_id))];
    return {runs,count:runs.length,device_ids:ids,users:ids.length,average_ms:runs.length?runs.reduce((total,r)=>total+r.duration_ms,0)/runs.length:null};
  },
  distribution(data){
    const ends=[10000,30000,60000,180000,600000,Infinity],labels=['≤10秒','>10–30秒','>30–60秒','>1–3分钟','>3–10分钟','>10分钟'];
    const rows=ends.map((end,i)=>({label:labels[i],count:0}));
    for(const r of data.recognition_runs)if(r.status==='ended')rows[ends.findIndex(end=>r.duration_ms<=end)].count++;
    return rows;
  },
  paths(data,measure){
    return [...data.trajectory_groups].sort((a,b)=>b[measure]-a[measure]||a.group_id.localeCompare(b.group_id));
  }
};
if(typeof module!=='undefined')module.exports=AnalysisMetrics;
