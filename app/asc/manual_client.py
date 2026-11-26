"""Finite SSH requests for manual clients; no vault operations or model work.

SQLite records identities/acknowledgments only. The existing incoming job folder
retains checksummed response bytes independently of runtime Redis expiry.
"""
from contextlib import closing
import hashlib
import json
import os
import tempfile
from pathlib import Path
import re
import sqlite3
import time

from . import ssh_jobs as jobs
from .ledger import connect
from .ids import validate_submission_id

SCHEMA = 'autoscribe.manual.v1'
APPLICATIONS = '''CREATE TABLE IF NOT EXISTS client_applications (
 result_id TEXT PRIMARY KEY REFERENCES ssh_jobs(dispatch_id),
 mode TEXT NOT NULL CHECK(mode IN ('writeback','writenew')),
 intent TEXT NOT NULL, target TEXT NOT NULL,
 claimed_at REAL NOT NULL, applied_at REAL, receipt TEXT)'''


def revision_identity(source, plan, original_sha, processing_sha):
    revision = hashlib.sha256(json.dumps([source, plan, original_sha, processing_sha],
        separators=(',', ':')).encode()).hexdigest()
    # UUIDv4-shaped deterministic submission key: keep the established UUID
    # validation/call-ID contract while deriving identity from immutable input.
    identifier = f'{revision[:8]}-{revision[8:12]}-4{revision[13:16]}-8{revision[17:20]}-{revision[20:32]}'
    return identifier, revision


def validate_manifest(dispatch, metadata, original, resolved):
    if len(original)>1_048_576 or len(resolved)>1_048_576: raise ValueError('Source document exceeds 1 MiB')
    required = {'schema','batch_id','revision','source','source_path','vault_id',
                'plan','original_sha256','processing_sha256','slug','note_type'}
    if set(metadata) != required or metadata['schema'] != SCHEMA:
        raise ValueError('Invalid manual submission manifest')
    if not re.fullmatch(r'bat_[a-f0-9]{32}', metadata['batch_id']):
        raise ValueError('Invalid batch identity')
    for name in ('revision','source','vault_id','original_sha256','processing_sha256'):
        if not re.fullmatch(r'[a-f0-9]{64}', metadata[name]):
            raise ValueError('Invalid manifest '+name)
    if (not re.fullmatch(r'pln_[A-Za-z0-9]+', metadata['plan'])
            or not isinstance(metadata['slug'], str) or not metadata['slug']
            or not isinstance(metadata['note_type'], str)):
        raise ValueError('Invalid manual plan/source identity')
    path = Path(metadata['source_path'])
    if (path.is_absolute() or any(p in ('.','..') or p.startswith('.') for p in path.parts)
            or not path.parts or '\\' in str(path)):
        raise ValueError('Unsafe source path')
    sha = lambda data: hashlib.sha256(data).hexdigest()
    expected, revision = revision_identity(metadata['source'], metadata['plan'], sha(original), sha(resolved))
    if (dispatch != expected or metadata['revision'] != revision
            or metadata['original_sha256'] != sha(original)
            or metadata['processing_sha256'] != sha(resolved)):
        raise ValueError('Manual source revision/identity mismatch')


def retain_manifest(dispatch, metadata, original, resolved, assets):
    folder = jobs.ROOT / dispatch
    if len(assets)>124 or sum(len(data) for data in assets.values())>1_048_576:
        raise ValueError('Source assets exceed limits')
    for name,data in assets.items():
        sha=hashlib.sha256(data).hexdigest()
        if not data or not re.fullmatch(rf'assets/{sha}\.[a-z0-9]+',name):
            raise ValueError('Invalid retained source asset')
    retained=[('manual.json', json.dumps(metadata, sort_keys=True, separators=(',',':')).encode()),
                       ('original.md', original), ('resolved.md', resolved), *assets.items()]
    for name,data in retained:
        path = folder / name
        if name.startswith('assets/'):
            if path.parent.is_symlink(): raise ValueError('Unsafe retained asset folder')
            path.parent.mkdir(exist_ok=True)
        if path.exists():
            if path.is_symlink() or path.read_bytes() != data:
                raise ValueError('Existing manual dispatch metadata differs')
        else:
            with tempfile.NamedTemporaryFile(dir=folder,delete=False) as stream:
                staged=Path(stream.name); stream.write(data); stream.flush(); os.fsync(stream.fileno())
            os.replace(staged,path)
    if assets:
        fd=os.open(folder/'assets',os.O_DIRECTORY)
        try: os.fsync(fd)
        finally: os.close(fd)
    fd = __import__('os').open(folder, __import__('os').O_DIRECTORY)
    try: __import__('os').fsync(fd)
    finally: __import__('os').close(fd)


def _read(ledger):
    # All index/query/fetch paths are genuinely read-only, including empty/new
    # ledgers: no ensure_schema, CREATE TABLE or Redis client connection.
    db = sqlite3.connect(Path(ledger).as_uri()+'?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    return db


def _application(db, identity):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='client_applications'").fetchone():
        return None
    row = db.execute('SELECT * FROM client_applications WHERE result_id=?',(identity,)).fetchone()
    return dict(row) if row else None


def _metadata(identity):
    path = jobs.ROOT / identity / 'manual.json'
    if not path.exists():
        return None
    if path.is_symlink(): raise ValueError('Unsafe manifest')
    return json.loads(path.read_bytes())


def _result(row):
    path = jobs.ROOT / row['dispatch_id'] / 'response.ndjson'
    if path.is_symlink(): raise ValueError('Unsafe response')
    data = path.read_bytes()
    if len(data)>4_194_304 or hashlib.sha256(data).hexdigest()!=row['response_sha256']:
        raise ValueError('Result checksum/size mismatch')
    value = json.loads(data)
    if value['submission_id'] != row['dispatch_id'] or value['call_id'] != row['call_id']:
        raise ValueError('Result identity mismatch')
    return value


def index(ledger, inflight_only=False):
    results=[]; batches={}; inflight=[]
    with closing(_read(ledger)) as db:
        for row in db.execute("SELECT * FROM ssh_jobs WHERE state IN ('accepted','queued','running') ORDER BY accepted_at,dispatch_id"):
            metadata=_metadata(row['dispatch_id'])
            inflight.append({'result_id':row['dispatch_id'],'state':row['state'],'plan':metadata['plan'] if metadata else 'unknown','accepted_at':row['accepted_at'],'started_at':row['started_at']})
        if inflight_only: return {'schema':SCHEMA,'inflight':inflight}
        for row in db.execute("SELECT * FROM ssh_jobs WHERE state='completed' ORDER BY completed_at,dispatch_id"):
            application=_application(db,row['dispatch_id'])
            if application and application['applied_at'] is not None: continue
            response=_result(row)
            if response['status']!='completed': continue
            metadata=_metadata(row['dispatch_id'])
            if metadata is None:
                raise ValueError('Completed legacy result needs explicit migration: '+row['dispatch_id'])
            result={**metadata,'result_id':row['dispatch_id'],'call_id':row['call_id'],
                    'response_sha256':row['response_sha256'],'completed_at':row['completed_at'],
                    'application':application}
            results.append(result)
            batch=batches.setdefault(metadata['batch_id'],{'batch_id':metadata['batch_id'],'count':0,'sources':[]})
            batch['count']+=1; batch['sources'].append(metadata['source_path'])
    return {'schema':SCHEMA,'results':results,'batches':list(batches.values()),'inflight':inflight}


def query(ledger, identities):
    if not isinstance(identities,list) or len(identities)>1024: raise ValueError('Bounded identity list required')
    states={}
    with closing(_read(ledger)) as db:
        for identity in identities:
            validate_submission_id(identity)
            row=db.execute('SELECT * FROM ssh_jobs WHERE dispatch_id=?',(identity,)).fetchone()
            if not row:
                partial=_metadata(identity)
                states[identity]={'state':'new','batch_id':partial['batch_id'] if partial else None}
                continue
            application=_application(db,identity)
            metadata=_metadata(identity)
            states[identity]={'state':'applied' if row['state']=='cleaned' or (application and application['applied_at'] is not None) else ('failed' if row['state']=='completed' and _result(row)['status']!='completed' else row['state']),
                              'batch_id':metadata['batch_id'] if metadata else None,
                              'package_sha256':row['package_sha256']}
    return {'schema':SCHEMA,'submissions':states}


def source_assets(identity):
    folder=jobs.ROOT/identity/'assets'
    if not folder.exists(): return {}
    if folder.is_symlink(): raise ValueError('Unsafe retained asset folder')
    result={}
    paths=sorted(folder.iterdir())
    if len(paths)>124: raise ValueError('Retained asset count exceeds limits')
    total=0
    for path in paths:
        if path.stat().st_size>1_048_576: raise ValueError('Retained asset exceeds limit')
        if path.is_symlink() or not path.is_file(): raise ValueError('Unsafe retained asset')
        data=path.read_bytes(); total+=len(data)
        if total>1_048_576: raise ValueError('Retained assets exceed limit')
        sha=hashlib.sha256(data).hexdigest()
        if not re.fullmatch(rf'{sha}\.[a-z0-9]+',path.name): raise ValueError('Retained asset checksum mismatch')
        result['assets/'+path.name]={'sha256':sha,'content_hex':data.hex()}
    return result


def fetch(ledger, identity):
    validate_submission_id(identity)
    with closing(_read(ledger)) as db:
        row=db.execute('SELECT * FROM ssh_jobs WHERE dispatch_id=?',(identity,)).fetchone()
        if row is None or row['state'] not in ('completed','applied','failed') or row['response_sha256'] is None: raise ValueError('Result is not available')
        application=_application(db,identity)
        metadata=_metadata(identity)
        if metadata is None: raise ValueError('Missing durable source manifest')
        return {'schema':SCHEMA,'result_id':identity,'metadata':metadata,
                'response_sha256':row['response_sha256'],'response':_result(row),'response_ndjson':(jobs.ROOT/identity/'response.ndjson').read_bytes().decode('utf-8'),
                'original_markdown':(jobs.ROOT/identity/'original.md').read_bytes().decode('utf-8'),
                'processing_markdown':(jobs.ROOT/identity/'resolved.md').read_bytes().decode('utf-8'),'assets':source_assets(identity),'application':application}


def application(ledger, operation, identity, request, retire_runtime=None):
    validate_submission_id(identity)
    if set(request)!={'mode','intent','target','response_sha256','receipt'}:
        raise ValueError('Invalid application request')
    if request['mode'] not in ('writeback','writenew'): raise ValueError('Invalid application mode')
    if any(not re.fullmatch(r'[a-f0-9]{64}',request[key]) for key in ('intent','target','response_sha256')):
        raise ValueError('Invalid application identity')
    with closing(connect(ledger)) as db:
        db.execute(APPLICATIONS); db.commit()
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT * FROM ssh_jobs WHERE dispatch_id=?',(identity,)).fetchone()
        if row is None or row['state'] not in ('completed','applied') or row['response_sha256']!=request['response_sha256']:
            raise ValueError('Result is not completed or checksum differs')
        if _result(row)['status']!='completed': raise ValueError('Failed result cannot be applied')
        prior=_application(db,identity)
        if prior is None:
            if operation!='claim': raise ValueError('Application requires a prior claim')
            db.execute('INSERT INTO client_applications(result_id,mode,intent,target,claimed_at) VALUES(?,?,?,?,?)',
                       (identity,request['mode'],request['intent'],request['target'],time.time()))
        elif any(prior[key]!=request[key] for key in ('mode','intent','target')):
            raise ValueError('Result already claimed for a different application; explicit reconciliation required')
        if operation=='ack':
            receipt=request['receipt']
            if not isinstance(receipt,dict) or set(receipt)!={'file_sha256','git_commit'}:
                raise ValueError('Successful file/Git receipt required')
            if not re.fullmatch(r'[a-f0-9]{64}',receipt['file_sha256']) or not re.fullmatch(r'[a-f0-9]{40,64}',receipt['git_commit']):
                raise ValueError('Invalid file/Git receipt')
            encoded=json.dumps(receipt,sort_keys=True,separators=(',',':'))
            if prior and prior['applied_at'] is not None and prior['receipt']!=encoded:
                raise ValueError('Application receipt differs')
            if retire_runtime is not None: retire_runtime(row['call_id'])
            db.execute('UPDATE client_applications SET applied_at=COALESCE(applied_at,?),receipt=? WHERE result_id=?',
                       (time.time(),encoded,identity))
            db.execute("UPDATE ssh_jobs SET state='applied' WHERE dispatch_id=?",(identity,))
        db.commit()
        return {'schema':SCHEMA,'result_id':identity,'application':_application(db,identity)}


def command(args, control, ledger, client):
    if not args: raise ValueError('Use index, query, fetch, claim or ack')
    op,*values=args
    if op=='index' and not values: return index(ledger)
    if op=='index' and values==['--inflight']: return index(ledger, inflight_only=True)
    if op=='query' and len(values)==1: return query(ledger,json.loads(values[0]))
    if op=='fetch' and len(values)==1: return fetch(ledger,values[0])
    if op in ('claim','ack') and len(values)==2:
        def retire(call_id):
            try: call=jobs.Call.load(call_id,client)
            except jobs.MissingRecord: return
            call.retain_after_cleanup(client)
        return application(ledger,op,values[0],json.loads(values[1]),retire)
    raise ValueError('Invalid manual client operation')
