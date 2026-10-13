"""Local GET-only Java proxy; capture one real browser input, never run AI."""
import hashlib
import json
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

HERE = Path(__file__).parent
CAPTURE = HERE / 'stage6-reading-input-v13-request.json'
assert sys.argv[1:] in ([], ['observe-terminal-poll'])
observe_only = bool(sys.argv[1:])
STATE = HERE / ('stage6-research-poll-v13-proxy-after.json' if observe_only else 'stage6-reading-input-v13-proxy.json')
PDF = '803219bf205d0142621b1ac5339f8d918d3f883f814559f6336b8bfdec5ca634.pdf'
ORIGINS = {'http://127.0.0.1:5174', 'http://localhost:5174'}
lock = Lock()
stats = {'getRequests': [], 'blockedWrites': [], 'capturedTranslationInputs': 0,
         'forwardedWrites': 0, 'providerRequests': 0}


def save_stats():
    STATE.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding='utf-8')


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def respond(self, status, body, content_type='application/json'):
        self.send_response(status)
        if self.headers.get('Origin') in ORIGINS:
            self.send_header('Access-Control-Allow-Origin', self.headers['Origin'])
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS, POST, PUT, PATCH, DELETE')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.respond(204, b'')

    def do_GET(self):
        parsed = urlsplit(self.path)
        if parsed.path == '/capture-status':
            self.respond(200, json.dumps(stats).encode())
            return
        if not parsed.path.startswith('/api/') or self.headers.get('Origin') not in ORIGINS:
            self.respond(403, b'{"message":"GET outside verification scope"}')
            return
        try:
            with urlopen(Request('http://127.0.0.1:8081' + self.path, method='GET'), timeout=60) as upstream:
                body, status = upstream.read(), upstream.status
                content_type = upstream.headers.get('Content-Type', 'application/octet-stream')
        except HTTPError as error:
            body, status = error.read(), error.code
            content_type = error.headers.get('Content-Type', 'application/json')
        with lock:
            stats['getRequests'].append({'path': self.path, 'status': status, 'bytes': len(body),
                                         'sha256': hashlib.sha256(body).hexdigest()})
            save_stats()
        self.respond(status, body, content_type)

    def refuse_write(self):
        length = int(self.headers.get('Content-Length', '0'))
        if length > 5_000_000:
            self.respond(413, b'{}')
            return
        body = self.rfile.read(length)
        with lock:
            stats['blockedWrites'].append({'method': self.command, 'path': self.path})
            if (not observe_only and self.command == 'POST' and self.path == '/api/translate-page'
                    and self.headers.get('Origin') in ORIGINS and not CAPTURE.exists()):
                data = json.loads(body)
                assert data['pdfId'] == PDF and data['pageIndex'] == 3
                with CAPTURE.open('x', encoding='utf-8') as stream:
                    json.dump({'capturedAt': datetime.now(timezone.utc).isoformat(),
                               'origin': self.headers['Origin'], 'method': self.command,
                               'path': self.path, 'bodySha256': hashlib.sha256(body).hexdigest(),
                               'request': data}, stream, ensure_ascii=False, indent=2)
                stats['capturedTranslationInputs'] += 1
            save_stats()
        self.respond(409, json.dumps({'message': '验证请求已截取，未调用模型，未保存翻译。'}, ensure_ascii=False).encode())

    do_POST = do_PUT = do_PATCH = do_DELETE = refuse_write


assert observe_only or not CAPTURE.exists(), 'Capture already exists; do not repeat the browser input'
server = ThreadingHTTPServer(('127.0.0.1', 8092), Handler)
save_stats()
print('GET-only input capture listening on 127.0.0.1:8092', flush=True)
try:
    server.serve_forever()
finally:
    server.server_close()
