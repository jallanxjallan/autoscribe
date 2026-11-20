"""Real Redis and executable components; deterministic Common SDK; no external requests."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

from asc import ssh_jobs as jobs, worker
from asc.control import materialize_plan
from asc.enqueue import enqueue_record, EnqueueError
from asc.models.call import (Call, Invocation, InvalidRecord, MissingRecord, ConcurrentUpdate,
    StorageUnavailable, RuntimeStore, StepExecution, ErrorInfo)
from asc.settings import retention_seconds
from asc.preprocess import prepare
from biznet_common.redis import RedisClient
from biznet_common import llm

ROOT=Path(__file__).resolve().parent
SCHEMA='''
CREATE TABLE control_meta(key TEXT PRIMARY KEY,value TEXT);
CREATE TABLE plans(id TEXT PRIMARY KEY,label TEXT,description TEXT,scope TEXT);
CREATE TABLE steps(id TEXT PRIMARY KEY,label TEXT,engine_kind TEXT,engine TEXT,model TEXT,script TEXT,rag_profile TEXT,args_json TEXT,source_commit TEXT,content_sha256 TEXT);
CREATE TABLE instructions(id TEXT PRIMARY KEY,label TEXT,kind TEXT,body TEXT,source_commit TEXT,content_sha256 TEXT);
CREATE TABLE plan_steps(plan_id TEXT,step_id TEXT,position INTEGER);
CREATE TABLE step_instructions(step_id TEXT,instruction_id TEXT,component TEXT,position INTEGER);
'''

def make_control(path):
    revision='d'*40
    with closing(sqlite3.connect(path)) as db,db:
        db.executescript(SCHEMA);db.execute('INSERT INTO control_meta VALUES (?,?)',('source_commit',revision))
        db.execute("INSERT INTO plans VALUES ('pln_TEST','Test','','books')")
        for position,kind,component in [(1,'llm','luna'),(3,'script','pair'),(8,'script','echo')]:
            db.execute('INSERT INTO steps VALUES (?,?,?,?,?,?,?,?,?,?)',('stp_'+str(position),'Step',kind,'chatgpt' if kind=='llm' else 'extension',component if kind=='llm' else None,component if kind=='script' else None,None,'{}',revision,'a'*64))
            db.execute('INSERT INTO plan_steps VALUES (?,?,?)',('pln_TEST','stp_'+str(position),position))
        db.execute('INSERT INTO instructions VALUES (?,?,?,?,?,?)',('rol_1','Role','role','Use deliberately generic prose.',revision,'b'*64))
        db.execute("INSERT INTO step_instructions VALUES ('stp_1','rol_1','role',1)")


class RuntimeCase(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.control=self.root/'control.sqlite';self.ledger=self.root/'ledger.sqlite';make_control(self.control)
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        self.server=subprocess.Popen(['/usr/bin/redis-server','--bind','127.0.0.1','--port',str(port),'--save','','--appendonly','no','--dir',str(self.root)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        self.addCleanup(self.tmp.cleanup);self.addCleanup(self.stop_server)
        self.client=RedisClient(port=port)
        for _ in range(100):
            try:self.client.ping();break
            except OSError:time.sleep(.01)
        else:self.fail('Isolated Redis did not start')
        self.registry=self.root/'registry.json';self.registry.write_text(json.dumps({'pair':str(ROOT/'pair_fixture.py'),'echo':str(ROOT/'echo_fixture.py'),'smoke-test':str(Path(os.environ['EXTENSIONS_ROOT'])/'scripts/smoke-test.py')}))
        self.env={'AUTOSCRIBE_REDIS_HOST':'127.0.0.1','AUTOSCRIBE_REDIS_PORT':str(port),
            'AUTOSCRIBE_LEDGER_DB':str(self.ledger),'AUTOSCRIBE_CONTROL_DB':str(self.control),
            'AUTOSCRIBE_RELEASE_ROOT':str(self.root/'fixture-release'),'AUTOSCRIBE_EXTENSION_REGISTRY':str(self.registry),
            'AUTOSCRIBE_RUNTIME_RETENTION_SECONDS':'259200','OPENAI_API_KEY':'synthetic-not-a-real-key'}
        env=patch.dict(os.environ,self.env);env.start();self.addCleanup(env.stop)
        root=patch.object(jobs,'ROOT',self.root);root.start();self.addCleanup(root.stop)
        self.dispatch='00000000-0000-4000-8000-000000000002';self.checksum='a'*64
        self.raw='---\r\nslug: psg_0123456789ABCDEF\r\n---\r\nOriginal human prose — café 東京.  \r\n'
        self.prepared=prepare({'schema':'autoscribe.document.v1','document':self.raw,'submission_id':self.dispatch,
            'metadata':{'plan':'pln_TEST','tone':'dry','narrative_mode':'first person'},'source':{},'baggage':{'client':{}}})
        self.assertEqual(self.prepared['status'],'ready',self.prepared)
        jobs.initialize(self.ledger)
        launch=patch.object(jobs,'launch',lambda l,d,h:jobs.read_job(l,d,h));launch.start();self.addCleanup(launch.stop)
        transport=patch.object(jobs,'prepare_dropbox',return_value=json.dumps(self.prepared));transport.start();self.addCleanup(transport.stop)
        self.sdk=SimpleNamespace(APITimeoutError=type('Timeout',(Exception,),{}),APIConnectionError=type('Connection',(Exception,),{}),APIStatusError=type('Status',(Exception,),{}))
        self.api=Mock();response=SimpleNamespace(output_text='Generic generated prose.',model='gpt-5.6-luna',status='completed',id='response-id',_request_id='request-id',usage=SimpleNamespace(model_dump=lambda:{'total_tokens':9}))
        self.api.responses.create.return_value=response
        self.sdk.OpenAI=Mock();self.sdk.OpenAI.return_value.__enter__=Mock(return_value=self.api);self.sdk.OpenAI.return_value.__exit__=Mock(return_value=False)
        sdk=patch.object(llm,'_sdk',return_value=self.sdk);sdk.start();self.addCleanup(sdk.stop)

    def stop_server(self):
        self.server.terminate()
        try:self.server.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.server.kill();self.server.wait(timeout=3)

    def accept(self):
        value=jobs.submit(self.control,self.ledger,self.client,self.dispatch,self.checksum,'fixture')
        self.call_id=value['call_id'];return value

    def execute(self):return jobs.execute(self.ledger,self.client,self.dispatch,self.checksum)


class CanonicalTests(RuntimeCase):
    def test_model_roundtrip_original_request_and_interchangeable_executables(self):
        self.accept();before=Call.load(self.call_id,self.client)
        self.assertEqual(before.source.original_text,self.raw)
        self.assertEqual(self.client.command('TTL',RuntimeStore.key(self.call_id)),-1)
        state=self.execute();self.assertEqual(state['state'],'completed')
        call=Call.load(self.call_id,self.client)
        self.assertIsNone(call.error,call.error)
        self.assertEqual(call.source.original_text,self.raw)
        self.assertEqual(call.result(3).data['generated'],'Generic generated prose.')
        self.assertEqual(call.result(3).data['original'],self.raw)
        self.assertEqual(call.result(3).data['identity'],'psg_0123456789ABCDEF')
        self.assertEqual(call.result(3).data['tone'],'dry')
        self.assertEqual(call.result(8).data,call.result(3).data)
        self.assertEqual(call.steps['1'].request.payload,self.api.responses.create.call_args.kwargs)
        self.assertEqual(call.steps['1'].request.payload['instructions'],'Use deliberately generic prose.')
        self.assertEqual(call.result(1).provider.usage,{'total_tokens':9})
        self.assertEqual(call.final_result,call.result(8))
        self.assertEqual(call.plan.revision,'d'*40)
        self.assertEqual(self.client.command('DBSIZE'),1)
        self.assertNotIn('original_text',call.steps['3'].invocation.model_dump_json())
        with closing(sqlite3.connect(self.ledger)) as db:
            self.assertEqual([r[1] for r in db.execute('PRAGMA table_info(calls)')],['call_id','created_at'])
            self.assertEqual(db.execute('SELECT role FROM call_keys').fetchall(),[('runtime',)])

    def test_original_and_processing_content_are_distinct(self):
        self.prepared['content']='Expanded processing text';self.prepared['content_sha256']=hashlib.sha256(self.prepared['content'].encode()).hexdigest()
        with patch.object(jobs,'prepare_dropbox',return_value=json.dumps(self.prepared)):self.accept()
        call=Call.load(self.call_id,self.client)
        self.assertEqual(call.source.original_text,self.raw);self.assertEqual(call.invocation(1).input.text,'Expanded processing text')

    def test_invalid_data_identity_and_original_replacement_fail(self):
        self.accept();call=Call.load(self.call_id,self.client)
        with self.assertRaises(InvalidRecord):call.evolve(source={**call.source.model_dump(),'original_text':'wrong'}).save(self.client)
        changed=dict(call.source.model_dump(),original_text='wrong',original_sha256=hashlib.sha256(b'wrong').hexdigest())
        with self.assertRaisesRegex(InvalidRecord,'immutable'):call.evolve(source=changed).save(self.client)
        self.client.command('SET',RuntimeStore.key(self.call_id),'{malformed')
        with self.assertRaises(InvalidRecord):Call.load(self.call_id,self.client)
        self.client.command('DEL',RuntimeStore.key(self.call_id))
        with self.assertRaises(MissingRecord):Call.load(self.call_id,self.client)
        with self.assertRaises(MissingRecord):enqueue_record(record=self.prepared,control_db=self.control,ledger_db=self.ledger,client=self.client)
        self.assertEqual(self.api.responses.create.call_count,0)

    def test_cas_rejects_stale_writers(self):
        self.accept();one=Call.load(self.call_id,self.client);two=Call.load(self.call_id,self.client)
        one.with_step(1,StepExecution(invocation=one.invocation(1))).save(self.client)
        with self.assertRaises(ConcurrentUpdate):two.evolve(error=ErrorInfo(code='test',message='test',stage='test').model_dump()).save(self.client)

    def test_plain_text_script_protocol_and_wrong_owner_are_rejected(self):
        self.accept();call=Call.load(self.call_id,self.client)
        with self.assertRaisesRegex(InvalidRecord,'stdout'):worker.run_extension(Path('/usr/bin/cat'),call.invocation(1),5)
        self.assertEqual(self.api.responses.create.call_count,0)

    def test_active_scripts_converted_to_typed_protocol(self):
        with closing(sqlite3.connect(self.control)) as db,db:
            db.execute('DELETE FROM plan_steps WHERE position!=1')
            db.execute("UPDATE steps SET engine_kind='script',engine='extension',model=NULL,script='smoke-test' WHERE id='stp_1'")
        valid='AUTOSCRIBE_LLM_SMOKE_V1\nROLE=PASS\nCONTEXT=PASS\nTASK=PASS\nINPUT=AUTOSCRIBE_SMOKE_INPUT_V1'
        self.prepared['content']=valid;self.prepared['content_sha256']=hashlib.sha256(valid.encode()).hexdigest()
        with patch.object(jobs,'prepare_dropbox',return_value=json.dumps(self.prepared)):self.accept()
        self.assertEqual(self.execute()['state'],'completed')
        call=Call.load(self.call_id,self.client)
        self.assertIsNone(call.error,call.error)
        self.assertEqual(call.final_result.text,valid)

    def test_result_owner_mismatch_cannot_advance(self):
        self.accept()
        def alien(executable,invocation,timeout):
            return invocation.result(text='wrong').model_copy(update={'call_id':'foreign-call'})
        with patch.object(worker,'run_extension',side_effect=alien):self.execute()
        call=Call.load(self.call_id,self.client)
        self.assertIsNotNone(call.error);self.assertIn('ownership',call.error.message)
        self.assertNotIn('8',call.steps)

    def test_images_and_structured_asset_results_roundtrip(self):
        from asc.models.call import Asset
        data=b'synthetic-image-bytes';checksum=hashlib.sha256(data).hexdigest()
        self.prepared['content']='![image](assets/image.png)'
        self.prepared['content_sha256']=hashlib.sha256(self.prepared['content'].encode()).hexdigest()
        self.prepared['assets']=[{'path':'assets/image.png','sha256':checksum,'content_hex':data.hex()}]
        with patch.object(jobs,'prepare_dropbox',return_value=json.dumps(self.prepared)):self.accept()
        self.execute();call=Call.load(self.call_id,self.client)
        request=call.steps['1'].request.payload
        self.assertEqual(request['input'][0]['content'][1]['type'],'input_image')
        self.assertEqual(request,self.api.responses.create.call_args.kwargs)
        inv=call.steps['3'].invocation
        result=inv.result(data={'nested':[1,True,None]},assets=(Asset(path='output.png',sha256=checksum,uri='https://example.invalid/output.png'),))
        self.assertEqual(type(result).model_validate_json(result.model_dump_json()),result)
        self.assertEqual(result.output.assets[0].uri,'https://example.invalid/output.png')

    def test_runtime_storage_failure_is_explicit(self):
        self.accept()
        with patch.object(self.client,'command',side_effect=OSError('unavailable')):
            with self.assertRaises(StorageUnavailable):Call.load(self.call_id,self.client)


    @unittest.skipUnless(os.environ.get('AUTOSCRIBE_TEST_CLIENT_BIN'),'native client fixture not selected')
    def test_current_native_package_preserves_external_contract(self):
        from asc.dropbox_package import retrieve
        self.client.command('CONFIG','SET','appendonly','yes')
        self.client.command('CONFIG','SET','appendfsync','always')
        shared=self.root/'.shared';shared.mkdir(mode=0o700);vault=self.root/'vault';vault.mkdir()
        raw='---\r\nslug: psg_0123456789ABCDEF\r\nplan: pln_TEST\r\ndispatch: true\r\n---\r\nNative original café.\r\n'
        (vault/'Note.md').write_bytes(raw.encode())
        args=['--redis',f'127.0.0.1:{self.client.port}','--shared',str(shared),'--vault-root',str(vault)]
        for option in (['--request','Note.md'],['--local-only','--once']):
            cp=subprocess.run([os.environ['AUTOSCRIBE_TEST_CLIENT_BIN'],*option,*args],capture_output=True,text=True,timeout=30)
            self.assertEqual(cp.returncode,0,cp.stderr)
        identifiers=self.client.hgetall('autoscribe:client:jobs');self.assertEqual(len(identifiers),1)
        identity=next(iter(identifiers));package=shared/f'autoscribe-{identity}.source'
        files={str(p.relative_to(package)):p.read_bytes() for p in package.rglob('*') if p.is_file()}
        checksum=hashlib.sha256(files['SHA256SUMS.json']).hexdigest()
        remote=f'dropbox:ingest/dispatch/{identity}-{checksum}/'
        verified=retrieve('dispatch',identity,checksum,remote,4_194_304,read=lambda locator,limit:files[locator.removeprefix(remote)])
        prepared=prepare(jobs.source_envelope(identity,verified),work_dir=self.root,require_dispatch=True)
        receipt=enqueue_record(record=prepared,control_db=self.control,ledger_db=self.ledger,client=self.client)
        self.assertEqual(Call.load(receipt.call_id,self.client).source.original_text,raw)
        self.assertFalse(enqueue_record(record=prepared,control_db=self.control,ledger_db=self.ledger,client=self.client).created)



class LifecycleTests(RuntimeCase):
    def test_duplicate_claim_and_delivery_recovery_do_not_repeat_provider(self):
        self.accept()
        with patch.object(jobs,'response_file',side_effect=OSError('delivery interrupted')):
            with self.assertRaises(OSError):self.execute()
        self.assertEqual(self.client.command('TTL',RuntimeStore.key(self.call_id)),-1)
        self.assertEqual(self.execute()['state'],'completed');self.execute()
        self.assertEqual(self.api.responses.create.call_count,1)

    def test_unknown_provider_outcome_is_not_replayed(self):
        self.accept();self.api.responses.create.side_effect=self.sdk.APITimeoutError('private provider text')
        self.assertEqual(self.execute()['state'],'completed');self.execute()
        call=Call.load(self.call_id,self.client)
        self.assertTrue(call.error.uncertain);self.assertIn('unknown',call.error.message)
        self.assertNotIn('private provider text',call.error.message)
        self.assertIsNotNone(call.steps['1'].request)
        self.assertEqual(self.api.responses.create.call_count,1)
        self.assertEqual(self.client.command('TTL',RuntimeStore.key(self.call_id)),-1)

    def test_interrupted_execution_remains_persistent_and_never_replays(self):
        self.accept();self.api.responses.create.side_effect=SystemExit('process interrupted')
        with self.assertRaises(SystemExit):self.execute()
        self.assertEqual(self.execute()['state'],'running');self.assertEqual(self.api.responses.create.call_count,1)
        self.assertEqual(self.client.command('TTL',RuntimeStore.key(self.call_id)),-1)

    def test_concurrent_claims(self):
        self.accept();entered=threading.Event();release=threading.Event();errors=[]
        response=self.api.responses.create.return_value
        def blocked(**kwargs):
            entered.set()
            if not release.wait(5):raise AssertionError('timeout')
            return response
        self.api.responses.create.side_effect=blocked
        def first():
            try:self.execute()
            except BaseException as exc:errors.append(exc)
        thread=threading.Thread(target=first);thread.start()
        try:self.assertTrue(entered.wait(5));self.assertEqual(self.execute()['state'],'running')
        finally:release.set();thread.join(5)
        self.assertFalse(thread.is_alive());self.assertEqual(errors,[]);self.assertEqual(self.api.responses.create.call_count,1)

    def test_cleanup_starts_fixed_short_expiry_only_after_ack(self):
        self.assertEqual(retention_seconds(),259200)
        with patch.dict(os.environ,{'AUTOSCRIBE_RUNTIME_RETENTION_SECONDS':'2'}):
            self.accept();state=self.execute()
            self.assertEqual(self.client.command('TTL',RuntimeStore.key(self.call_id)),-1)
            with self.assertRaises(ValueError):jobs.cleanup(self.ledger,self.dispatch,self.checksum,'0'*64,self.client)
            jobs.cleanup(self.ledger,self.dispatch,self.checksum,state['response_sha256'],self.client)
            deadline=Call.load(self.call_id,self.client).retention_deadline
            jobs.cleanup(self.ledger,self.dispatch,self.checksum,state['response_sha256'],self.client)
            self.assertEqual(Call.load(self.call_id,self.client).retention_deadline,deadline)
            end=time.monotonic()+4
            while self.client.command('EXISTS',RuntimeStore.key(self.call_id)) and time.monotonic()<end:time.sleep(.05)
            with self.assertRaises(MissingRecord):Call.load(self.call_id,self.client)
            self.assertEqual(jobs.cleanup(self.ledger,self.dispatch,self.checksum,state['response_sha256'],self.client)['state'],'cleaned')
            self.execute();self.assertEqual(self.api.responses.create.call_count,1)

    def test_cleanup_retries_redis_failure_after_durable_ack(self):
        self.accept();state=self.execute()
        with patch.object(Call,'retain_after_cleanup',side_effect=StorageUnavailable('fixture')):
            with self.assertRaises(StorageUnavailable):jobs.cleanup(self.ledger,self.dispatch,self.checksum,state['response_sha256'],self.client)
        self.assertEqual(self.client.command('TTL',RuntimeStore.key(self.call_id)),-1)
        self.assertEqual(jobs.cleanup(self.ledger,self.dispatch,self.checksum,state['response_sha256'],self.client)['state'],'cleaned')
        self.assertGreater(self.client.command('TTL',RuntimeStore.key(self.call_id)),0)

    def test_accepted_release_cannot_be_rebound(self):
        self.accept()
        with patch.dict(os.environ,{'AUTOSCRIBE_RELEASE_ROOT':str(self.root/'different')}):
            with self.assertRaisesRegex(ValueError,'refuse rebind'):self.execute()
        self.assertEqual(self.api.responses.create.call_count,0)

if __name__=='__main__':unittest.main()
