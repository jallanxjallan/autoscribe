"""Prepared-call boundary. No document interpretation or Pandoc invocation."""
from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import os

from .settings import retention_seconds, release_identity

from .control import materialize_plan, UnknownPlanError
from .ids import validate_submission_id
from .ledger import connect, ensure_schema, record_call, record_response
from biznet_common.redis import RedisClient
from .models.call import Call, Source, Plan, ErrorInfo, RuntimeStore, MissingRecord, ConcurrentUpdate, digest

INPUT_SCHEMA = 'autoscribe.prepared.v2'


class EnqueueError(ValueError):
    pass


@dataclass(frozen=True)
class EnqueueResult:
    record_id: str
    call_id: str
    created: bool
    runtime_key: str
    failure: str | None = None


def validate_input_record(record: object) -> tuple[str, str | None]:
    if not isinstance(record, dict) or record.get('schema')!=INPUT_SCHEMA:
        raise EnqueueError('asc enqueue requires autoscribe.prepared.v2; use asc ingest for documents')
    try:
        encoded=json.dumps(record, ensure_ascii=False, allow_nan=False).encode('utf-8')
    except (ValueError, TypeError, UnicodeError) as exc:
        raise EnqueueError('Invalid prepared serialization') from exc
    if len(encoded)>=4194304: raise EnqueueError('Prepared record exceeds transport limit')
    patterns={'record_id':r'inp_[0-9a-f]{32}', 'call_id':r'(?:call_[0-9a-f]{40}|failed_[0-9a-f]{64})',
              'submission_id':r'[0-9a-f-]{36}'}
    for key, pattern in patterns.items():
        if not isinstance(record.get(key), str) or not re.fullmatch(pattern,record[key]):
            raise EnqueueError('Invalid prepared '+key)
    try:
        validate_submission_id(record['submission_id'])
    except ValueError as exc:
        raise EnqueueError(str(exc)) from exc
    if set(record)-set('schema record_id call_id submission_id status plan source baggage content content_sha256 original_text source_format metadata directives asset_references assets references staged_assets failure diagnostic_envelope'.split()):
        raise EnqueueError('Unknown prepared field')
    identity=record['submission_id'].encode('utf-8')
    if record['record_id']!='inp_'+hashlib.sha256(identity).hexdigest()[:32]:
        raise EnqueueError('record_id does not identify submission')
    expected_call='call_'+hashlib.sha1(identity).hexdigest()
    expected_failure='failed_'+hashlib.sha256(identity).hexdigest()
    if record['call_id'] not in (expected_call,expected_failure):
        raise EnqueueError('call_id does not identify submission')
    if record.get('status') not in ('ready','failed'): raise EnqueueError('Invalid prepared status')
    failed=record['status']=='failed'
    if not isinstance(record.get('source'),dict) or not isinstance(record.get('baggage'),dict):
        raise EnqueueError('Prepared source and baggage must be objects')
    # Validate coordination structurally without importing the document adapter.
    source=record['source'];client=record['baggage'].get('client',{})
    if not isinstance(client,dict): raise EnqueueError('Invalid client coordination')
    if 'path' in source:
        path=source['path']
        if (not isinstance(path,str) or not path or any(c in path for c in '\\:')
                or any(ord(c)<32 or ord(c)==127 for c in path)
                or any(p in ('','.','..') or p.lower()=='.git' for p in path.split('/'))):
            if not failed: raise EnqueueError('Invalid source coordination')
        if client.get('source_path',path)!=path and not failed: raise EnqueueError('Source/baggage identity mismatch')
    elif 'source_path' in client and not failed: raise EnqueueError('Source/baggage identity mismatch')
    if client.get('source_slug',source.get('slug'))!=source.get('slug') and not failed:
        raise EnqueueError('Source/baggage slug mismatch')
    content=record.get('content')
    if not isinstance(content,str) or len(content.encode('utf-8'))>1048576:
        raise EnqueueError('Invalid prepared content')
    if record.get('content_sha256')!=hashlib.sha256(content.encode('utf-8')).hexdigest():
        raise EnqueueError('input content_sha256 does not match content')
    if 'original_text' not in record or (record['original_text'] is not None and not isinstance(record['original_text'], str)):
        raise EnqueueError('Prepared original_text is required')
    if not failed and record['original_text'] is None:
        raise EnqueueError('Ready call requires original source')
    original_hash=client.get('raw_markdown_sha256')
    if original_hash is not None and (record['original_text'] is None or digest(record['original_text'])!=original_hash):
        raise EnqueueError('Original source checksum mismatch')
    if failed:
        failure=record.get('failure')
        if not isinstance(failure,dict) or not all(isinstance(failure.get(k),str) and failure[k] for k in ('code','message')):
            raise EnqueueError('Invalid structured failure')
    else:
        if record['call_id'].startswith('failed_') or 'failure' in record: raise EnqueueError('Failure cannot be ready')
        if not isinstance(record.get('plan'),str) or not re.fullmatch(r'pln_[A-Za-z0-9_-]{1,156}',record['plan']):
            raise EnqueueError('Invalid first-class plan')
        if record.get('source_format')!='markdown': raise EnqueueError('Unsupported prepared content policy')
        if not content: raise EnqueueError('Empty ready content')
    for key in ('assets','references','directives','asset_references','staged_assets'):
        if key in record and not isinstance(record[key],list):
            raise EnqueueError('Invalid prepared '+key)
    if 'metadata' in record and not isinstance(record['metadata'],dict):
        raise EnqueueError('Invalid prepared metadata')
    seen=set()
    for asset in record.get('assets',[]):
        if not isinstance(asset,dict): raise EnqueueError('Invalid asset')
        path=asset.get('path')
        if (not isinstance(path,str) or not path.startswith('assets/') or '\\' in path or ':' in path
                or any(p in ('','.','..') for p in path.split('/')) or path.lower() in seen):
            raise EnqueueError('Invalid asset path')
        seen.add(path.lower())
        try:
            encoded=asset['content_hex']
            if not isinstance(encoded,str) or not re.fullmatch(r'(?:[a-fA-F0-9]{2})+',encoded):
                raise ValueError('Invalid asset hex')
            data=bytes.fromhex(encoded)
            if hashlib.sha256(data).hexdigest()!=asset['sha256']: raise ValueError('Asset checksum mismatch')
        except (KeyError,ValueError,TypeError) as exc:
            raise EnqueueError('Invalid asset bytes/checksum') from exc
    if 'routing' in record or 'raw_markdown' in record: raise EnqueueError('Duplicate/unprepared authoritative fields')
    return record['record_id'],record.get('plan')



def register_failure(ledger_db: Path, client: RedisClient, call_id: str, error: ErrorInfo) -> None:
    call=Call.load(call_id,client)
    call.evolve(error=error.model_dump()).save(client)
    record_response(ledger_db,call_id,RuntimeStore.key(call_id))


def enqueue_record(*, record: dict, control_db: Path, ledger_db: Path, client: RedisClient) -> EnqueueResult:
    record_id,plan_id=validate_input_record(record)
    call_id=record['call_id']
    fingerprint=hashlib.sha256(json.dumps(record,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    ensure_schema(ledger_db)
    with closing(connect(ledger_db)) as db,db:
        db.execute('CREATE TABLE IF NOT EXISTS enqueue_inputs (record_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, call_id TEXT NOT NULL UNIQUE, queued INTEGER NOT NULL DEFAULT 0)')
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT * FROM enqueue_inputs WHERE record_id=?',(record_id,)).fetchone()
        if row and (row['fingerprint']!=fingerprint or row['call_id']!=call_id):
            raise EnqueueError('record_id already belongs to different input')
        if not row:db.execute('INSERT INTO enqueue_inputs(record_id,fingerprint,call_id) VALUES (?,?,?)',(record_id,fingerprint,call_id))
    key=RuntimeStore.key(call_id)
    try:
        previous=Call.load(call_id,client)
    except MissingRecord:
        # A durable intake reservation never authorizes reconstruction of lost payloads.
        if row and row['queued']:raise
    else:
        if previous.fingerprint!=fingerprint:raise EnqueueError('Call already belongs to different input')
        record_call(ledger_db,call_id,{'runtime':key})
        if previous.error:record_response(ledger_db,call_id,key)
        with closing(connect(ledger_db)) as db,db:db.execute('UPDATE enqueue_inputs SET queued=1 WHERE record_id=?',(record_id,))
        return EnqueueResult(record_id,call_id,False,key,previous.error.code if previous.error else None)
    error=ErrorInfo(code=record['failure']['code'],message=record['failure']['message'],stage='ingest') if record['status']=='failed' else None
    plan=None
    if error is None:
        try:plan=materialize_plan(control_db,plan_id)
        except UnknownPlanError as exc:error=ErrorInfo(code='unknown_plan',message=str(exc),stage='control')
    original=record['original_text']
    call=Call(identity=call_id,submission_id=record['submission_id'],record_id=record_id,
        release_id=release_identity(),fingerprint=fingerprint,requested_plan_id=plan_id,retention_period_seconds=retention_seconds(),
        source=Source(original_text=original,original_sha256=digest(original) if original is not None else None,
            processing_text=record['content'],processing_sha256=record['content_sha256'],
            identity=record['source'].get('slug'),format=record['source_format'],coordination=record['source'],
            assets=record.get('assets',[]),
            resources={k:record[k] for k in ('references','directives','asset_references','staged_assets') if k in record}),
        plan=plan,baggage=record['baggage'],error=error)
    created=True
    try:call.save(client)
    except ConcurrentUpdate:
        call=Call.load(call_id,client)
        if call.fingerprint!=fingerprint:raise EnqueueError('Concurrent intake collision')
        created=False
    record_call(ledger_db,call_id,{'runtime':key})
    if call.error:record_response(ledger_db,call_id,key)
    with closing(connect(ledger_db)) as db,db:db.execute('UPDATE enqueue_inputs SET queued=1 WHERE record_id=?',(record_id,))
    return EnqueueResult(record_id,call_id,created,key,call.error.code if call.error else None)
