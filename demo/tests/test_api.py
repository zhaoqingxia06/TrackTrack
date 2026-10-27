import json
import sqlite3
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen, build_opener, HTTPCookieProcessor
from http.cookiejar import CookieJar
from urllib.error import HTTPError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server import Handler, ThreadingHTTPServer

class APITest(unittest.TestCase):
    def test_persistence_retry_dedup_and_invalid_event(self):
        with tempfile.TemporaryDirectory() as folder:
            dbpath=str(Path(folder)/'events.sqlite')
            with sqlite3.connect(dbpath) as db:
                db.execute('CREATE TABLE events(seq INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT UNIQUE,payload TEXT NOT NULL)')
            server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            server.db=dbpath
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            base=f'http://127.0.0.1:{server.server_port}'
            try:
                opener=build_opener(HTTPCookieProcessor(CookieJar()))
                with opener.open(base+'/api/device') as r: device=json.load(r)['device_id']
                e=dict(id='retry-same-id',event_id='voice.summary.open',user='untrusted-user',session='s1',type='click',component='summary_tab')
                for _ in range(2):
                    with opener.open(Request(base+'/api/events',data=json.dumps(e).encode(),headers={'Content-Type':'application/json'})) as r:
                        self.assertEqual(r.status,200)
                with urlopen(base+'/api/stats') as r:
                    data=json.load(r)
                self.assertEqual(data['total_events'],1)
                e.update(id='second-id',user='different-client-value')
                with opener.open(Request(base+'/api/events',data=json.dumps(e).encode())) as r: self.assertEqual(r.status,200)
                with opener.open(base+'/api/stats') as r: updated=json.load(r)
                self.assertEqual(updated['components']['summary_tab']['today_users'],1)
                self.assertEqual(updated['components']['summary_tab']['today_clicks'],2)
                records=updated['components']['summary_tab']['click_records']
                self.assertEqual(len(set(r['record_id'] for r in records)),2)
                self.assertEqual(set(r['device_id'] for r in records),{device})
                self.assertEqual(set(r['event_id'] for r in records),{'voice.summary.open'})
                with opener.open(base+'/api/device') as r: self.assertEqual(json.load(r)['device_id'],device)
                self.assertEqual(data['components']['summary_tab']['today_clicks'],1)
                with sqlite3.connect(dbpath) as db:
                    self.assertEqual(db.execute('SELECT COUNT(*) FROM events').fetchone()[0],2)
                from datetime import datetime, timezone
                now=datetime.now(timezone.utc).isoformat()
                trace=dict(id='trace-entry',event_id='voice.page.view',user='untrusted',session='visit',trajectory_id='visit',trajectory_seq=0,page_id='transcript',type='page_view',occurred_at=now,started_at=now)
                with opener.open(Request(base+'/api/events',data=json.dumps(trace).encode())) as r:self.assertEqual(r.status,200)
                trace.update(id='trace-end',event_id='voice.session.end',type='session_end',trajectory_seq=1,ended_at=now,duration_ms=0,end_reason='exit')
                for _ in range(2):
                    with opener.open(Request(base+'/api/events',data=json.dumps(trace).encode())) as r:self.assertEqual(r.status,200)
                with opener.open(base+'/api/stats') as r:journeys=json.load(r)
                self.assertEqual(journeys['trajectory_totals']['ended'],1)
                self.assertEqual(journeys['trajectory_groups'][0]['count'],1)
                self.assertEqual(journeys['trajectories'][0]['device_id'],device)
                trace.update(id='invalid-seq',trajectory_seq=True)
                with self.assertRaises(HTTPError) as caught:
                    opener.open(Request(base+'/api/events',data=json.dumps(trace).encode()))
                self.assertEqual(caught.exception.code,400);caught.exception.close()
                e['component']='invalid'
                with self.assertRaises(HTTPError) as caught:
                    urlopen(Request(base+'/api/events',data=json.dumps(e).encode()))
                self.assertEqual(caught.exception.code,400)
                caught.exception.close()
                with self.assertRaises(HTTPError) as caught:
                    urlopen(base+'/data/events.sqlite')
                self.assertEqual(caught.exception.code,404)
                caught.exception.close()
            finally:
                server.shutdown();server.server_close();thread.join()
