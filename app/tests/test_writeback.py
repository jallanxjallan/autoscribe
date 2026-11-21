"""Actual dispatcher -> canonical lifecycle -> packaged response -> Rust application.

Only paid SDK/embeddings and remote upload/download are deterministic fixtures.
No response object is fabricated at the client boundary.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
from unittest.mock import patch
import unittest

import test_composition as composition
from test_runtime import RuntimeCase
from asc.models.call import Call, ClientResponse
from asc.preprocess import prepare
from asc import ssh_jobs as jobs


class WritebackTests(composition.CompositionFixture):
    make_candidate=composition.CompositionTests.make_candidate
    plan=composition.CompositionTests.plan
    def setUp(self):
        super().setUp()
        self.client.command('CONFIG','SET','appendonly','yes')
        self.client.command('CONFIG','SET','appendfsync','always')
        self.shared=self.root/'.shared';self.shared.mkdir(mode=0o700)
        self.vault=self.root/'vault';self.vault.mkdir()
        self.adapter=self.root/'git.py'
        self.adapter.write_text('#!/usr/bin/python3\nimport os,sys\nos.execv("/usr/bin/python3",["/usr/bin/python3",'+repr(os.environ['AUTOSCRIBE_TEST_GIT_ADAPTER'])+',*sys.argv[1:]])\n')
        self.adapter.chmod(0o755)
        self.native_env=dict(os.environ,AUTOSCRIBE_GIT_ADAPTER=str(self.adapter))
        for args in [('init',),('config','user.name','Fixture'),('config','user.email','fixture@example.invalid')]:self.git(*args)
        self.raw='---\r\nslug: psg_0123456789ABCDEF\r\nstatus: draft # human\r\nplan: pln_TEST\r\ndispatch: true\r\nprocessed: null\r\nnarrative-mode: first-person\r\ntone: dry\r\n# retain formatting\r\n---\r\nOriginal café 東京.\r\n![[Example]]\r\n'
        (self.vault/'Note.md').write_bytes(self.raw.encode())
        (self.vault/'Example.md').write_bytes(b'---\r\nslug: psg_1123456789ABCDEF\r\n---\r\nResolved example prose.\r\n')
        self.git('add','.');self.git('commit','-m','Seed')

    def git(self,*args):
        return subprocess.check_output(['/usr/bin/python3',os.environ['AUTOSCRIBE_TEST_GIT_ADAPTER'],'-C',str(self.vault),*args],text=True)

    def native(self,name,*args):
        binary=Path(os.environ['AUTOSCRIBE_TEST_CLIENT_BIN']).parent/name
        result=subprocess.run([str(binary),*args,'--shared',str(self.shared),'--redis',f'127.0.0.1:{self.client.port}','--vault-root',str(self.vault)],env=self.native_env,capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)
        return result

    def pipeline(self,kinds):
        self.plan(kinds)
        self.native('dispatch','--request','Note.md')
        self.native('dispatch','--local-only','--once')
        rows=self.client.hgetall('autoscribe:client:jobs');self.assertEqual(len(rows),1)
        self.dispatch=next(iter(rows));job=json.loads(rows[self.dispatch])
        package=self.shared/f'autoscribe-{self.dispatch}.source'
        files={str(p.relative_to(package)):p.read_bytes() for p in package.rglob('*') if p.is_file()}
        self.checksum=hashlib.sha256(files.pop('SHA256SUMS.json')).hexdigest()
        self.prepared=prepare(jobs.source_envelope(self.dispatch,files))
        self.assertEqual(self.prepared['status'],'ready',self.prepared)
        with patch.object(jobs,'prepare_dropbox',return_value=json.dumps(self.prepared)):self.accept()
        state=self.execute();self.assertEqual(state['state'],'completed')
        call=Call.load(self.call_id,self.client)
        self.assertIsNone(call.error,call.error)
        self.assertEqual(call.source.original_text,self.raw)
        self.assertIn('![[Example]]',call.source.original_body)
        self.assertIn('Resolved example prose.',call.source.processing_text)
        self.assertNotEqual(call.source.original_text,call.source.processing_text)
        self.assertEqual(call.source.metadata['tone'],'dry')
        response=(jobs.ROOT/self.dispatch/'response.ndjson').read_bytes()
        self.assertEqual(hashlib.sha256(response).hexdigest(),state['response_sha256'])
        envelope=ClientResponse.model_validate_json(response)
        self.assertEqual(envelope.source['slug'],call.source.identity)
        self.assertEqual(envelope.terminal_step.id,call.final_result.step_id)
        # Substitute only remote I/O: stage the real checksum-verified server bytes.
        # The ordinary Rust application path, authorization and Git are unchanged.
        job.update(state='submitted',call_id=self.call_id,transport='fixture',server_package_sha256=self.checksum)
        self.client.command('HSET','autoscribe:client:jobs',self.dispatch,json.dumps(job,sort_keys=True,separators=(',',':'),ensure_ascii=False))
        target=self.vault/'Note.md'
        edited=self.raw.replace('status: draft # human','status: reviewed # human').replace('tone: dry','tone: reflective')
        target.write_bytes(edited.encode())
        before={p.name:p.read_bytes() for p in self.vault.glob('*.md') if p!=target}
        delivery=self.shared/f'autoscribe-response-{self.dispatch}.ndjson';delivery.write_bytes(response)
        self.native('autoscribe-apply','--once')
        applied=json.loads(self.client.hgetall('autoscribe:client:jobs')[self.dispatch])
        self.assertEqual(applied['state'],'applied',str(applied.get('error'))+' responses='+str(self.client.hgetall('autoscribe:client:responses'))+' staging='+str(self.client.hgetall('autoscribe:client:response-staging')))
        at=applied['application_timestamp']
        front=edited[:edited.index('---\r\n',5)+5]
        expected_front=front.replace('plan: pln_TEST','plan: ""').replace('dispatch: true','dispatch: false').replace('processed: null',f'processed: "{at}"')
        self.assertEqual(target.read_bytes(),(expected_front+call.final_result.delivery_text).encode())
        self.assertEqual({p.name:p.read_bytes() for p in self.vault.glob('*.md') if p!=target},before)
        self.assertIn('status: reviewed # human',target.read_text())
        self.assertNotIn('status: draft',target.read_text())
        self.assertEqual(applied['receipt']['receipt_id'],envelope.receipt_id)
        self.assertEqual(applied['receipt']['response_sha256'],state['response_sha256'])
        self.assertEqual(jobs.read_job(self.ledger,self.dispatch,self.checksum)['state'],'completed')
        commits=self.git('rev-list','--count','HEAD')
        delivery.write_bytes(response);self.native('autoscribe-apply','--once')
        self.assertEqual(self.git('rev-list','--count','HEAD'),commits)
        self.assertEqual(self.api.responses.create.call_count,kinds.count('llm'))
        # Acknowledgement is a separate checksum-bound lifecycle operation.
        cleaned=jobs.cleanup(self.ledger,self.dispatch,self.checksum,state['response_sha256'],self.client)
        self.assertEqual(cleaned['state'],'cleaned')
        deadline=Call.load(self.call_id,self.client).retention_deadline
        jobs.cleanup(self.ledger,self.dispatch,self.checksum,state['response_sha256'],self.client)
        self.assertEqual(Call.load(self.call_id,self.client).retention_deadline,deadline)
        self.assertEqual(self.git('status','--porcelain'),'')

    def test_llm_script_through_rust_writeback_and_cleanup(self):self.pipeline(['llm','script'])
    def test_repeated_rag_llm_through_rust_writeback_and_cleanup(self):self.pipeline(['rag','llm','rag','llm','script'])


class WireTests(RuntimeCase):
    def test_python_contract_fixture_and_strict_validation(self):
        self.accept();self.execute();call=Call.load(self.call_id,self.client)
        value=call.response_record(client_protocol=True)
        fixture=Path(__file__).with_name('client_response_fixture.json')
        if os.environ.get('AUTOSCRIBE_WRITE_WIRE_FIXTURE')=='1':fixture.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
        self.assertEqual(value,json.loads(fixture.read_text()))
        self.assertEqual(ClientResponse.model_validate(value).model_dump(mode='json',by_alias=True),value)
        for field in ['submission_id','call_id','record_id','result_sha256','receipt_id','result_bytes']:
            invalid=dict(value);invalid[field]='invalid'
            with self.assertRaises(ValueError):ClientResponse.model_validate(invalid)
        for field in ['identity','extra']:
            with self.assertRaises(ValueError):ClientResponse.model_validate(dict(value,**{field:'retired'}))
