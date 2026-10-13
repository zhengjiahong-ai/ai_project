from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

from core.rate_limiter import RateLimiterMiddleware, _route_bucket


def test_read_only_polling_does_not_consume_research_creation_quota():
    app = FastAPI()
    app.add_middleware(RateLimiterMiddleware)
    @app.get('/api/research-tasks/r')
    def read():
        return {'status': 'completed'}
    @app.post('/api/research-tasks')
    def start():
        return {'status': 'queued'}
    with TestClient(app) as client:
        assert all(client.get('/api/research-tasks/r').status_code == 200 for _ in range(65))
        assert client.post('/api/research-tasks').status_code == 200
        assert any(client.post('/api/research-tasks').status_code == 429 for _ in range(8))


def test_mutations_and_source_export_keep_explicit_bounded_buckets():
    def bucket(method, path):
        return _route_bucket(Request({'type': 'http', 'method': method, 'path': path, 'headers': []}))
    assert bucket('GET', '/api/research-tasks/r/sources/s/export') == 'status'
    assert bucket('POST', '/api/research-tasks') == 'agent'
    assert bucket('POST', '/api/research-tasks/r/cancel') == 'global'
    assert bucket('POST', '/api/chat') == 'chat'
