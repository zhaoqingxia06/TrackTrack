const test=require('node:test'),assert=require('node:assert/strict');
const Metrics=require('../static/analysis-metrics.js');
test('daily counts and users stay distinct and missing stays null',()=>{
 const stats={period_clicks:5,period_users:2,trend:[{date:'2026-10-23',clicks:null,users:null},{date:'2026-10-24',clicks:5,users:2}]};
 const data={components:{summary_tab:stats}};
 assert.deepEqual(Metrics.event(data,'summary_tab','users'),{count:5,users:2,rows:[{date:'2026-10-23',value:null},{date:'2026-10-24',value:2}]});
});
test('duration bucket boundaries count each completed run exactly once',()=>{
 const data={recognition_runs:[0,10000,10001,30000,30001,60000,60001,180000,180001,600000,600001].map(duration_ms=>({status:'ended',duration_ms})).concat([{status:'unconfirmed',duration_ms:30000}])};
 const bins=Metrics.distribution(data);assert.deepEqual(bins.map(b=>b.count),[2,2,2,2,2,1]);assert.equal(bins.reduce((sum,b)=>sum+b.count,0),11);
});
test('rank counts and users independently, never mutate raw group order',()=>{
 const data={trajectory_groups:[{group_id:'a',count:3,users:1},{group_id:'b',count:2,users:2}]};
 assert.equal(Metrics.paths(data,'count')[0].group_id,'a');assert.equal(Metrics.paths(data,'users')[0].group_id,'b');assert.equal(data.trajectory_groups[0].group_id,'a');
});
test('recognition users are deduplicated within each end date and whole period',()=>{
 const data={recognition_runs:[{status:'ended',device_id:'a',ended_at:'2026-10-24T10:00:00+08:00'},{status:'ended',device_id:'a',ended_at:'2026-10-24T11:00:00+08:00'},{status:'running',device_id:'b'}],recognition_daily:[{date:'2026-10-23',ended:null},{date:'2026-10-24',ended:2}]};
 const out=Metrics.event(data,'recognition_end','users');assert.equal(out.count,2);assert.equal(out.users,1);assert.deepEqual(out.rows.map(r=>r.value),[null,1]);
});
test('duration summary is one weighted population and Top5 excludes unconfirmed',()=>{
 const data={recognition_runs:[30,10,80,70,60,50,40].map((s,i)=>({status:'ended',device_id:i<2?'a':'b',recognition_id:String(i),duration_ms:s*1000,ended_at:'2026-10-24T10:00:00+08:00'})).concat([{status:'running',duration_ms:999999,device_id:'c'}])};
 const out=Metrics.durationSummary(data);assert.equal(out.count,7);assert.equal(out.users,2);assert.equal(out.average_ms,340000/7);assert.deepEqual(out.runs.slice(0,5).map(r=>r.duration_ms),[80000,70000,60000,50000,40000]);assert.equal(data.recognition_runs[0].duration_ms,30000);
 assert.equal(Metrics.durationSummary({recognition_runs:[]}).average_ms,null);
});
test('raw recognition records preserve pending runs and sort by start, without changing completed summary',()=>{
 const data={recognition_runs:[{recognition_id:'a',started_at:'2026-10-26T10:00:00+08:00',ended_at:'2026-10-26T10:00:10+08:00',status:'ended',device_id:'user',duration_ms:10000},{recognition_id:'b',started_at:'2026-10-26T11:00:00+08:00',status:'running',device_id:'user',duration_ms:5000},{recognition_id:'c',started_at:'2026-10-26T09:00:00+08:00',status:'unconfirmed',device_id:'user',duration_ms:1000}]};
 assert.deepEqual(Metrics.recognitionRecords(data).map(r=>r.recognition_id),['b','a','c']);assert.equal(Metrics.durationSummary(data).count,1);assert.equal(data.recognition_runs[0].recognition_id,'a');
});

