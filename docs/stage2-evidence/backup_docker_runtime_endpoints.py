"""Back up only the three known empty Docker runtime endpoint files in WSL.

Inspection is the default. Never recurse, delete files, or touch engine data.
Run only while Docker Desktop is stopped; --backup explicitly enables renames.
"""
import argparse
import json
import stat
from datetime import datetime, timezone
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--backup', action='store_true')
args = parser.parse_args()

local = Path('/mnt/c/Users/Lenovo/AppData/Local').resolve(strict=True)
endpoints = [local / 'Docker/run/dockerInference',
             local / 'docker-secrets-engine/engine.sock',
             local / 'Docker/run/userAnalyticsOtlpHttp.sock']
stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
rows = []
for endpoint in endpoints:
    if not endpoint.exists():
        rows.append({'path': str(endpoint), 'status': 'missing'})
        continue
    resolved = endpoint.resolve(strict=True)
    allowed_parent = (local / endpoint.relative_to(local).parent).resolve(strict=True)
    if resolved.parent != allowed_parent or not allowed_parent.is_relative_to(local):
        raise RuntimeError('Endpoint is outside its explicit runtime directory')
    info = endpoint.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_size != 0:
        raise RuntimeError('Refusing a nonempty or nonregular endpoint: ' + str(endpoint))
    backup = endpoint.with_name(endpoint.name + '.stage7-' + stamp + '.bak')
    if backup.parent.resolve(strict=True) != allowed_parent or backup.exists():
        raise RuntimeError('Backup destination is invalid or already exists')
    row = {'path': str(endpoint), 'bytes': info.st_size, 'status': 'checked'}
    if args.backup:
        endpoint.rename(backup)
        row.update(status='backed_up', backup=str(backup))
    rows.append(row)
print(json.dumps({'backupEnabled': args.backup, 'endpoints': rows}))
