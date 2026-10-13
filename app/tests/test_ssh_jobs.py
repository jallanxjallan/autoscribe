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
    def test_execute_once_without_queues_and_acknowledged_cleanup(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); control=root/'control.sqlite'; ledger=root/'ledger.sqlite'
            make_control(control)
            with sqlite3.connect(control) as db:
                db.execute("UPDATE steps SET engine_kind='script',engine='extension',model=NULL,script='echo'")
            registry=root/'registry.json'; registry.write_text(json.dumps({'echo':'/usr/bin/cat'}))
            dispatch='sub_direct_test'; package=root/dispatch; package.mkdir()
            value=record(); value['baggage']['client']={'submission_id':dispatch}
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
                self.assertEqual(response['baggage'],value['baggage'])
                with sqlite3.connect(ledger) as db:
                    self.assertEqual(db.execute('SELECT count(*) FROM exports').fetchone()[0],1)
                with self.assertRaises(ValueError): jobs.cleanup(ledger,dispatch,digest,'0'*64)
                jobs.cleanup(ledger,dispatch,digest,completed['response_sha256'])
                self.assertFalse(package.exists())
                self.assertEqual(jobs.cleanup(ledger,dispatch,digest,completed['response_sha256'])['state'],'cleaned')
                self.assertEqual(jobs.submit(control,ledger,client,dispatch,digest)['state'],'cleaned')

if __name__=='__main__': unittest.main()
