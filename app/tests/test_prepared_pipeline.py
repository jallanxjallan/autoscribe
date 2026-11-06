"""Isolated Redis + real asc/Pandoc integration. Never starts an execution worker."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from autoscribe.enqueue import enqueue_record, EnqueueError
from autoscribe.effects import build_pending_record, iter_pending_ndjson
from autoscribe.ledger import record_response
from autoscribe.preprocess import prepare
from autoscribe.redis_runtime import RedisClient, load_json, EXECUTOR_QUEUE_KEY
from test_enqueue import make_control
from test_preprocess import document


class IsolatedRedisCase(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));self.port=sock.getsockname()[1]
        self.server=subprocess.Popen(['/usr/bin/redis-server','--bind','127.0.0.1','--port',str(self.port),
             '--save','','--appendonly','no','--dir',str(self.root)],stdout=subprocess.DEVNULL)
        self.addCleanup(self.server.wait);self.addCleanup(self.server.terminate)
        self.addCleanup(self.tmp.cleanup)
        self.client=RedisClient(port=self.port)
        for _ in range(100):
            try:self.client.ping();break
            except OSError:time.sleep(.01)
        else:self.fail('Isolated Redis did not start')
        self.control=self.root/'control.sqlite';self.ledger=self.root/'ledger.sqlite';make_control(self.control)
        self.asc=Path(__file__).resolve().parents[1]/'bin/asc'
        self.env={**os.environ,'AUTOSCRIBE_CONTROL_DB':str(self.control),'AUTOSCRIBE_LEDGER_DB':str(self.ledger),
                  'AUTOSCRIBE_REDIS_HOST':'127.0.0.1','AUTOSCRIBE_REDIS_PORT':str(self.port),'PYTHONDONTWRITEBYTECODE':'1'}

    def cli(self, *args, payload=''):
        return subprocess.run([sys.executable,'-B',str(self.asc),*args],input=payload,text=True,capture_output=True,env=self.env)

    def enqueue(self, record):
        return enqueue_record(record=record,control_db=self.control,ledger_db=self.ledger,client=self.client)

class PreparedPipelineTests(IsolatedRedisCase):
    def test_cli_allocates_once_before_retryable_delivery(self):
        import uuid
        first=self.cli('submission-id');second=self.cli('submission-id')
        self.assertEqual(first.returncode,0,first.stderr)
        self.assertEqual(second.returncode,0,second.stderr)
        identifiers=[first.stdout.strip(),second.stdout.strip()]
        self.assertNotEqual(*identifiers)
        for identity in identifiers:self.assertEqual(uuid.UUID(identity).version,4)
        value=document(submission=identifiers[0]);payload=json.dumps(value)+'\n'
        accepted=self.cli('ingest',payload=payload)
        retried=self.cli('ingest',payload=payload)
        self.assertEqual(accepted.returncode,0,accepted.stderr)
        self.assertEqual(retried.returncode,0,retried.stderr)
        self.assertEqual(json.loads(accepted.stdout)['call_id'],json.loads(retried.stdout)['call_id'])
        self.assertFalse(json.loads(retried.stdout)['created'])

    def test_cli_mixed_records_retry_response_export_and_ledger(self):
        raw='---\r\nplan: pln_TEST\r\nslug: psg_original\r\n---\r\n## **Café** — 東京\r\nBody  \r\n'
        value=document(raw,source={'path':'Notes/original.md'},submission='00000000-0000-4000-8000-000000000006')
        cp=self.cli('ingest',payload='{invalid json}\n'+json.dumps(value)+'\n')
        self.assertEqual(cp.returncode,1,cp.stderr)
        lines=[json.loads(x) for x in cp.stdout.splitlines()]
        self.assertEqual(lines[0]['schema'],'autoscribe.ingest-error.v1')
        receipt=lines[1];cid=receipt['call_id']
        content=load_json(self.client,f'call:{cid}:content');baggage=load_json(self.client,f'call:{cid}:baggage')
        self.assertEqual(content['input']['content'].encode(),raw.encode())
        self.assertEqual(baggage['custom'],value['baggage']['custom'])
        self.assertEqual(content['routing']['plan_id'],'pln_TEST')
        self.assertEqual(content['submission_id'],value['submission_id'])
        replay=self.cli('ingest',payload=json.dumps(value)+'\n')
        self.assertEqual(replay.returncode,0,replay.stderr)
        self.assertFalse(json.loads(replay.stdout)['created'])
        self.assertEqual(self.client.zrange(EXECUTOR_QUEUE_KEY,0,-1),[cid])
        # Synthetic response verifies transport only; no model or worker runs.
        key=f'response:{cid}:content';self.client.hset(key,{'content':'Synthetic response'})
        record_response(self.ledger,cid,key)
        response=self.cli('response',cid)
        self.assertEqual(json.loads(response.stdout)['baggage'],baggage)
        self.assertEqual(json.loads(response.stdout)['submission_id'],value['submission_id'])
        exported=[json.loads(x) for x in iter_pending_ndjson(self.ledger,self.client)]
        self.assertEqual(exported[0]['baggage'],baggage)
        self.assertEqual(exported[0]['submission_id'],value['submission_id'])
        with sqlite3.connect(self.ledger) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM calls').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT role FROM call_keys ORDER BY role').fetchall(),[('baggage',),('content',)])
        changed=prepare({**value,'document':raw+'Changed'})
        with self.assertRaisesRegex(EnqueueError,'different input'):self.enqueue(changed)

    def test_structured_failure_never_queues_and_is_exportable(self):
        value=document('## No plan',metadata={});value['metadata']={}
        prepared=prepare(value);receipt=self.enqueue(prepared)
        self.assertEqual(self.client.zrange(EXECUTOR_QUEUE_KEY,0,-1),[])
        self.assertEqual(receipt.failure,'missing_plan')
        response=self.cli('response',receipt.call_id)
        parsed=json.loads(response.stdout)
        self.assertEqual(parsed['status'],'failed')
        self.assertEqual(parsed['baggage']['custom'],value['baggage']['custom'])
        self.assertEqual(build_pending_record(self.client,call_id=receipt.call_id,baggage_key=receipt.baggage_key)['baggage'],parsed['baggage'])
        with patch('autoscribe.preprocess.subprocess.run',side_effect=OSError('missing executable')):
            failed=prepare(document(submission='00000000-0000-4000-8000-000000000007'))
        receipt=self.enqueue(failed)
        self.assertEqual(receipt.failure,'pandoc_execution')
        self.assertEqual(self.client.zrange(EXECUTOR_QUEUE_KEY,0,-1),[])

    def test_enqueue_has_no_pandoc_and_file_stream_inputs_are_lossless(self):
        raw='---\r\nplan: pln_TEST\r\n---\r\n## Heading\r\nBody\r\n'
        path=self.root/'Original.md';path.write_bytes(raw.encode())
        cp=self.cli('prepare-file',str(path),'--submission-id','00000000-0000-4000-8000-000000000004')
        self.assertEqual(cp.returncode,0,cp.stdout)
        prepared=json.loads(cp.stdout)
        self.assertEqual(prepared['content'].encode(),path.read_bytes())
        self.assertNotIn('path',prepared['source'])
        # An unavailable Pandoc cannot affect prepared-only enqueue.
        self.env['AUTOSCRIBE_PANDOC']='/missing/pandoc'
        cp=self.cli('enqueue',payload=json.dumps(prepared)+'\n')
        self.assertEqual(cp.returncode,0,cp.stderr)
        self.env['AUTOSCRIBE_PANDOC']=os.environ['AUTOSCRIBE_PANDOC']
        cp=self.cli('prepare-file','-','--submission-id','00000000-0000-4000-8000-000000000009',payload=raw)
        stream=json.loads(cp.stdout)
        self.assertEqual(stream['content'].encode(),raw.encode())
        self.assertNotIn('path',stream['source'])
        self.assertNotEqual(prepared['call_id'],stream['call_id'])
        self.assertEqual(self.enqueue(stream).created,True)
        cp=self.cli('prepare-file',str(self.root/'missing.md'),'--submission-id','00000000-0000-4000-8000-000000000005')
        missing=json.loads(cp.stdout)
        self.assertEqual(missing['failure']['code'],'unreadable_document')
        self.assertEqual(missing['submission_id'],'00000000-0000-4000-8000-000000000005')




class ClientAdapterPipelineTests(IsolatedRedisCase):
    @unittest.skipUnless(os.environ.get('AUTOSCRIBE_TEST_CLIENT_BIN'),'set AUTOSCRIBE_TEST_CLIENT_BIN for native-client smoke')
    def test_native_client_uuid_and_staged_retry_match_server_contract(self):
        import uuid
        binary=Path(os.environ['AUTOSCRIBE_TEST_CLIENT_BIN']).resolve()
        # These are test-owned Redis settings and temporary AOF files only.
        self.client.command('CONFIG','SET','appendonly','yes')
        self.client.command('CONFIG','SET','appendfsync','always')
        shared=self.root/'.shared';shared.mkdir(mode=0o700)
        vault=self.root/'vault';vault.mkdir()
        raw=b'---\r\nplan: pln_TEST\r\n---\r\n## Native client\r\nBody\r\n'
        source=vault/'Note.md';source.write_bytes(raw)
        common=['--redis',f'127.0.0.1:{self.port}','--shared',str(shared),'--vault-root',str(vault)]
        def client(*args):
            return subprocess.run([str(binary),*args,*common],capture_output=True,text=True,env=self.env)
        requested=client('--request','Note.md')
        self.assertEqual(requested.returncode,0,requested.stderr)
        jobs=self.client.hgetall('autoscribe:client:jobs')
        self.assertEqual(len(jobs),1)
        identifier=next(iter(jobs));self.assertEqual(uuid.UUID(identifier).version,4)
        prepared=client('--local-only','--once')
        self.assertEqual(prepared.returncode,0,prepared.stderr)
        staged=shared/f'autoscribe-{identifier}.request.ndjson';frozen=staged.read_bytes()
        request=json.loads(frozen)
        self.assertEqual(request['submission_id'],identifier)
        self.assertEqual(request['raw_markdown'].encode(),raw)
        self.assertEqual(request['record_id'],'inp_'+hashlib.sha256(identifier.encode()).hexdigest()[:32])
        self.assertNotIn('submission_id',request['baggage']['client'])
        accepted=self.cli('ingest',payload=frozen.decode())
        self.assertEqual(accepted.returncode,0,accepted.stderr)
        receipt=json.loads(accepted.stdout)
        self.assertEqual(receipt['record_id'],request['record_id'])
        self.assertEqual(receipt['call_id'],'call_'+hashlib.sha1(identifier.encode()).hexdigest())
        source.write_bytes(b'edited after durable staging')
        self.assertEqual(client('--request','Note.md').returncode,0)
        self.assertEqual(client('--local-only','--once').returncode,0)
        self.assertEqual(staged.read_bytes(),frozen)
        self.assertEqual(list(self.client.hgetall('autoscribe:client:jobs')),[identifier])
        repeated=self.cli('ingest',payload=frozen.decode())
        self.assertEqual(repeated.returncode,0,repeated.stderr)
        self.assertEqual(json.loads(repeated.stdout)['call_id'],receipt['call_id'])
        self.assertFalse(json.loads(repeated.stdout)['created'])


if __name__=='__main__':unittest.main()
