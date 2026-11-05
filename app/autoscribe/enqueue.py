"""Prepared-call boundary. No document interpretation or Pandoc invocation."""
from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

from .control import materialize_plan
from .ids import validate_submission_id
from .ledger import connect, ensure_schema, record_call, record_response
from .redis_runtime import EXECUTOR_QUEUE_KEY, FORENSIC_TTL, RedisClient, load_json

INPUT_SCHEMA = 'autoscribe.prepared.v2'
CALL_SCHEMA = 'autoscribe.call-content.v2'


class EnqueueError(ValueError):
    pass


@dataclass(frozen=True)
class EnqueueResult:
    record_id: str
    call_id: str
    created: bool
    content_key: str
    baggage_key: str
    failure: str | None = None


def validate_input_record(record: object) -> tuple[str, str | None]:
    if not isinstance(record, dict) or record.get('schema')!=INPUT_SCHEMA:
        raise EnqueueError('asc enqueue requires autoscribe.prepared.v2; use asc ingest for documents')
    try:
        encoded=json.dumps(record, ensure_ascii=False, allow_nan=False).encode('utf-8')
    except (ValueError, TypeError, UnicodeError) as exc:
        raise EnqueueError('Invalid prepared serialization') from exc
    if len(encoded)>=2097152: raise EnqueueError('Prepared record exceeds transport limit')
    patterns={'record_id':r'inp_[0-9a-f]{32}', 'call_id':r'(?:call_[0-9a-f]{40}|failed_[0-9a-f]{64})',
              'submission_id':r'[0-9a-f-]{36}'}
    for key, pattern in patterns.items():
        if not isinstance(record.get(key), str) or not re.fullmatch(pattern,record[key]):
            raise EnqueueError('Invalid prepared '+key)
    try:
        validate_submission_id(record['submission_id'])
    except ValueError as exc:
        raise EnqueueError(str(exc)) from exc
    if 'call_source' in record:
        raise EnqueueError('call_source is not part of the prepared contract')
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


def build_call_content(record: dict, plan: dict) -> dict:
    result={'schema':CALL_SCHEMA,'record_id':record['record_id'],'call_id':record['call_id'],
            'submission_id':record['submission_id'],'source':record['source'],
            'routing':{'plan_id':record.get('plan')},'plan':plan,
            'input':{'content':record['content'],'content_sha256':record['content_sha256'],
                     'content_format':record['source_format'],'directive_policy':'inline.v1'}}
    for key in ('metadata','directives','assets','references','asset_references','staged_assets'):
        if key in record: result['input'][key]=record[key]
    if record['status']=='failed':
        result.update(failure=record['failure']['code'],failure_reason=record['failure']['message'])
    return result


def register_failure(ledger_db: Path, client: RedisClient, call_id: str, content: dict) -> None:
    key=f'response:{call_id}:content'
    client.hset(key,{'status':'failed','content':'','failure':content['failure'],'error':content['failure_reason']})
    record_response(ledger_db,call_id,key)


def enqueue_record(*, record: dict, control_db: Path, ledger_db: Path, client: RedisClient,
                   queue: bool = True) -> EnqueueResult:
    record_id,plan_id=validate_input_record(record)
    call_id=record['call_id'];failure=record.get('failure',{}).get('code')
    fingerprint=hashlib.sha256(json.dumps(record,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    ensure_schema(ledger_db)
    with closing(connect(ledger_db)) as db,db:
        db.execute('CREATE TABLE IF NOT EXISTS enqueue_inputs (record_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, call_id TEXT NOT NULL UNIQUE, queued INTEGER NOT NULL DEFAULT 0)')
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT * FROM enqueue_inputs WHERE record_id=?',(record_id,)).fetchone()
        if row:
            if row['fingerprint']!=fingerprint or row['call_id']!=call_id:
                raise EnqueueError('record_id already belongs to different input')
        else:
            db.execute('INSERT INTO enqueue_inputs(record_id,fingerprint,call_id) VALUES (?,?,?)',(record_id,fingerprint,call_id))
    content_key=f'call:{call_id}:content';baggage_key=f'call:{call_id}:baggage';marker=f'enqueue:{call_id}'
    if row and row['queued']:
        return EnqueueResult(record_id,call_id,False,content_key,baggage_key,failure)
    prior=client.command('GET',marker)
    if prior is not None and prior!=fingerprint: raise EnqueueError('enqueue marker collision')
    if prior==fingerprint:
        content=load_json(client,content_key)
        if failure: register_failure(ledger_db,client,call_id,content)
        with closing(connect(ledger_db)) as db,db:
            db.execute('UPDATE enqueue_inputs SET queued=1 WHERE record_id=?',(record_id,))
        return EnqueueResult(record_id,call_id,False,content_key,baggage_key,failure)
    # Existing Control authority resolves the explicit ID; no plan discovery here.
    plan={} if failure else materialize_plan(control_db,plan_id)
    content=build_call_content(record,plan)
    record_call(ledger_db,call_id,{'content':content_key,'baggage':baggage_key})
    created=client.command('EVAL', '''
        local prior=redis.call('GET',KEYS[1])
        if prior then
            if prior~=ARGV[1] then return redis.error_reply('enqueue collision') end
            return 0
        end
        redis.call('HSET',KEYS[2],'json',ARGV[2])
        redis.call('PERSIST',KEYS[2])
        redis.call('HSET',KEYS[3],'json',ARGV[3])
        redis.call('PERSIST',KEYS[3])
        if ARGV[6]=='1' then redis.call('ZADD',KEYS[4],0,ARGV[5]) end
        redis.call('SET',KEYS[1],ARGV[1])
        return 1
        ''',4,marker,content_key,baggage_key,EXECUTOR_QUEUE_KEY,fingerprint,
        json.dumps(content,ensure_ascii=False),json.dumps(record['baggage'],ensure_ascii=False),
        FORENSIC_TTL,call_id,int(queue and not failure))
    if failure: register_failure(ledger_db,client,call_id,content)
    with closing(connect(ledger_db)) as db,db:
        db.execute('UPDATE enqueue_inputs SET queued=1 WHERE record_id=?',(record_id,))
    return EnqueueResult(record_id,call_id,bool(created),content_key,baggage_key,failure)
