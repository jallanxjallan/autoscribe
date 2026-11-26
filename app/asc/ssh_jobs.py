"""Explicit per-job execution through asc; identity and state use its SQLite ledger."""
from contextlib import closing
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

from biznet_common.llm import SYSTEMD_CREDENTIAL_PROPERTY

from .enqueue import enqueue_record, register_failure, validate_input_record
from .ids import validate_submission_id
from .ledger import connect, ensure_schema, record_response, record_export
from .models.call import Call, ErrorInfo, Receipt, RuntimeStore, MissingRecord
from .worker import execute as execute_component, load_registry

ROOT = Path('/home/jeremy/incoming')
ASC = Path(__file__).resolve().parents[1] / 'bin/asc'
SCHEMA = '''CREATE TABLE IF NOT EXISTS ssh_jobs (
 dispatch_id TEXT PRIMARY KEY, record_id TEXT NOT NULL UNIQUE, call_id TEXT NOT NULL UNIQUE,
 package_sha256 TEXT NOT NULL, state TEXT NOT NULL, response_sha256 TEXT,
 error TEXT, accepted_at REAL NOT NULL, started_at REAL, completed_at REAL)'''


def initialize(ledger):
    ensure_schema(ledger)
    with closing(connect(ledger)) as db, db:
        db.execute(SCHEMA)


def check(dispatch, digest):
    validate_submission_id(dispatch)
    if not re.fullmatch(r'[a-f0-9]{64}', digest):
        raise ValueError('Unsafe dispatch checksum')


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


def launch_environment():
    """Retain the accepting process's selected paths, never a later mutable config.

    Credentials remain in the established private EnvironmentFile and are never
    copied into process arguments. These assignments contain only runtime policy
    paths, roots and limits; env applies them after systemd's environment files.
    """
    keys = ('AUTOSCRIBE_RELEASE_ROOT', 'AUTOSCRIBE_CONTROL_DB', 'AUTOSCRIBE_LEDGER_DB',
            'AUTOSCRIBE_REDIS_HOST', 'AUTOSCRIBE_REDIS_PORT', 'AUTOSCRIBE_RUNTIME_RETENTION_SECONDS',
            'AUTOSCRIBE_EXTENSION_REGISTRY', 'AUTOSCRIBE_EXTENSION_TIMEOUT_SECONDS',
            'AUTOSCRIBE_LLM_TIMEOUT_SECONDS', 'AUTOSCRIBE_PANDOC',
            'TEMPLATES_ROOT', 'EXTENSIONS_ROOT',
            'DROPBOX_ASSET_ROOT', 'AUTOSCRIBE_RCLONE')
    paths = {'AUTOSCRIBE_RELEASE_ROOT', 'AUTOSCRIBE_CONTROL_DB', 'AUTOSCRIBE_LEDGER_DB',
             'AUTOSCRIBE_EXTENSION_REGISTRY', 'AUTOSCRIBE_PANDOC',
             'TEMPLATES_ROOT', 'EXTENSIONS_ROOT',
             'AUTOSCRIBE_RCLONE'}
    values = []
    for key in keys:
        value = os.environ.get(key)
        if value is None:
            continue
        if key in paths:
            path = Path(value)
            if not path.is_absolute():
                raise ValueError(f'{key} must be absolute')
            value = str(path.resolve())
        values.append(f'{key}={value}')
    return values


def launch(ledger, dispatch, digest):
    state = read_job(ledger, dispatch, digest)
    if state['state'] != 'accepted':
        return state
    verify_release(dispatch)
    # Stable unit name + ledger claim protect a lost systemd/SSH acknowledgment.
    unit = 'asc-' + state['call_id']
    loaded = subprocess.run(['/usr/bin/systemctl', '--user', 'show', unit, '-p', 'LoadState', '--value'],
                            check=True, capture_output=True, text=True, timeout=10)
    if loaded.stdout.strip() == 'not-found':
        subprocess.run(['/usr/bin/systemd-run', '--user', '--collect', '--quiet', '--unit=' + unit,
                        '--property=UMask=0077',
                        SYSTEMD_CREDENTIAL_PROPERTY,
                        '/usr/bin/env', *launch_environment(), sys.executable,
                        str(Path(os.environ['AUTOSCRIBE_RELEASE_ROOT']) / 'bin/asc'), 'job', 'execute', dispatch, digest],
                       check=True, capture_output=True, text=True, timeout=30)
    return read_job(ledger, dispatch, digest)


def release_binding():
    """Pin executable and dependency selection; never resolve another release."""
    return {'executable': str(ASC.resolve()), 'python': sys.executable,
            'environment': launch_environment()}


def bind_release(dispatch):
    path = ROOT / dispatch / 'execution-release.json'
    data = json.dumps(release_binding(), sort_keys=True, separators=(',', ':'))
    try:
        with path.open('x') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except FileExistsError:
        verify_release(dispatch)


def verify_release(dispatch):
    path = ROOT / dispatch / 'execution-release.json'
    if path.is_symlink() or json.loads(path.read_text()) != release_binding():
        raise ValueError('Job belongs to a different pinned release; refuse rebind')


def source_envelope(dispatch, files):
    files = dict(files)
    meta = json.loads(files.pop('dispatch.json'))
    manual = json.loads(files.pop('manual.json'))
    original = files.pop('original.md')
    resolved = files.pop('resolved.md')
    from .manual_client import validate_manifest, retain_manifest
    validate_manifest(dispatch, manual, original, resolved)
    if any(manual[a] != meta[b] for a,b in [('plan','plan'),('source','source'),('source_path','source_path'),('vault_id','vault_id'),('original_sha256','raw_markdown_sha256')]):
        raise ValueError('Manual manifest differs from dispatch metadata')
    digest = lambda data: hashlib.sha256(data).hexdigest()
    expected = 'inp_' + digest(dispatch.encode())[:32]
    fields = {'submission_id', 'record_id', 'source', 'vault_id', 'source_path',
              'raw_markdown_sha256', 'output_operation'}
    path = meta['source_path']
    if path is not None:
        fields.add('plan')
    if (set(meta) != fields or meta['submission_id'] != dispatch or meta['record_id'] != expected
            or digest(original) != meta['raw_markdown_sha256']
            or not re.fullmatch(r'[a-f0-9]{64}', meta['vault_id'])
            or not re.fullmatch(r'[a-f0-9]{64}', meta['source'])):
        raise ValueError('Dropbox dispatch source identity/checksum mismatch')

    def front(raw):
        match = re.match(rb'(?:\xef\xbb\xbf)?---\r?\n.*?^---(?:\r?\n|$)', raw, re.M | re.S)
        return match[0] if match else b''

    client = {key:meta[key] for key in ('source', 'vault_id', 'raw_markdown_sha256')}
    source = {'kind':'stdin' if path is None else 'obsidian', 'vault_id':meta['vault_id']}
    envelope = {'schema':'autoscribe.input.v3', 'submission_id':dispatch, 'record_id':expected,
                'raw_markdown':original.decode('utf-8'), 'raw_markdown_sha256':digest(original),
                'content':resolved.decode('utf-8'), 'content_sha256':digest(resolved),
                'assets':[], 'source':source, 'baggage':{'client':client}}
    if path is not None:
        if not front(original) or front(original) != front(resolved) or not re.fullmatch(r'pln_[A-Za-z0-9]+', meta['plan']):
            raise ValueError('Dropbox dispatch frontmatter or plan claim mismatch')
        source['path'] = client['source_path'] = path
        envelope['routing'] = {'plan_id':meta['plan']}
    operation = meta['output_operation']
    if (not isinstance(operation, dict) or operation.get('schema') != 'autoscribe.output-operation.v1'
            or operation.get('submission_id') != dispatch or operation.get('vault_id') != meta['vault_id']
            or operation.get('representation') != 'markdown-body.utf8'
            or operation.get('type') not in ('update', 'writenew')
            or (operation['type'] == 'update' and (path is None or operation.get('path') != path))):
        raise ValueError('Invalid Dropbox dispatch output operation')
    client['output_operation'] = operation
    for name, data in sorted(files.items(), key=lambda item: resolved.find(item[0].encode())):
        sha = digest(data)
        if not data or not re.fullmatch(rf'assets/{sha}\.[a-z0-9]+', name):
            raise ValueError(f'Invalid inline dispatch asset: {name}')
        envelope['assets'].append({'path':name, 'sha256':sha, 'content_hex':data.hex()})
    retain_manifest(dispatch, manual, original, resolved, files)
    return envelope


def prepare_dropbox(dispatch, digest, location, path, control):
    from .dropbox_package import retrieve
    from .preprocess import prepare, canonical
    envelope = source_envelope(dispatch, retrieve('dispatch', dispatch, digest, location, 4_194_304))
    record = prepare(envelope, work_dir=path,
                     require_plan=envelope['source']['kind'] == 'obsidian')
    if record.get('submission_id') != dispatch:
        raise ValueError('Request dispatch identity mismatch')
    from .control import plan_index
    manual = json.loads((path/'manual.json').read_text())
    if record.get('status') != 'ready' or record.get('plan') not in {p['plan_id'] for p in plan_index(control)}:
        raise ValueError('Source/registered plan is not eligible for submission')
    if record['plan'] != manual['plan'] or record['source'].get('slug') != manual['slug']:
        raise ValueError('Prepared source differs from manifest identity')
    line = canonical(record) + b'\n'
    validate_input_record(json.loads(line))
    return line


def submit(control, ledger, client, dispatch, digest, location):
    check(dispatch, digest)
    # Hold the existing job directory across verification and ledger acceptance.
    path = ROOT / dispatch
    state = read_job(ledger, dispatch, digest)
    if state['state'] != 'absent':
        return resume(ledger, client, dispatch, digest, state)
    path.mkdir(mode=0o700, exist_ok=True)
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        return accept_dropbox(control, ledger, client, dispatch, digest, location, path)
    finally:
        os.close(fd)


def resume(ledger, client, dispatch, digest, state):
    if state['state'] in ('completed', 'cleaned', 'applied') or (state['state']=='failed' and state['response_sha256'] is not None):
        return state
    verify_release(dispatch)
    if Call.load(state['call_id'],client).terminal:
        return complete_response(ledger, client, state)
    return launch(ledger, dispatch, digest)


def accept_dropbox(control, ledger, client, dispatch, digest, location, path):
    state = read_job(ledger, dispatch, digest)
    if state['state'] != 'absent':
        return resume(ledger, client, dispatch, digest, state)
    record = json.loads(prepare_dropbox(dispatch, digest, location, path, control))
    bind_release(dispatch)
    result = enqueue_record(record=record, control_db=control, ledger_db=ledger, client=client)
    with closing(connect(ledger)) as db, db:
        db.execute('INSERT OR IGNORE INTO ssh_jobs (dispatch_id,record_id,call_id,package_sha256,state,accepted_at,error) VALUES (?,?,?,?,?,?,?)',
                   (dispatch, result.record_id, result.call_id, digest,
                    'failed' if result.failure else 'accepted', time.time(), result.failure))
    if result.failure:
        return complete_response(ledger, client, read_job(ledger, dispatch, digest))
    return launch(ledger, dispatch, digest)


def response_file(path, record):
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='', dir=path, prefix='.response-', delete=False) as stream:
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


def complete_response(ledger, client, state):
    """Publish the existing ledger response through the unchanged SSH receipt path.

    completed means transport output is ready, not manuscript success. A terminal
    preprocessing response carries status=failed and must not trigger writeback.
    """
    if state['state'] in ('completed', 'cleaned', 'applied') or (state['state']=='failed' and state['response_sha256'] is not None):
        return state
    call_id=state['call_id']
    call=Call.load(call_id,client)
    if not call.terminal:raise ValueError('Response is not terminal')
    record=call.response_record(client_protocol=True)
    path=ROOT/state['dispatch_id']
    checksum=response_file(path,record)
    call.evolve(receipt=Receipt(kind='ssh',target=str(path/'response.ndjson'),checksum=checksum,details={'response_receipt_id':record['receipt_id']}).model_dump()).save(client)
    key=RuntimeStore.key(call_id)
    record_response(ledger,call_id,key)
    record_export(ledger,call_id,key)
    with closing(connect(ledger)) as db,db:
        terminal_state='completed' if record['status']=='completed' else 'failed'
        db.execute("UPDATE ssh_jobs SET state=?,response_sha256=?,completed_at=? WHERE dispatch_id=?",(terminal_state,checksum,time.time(),state['dispatch_id']))
    if record['status']=='failed':
        # There is no applicable output to await; retain the existing recovery TTL.
        Call.load(call_id,client).retain_after_cleanup(client)
    return read_job(ledger,state['dispatch_id'],state['package_sha256'])


def execute(ledger, client, dispatch, digest):
    prior=read_job(ledger,dispatch,digest)
    if prior['state'] in ('absent','completed','cleaned','applied') or (prior['state']=='failed' and prior['response_sha256'] is not None):return prior
    verify_release(dispatch)
    call=Call.load(prior['call_id'],client)
    if call.terminal:return complete_response(ledger,client,prior)
    with closing(connect(ledger)) as db,db:
        changed=db.execute("UPDATE ssh_jobs SET state='running',started_at=? WHERE dispatch_id=? AND package_sha256=? AND state='accepted'",(time.time(),dispatch,digest)).rowcount
    if not changed:return read_job(ledger,dispatch,digest)
    state=read_job(ledger,dispatch,digest)
    try:
        registry_path=Path(os.environ['AUTOSCRIBE_EXTENSION_REGISTRY'])
        if not registry_path.is_absolute():raise ValueError('Pinned registry must be absolute')
        registry=load_registry(registry_path)
        for step in call.plan.ordered_steps:
            current=Call.load(call.identity,client)
            result=execute_component(current.invocation(step.position),client,registry,
                script_timeout=float(os.environ.get('AUTOSCRIBE_EXTENSION_TIMEOUT_SECONDS','30')),
                llm_timeout=float(os.environ.get('AUTOSCRIBE_LLM_TIMEOUT_SECONDS','120')))
            if result.error:
                current=Call.load(call.identity,client)
                current.evolve(error=result.error.model_dump(),final_position=step.position).save(client)
                break
        else:
            Call.load(call.identity,client).evolve(final_position=step.position).save(client)
    except Exception as exc:
        update(ledger,dispatch,'failed',error=str(exc),completed_at=time.time())
        register_failure(ledger,client,call.identity,ErrorInfo(code=type(exc).__name__,message=str(exc) or type(exc).__name__,stage='execution'))
    return complete_response(ledger,client,state)


def cleanup(ledger, dispatch, digest, checksum, client):
    state=read_job(ledger,dispatch,digest)
    if state['state'] not in ('completed','cleaned') or state['response_sha256']!=checksum:
        raise ValueError('Cleanup requires acknowledged completed response')
    try:call=Call.load(state['call_id'],client)
    except MissingRecord:
        if state['state']!='cleaned':raise
        return state
    if call.receipt is None or call.receipt.checksum!=checksum:raise ValueError('Runtime receipt mismatch')
    path=ROOT/dispatch
    if path.exists():
        if hashlib.sha256((path/'response.ndjson').read_bytes()).hexdigest()!=checksum:raise ValueError('Response changed before cleanup')
        shutil.rmtree(path)
    # Commit the durable acknowledgement before imposing expiry. Retry finishes
    # a Redis failure after this commit, without resetting an existing deadline.
    update(ledger,dispatch,'cleaned')
    call.retain_after_cleanup(client)
    return read_job(ledger,dispatch,digest)


def command(args, control, ledger, client):
    if len(args) not in (3, 4):
        raise ValueError('usage: asc job submit|status|execute DISPATCH SHA256 [DROPBOX_LOCATION|RESPONSE_SHA256]')
    operation, dispatch, digest = args[:3]
    check(dispatch, digest)
    initialize(ledger)
    if operation == 'submit' and len(args) == 4:
        return submit(control, ledger, client, dispatch, digest, args[3])
    if operation == 'status' and len(args) == 3:
        return read_job(ledger, dispatch, digest)
    if operation == 'execute' and len(args) == 3:
        return execute(ledger, client, dispatch, digest)
    raise ValueError('Invalid asc job operation')
