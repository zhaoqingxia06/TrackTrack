from collections import defaultdict
from datetime import datetime, timedelta, date, time
from zoneinfo import ZoneInfo

ZONE = ZoneInfo('Asia/Shanghai')
LABELS = {'detail': '查看介绍', 'save': '收藏', 'transcript_tab': '转写 Tab', 'summary_tab': '摘要 Tab', 'recognition_toggle': '识别按钮', 'content_save': '保存'}

def window(now=None, start_date=None, end_date=None):
    now = now or datetime.now(ZONE)
    start = date.fromisoformat(start_date) if start_date else now.date()
    end = date.fromisoformat(end_date) if end_date else now.date()
    if start > end or end > now.date() or (end-start).days > 3660:
        raise ValueError('日期范围无效：开始不得晚于结束，结束不得晚于今天，最长10年')
    lower = datetime.combine(start, time.min, ZONE)
    upper = min(datetime.combine(end+timedelta(days=1), time.min, ZONE), now)
    days = [(start+timedelta(days=i)).isoformat() for i in range((end-start).days+1)]
    return now, lower, upper, days

def event_time(e):
    return datetime.fromisoformat(e['timestamp']).astimezone(ZONE)

def in_window(at, lower, upper, now):
    return lower <= at <= upper if upper == now else lower <= at < upper

def summarize(events, now=None, start_date=None, end_date=None):
    now, lower, upper, days = window(now, start_date, end_date)
    selected = [e for e in events if in_window(event_time(e), lower, upper, now)]
    selected.sort(key=event_time)
    observed = {event_time(e).date().isoformat() for e in selected}
    daily = {d: {'users': set(), 'views': 0, 'clicks': 0} for d in days}
    components = {key: [] for key in LABELS}
    sessions = defaultdict(list)
    for e in selected:
        day = event_time(e).date().isoformat()
        if e['type'] in ('page_view', 'click'): daily[day]['users'].add(e['user'])
        if e['type'] == 'page_view': daily[day]['views'] += 1
        if e['type'] == 'click':
            daily[day]['clicks'] += 1
            components[e['component']].append(e)
        sessions[e['session']].append(e)

    def stats(rows):
        by_day = {d: [] for d in days}
        for e in rows: by_day[event_time(e).date().isoformat()].append(e)
        records = [{'record_id': e['id'], 'event_id': e.get('event_id',''), 'device_id': e.get('device_id',e['user']), 'timestamp': e['timestamp']} for e in reversed(rows)]
        return {'period_clicks': len(rows), 'period_users': len({e['user'] for e in rows}),
                # Compatibility with the original today-only client.
                'today_clicks': len(rows), 'today_users': len({e['user'] for e in rows}),
                'click_times': [r['timestamp'] for r in records], 'click_records': records,
                'avg_clicks': round(len(rows)/len(observed),2) if observed else None,
                'observed_days': len(observed),
                'trend': [{'date': d, 'clicks': len(by_day[d]) if d in observed else None,
                           'users': len({e['user'] for e in by_day[d]}) if d in observed else None} for d in days]}
    result = {key: {'name': LABELS[key], **stats(rows)} for key, rows in components.items()}
    result['recognition_toggle']['actions'] = {action: stats([e for e in components['recognition_toggle'] if e.get('action') == action]) for action in ('recognition_start','recognition_stop')}
    result['recognition_toggle']['unclassified_clicks'] = sum(not e.get('action') for e in components['recognition_toggle'])
    groups = {}
    for sid, rows in sessions.items():
        clicks = [e for e in rows if e['type']=='click']
        route = ['进入页面'] + [{'recognition_start':'启动识别','recognition_stop':'关闭识别'}.get(e.get('action'),LABELS[e['component']]) for e in clicks]
        group = groups.setdefault(tuple(route), {'steps':route,'users':set(),'count':0,'sessions':[]})
        group['users'].add(rows[0]['user']); group['count'] += 1
        group['sessions'].append({'session':sid,'user':rows[0]['user'],'events':rows,'ended':any(e['type']=='session_end' for e in rows)})
    return {'today':now.date().isoformat(),'range':{'start':days[0],'end':days[-1],'days':len(days),'observed_days':len(observed)},
            'components':result,'paths':[{**g,'users':len(g['users'])} for g in groups.values()],
            'daily':[{'date':d,'users':len(daily[d]['users']) if d in observed else None,
                      'views':daily[d]['views'] if d in observed else None,'clicks':daily[d]['clicks'] if d in observed else None} for d in days],
            'recent':list(reversed(selected[-35:])),'total_events':len(selected)}

def summarize_recognition(events, now=None, start_date=None, end_date=None):
    now, lower, upper, days = window(now,start_date,end_date)
    groups = defaultdict(list)
    for e in events:
        if e.get('recognition_id'):
            groups[(e.get('device_id',e['user']),e['recognition_id'])].append(e)
    runs=[]
    for (device,run_id), rows in groups.items():
        start=next((e for e in rows if e.get('action')=='recognition_start'),None)
        if not start:
            start=next((e for e in rows if e['type']=='recognition_active' and e.get('started_at')),None)
        if not start: continue
        end=next((e for e in rows if e['type']=='recognition_end' and e.get('ended_at') and e.get('duration_ms') is not None),None)
        started=start.get('started_at',start['timestamp'])
        last=max(rows,key=event_time)
        at=datetime.fromisoformat(end['ended_at']) if end else event_time(last)
        if not in_window(at,lower,upper,now): continue
        age=(now-event_time(last)).total_seconds()
        status='ended' if end else 'running' if age<=15 else 'unconfirmed'
        runs.append({'recognition_id':run_id,'device_id':device,'started_at':started,
                     'ended_at':end['ended_at'] if end else None,
                     'duration_ms':end['duration_ms'] if end else max(e.get('duration_ms',0) for e in rows),
                     'end_reason':end.get('end_reason') if end else None,'status':status,
                     'end_record_id':end['id'] if end else None,
                     'trajectory_id':start.get('trajectory_id') or (end.get('trajectory_id') if end else None),
                     'last_observed_at':last['timestamp']})
    runs.sort(key=lambda r:r['started_at'],reverse=True)
    complete=[r for r in runs if r['status']=='ended']
    daily=[]
    observed={event_time(e).date().isoformat() for e in events if in_window(event_time(e),lower,upper,now)}
    for d in days:
        ended=[r for r in complete if datetime.fromisoformat(r['ended_at']).astimezone(ZONE).date().isoformat()==d]
        total=sum(r['duration_ms'] for r in ended)
        daily.append({'date':d,'ended':len(ended) if d in observed else None,'average_duration_ms':round(total/len(ended)) if ended else None})
    return {'recognition_runs':runs,'recognition_daily':daily,'recognition_totals':{'ended':len(complete),
            'unfinished':len(runs)-len(complete),'users':len({r['device_id'] for r in complete}),
            'total_duration_ms':sum(r['duration_ms'] for r in complete),
            'average_duration_ms':round(sum(r['duration_ms'] for r in complete)/len(complete)) if complete else None}}


def summarize_trajectories(events, now=None, start_date=None, end_date=None):
    """Reconstruct one durable record per visit; group completed identical sequences.

    Only new explicitly identified visits qualify. Never infer old session boundaries.
    Arrival/retry order does not affect the client sequence within a visit.
    """
    import hashlib
    import json
    now, lower, upper, _ = window(now, start_date, end_date)
    visits = defaultdict(dict)
    for e in events:
        if e.get('trajectory_id') and isinstance(e.get('trajectory_seq'), int):
            visits[(e.get('device_id', e['user']), e['trajectory_id'])][e['id']] = e
    traces = []
    action_names = {'recognition_start':'开始识别','recognition_stop':'关闭识别'}
    for (device, tid), unique in visits.items():
        rows = sorted(unique.values(), key=lambda e:(e['trajectory_seq'], event_time(e)))
        entry = next((e for e in rows if e['type']=='page_view'), None)
        if not entry or not in_window(event_time(entry), lower, upper, now):
            continue
        rows = [e for e in rows if e['trajectory_seq']>=entry['trajectory_seq']]
        end = next((e for e in rows if e['type']=='session_end'), None)
        if end:
            rows = [e for e in rows if e['trajectory_seq']<=end['trajectory_seq']]
        last = max(rows, key=event_time)
        status = 'ended' if end else 'running' if (now-event_time(last)).total_seconds()<=20 else 'unconfirmed'
        steps = []
        signature = []
        for e in rows:
            if e['type'] not in ('page_view','click','session_end'):
                continue
            if e['type']=='page_view':
                label='进入 · '+('摘要' if e.get('page_id')=='summary' else '转写')
                signature.append((e['event_id'], e.get('page_id','transcript')))
            elif e['type']=='session_end':
                label='退出';signature.append((e['event_id'],))
            else:
                label=action_names.get(e.get('action')) or {'transcript_tab':'点击转写','summary_tab':'点击摘要','content_save':'点击保存'}.get(e['component'],LABELS.get(e['component'],e['component']))
                signature.append((e['event_id'],))
            step={'label':label,'event_id':e['event_id'],'record_id':e['id'],'timestamp':e['timestamp']}
            if e.get('action')=='recognition_start':
                recognition_end=next((r for r in rows if r['type']=='recognition_end' and r.get('recognition_id')==e.get('recognition_id')),None)
                if recognition_end:step['recognition_duration_ms']=recognition_end['duration_ms']
            steps.append(step)
        group_id=hashlib.sha256(json.dumps(signature,ensure_ascii=False).encode()).hexdigest()[:16]
        traces.append({'trajectory_id':tid,'device_id':device,'started_at':entry['timestamp'],
                       'ended_at':end.get('ended_at',end['timestamp']) if end else None,
                       'last_observed_at':last['timestamp'],'duration_ms':end.get('duration_ms') if end else None,
                       'status':status,'steps':steps,'step_count':sum(e['type']=='click' for e in rows),'group_id':group_id})
    traces.sort(key=lambda t:t['started_at'],reverse=True)
    groups = {}
    for trace in traces:
        if trace['status']!='ended':continue
        g=groups.setdefault(trace['group_id'],{'group_id':trace['group_id'],'steps':[s['label'] for s in trace['steps']],
                                             'count':0,'step_count':trace['step_count'],'device_ids':set(),'records':[]})
        g['count']+=1;g['device_ids'].add(trace['device_id']);g['records'].append(trace)
    return {'trajectories':traces,'trajectory_groups':[
        {**g,'users':len(g['device_ids']),'device_ids':sorted(g['device_ids'])} for g in groups.values()],
        'trajectory_totals':{'records':len(traces),'ended':sum(t['status']=='ended' for t in traces),
                             'running':sum(t['status']=='running' for t in traces),
                             'unconfirmed':sum(t['status']=='unconfirmed' for t in traces)}}


def summarize_dashboard(events, now=None, start_date=None, end_date=None):
    """Observed browser identities; does not infer people or pre-collection history."""
    now, lower, upper, days = window(now, start_date, end_date)
    eligible = [e for e in events if e['type'] in ('page_view', 'click') and event_time(e) <= now]
    first = {}
    for e in eligible:
        identity = e.get('device_id') or e.get('user')
        if not identity: continue
        at = event_time(e)
        if identity not in first or at < first[identity]: first[identity] = at
    selected = [e for e in eligible if in_window(event_time(e), lower, upper, now)]
    observed = {event_time(e).date().isoformat() for e in selected}
    daily = []
    for day in days:
        users = {e.get('device_id') or e.get('user') for e in selected if event_time(e).date().isoformat() == day}
        daily.append({'date':day, 'active':len(users) if day in observed else None})
    # The overview always uses today, independent of the shared analysis filter.
    today = now.date()
    recent = []
    for offset in range(6, -1, -1):
        day = today - timedelta(days=offset)
        identities = {e.get('device_id') or e.get('user') for e in eligible
                      if event_time(e).date() == day and (e.get('device_id') or e.get('user'))}
        recent.append({'date': day.isoformat(), 'active': len(identities) if identities else None})
    annual = {e.get('device_id') or e.get('user') for e in eligible
              if event_time(e).date().year == today.year and (e.get('device_id') or e.get('user'))}
    today_first = sum(at.date() == today for at in first.values()) if recent[-1]['active'] is not None else None
    # One observed entry per identified trajectory. Missing IDs cannot be deduplicated.
    entries = {}
    unidentified = []
    for e in eligible:
        if e['type'] != 'page_view': continue
        identity = e.get('device_id') or e.get('user')
        tid = e.get('trajectory_id')
        if not identity or not tid:
            unidentified.append(e)
            continue
        key = (identity, tid)
        if key not in entries or event_time(e) < event_time(entries[key]): entries[key] = e
    starts = list(entries.values())
    for day in recent:
        date_value = date.fromisoformat(day['date'])
        day_starts = [e for e in starts if event_time(e).date() == date_value]
        day_unknown = any(event_time(e).date() == date_value for e in unidentified)
        day['visits'] = len(day_starts) if day_starts else None
        day['visits_partial'] = day_unknown
    year_starts = [e for e in starts if event_time(e).year == today.year]
    year_unknown = any(event_time(e).year == today.year for e in unidentified)
    today_visits = recent[-1]['visits']
    today_per_user = round(today_visits / recent[-1]['active'], 2) if today_visits is not None and recent[-1]['active'] else None
    return {'dashboard':{'daily':daily, 'period_active':len({e.get('device_id') or e.get('user') for e in selected}) if selected else None,
                         'first_observed':sum(in_window(at, lower, upper, now) for at in first.values()) if selected else None,
                         'coverage_start':min((event_time(e) for e in eligible), default=None).isoformat() if eligible else None,
                         'today_active':recent[-1]['active'], 'today_first_observed':today_first,
                         'year_active':len(annual) if annual else None, 'recent_daily':recent,
                         'today_visits':today_visits, 'today_visits_per_user':today_per_user,
                         'year_visits':len(year_starts) if year_starts else None, 'year_visits_partial':year_unknown}}
