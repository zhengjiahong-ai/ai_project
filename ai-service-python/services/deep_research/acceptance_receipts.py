"""Durable submission receipts for explicit developer acceptance runs."""
import json
import os
from pathlib import Path
import tempfile
from contextlib import contextmanager


@contextmanager
def _receipt_lock(path):
    lock = path.with_suffix(path.suffix + '.lock')
    stream = lock.open('x', encoding='utf-8')
    try:
        yield
    finally:
        stream.close()
        lock.unlink()


def read_receipt(path):
    value = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(value, dict) or value.get('schemaVersion') != 1 or not isinstance(value.get('intent'), dict):
        raise ValueError('Invalid receipt schema')
    status, run = value.get('submissionStatus'), value.get('runId')
    if status == 'unconfirmed' and run is None:
        return value
    if status == 'confirmed' and isinstance(run, str) and run.strip():
        return value
    raise ValueError('Invalid receipt status or run identity')


def claim_submission(path, intent):
    if not isinstance(intent, dict):
        raise ValueError('Intent must be an object')
    value = {'schemaVersion': 1, 'intent': intent, 'runId': None, 'submissionStatus': 'unconfirmed'}
    content = json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    return value


def confirm_submission(path, run_id):
    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError('Run identity must be nonempty')
    path = Path(path)
    # Conflicting concurrent confirmations fail closed; no hidden retry.
    with _receipt_lock(path):
        temporary = None
        try:
            value = read_receipt(path)
            if value['runId'] not in (None, run_id):
                raise ValueError('Receipt already confirms a different run')
            if value['runId'] == run_id:
                return value
            value.update(runId=run_id, submissionStatus='confirmed')
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                             prefix=path.name + '.', suffix='.tmp', delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            return value
        finally:
            if temporary and temporary.exists():
                temporary.unlink()
