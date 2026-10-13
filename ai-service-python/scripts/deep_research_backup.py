"""Run from any directory. No network calls or model initialization."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.deep_research.backup import create_backup, restore_backup, verify_backup

parser = argparse.ArgumentParser(description=__doc__)
commands = parser.add_subparsers(dest='command', required=True)
backup = commands.add_parser('backup')
backup.add_argument('--database', required=True)
backup.add_argument('--sources', required=True)
backup.add_argument('--destination', required=True)
backup.add_argument('--services-stopped', action='store_true')
verify = commands.add_parser('verify')
verify.add_argument('directory')
restore = commands.add_parser('restore')
restore.add_argument('--backup', required=True)
restore.add_argument('--destination', required=True)
args = parser.parse_args()
if args.command == 'backup':
    result = create_backup(args.database, args.sources, args.destination, services_stopped=args.services_stopped)
elif args.command == 'restore':
    result = restore_backup(args.backup, args.destination)
else:
    result = verify_backup(args.directory)
print(json.dumps({'scope': result['scope'], 'runs': result['runCount'], 'files': len(result['files']), 'verified': True}))
