"""The selected on-demand lifecycle, without paid providers or external transport."""
import json
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from test_enqueue import FakeRedis, make_control, record
from autoscribe import ssh_jobs as jobs, worker
from biznet_common.llm import LLMError, Response

LAUNCH = jobs.launch


class DirectJobsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name); self.control=self.root/'control.sqlite'; self.ledger=self.root/'ledger.sqlite'
        make_control(self.control); jobs.initialize(self.ledger)
        self.dispatch='00000000-0000-4000-8000-000000000002'; self.digest='a'*64
        self.registry=self.root/'registry.json'; self.registry.write_text(json.dumps({'echo':'/usr/bin/cat'}))
        with closing(sqlite3.connect(self.control)) as db, db:
            db.execute("INSERT INTO steps VALUES ('stp_2','Second','script','extension',NULL,'echo',NULL,'{}')")
            db.execute("INSERT INTO plan_steps VALUES ('pln_TEST','stp_2',2)")
        self.client=FakeRedis()
        for target in [patch.object(jobs,'ROOT',self.root),
                       patch.dict(os.environ,{'AUTOSCRIBE_EXTENSION_REGISTRY':str(self.registry)}),
                       patch.object(jobs,'prepare_dropbox',return_value=json.dumps(record())),
                       patch.object(jobs,'launch',lambda l,d,h:jobs.read_job(l,d,h))]:
            target.start(); self.addCleanup(target.stop)
        self.accepted=jobs.submit(self.control,self.ledger,self.client,self.dispatch,self.digest,'fixture-only')

    def execute(self): return jobs.execute(self.ledger,self.client,self.dispatch,self.digest)
    def response(self): return json.loads((self.root/self.dispatch/'response.ndjson').read_text())
    def provider(self): return Response('GENERATED','OpenAI','gpt-5.6-luna','completed','response','request',{'tokens':1})

    def test_claim_chaining_delivery_replay_and_receipt(self):
        with patch.object(worker,'respond',return_value=self.provider()) as provider:
            self.assertEqual(self.execute()['state'],'completed')
            self.execute()
            jobs.submit(self.control,self.ledger,self.client,self.dispatch,self.digest,'fixture-only')
            self.assertEqual(provider.call_count,1)
            self.assertEqual(provider.call_args.args[2],'Hello')
        self.assertEqual(self.response()['result'],'GENERATED')
        self.assertEqual(self.response()['submission_id'],self.dispatch)
        self.assertFalse(self.client.zsets)
        state=jobs.read_job(self.ledger,self.dispatch,self.digest)
        with self.assertRaises(ValueError): jobs.cleanup(self.ledger,self.dispatch,self.digest,'0'*64)
        self.assertEqual(jobs.cleanup(self.ledger,self.dispatch,self.digest,state['response_sha256'])['state'],'cleaned')
        self.assertEqual(jobs.cleanup(self.ledger,self.dispatch,self.digest,state['response_sha256'])['state'],'cleaned')

    def test_provider_uncertainty_is_terminal_and_never_repeated(self):
        with patch.object(worker,'respond',side_effect=LLMError('audit','timeout','Provider execution status is unknown')) as provider:
            self.assertEqual(self.execute()['state'],'completed')
            self.assertEqual(self.response()['status'],'failed')
            self.assertIn('unknown',self.response()['error'])
            self.execute(); self.assertEqual(provider.call_count,1)

    def test_process_crash_after_claim_never_repeats_provider(self):
        with patch.object(worker,'respond',side_effect=SystemExit('interrupted')) as provider:
            with self.assertRaises(SystemExit):self.execute()
            self.assertEqual(self.execute()['state'],'running')
            self.assertEqual(provider.call_count,1)

    def test_interrupted_delivery_recovers_without_execution(self):
        with patch.object(worker,'respond',return_value=self.provider()) as provider:
            with patch.object(jobs,'response_file',side_effect=OSError('interrupted delivery')):
                with self.assertRaises(OSError):self.execute()
            self.assertEqual(self.execute()['state'],'completed')
            self.assertEqual(provider.call_count,1)
            self.assertEqual(self.response()['result'],'GENERATED')

    def test_concurrent_duplicate_claim_executes_once(self):
        entered=threading.Event();release=threading.Event();errors=[]
        def provider(*args,**kwargs):
            entered.set()
            if not release.wait(5):raise AssertionError('claim test timed out')
            return self.provider()
        def first():
            try:self.execute()
            except BaseException as exc:errors.append(exc)
        with patch.object(worker,'respond',side_effect=provider) as invoke:
            thread=threading.Thread(target=first);thread.start()
            try:
                self.assertTrue(entered.wait(5))
                self.assertEqual(self.execute()['state'],'running')
            finally:release.set();thread.join(5)
            self.assertFalse(thread.is_alive());self.assertEqual(errors,[]);self.assertEqual(invoke.call_count,1)

    def test_accepted_job_rejects_changed_release(self):
        with patch.dict(os.environ,{'AUTOSCRIBE_EXTENSION_REGISTRY':str(self.root/'another.json')}):
            with patch.object(worker,'respond') as provider:
                with self.assertRaisesRegex(ValueError,'refuse rebind'):self.execute()
                provider.assert_not_called()

    def test_transient_launch_pins_selected_executable_without_credentials(self):
        engine=self.root/'selected-engine';engine.mkdir()
        binding=self.root/self.dispatch/'execution-release.json';binding.unlink()
        with patch.dict(os.environ,{'AUTOSCRIBE_RELEASE_ROOT':str(engine),'OPENAI_API_KEY':'synthetic-secret'}):
            jobs.bind_release(self.dispatch)
            with patch.object(jobs.subprocess,'run',return_value=SimpleNamespace(stdout='not-found')) as run:
                LAUNCH(self.ledger,self.dispatch,self.digest)
            argv=run.call_args.args[0]
        self.assertIn(str(engine/'bin/asc'),argv)
        self.assertIn('AUTOSCRIBE_RELEASE_ROOT='+str(engine),argv)
        self.assertFalse(any('synthetic-secret' in v for v in argv))
        self.assertNotIn('--property=EnvironmentFile=/home/jeremy/.config/autoscribe/autoscribe.env',argv)

if __name__=='__main__':unittest.main()
