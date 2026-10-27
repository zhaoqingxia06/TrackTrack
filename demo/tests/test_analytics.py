import sys
import unittest
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analytics import summarize, summarize_recognition, ZONE

class AnalyticsTest(unittest.TestCase):
    def test_users_clicks_paths_and_history(self):
        rows=[]
        def event(user, session, kind, component='', day='24'):
            rows.append(dict(id=str(len(rows)), user=user, session=session, type=kind, component=component,
                             timestamp=f'2026-10-{day}T10:00:00+08:00', value=True))
        event('one','s1','page_view')
        event('one','s1','click','detail')
        event('one','s1','state_change','detail')
        event('one','s1','click','detail')
        event('one','s1','session_end')
        event('one','s2','page_view')
        event('one','s2','click','save')
        event('two','s3','page_view')
        event('two','s3','click','save')
        event('old','old','click','detail','23')
        r=summarize(rows, datetime(2026,10,24,12,tzinfo=ZONE))
        self.assertEqual((r['components']['detail']['today_users'],r['components']['detail']['today_clicks']),(1,2))
        self.assertEqual((r['daily'][-1]['users'],r['daily'][-1]['views'],r['daily'][-1]['clicks']),(2,3,4))
        save=next(p for p in r['paths'] if p['steps']==['进入页面','收藏'])
        self.assertEqual((save['users'],save['count']),(2,2))
        self.assertEqual(r['components']['detail']['avg_clicks'],2.0)
        self.assertEqual(len(r['components']['detail']['click_times']),2)
        self.assertTrue(all(t.startswith('2026-10-24') for t in r['components']['detail']['click_times']))
        detail=next(p for p in r['paths'] if len(p['steps'])==3)
        self.assertTrue(detail['sessions'][0]['ended'])
    def test_recognition_transitions_are_separate_and_legacy_not_inferred(self):
        actions=['', 'recognition_start','recognition_stop','recognition_start']
        events=[dict(id=str(i),user='one',session='s1',type='click',component='recognition_toggle',action=a,timestamp=f'2026-10-24T10:00:0{i}+08:00') for i,a in enumerate(actions)]
        r=summarize(events,datetime(2026,10,24,12,tzinfo=ZONE))
        c=r['components']['recognition_toggle']
        self.assertEqual(c['today_clicks'],4)
        self.assertEqual(c['actions']['recognition_start']['today_clicks'],2)
        self.assertEqual(c['actions']['recognition_stop']['today_clicks'],1)
        self.assertEqual(c['actions']['recognition_start']['today_users'],1)
        self.assertEqual(c['unclassified_clicks'],1)
        self.assertEqual(r['paths'][0]['steps'],['进入页面','识别按钮','启动识别','关闭识别','启动识别'])
    def test_duration_matching_exit_and_missing_end(self):
        def e(i,run,kind,action='',at='2026-10-24T10:00:00+08:00',**extra):
            return dict(id=i,user='one',device_id='one',session='s',recognition_id=run,type=kind,component='recognition_toggle',action=action,timestamp=at,started_at='2026-10-24T10:00:00+08:00',**extra)
        rows=[e('a','r1','click','recognition_start'),e('b','r1','recognition_end',at='2026-10-24T10:00:03+08:00',ended_at='2026-10-24T10:00:03+08:00',duration_ms=3000,end_reason='manual'),e('c','r1','recognition_end',duration_ms=9999,end_reason='exit'),e('d','r2','click','recognition_start'),e('e','r2','recognition_end',at='2026-10-24T10:00:05+08:00',ended_at='2026-10-24T10:00:05+08:00',duration_ms=5000,end_reason='exit'),e('f','r3','click','recognition_start')]
        result=summarize_recognition(rows,datetime(2026,10,24,11,tzinfo=ZONE))
        self.assertEqual(result['recognition_totals'],dict(ended=2,total_duration_ms=8000,average_duration_ms=4000,users=1,unfinished=1))
        self.assertEqual(next(r for r in result['recognition_runs'] if r['recognition_id']=='r3')['status'],'unconfirmed')
        self.assertEqual(summarize(rows,datetime(2026,10,24,11,tzinfo=ZONE))['components']['recognition_toggle']['today_clicks'],3)
    def test_empty_history(self):
        r=summarize([],datetime(2026,10,24,tzinfo=ZONE))
        self.assertEqual(r['paths'],[])
        self.assertEqual(r['components']['save']['observed_days'],0)

if __name__=='__main__': unittest.main()
