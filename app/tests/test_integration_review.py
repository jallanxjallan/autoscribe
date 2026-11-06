"""Independent boundary/fault checks for release qualification; no paid models."""
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import uuid
from unittest.mock import patch

from autoscribe import ssh_jobs as jobs
from autoscribe.enqueue import EnqueueError, enqueue_record
from autoscribe.exporter import iter_pending_records
from autoscribe.preprocess import prepare
from autoscribe.redis_runtime import EXECUTOR_QUEUE_KEY, WORKER_QUEUE_KEY, load_json
from test_prepared_pipeline import IsolatedRedisCase
from test_preprocess import document


def daemon(name, environment):
    path=Path(__file__).resolve().parents[1]/'daemon'/f'{name}.py'
    spec=importlib.util.spec_from_file_location(f'review_{name}',path)
    module=importlib.util.module_from_spec(spec)
    with patch.dict(os.environ,environment):spec.loader.exec_module(module)
    return module


class ReviewBoundaryTests(IsolatedRedisCase):
    def script_plan(self, executable='/usr/bin/cat'):
        with sqlite3.connect(self.control) as db:
            db.execute("UPDATE steps SET engine_kind='script',engine='extension',model=NULL,script='review-script'")
        registry=self.root/'registry.json';registry.write_text(json.dumps({'review-script':executable}))
        self.env['AUTOSCRIBE_EXTENSION_REGISTRY']=str(registry)
        return {'review-script':Path(executable)}

    def test_unknown_plan_is_terminal_discoverable_and_retry_stable(self):
        record=prepare(document(metadata={'plan':'pln_UNKNOWN'}))
        result=self.enqueue(record)
        self.assertEqual(result.failure,'unknown_plan')
        self.assertEqual(self.client.zrange(EXECUTOR_QUEUE_KEY,0,-1),[])
        response=self.cli('response',result.call_id)
        self.assertEqual(json.loads(response.stdout)['status'],'failed')
        self.assertTrue(json.loads(response.stdout)['failure'])
        self.assertTrue(json.loads(response.stdout)['error'])
        self.assertEqual(len(list(iter_pending_records(self.ledger,self.client))),1)
        repeated=self.enqueue(record)
        self.assertEqual(repeated.failure,'unknown_plan')
        self.assertFalse(repeated.created)
        self.assertEqual(repeated.call_id,result.call_id)

    def test_uuid_cannot_switch_execution_driver_after_acceptance(self):
        record=prepare(document())
        direct=enqueue_record(record=record,control_db=self.control,ledger_db=self.ledger,client=self.client,queue=False)
        with self.assertRaisesRegex(EnqueueError,'different input'):self.enqueue(record)
        self.assertEqual(self.client.zrange(EXECUTOR_QUEUE_KEY,0,-1),[])
        self.assertEqual(load_json(self.client,direct.content_key)['submission_id'],record['submission_id'])

    def test_redis_and_ledger_failure_retry_keep_one_call_and_do_not_execute(self):
        record=prepare(document())
        original=self.client.command
        def fail_materialization(*args):
            if args[0]=='EVAL':raise OSError('synthetic Redis interruption')
            return original(*args)
        with patch.object(self.client,'command',side_effect=fail_materialization):
            with self.assertRaises(OSError):self.enqueue(record)
        self.assertEqual(self.client.zrange(EXECUTOR_QUEUE_KEY,0,-1),[])
        with patch('autoscribe.enqueue.record_call',side_effect=sqlite3.OperationalError('synthetic ledger failure')):
            with self.assertRaises(sqlite3.OperationalError):self.enqueue(record)
        self.assertEqual(self.client.zrange(EXECUTOR_QUEUE_KEY,0,-1),[])
        result=self.enqueue(record)
        self.assertTrue(result.created)
        self.assertFalse(self.enqueue(record).created)
        with sqlite3.connect(self.ledger) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM calls').fetchone()[0],1)

    def test_stale_executor_and_worker_snapshots_cannot_repeat_a_step(self):
        registry=self.script_plan()
        receipt=self.enqueue(prepare(document()))
        executor=daemon('executord',self.env);worker=daemon('workerd',self.env)
        with patch.object(self.client,'zrange',return_value=[receipt.call_id]),patch.object(executor,'prepare_first_step',wraps=executor.prepare_first_step) as prepare_first:
            executor.process_active(self.client)
            task=f'task:{receipt.call_id}:1'
            with patch.object(self.client,'zrange',return_value=[task]),patch.object(worker,'execute_task',wraps=worker.execute_task) as execute:
                worker.process_ready(self.client,registry)
                worker.process_ready(self.client,registry)
                self.assertEqual(execute.call_count,1)
            executor.process_active(self.client)
            self.assertEqual(prepare_first.call_count,1)
        self.assertEqual(self.client.zrange(WORKER_QUEUE_KEY,0,-1),[])
        self.assertEqual(self.client.hgetall(f'response:{receipt.call_id}:content')['content'],'Body\n')

    def test_queued_execution_failure_has_response_and_never_requeues(self):
        registry=self.script_plan('/usr/bin/false')
        receipt=self.enqueue(prepare(document()))
        executor=daemon('executord',self.env);worker=daemon('workerd',self.env)
        executor.process_active(self.client)
        with patch.object(worker,'execute_task',wraps=worker.execute_task) as execute:
            worker.process_ready(self.client,registry)
            self.assertFalse(self.enqueue(prepare(document())).created)
            executor.process_active(self.client);worker.process_ready(self.client,registry)
            self.assertEqual(execute.call_count,1)
        response=self.cli('response',receipt.call_id)
        self.assertEqual(json.loads(response.stdout)['status'],'failed')
        self.assertTrue(json.loads(response.stdout)['failure'])
        self.assertTrue(json.loads(response.stdout)['error'])
        self.assertEqual(self.client.zrange(EXECUTOR_QUEUE_KEY,0,-1),[])
        self.assertEqual(self.client.zrange(WORKER_QUEUE_KEY,0,-1),[])
        self.assertEqual(len(list(iter_pending_records(self.ledger,self.client))),1)

    def test_failed_driver_diagnostics_retain_uuid_but_not_previous_line_identity(self):
        identifier=str(uuid.uuid4());record=prepare(document(submission=identifier))
        self.env['AUTOSCRIBE_LEDGER_DB']=str(self.root/'missing'/'ledger.sqlite')
        (self.root/'missing').write_text('not a directory')
        cp=self.cli('enqueue',payload=json.dumps(record)+'\n{invalid}\n')
        results=[json.loads(line) for line in cp.stdout.splitlines()]
        self.assertEqual(results[0]['submission_id'],identifier)
        self.assertNotIn('submission_id',results[1])

    def test_single_installed_layout_pins_resolve_without_worktree_paths(self):
        import shutil
        installed=self.root/'opt/autoscribe'
        templates=installed/'templates/releases/templates-pin'
        extensions=installed/'extensions/releases/extensions-pin'
        shutil.copytree(os.environ['TEMPLATES_ROOT'],templates,ignore=shutil.ignore_patterns('.git','__pycache__'))
        shutil.copytree(os.environ['EXTENSIONS_ROOT'],extensions,ignore=shutil.ignore_patterns('.git','__pycache__'))
        with patch.dict(os.environ,{'TEMPLATES_ROOT':str(templates),'EXTENSIONS_ROOT':str(extensions)}):
            out=prepare(document())
        self.assertEqual(out['status'],'ready',out)
        self.assertEqual(out['content'],'Body\n')
        self.assertNotIn(str(templates),json.dumps(out))
