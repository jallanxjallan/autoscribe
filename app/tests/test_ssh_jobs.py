import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_enqueue import FakeRedis, make_control, record
from autoscribe import ssh_jobs as jobs

class DirectJobsTests(unittest.TestCase):
    def test_transient_launch_pins_engine_and_selected_nonsecret_dependencies(self):
        import os
        import sys
        from types import SimpleNamespace
        state={'state':'accepted','call_id':'call_test'}
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);one=root/'version-one';two=root/'version-two';one.mkdir();two.mkdir()
            current=root/'current';current.symlink_to(one,target_is_directory=True)
            env={'TEMPLATES_ROOT':str(current),'EXTENSIONS_ROOT':str(one),
                 'AUTOSCRIBE_CONTROL_DB':str(root/'control.sqlite'),
                 'OPENAI_API_KEY':'must-not-appear-in-argv'}
            with patch.dict(os.environ,env),patch.object(jobs,'read_job',return_value=state),patch.object(jobs.subprocess,'run',return_value=SimpleNamespace(stdout='not-found')) as run:
                jobs.launch(root/'ledger.sqlite','00000000-0000-4000-8000-000000000001','a'*64)
                argv=run.call_args.args[0]
            self.assertIn(str(Path(jobs.__file__).resolve().parents[1]/'bin/asc'),argv)
            self.assertIn(sys.executable,argv)
            self.assertIn('TEMPLATES_ROOT='+str(one),argv)
            self.assertFalse(any('must-not-appear' in arg for arg in argv))
            self.assertNotIn('--property=EnvironmentFile=/home/jeremy/.config/autoscribe/autoscribe.env',argv)
            current.unlink();current.symlink_to(two,target_is_directory=True)
            self.assertIn('TEMPLATES_ROOT='+str(one),argv)

    def test_execute_once_without_queues_and_acknowledged_cleanup(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); control=root/'control.sqlite'; ledger=root/'ledger.sqlite'
            make_control(control)
            with sqlite3.connect(control) as db:
                db.execute("UPDATE steps SET engine_kind='script',engine='extension',model=NULL,script='echo'")
            registry=root/'registry.json'; registry.write_text(json.dumps({'echo':'/usr/bin/cat'}))
            dispatch='00000000-0000-4000-8000-000000000003'; package=root/dispatch; package.mkdir()
            value={'schema':'autoscribe.document.v1','document':'Hello','submission_id':dispatch,'metadata':{'plan':'pln_TEST'},
                   'baggage':{'client':{}}}
            data=json.dumps(value).encode(); (package/'request.ndjson').write_bytes(data)
            manifest=hashlib.sha256(data).hexdigest()+'  request.ndjson\n'
            (package/'SHA256SUMS').write_text(manifest)
            digest=hashlib.sha256(manifest.encode()).hexdigest()
            (package/'.package-sha256').write_text(digest)
            client=FakeRedis(); jobs.initialize(ledger)
            with patch.object(jobs,'ROOT',root), patch.object(jobs,'launch',lambda l,d,h:jobs.read_job(l,d,h)), patch.dict('os.environ',{'AUTOSCRIBE_EXTENSION_REGISTRY':str(registry)}):
                accepted=jobs.submit(control,ledger,client,dispatch,digest)
                replay=jobs.submit(control,ledger,client,dispatch,digest)
                self.assertEqual(accepted['call_id'],replay['call_id'])
                self.assertFalse(client.zsets)
                with patch.object(jobs,'execute_task',wraps=jobs.execute_task) as engine:
                    completed=jobs.execute(ledger,client,dispatch,digest)
                    self.assertEqual(completed['state'],'completed')
                    jobs.execute(ledger,client,dispatch,digest)
                    self.assertEqual(engine.call_count,1)
                self.assertFalse(client.zsets)
                response=json.loads((package/'response.ndjson').read_text())
                self.assertEqual(response['result'],'Hello')
                self.assertEqual(response['result_bytes'],len(response['result'].encode('utf-8')))
                self.assertEqual(response['result_sha256'],hashlib.sha256(response['result'].encode('utf-8')).hexdigest())
                self.assertEqual(response['submission_id'],dispatch)
                self.assertEqual(response['baggage']['client'],value['baggage']['client'])
                with sqlite3.connect(ledger) as db:
                    self.assertEqual(db.execute('SELECT count(*) FROM exports').fetchone()[0],1)
                # A failed status without a failure detail must not become a success.
                with sqlite3.connect(ledger) as db:
                    db.execute("UPDATE ssh_jobs SET state='running' WHERE dispatch_id=?",(dispatch,))
                client.hset(f"response:{accepted['call_id']}:content",{'status':'failed'})
                completed=jobs.complete_response(ledger,client,jobs.read_job(ledger,dispatch,digest))
                self.assertEqual(json.loads((package/'response.ndjson').read_text())['status'],'failed')
                retained=(package/'response.ndjson').read_bytes()
                with sqlite3.connect(ledger) as db:
                    db.execute("UPDATE ssh_jobs SET state='running' WHERE dispatch_id=?",(dispatch,))
                client.hset(f"response:{accepted['call_id']}:content",{'status':'running'})
                with self.assertRaisesRegex(ValueError,'not terminal'):
                    jobs.complete_response(ledger,client,jobs.read_job(ledger,dispatch,digest))
                self.assertEqual((package/'response.ndjson').read_bytes(),retained)
                with sqlite3.connect(ledger) as db:
                    db.execute("UPDATE ssh_jobs SET state='completed' WHERE dispatch_id=?",(dispatch,))
                with self.assertRaises(ValueError): jobs.cleanup(ledger,dispatch,digest,'0'*64)
                jobs.cleanup(ledger,dispatch,digest,completed['response_sha256'])
                self.assertFalse(package.exists())
                self.assertEqual(jobs.cleanup(ledger,dispatch,digest,completed['response_sha256'])['state'],'cleaned')
                self.assertEqual(jobs.submit(control,ledger,client,dispatch,digest)['state'],'cleaned')

if __name__=='__main__': unittest.main()
