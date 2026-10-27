import argparse
import json
import sqlite3
import threading
import uuid
import math
from http.cookies import SimpleCookie
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from analytics import summarize, summarize_recognition, summarize_trajectories, summarize_dashboard, ZONE, LABELS

ROOT = Path(__file__).parent
LOCK = threading.Lock()

EVENT_IDS = {'transcript_tab': 'voice.transcript.open', 'summary_tab': 'voice.summary.open', 'content_save': 'voice.content.save'}
SYSTEM_IDS = {'recognition_end': 'voice.recognition.end', 'recognition_active': 'voice.recognition.active'}
ACTION_IDS = {'recognition_start': 'voice.recognition.start', 'recognition_stop': 'voice.recognition.stop'}

class Handler(BaseHTTPRequestHandler):
    def device(self):
        cookie = SimpleCookie(self.headers.get('Cookie', ''))
        value = cookie.get('trail_device')
        try:
            return str(uuid.UUID(value.value)) if value else str(uuid.uuid4())
        except ValueError:
            return str(uuid.uuid4())

    def reply(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        if hasattr(self, 'device_id'):
            self.send_header('Set-Cookie', f'trail_device={self.device_id}; Path=/; Max-Age=31536000; HttpOnly; SameSite=Strict')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/api/device':
            self.device_id = self.device()
            return self.reply(200, {'device_id': self.device_id, 'scope': 'browser'})
        if path == '/api/plan':
            return self.reply(200, json.loads((ROOT/'event-plan.json').read_text()))
        if path == '/api/stats':
            with LOCK, sqlite3.connect(self.server.db) as db:
                events = [json.loads(r[0]) for r in db.execute('SELECT payload FROM events ORDER BY seq')]
            active = [e for e in events if e.get('identity_version') == 2]
            query = parse_qs(urlparse(self.path).query)
            start = query.get('start', [None])[0]; end = query.get('end', [None])[0]
            try:
                now = datetime.now(ZONE)
                result = summarize(active, now, start, end)
                result.update(summarize_recognition(active, now, start, end))
                result.update(summarize_trajectories(active, now, start, end))
                result.update(summarize_dashboard(active, now, start, end))
            except ValueError as error:
                return self.reply(400, {'error': str(error)})
            result['archived_events'] = len(events) - len(active)
            return self.reply(200, result)
        names = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'), '/analysis-metrics.js': ('analysis-metrics.js', 'text/javascript'), '/product': ('product.html', 'text/html'), '/product.js': ('product.js', 'text/javascript'), '/product.css': ('product.css', 'text/css'), '/tracker.js': ('tracker.js', 'text/javascript'), '/style.css': ('style.css', 'text/css')}
        if path not in names: return self.reply(404, {'error': 'Not found'})
        name, mime = names[path]; body = (ROOT/'static'/name).read_bytes()
        self.send_response(200); self.send_header('Content-Type', mime+'; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_POST(self):
        if self.path != '/api/events': return self.reply(404, {'error': 'Not found'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 4096: raise ValueError()
            raw = json.loads(self.rfile.read(size))
            for key in ('id', 'user', 'session'):
                if not isinstance(raw.get(key), str) or not 1 <= len(raw[key]) <= 80: raise ValueError()
            kind = raw.get('type')
            if kind not in ('page_view', 'click', 'state_change', 'session_end', 'session_active', 'recognition_end', 'recognition_active'): raise ValueError()
            component = raw.get('component', '')
            if kind in ('click', 'state_change', 'recognition_end', 'recognition_active') and component not in LABELS: raise ValueError()
            if kind == 'state_change' and not isinstance(raw.get('value'), bool): raise ValueError()
            action = raw.get('action', '')
            if not isinstance(action, str): raise ValueError()
            if action and (kind != 'click' or component != 'recognition_toggle' or action not in ('recognition_start', 'recognition_stop')): raise ValueError()
            event_id = raw.get('event_id', '')
            expected = {'session_end':'voice.session.end','session_active':'voice.session.active'}.get(kind) or SYSTEM_IDS.get(kind) or ('voice.page.view' if kind == 'page_view' else ACTION_IDS.get(action) if component == 'recognition_toggle' else EVENT_IDS.get(component))
            if event_id and event_id != expected: raise ValueError()
            current = bool(event_id and event_id == expected)
            self.device_id = self.device()
            extra = {}
            for field in ('recognition_id','trajectory_id'):
                if field in raw:
                    if not isinstance(raw[field], str) or not 1 <= len(raw[field]) <= 80: raise ValueError()
                    extra[field] = raw[field]
            if 'trajectory_id' in raw:
                seq=raw.get('trajectory_seq')
                if isinstance(seq,bool) or not isinstance(seq,int) or seq<0 or seq>10000000: raise ValueError()
                if raw['trajectory_id'] != raw['session']: raise ValueError()
                if raw.get('page_id') not in ('transcript','summary'): raise ValueError()
                extra.update(trajectory_seq=seq,page_id=raw['page_id'])
            if kind in ('session_end','session_active') and 'trajectory_id' not in extra: raise ValueError()
            for field in ('occurred_at', 'started_at', 'ended_at'):
                if field in raw:
                    parsed = datetime.fromisoformat(raw[field])
                    if parsed.tzinfo is None: raise ValueError()
                    extra[field] = parsed.astimezone(ZONE).isoformat()
            if 'duration_ms' in raw:
                duration = raw['duration_ms']
                if isinstance(duration, bool) or not isinstance(duration, (int,float)) or not math.isfinite(duration) or duration < 0: raise ValueError()
                extra['duration_ms'] = round(duration)
            if kind in SYSTEM_IDS:
                if component != 'recognition_toggle' or not all(f in extra for f in ('recognition_id','started_at','duration_ms')): raise ValueError()
            if kind == 'recognition_end':
                if raw.get('end_reason') not in ('manual','exit') or 'ended_at' not in extra: raise ValueError()
                if extra['ended_at'] < extra['started_at']: raise ValueError()
                extra['end_reason'] = raw['end_reason']
            if kind == 'session_end':
                if raw.get('end_reason')!='exit' or not all(f in extra for f in ('started_at','ended_at','duration_ms')): raise ValueError()
                if extra['ended_at']<extra['started_at']: raise ValueError()
                extra['end_reason']='exit'
            event = {k: raw[k] for k in ('id', 'user', 'session')}
            if current: event['user'] = self.device_id
            event.update(event_id=event_id, device_id=self.device_id if current else raw['user'], identity_version=2 if current else 1)
            event.update(type=kind, component=component if kind in ('click', 'state_change', 'recognition_end', 'recognition_active') else '',
                         action=action, value=raw.get('value') if kind == 'state_change' else None,
                         timestamp=extra.get('occurred_at',datetime.now(ZONE).isoformat()),received_at=datetime.now(ZONE).isoformat())
            event.update(extra)
            with LOCK, sqlite3.connect(self.server.db) as db:
                db.execute('INSERT OR IGNORE INTO events(id,payload) VALUES (?,?)', (event['id'], json.dumps(event, ensure_ascii=False)))
            return self.reply(200, {'ok': True, 'id': event['id']})
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            return self.reply(400, {'error': '事件格式无效'})

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8767)
    parser.add_argument('--db', default=str(ROOT/'data'/'events.sqlite'))
    args = parser.parse_args()
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(args.db) as db:
        db.execute('CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT UNIQUE,payload TEXT NOT NULL)')
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    server.db = args.db
    print(f'Local: http://127.0.0.1:{args.port}', flush=True)
    server.serve_forever()
