import sys
import unittest
from datetime import datetime
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from analytics import summarize, summarize_recognition, ZONE

NOW=datetime(2026,10,24,12,tzinfo=ZONE)
def event(i,at,user='one',kind='click',component='content_save',**extra):
    return dict(id=str(i),timestamp=at,user=user,device_id=user,session='s'+str(i),type=kind,component=component,**extra)

class RangeTest(unittest.TestCase):
    def test_inclusive_calendar_dates_distinct_users_and_unknown_days(self):
        events=[event(1,'2026-10-21T00:00:00+08:00'),event(2,'2026-10-21T23:59:59+08:00'),event(3,'2026-10-22T00:00:00+08:00'),event(4,'2026-10-24T10:00:00+08:00',kind='page_view',component='')]
        single=summarize(events,NOW,'2026-10-21','2026-10-21')
        self.assertEqual(single['components']['content_save']['period_clicks'],2)
        ranged=summarize(events,NOW,'2026-10-21','2026-10-24')
        c=ranged['components']['content_save']
        self.assertEqual((c['period_clicks'],c['period_users'],c['avg_clicks']),(3,1,1))
        self.assertEqual([d['clicks'] for d in c['trend']],[2,1,None,0])
        self.assertEqual((ranged['range']['observed_days'],ranged['range']['days']),(3,4))
        self.assertEqual(summarize(events,NOW)['components']['content_save']['period_clicks'],0)
    def test_duration_uses_end_day_and_weighted_mean(self):
        rows=[]
        for n,(start,end,ms) in enumerate([
            ('2026-10-21T23:59:55+08:00','2026-10-22T00:00:05+08:00',10000),
            ('2026-10-22T12:00:00+08:00','2026-10-22T12:00:10+08:00',10000),
            ('2026-10-23T12:00:00+08:00','2026-10-23T12:01:40+08:00',100000)]):
            rows += [event(f's{n}',start,component='recognition_toggle',action='recognition_start',recognition_id=f'r{n}',started_at=start),event(f'e{n}',end,kind='recognition_end',component='recognition_toggle',recognition_id=f'r{n}',started_at=start,ended_at=end,duration_ms=ms,end_reason='manual')]
        before=summarize_recognition(rows,NOW,'2026-10-21','2026-10-21')
        self.assertEqual(before['recognition_totals']['ended'],0)
        one=summarize_recognition(rows,NOW,'2026-10-22','2026-10-22')
        self.assertEqual(one['recognition_totals']['ended'],2)
        self.assertEqual(one['recognition_runs'][-1]['started_at'],'2026-10-21T23:59:55+08:00')
        all_days=summarize_recognition(rows,NOW,'2026-10-22','2026-10-23')
        self.assertEqual(all_days['recognition_totals']['average_duration_ms'],40000)
        self.assertEqual([d['average_duration_ms'] for d in all_days['recognition_daily']],[10000,100000])
    def test_invalid_ranges(self):
        for start,end in [('2026-10-24','2026-10-21'),('bad','2026-10-24'),('2026-10-24','2026-10-25')]:
            with self.assertRaises(ValueError): summarize([],NOW,start,end)

class RecognitionDetailTest(unittest.TestCase):
    def test_trace_link_and_pending_status_are_preserved_without_false_end(self):
        rows=[event('start','2026-10-24T11:59:58+08:00',component='recognition_toggle',action='recognition_start',recognition_id='live',trajectory_id='trace-live',started_at='2026-10-24T11:59:58+08:00'),event('old','2026-10-24T10:00:00+08:00',component='recognition_toggle',action='recognition_start',recognition_id='unknown',started_at='2026-10-24T10:00:00+08:00')]
        result=summarize_recognition(rows,NOW)
        runs={r['recognition_id']:r for r in result['recognition_runs']}
        self.assertEqual(runs['live']['trajectory_id'],'trace-live')
        self.assertEqual(runs['live']['status'],'running')
        self.assertEqual(runs['unknown']['status'],'unconfirmed')
        self.assertIsNone(runs['unknown']['ended_at'])
        self.assertIsNone(runs['unknown']['trajectory_id'])
        self.assertEqual(result['recognition_totals']['ended'],0)
