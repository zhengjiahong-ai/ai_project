"""Offline backup/restore of the v2 engine, never an in-place database replacement."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
from contextlib import closing


def file_hash(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _readonly(path):
    return closing(sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True))


def _snapshot(source, target):
    with _readonly(source) as original, closing(sqlite3.connect(target)) as copied:
        original.backup(copied)
        copied.execute('PRAGMA journal_mode=DELETE')
        if copied.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Database integrity check failed')


def create_backup(database, sources, destination, *, services_stopped=False):
    """Caller must stop the Python service first; Java/files need their own backup."""
    if not services_stopped:
        raise ValueError('Stop the Python service before taking a coordinated backup')
    database, sources, destination = map(Path, (database, sources, destination))
    if not database.is_file() or (sources.exists() and not sources.is_dir()):
        raise ValueError('Database must exist and source cache must be a directory')
    with _readonly(database) as db:
        rows = db.execute('SELECT status, payload FROM deep_research_runs_v2').fetchall()
    if any(status in {'queued', 'running', 'stopping'} for status, _ in rows):
        raise ValueError('Active runs must finish or be paused before backup')
    required = set()
    for _, payload in rows:
        for source in json.loads(payload).get('state', {}).get('sources', []):
            if source.get('sourceKind') == 'arxiv' and source.get('accessLevel') == 'fulltext':
                digest = source.get('contentHash', '')
                if not re.fullmatch('[0-9a-f]{64}', digest):
                    raise ValueError('Invalid source identity')
                required.add(digest + '.pdf')
    for name in required:
        source = sources / name
        if not source.is_file() or source.is_symlink() or file_hash(source) != name[:-4]:
            raise ValueError('A referenced source is missing or has changed')
    destination.mkdir(parents=True, exist_ok=False)
    _snapshot(database, destination / 'research.sqlite3')
    checkpoint = Path(str(database) + '.checkpoints')
    if checkpoint.exists():
        _snapshot(checkpoint, destination / 'research.sqlite3.checkpoints')
    (destination / 'sources').mkdir()
    for name in sorted(required):
        shutil.copyfile(sources / name, destination / 'sources' / name)
    paths = [p for p in destination.rglob('*') if p.is_file()]
    manifest = {'format': 1, 'scope': 'deep-research-v2-only', 'runCount': len(rows),
                'files': {p.relative_to(destination).as_posix(): file_hash(p) for p in paths}}
    # Written last: a partial copy is never a valid completed backup.
    (destination / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    verify_backup(destination)
    return manifest


def verify_backup(directory):
    directory = Path(directory)
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    files = manifest.get('files', {})
    if manifest.get('format') != 1 or 'research.sqlite3' not in files:
        raise ValueError('Unsupported or incomplete backup')
    for name, digest in files.items():
        if not re.fullmatch(r'research\.sqlite3(?:\.checkpoints)?|sources/[0-9a-f]{64}\.pdf', name):
            raise ValueError('Invalid backup path')
        path = directory / name
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):
            raise ValueError('Backup file is missing or escapes its directory')
        if file_hash(path) != digest:
            raise ValueError('Backup hash mismatch')
        if name.startswith('sources/') and digest != path.stem:
            raise ValueError('Source identity mismatch')
        if name.startswith('research.sqlite3'):
            with _readonly(path) as db:
                if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError('Database integrity check failed')
    with _readonly(directory / 'research.sqlite3') as db:
        rows = db.execute('SELECT payload FROM deep_research_runs_v2').fetchall()
    for (payload,) in rows:
        for source in json.loads(payload).get('state', {}).get('sources', []):
            if source.get('sourceKind') == 'arxiv' and source.get('accessLevel') == 'fulltext':
                if f"sources/{source.get('contentHash')}.pdf" not in files:
                    raise ValueError('Referenced fulltext is absent from backup')
    if len(rows) != manifest.get('runCount'):
        raise ValueError('Run count mismatch')
    return manifest


def restore_backup(backup, destination):
    """Restore only into a new directory; no overwrite or automatic service start."""
    backup, destination = Path(backup), Path(destination)
    manifest = verify_backup(backup)
    destination.mkdir(parents=True, exist_ok=False)
    (destination / 'sources').mkdir()
    for name in manifest['files']:
        shutil.copyfile(backup / name, destination / name)
    shutil.copyfile(backup / 'manifest.json', destination / 'manifest.json')
    return verify_backup(destination)
