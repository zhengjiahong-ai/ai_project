import hashlib
import json
import sqlite3

import pytest

from services.deep_research.backup import create_backup, restore_backup, verify_backup


@pytest.fixture
def data(tmp_path):
    database = tmp_path / 'live.sqlite3'
    sources = tmp_path / 'sources'
    sources.mkdir()
    body = b'%PDF-authorized-public-source'
    digest = hashlib.sha256(body).hexdigest()
    (sources / (digest + '.pdf')).write_bytes(body)
    payload = {'state': {'sources': [{'sourceKind': 'arxiv', 'accessLevel': 'fulltext', 'contentHash': digest}]}}
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE deep_research_runs_v2 (status TEXT, payload TEXT)')
        db.execute('INSERT INTO deep_research_runs_v2 VALUES (?, ?)', ('completed', json.dumps(payload)))
    with sqlite3.connect(str(database) + '.checkpoints') as db:
        db.execute('CREATE TABLE checkpoint (value TEXT)')
        db.execute("INSERT INTO checkpoint VALUES ('saved state')")
    return database, sources, tmp_path / 'backup'


def test_roundtrip_preserves_checkpoint_and_source_identity(data, tmp_path):
    manifest = create_backup(*data, services_stopped=True)
    assert manifest['runCount'] == 1 and len(manifest['files']) == 3
    assert restore_backup(data[2], tmp_path / 'restored') == manifest
    with sqlite3.connect(tmp_path / 'restored/research.sqlite3.checkpoints') as db:
        assert db.execute('SELECT value FROM checkpoint').fetchone()[0] == 'saved state'
    with pytest.raises(FileExistsError):
        restore_backup(data[2], tmp_path / 'restored')


def test_requires_stopped_services_and_no_active_runs(data):
    with pytest.raises(ValueError, match='Stop the Python'):
        create_backup(*data)
    with sqlite3.connect(data[0]) as db:
        db.execute("UPDATE deep_research_runs_v2 SET status='running'")
    with pytest.raises(ValueError, match='Active runs'):
        create_backup(*data, services_stopped=True)
    assert not data[2].exists()


def test_missing_referenced_pdf_refuses_incomplete_backup(data):
    next(data[1].glob('*.pdf')).unlink()
    with pytest.raises(ValueError, match='missing or has changed'):
        create_backup(*data, services_stopped=True)
    assert not data[2].exists()


def test_tampered_file_refuses_restore_before_creating_destination(data, tmp_path):
    create_backup(*data, services_stopped=True)
    next((data[2] / 'sources').glob('*.pdf')).write_bytes(b'tampered')
    with pytest.raises(ValueError, match='hash mismatch'):
        restore_backup(data[2], tmp_path / 'restored')
    assert not (tmp_path / 'restored').exists()


def test_manifest_cannot_drop_referenced_source_or_escape_directory(data):
    manifest = create_backup(*data, services_stopped=True)
    source = next(name for name in manifest['files'] if name.startswith('sources/'))
    del manifest['files'][source]
    (data[2] / 'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='absent'):
        verify_backup(data[2])
    manifest['files']['../secret'] = 'anything'
    (data[2] / 'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='Invalid backup path'):
        verify_backup(data[2])


def test_no_external_fulltext_does_not_require_a_cache_directory(data):
    with sqlite3.connect(data[0]) as db:
        db.execute('UPDATE deep_research_runs_v2 SET payload=?', (json.dumps({'state': {'sources': []}}),))
    manifest = create_backup(data[0], data[1] / 'not-created', data[2], services_stopped=True)
    assert len(manifest['files']) == 2


def test_wal_database_is_saved_as_standalone_file(data, tmp_path):
    from contextlib import closing
    with closing(sqlite3.connect(data[0])) as db:
        db.execute('PRAGMA journal_mode=WAL')
        manifest = create_backup(*data, services_stopped=True)
    assert all(not name.endswith(('-wal', '-shm')) for name in manifest['files'])
    assert not list(data[2].glob('*-wal')) and not list(data[2].glob('*-shm'))
    restore_backup(data[2], tmp_path / 'restored-wal')
