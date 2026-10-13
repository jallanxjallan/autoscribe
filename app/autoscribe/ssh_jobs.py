"""Explicit per-job execution through asc; identity and state use its SQLite ledger."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time

from .enqueue import enqueue_record
from .executor import ordered_steps, prepare_step
from .ledger import connect, ensure_schema, load_call_keys
from .redis_runtime import load_json, FORENSIC_TTL
from .worker import execute_task, load_registry, persist_step_result, persist_redis_response

ROOT = Path('/home/jeremy/incoming')
ASC = Path('/home/jeremy/.local/bin/asc')
SCHEMA = '''CREATE TABLE IF NOT EXISTS ssh_jobs (
 dispatch_id TEXT PRIMARY KEY, record_id TEXT NOT NULL UNIQUE, call_id TEXT NOT NULL UNIQUE,
 package_sha256 TEXT NOT NULL, state TEXT NOT NULL, response_sha256 TEXT,
 error TEXT, accepted_at REAL NOT NULL, started_at REAL, completed_at REAL)'''


def initialize(ledger):
    ensure_schema(ledger)
    with closing(connect(ledger)) as db, db:
        db.execute(SCHEMA)


def check(dispatch, digest):
    if (not re.fullmatch(r'sub_[A-Za-z0-9_-]{1,150}', dispatch)
            or not re.fullmatch(r'[a-f0-9]{64}', digest)):
        raise ValueError('Unsafe dispatch identity or checksum')


def read_job(ledger, dispatch, digest):
    with closing(connect(ledger)) as db:
        row = db.execute('SELECT * FROM ssh_jobs WHERE dispatch_id=?', (dispatch,)).fetchone()
    if row is None:
        return {'schema': 'autoscribe.job.v1', 'dispatch_id': dispatch, 'package_sha256': digest, 'state': 'absent'}
    if row['package_sha256'] != digest:
        raise ValueError('Dispatch identity already belongs to different package')
    return {'schema': 'autoscribe.job.v1', **dict(row)}


def update(ledger, dispatch, state, **values):
    fields = {'state': state, **values}
    if not set(fields) <= {'state', 'response_sha256', 'error', 'started_at', 'completed_at'}:
        raise ValueError('Invalid execution update')
    with closing(connect(ledger)) as db, db:
        db.execute('UPDATE ssh_jobs SET ' + ','.join(k + '=?' for k in fields) + ' WHERE dispatch_id=?', (*fields.values(), dispatch))


def launch(ledger, dispatch, digest):
    state = read_job(ledger, dispatch, digest)
    if state['state'] != 'accepted':
        return state
    # Stable unit name + ledger claim protect a lost systemd/SSH acknowledgment.
    unit = 'asc-' + state['call_id']
    loaded = subprocess.run(['/usr/bin/systemctl', '--user', 'show', unit, '-p', 'LoadState', '--value'],
                            check=True, capture_output=True, text=True, timeout=10)
    if loaded.stdout.strip() == 'not-found':
        subprocess.run(['/usr/bin/systemd-run', '--user', '--collect', '--quiet', '--unit=' + unit,
                        '--property=UMask=0077',
                        '--property=EnvironmentFile=/home/jeremy/.config/autoscribe/autoscribe.env',
                        '--property=EnvironmentFile=-/home/jeremy/.config/autoscribe/credentials.env',
                        '/opt/autoscribe/.venv/bin/python', str(ASC), 'job', 'execute', dispatch, digest],
                       check=True, capture_output=True, text=True, timeout=30)
    return read_job(ledger, dispatch, digest)


def submit(control, ledger, client, dispatch, digest):
    state = read_job(ledger, dispatch, digest)
    if state['state'] != 'absent':
        return launch(ledger, dispatch, digest)
    path = ROOT / dispatch
    if path.is_symlink() or (path / '.package-sha256').read_text() != digest:
        raise ValueError('Incomplete or mismatched request package')
    if hashlib.sha256((path / 'SHA256SUMS').read_bytes()).hexdigest() != digest:
        raise ValueError('Request manifest checksum mismatch')
    subprocess.run(['/usr/bin/sha256sum', '--strict', '-c', 'SHA256SUMS'], cwd=path,
                   check=True, stdout=subprocess.DEVNULL)
    record = json.loads((path / 'request.ndjson').read_text())
    if record['baggage']['client']['submission_id'] != dispatch:
        raise ValueError('Request dispatch identity mismatch')
    # Existing plan resolution, validation, fingerprints and call reservation.
    result = enqueue_record(record=record, control_db=control, ledger_db=ledger, client=client, queue=False)
    with closing(connect(ledger)) as db, db:
        db.execute('INSERT OR IGNORE INTO ssh_jobs (dispatch_id,record_id,call_id,package_sha256,state,accepted_at) VALUES (?,?,?,?,?,?)',
                   (dispatch, result.record_id, result.call_id, digest, 'accepted', time.time()))
    return launch(ledger, dispatch, digest)


def response_file(path, record):
    with tempfile.NamedTemporaryFile(mode='w', dir=path, prefix='.response-', delete=False) as stream:
        stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n')
        stream.flush()
        os.fsync(stream.fileno())
        staged = Path(stream.name)
    os.replace(staged, path / 'response.ndjson')
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return hashlib.sha256((path / 'response.ndjson').read_bytes()).hexdigest()


def execute(ledger, client, dispatch, digest):
    # Commit running BEFORE executing any extension/LLM. Never automatically
    # repeat a running/failed job whose remote side effects may be uncertain.
    with closing(connect(ledger)) as db, db:
        changed = db.execute("UPDATE ssh_jobs SET state='running',started_at=? WHERE dispatch_id=? AND package_sha256=? AND state='accepted'",
                             (time.time(), dispatch, digest)).rowcount
    if not changed:
        return read_job(ledger, dispatch, digest)
    state = read_job(ledger, dispatch, digest)
    path = ROOT / dispatch
    try:
        keys = load_call_keys(ledger, state['call_id'])
        content = load_json(client, keys['content'])
        registry = load_registry(Path(os.environ.get('AUTOSCRIBE_EXTENSION_REGISTRY', '/opt/autoscribe/extensions/registry.json')))
        input_key = None
        for step in ordered_steps(content):
            prepared = prepare_step(client, state['call_id'], keys['content'], int(step['position']), input_key=input_key, queue=False)
            result = execute_task(client, prepared.task_key, registry,
                                  script_timeout=float(os.environ.get('AUTOSCRIBE_EXTENSION_TIMEOUT_SECONDS', '30')),
                                  llm_timeout=float(os.environ.get('AUTOSCRIBE_LLM_TIMEOUT_SECONDS', '120')))
            input_key = persist_step_result(client, result)
        key = persist_redis_response(client, result)
        baggage = load_json(client, keys['baggage'])
        checksum = response_file(path, {'schema': 'autoscribe.client-response.v1', 'call_id': state['call_id'],
                                       'status': 'completed', 'result': result.content, 'baggage': baggage})
        receipt = 'export:' + state['call_id'] + ':receipt'
        client.hset(receipt, {'kind': 'ssh', 'target': str(path / 'response.ndjson'), 'result_sha256': checksum})
        client.expire(receipt, FORENSIC_TTL)
        # One transaction keeps direct results out of the old Dropbox exporter.
        with closing(connect(ledger)) as db, db:
            db.execute('INSERT OR IGNORE INTO responses(call_id,redis_key) VALUES (?,?)', (state['call_id'], key))
            db.execute('INSERT OR IGNORE INTO exports(call_id,redis_key) VALUES (?,?)', (state['call_id'], receipt))
            db.execute("UPDATE ssh_jobs SET state='completed',response_sha256=?,completed_at=? WHERE dispatch_id=?",
                       (checksum, time.time(), dispatch))
    except Exception as exc:
        update(ledger, dispatch, 'failed', error=str(exc), completed_at=time.time())
        raise
    return read_job(ledger, dispatch, digest)


def cleanup(ledger, dispatch, digest, checksum):
    state = read_job(ledger, dispatch, digest)
    if state['state'] == 'cleaned' and state['response_sha256'] == checksum:
        return state
    if state['state'] != 'completed' or state['response_sha256'] != checksum:
        raise ValueError('Cleanup requires acknowledged completed response')
    path = ROOT / dispatch
    if path.exists():
        if hashlib.sha256((path / 'response.ndjson').read_bytes()).hexdigest() != checksum:
            raise ValueError('Response changed before cleanup')
        shutil.rmtree(path)
    update(ledger, dispatch, 'cleaned')
    return read_job(ledger, dispatch, digest)


def command(args, control, ledger, client):
    if len(args) not in (3, 4):
        raise ValueError('usage: asc job submit|status|execute|cleanup DISPATCH SHA256 [RESPONSE_SHA256]')
    operation, dispatch, digest = args[:3]
    check(dispatch, digest)
    initialize(ledger)
    if operation == 'submit' and len(args) == 3:
        return submit(control, ledger, client, dispatch, digest)
    if operation == 'status' and len(args) == 3:
        return read_job(ledger, dispatch, digest)
    if operation == 'execute' and len(args) == 3:
        return execute(ledger, client, dispatch, digest)
    if operation == 'cleanup' and len(args) == 4:
        return cleanup(ledger, dispatch, digest, args[3])
    raise ValueError('Invalid asc job operation')
