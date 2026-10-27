import sys
import unittest
from pathlib import Path
from datetime import datetime
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from analytics import summarize_trajectories, ZONE

NOW=datetime(2026,10,24,12,tzinfo=ZONE)

def visit(tid,user='device-a',day='2026-10-24',complete=True,action='summary_tab'):
    start=f'{day}T10:00:00+08:00'
    base=dict(trajectory_id=tid,session=tid,user=user,device_id=user,page_id='transcript')
    rows=[dict(base,id=tid+'-0',type='page_view',event_id='voice.page.view',timestamp=start,trajectory_seq=0)]
    if action:
        rows.append(dict(base,id=tid+'-1',type='click',component=action,event_id={'summary_tab':'voice.summary.open','transcript_tab':'voice.transcript.open'}[action],timestamp=f'{day}T10:00:01+08:00',trajectory_seq=1))
    if complete:
        rows.append(dict(base,id=tid+'-2',type='session_end',event_id='voice.session.end',timestamp=f'{day}T10:00:02+08:00',ended_at=f'{day}T10:00:02+08:00',duration_ms=2000,trajectory_seq=2))
    return rows

class TrajectoryTest(unittest.TestCase):
    def test_group_counts_users_retry_order_and_retained_records(self):
        rows=visit('one')+visit('two')+visit('three','device-b')
        # Duplicated deliveries and reverse arrival must preserve one record and order.
        result=summarize_trajectories(list(reversed(rows))+rows[:1],NOW)
        self.assertEqual(len(result['trajectories']),3)
        group=result['trajectory_groups'][0]
        self.assertEqual((group['count'],group['users']),(3,2))
        self.assertEqual(group['steps'],['进入 · 转写','点击摘要','退出'])
        self.assertEqual(group['step_count'],1)
        self.assertEqual(len(group['records']),3)
        self.assertEqual(len({r['trajectory_id'] for r in group['records']}),3)

    def test_incomplete_legacy_and_page_order_do_not_merge(self):
        rows=visit('ended')+visit('other',action='transcript_tab')+visit('unknown',complete=False)
        running=visit('running',complete=False)
        for r in running:r['timestamp']='2026-10-24T11:59:59+08:00'
        legacy=visit('legacy')
        for r in legacy:r.pop('trajectory_id')
        result=summarize_trajectories(rows+running+legacy,NOW)
        self.assertEqual(result['trajectory_totals'],dict(records=4,ended=2,running=1,unconfirmed=1))
        self.assertEqual(len(result['trajectory_groups']),2)
        self.assertTrue(all(t['ended_at'] is None and t['duration_ms'] is None for t in result['trajectories'] if t['status']!='ended'))

    def test_entry_date_retains_full_cross_day_visit(self):
        rows=visit('cross',day='2026-10-23')
        rows[-1].update(timestamp='2026-10-24T00:01:00+08:00',ended_at='2026-10-24T00:01:00+08:00')
        yesterday=summarize_trajectories(rows,NOW,'2026-10-23','2026-10-23')
        today=summarize_trajectories(rows,NOW,'2026-10-24','2026-10-24')
        self.assertEqual(yesterday['trajectory_totals']['ended'],1)
        self.assertEqual(yesterday['trajectories'][0]['steps'][-1]['timestamp'],rows[-1]['timestamp'])
        self.assertEqual(today['trajectory_totals']['records'],0)

    def test_heartbeats_and_recognition_end_are_not_extra_actions(self):
        rows=visit('run')
        rows[1].update(component='recognition_toggle',action='recognition_start',event_id='voice.recognition.start',recognition_id='recognition')
        rows.insert(2,dict(rows[1],id='active',type='session_active',event_id='voice.session.active',trajectory_seq=2))
        rows.insert(3,dict(rows[1],id='recognition-end',type='recognition_end',event_id='voice.recognition.end',duration_ms=900,trajectory_seq=3))
        rows[-1]['trajectory_seq']=4
        trace=summarize_trajectories(rows,NOW)['trajectories'][0]
        self.assertEqual(len(trace['steps']),3)
        self.assertEqual(trace['step_count'],1)
        self.assertEqual(trace['steps'][1]['recognition_duration_ms'],900)

    def test_two_clicks_are_two_steps_not_entry_exit_or_heartbeats(self):
        rows=visit('steps')
        save=dict(rows[1],id='save',component='content_save',event_id='voice.content.save',trajectory_seq=2)
        rows[-1]['trajectory_seq']=3
        rows.insert(2,save)
        result=summarize_trajectories(rows,NOW)
        self.assertEqual(result['trajectories'][0]['step_count'],2)
        self.assertEqual(result['trajectory_groups'][0]['step_count'],2)
        self.assertEqual(len(result['trajectories'][0]['steps']),4)

if __name__=='__main__':unittest.main()
