"""Five-candidate local qualification with synthetic execution and disposable state.

Only SSH upload/launch/retrieve is replaced by local delivery. No paid models,
production Redis, production files, service activation or network output.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
from unittest.mock import patch

from autoscribe import ssh_jobs as jobs
from autoscribe.redis_runtime import load_json
from test_prepared_pipeline import IsolatedRedisCase


class Smoke(IsolatedRedisCase):
    def runTest(self):
        self.client.command('CONFIG', 'SET', 'appendonly', 'yes')
        self.client.command('CONFIG', 'SET', 'appendfsync', 'always')
        shared = self.root / '.shared'; shared.mkdir(mode=0o700)
        vault = self.root / 'vault'; vault.mkdir()
        binaries = Path(os.environ['AUTOSCRIBE_TEST_CLIENT_BIN']).resolve().parent
        self.env.update(DBUS_SESSION_BUS_ADDRESS='unix:path='+str(self.root/'no-desktop-bus'), DISPLAY='', WAYLAND_DISPLAY='')
        common = ['--redis', f'127.0.0.1:{self.port}', '--shared', str(shared), '--vault-root', str(vault)]
        def native(name, *args):
            result = subprocess.run([str(binaries/name), *args, *common], capture_output=True, text=True, env=self.env)
            if result.returncode: raise RuntimeError(result.stderr or result.stdout)
            return result
        def state(identifier):
            return json.loads(self.client.hgetall('autoscribe:client:jobs')[identifier])
        server_jobs = self.root/'server-jobs'; server_jobs.mkdir()
        capture = self.root/'execution-input.md'
        script = self.root/'process-body'
        script.write_text('#!/bin/sh\ncat > "$REVIEW_INPUT_CAPTURE"\nprintf "%s\\n" "---" "generated: body only" "Processed body"\n'); script.chmod(0o700)
        registry = self.root/'registry.json'; registry.write_text(json.dumps({'review': str(script)}))
        with sqlite3.connect(self.control) as db:
            db.execute("UPDATE steps SET engine_kind='script',engine='extension',model=NULL,script='review'")
        counter = self.root/'pandoc-calls'
        pandoc = self.root/'pandoc'
        pandoc.write_text('#!/bin/sh\nprintf "call\\n" >> "$REVIEW_PANDOC_COUNTER"\nexec /usr/bin/pandoc "$@"\n'); pandoc.chmod(0o700)
        self.env.update(AUTOSCRIBE_EXTENSION_REGISTRY=str(registry), REVIEW_INPUT_CAPTURE=str(capture),
                        AUTOSCRIBE_PANDOC=str(pandoc), REVIEW_PANDOC_COUNTER=str(counter))
        jobs.initialize(self.ledger)
        def package(identifier, payload):
            directory = server_jobs/identifier; directory.mkdir(exist_ok=True)
            (directory/'request.ndjson').write_bytes(payload)
            manifest = hashlib.sha256(payload).hexdigest()+'  request.ndjson\n'
            digest = hashlib.sha256(manifest.encode()).hexdigest()
            (directory/'SHA256SUMS').write_text(manifest); (directory/'.package-sha256').write_text(digest)
            return directory, digest
        def delivered(identifier, receipt, response):
            path = shared/f'autoscribe-response-{identifier}.ndjson'; path.write_bytes(response)
            job = state(identifier)
            job.update(state='submitted', call_id=receipt['call_id'], response_detected_at=1,
                       response_path=str(path), awaiting_response=False, accepted_at=1)
            # Disable only external transport; native staging/application remains real.
            job.pop('transport', None)
            self.client.hset('autoscribe:client:jobs', {identifier: json.dumps(job, sort_keys=True, separators=(',', ':'), ensure_ascii=False)})
            return path
        raw = b'---\r\nplan: pln_TEST\r\nslug: psg_0123456789ABCDEF\r\n# exact frontmatter\r\ntags: [original]\r\n---\r\n## Source\r\nOriginal body\r\n'
        (vault/'Note.md').write_bytes(raw)
        input_file = self.root/'input-stream'; input_file.write_bytes(raw)
        # Reuse the installed canonical helpers as read-only code resources.
        helper = vault/'_tools/scripts/lib/text.js'; helper.parent.mkdir(parents=True)
        shutil.copyfile(Path.home()/'.config/obsidian-vault/tools/scripts/lib/text.js', helper)
        spec = self.root/'create.json'; configured = self.root/'configured.json'
        spec.write_text(json.dumps({'path': 'Created.md', 'prefix': 'psg',
            'metadata': {'type': 'passage', 'tags': ['synthetic']}, 'required': ['type', 'slug', 'tags']}))
        configured.write_text(json.dumps({'folder': '.', 'title': 'configured result', 'prefix': 'psg',
            'metadata': {'type': 'passage', 'tags': []}, 'required': ['type', 'slug', 'tags']}))
        report = {}
        with patch.object(jobs, 'ROOT', server_jobs), patch.object(jobs, 'launch', lambda l,s,d: jobs.read_job(l,s,d)), patch.dict(os.environ, self.env):
            for name, arguments in [
                ('update', ['--request', 'Note.md']),
                ('create_explicit', ['--request', 'Note.md', '--creation-spec', str(spec)]),
                ('create_pathless_configured', ['--input', str(input_file), '--creation-spec', str(configured)]),
            ]:
                before = set(self.client.hgetall('autoscribe:client:jobs'))
                native('autoscribe-dispatch', *arguments)
                identifier = (set(self.client.hgetall('autoscribe:client:jobs'))-before).pop()
                native('autoscribe-dispatch', '--local-only', '--once')
                staged = shared/f'autoscribe-{identifier}.request.ndjson'; payload = staged.read_bytes()
                record = json.loads(payload); op = state(identifier)['output_operation']
                native('autoscribe-dispatch', *arguments)
                self.assertEqual(staged.read_bytes(), payload)
                self.assertEqual(state(identifier)['output_operation'], op)
                if 'pathless' in name: self.assertNotIn('path', record['source'])
                directory, digest = package(identifier, payload)
                prior_calls = len(counter.read_text().splitlines()) if counter.exists() else 0
                accepted = jobs.submit(self.control, self.ledger, self.client, identifier, digest)
                repeated = jobs.submit(self.control, self.ledger, self.client, identifier, digest)
                self.assertEqual(accepted['call_id'], repeated['call_id'])
                self.assertEqual(len(counter.read_text().splitlines()), prior_calls+1)
                with patch.object(jobs, 'execute_task', wraps=jobs.execute_task) as execute:
                    completed = jobs.execute(self.ledger, self.client, identifier, digest)
                    jobs.execute(self.ledger, self.client, identifier, digest)
                    self.assertEqual(execute.call_count, 1)
                self.assertEqual(capture.read_bytes(), record['raw_markdown'].encode())
                response_bytes = (directory/'response.ndjson').read_bytes(); response = json.loads(response_bytes)
                self.assertEqual(response['status'], 'completed')
                self.assertEqual(response['result_bytes'], len(response['result'].encode()))
                self.assertEqual(response['result_sha256'], hashlib.sha256(response['result'].encode()).hexdigest())
                runtime = load_json(self.client, f"call:{accepted['call_id']}:content")
                self.assertEqual(runtime['input']['content'].encode(), record['raw_markdown'].encode())
                path = delivered(identifier, completed, response_bytes)
                if name == 'update':
                    current=vault/op['path']; baseline=current.read_bytes(); current.write_bytes(baseline+b'Local edit\n')
                    native('autoscribe-apply','--once')
                    self.assertEqual(state(identifier)['state'],'conflict')
                    self.assertEqual(current.read_bytes(),baseline+b'Local edit\n')
                    current.write_bytes(baseline); native('autoscribe-apply','--retry-job',identifier)
                native('autoscribe-apply', '--once')
                self.assertEqual(state(identifier)['state'], 'applied', native('autoscribe-apply','--status').stdout)
                target = vault/op['path']; created = target.read_bytes()
                if name == 'update':
                    front = raw[:raw.index(b'## Source')]
                    self.assertEqual(created, front+response['result'].encode())
                else:
                    self.assertTrue(created.endswith(response['result'].encode()))
                    front = created[:-len(response['result'].encode())]
                    self.assertNotIn(b'plan:', front); self.assertNotIn(b'autoscribe:', front); self.assertNotIn(b'status:', front)
                    self.assertIn(op['metadata']['slug'].encode(), front)
                self.assertTrue(staged.exists())
                path.write_bytes(response_bytes); native('autoscribe-apply', '--once')
                self.assertEqual(target.read_bytes(), created); self.assertFalse(path.exists())
                report[name] = {'status': 'passed', 'submission_id': identifier, 'call_id': accepted['call_id'],
                                'destination': op['path'], 'pandoc_calls': 1, 'script_executions': 1,
                                'duplicate_delivery': 'idempotent', 'receipt': state(identifier)['receipt']}
            bad = vault/'Invalid.md'; bad.write_bytes(b'## Missing plan\n')
            native('autoscribe-dispatch', '--request', 'Invalid.md'); native('autoscribe-dispatch', '--local-only', '--once')
            identifier = next(sid for sid in self.client.hgetall('autoscribe:client:jobs') if state(sid).get('path') == 'Invalid.md')
            directory, digest = package(identifier, (shared/f'autoscribe-{identifier}.request.ndjson').read_bytes())
            failed = jobs.submit(self.control, self.ledger, self.client, identifier, digest)
            with patch.object(jobs, 'execute_task', side_effect=AssertionError('failure executed')):
                jobs.execute(self.ledger, self.client, identifier, digest)
            response = (directory/'response.ndjson').read_bytes(); self.assertEqual(json.loads(response)['status'], 'failed')
            delivered(identifier, failed, response); native('autoscribe-apply', '--once')
            self.assertEqual(bad.read_bytes(), b'## Missing plan\n')
            self.assertNotEqual(state(identifier)['state'], 'applied')
            report['terminal_failure'] = 'passed: diagnostic retained; source unchanged; no execution'
        return report


class SignedOutput(IsolatedRedisCase):
    def runTest(self):
        import hmac
        from test_preprocess import document
        binaries=Path(os.environ['AUTOSCRIBE_TEST_SERVICES_BIN']).resolve()
        adapter=Path(os.environ['AUTOSCRIBE_GIT_ADAPTER']).resolve()
        repos=self.root/'Repos'; repos.mkdir(); repo=repos/'output.git'
        subprocess.run([str(adapter),'init','--bare','-q',str(repo)],check=True)
        secret=bytes.fromhex('11'*32); key=self.root/'effect.key'; key.write_text(secret.hex()); key.chmod(0o600)
        policy=self.root/'services.toml'
        policy.write_text(f'''[paths]
repo_roots=["{repos}"]
file_roots=[]
effect_key_file="{key}"
effects_db="{self.root/'effects.sqlite'}"
control_db="{self.control}"
[limits]
max_record_bytes=2097152
max_body_bytes=1048576
max_outputs=1
max_control_file_bytes=262144
max_control_records=10000
[git]
default_branch="main"
user_name="Synthetic Smoke"
user_email="smoke@example.invalid"
''')
        value=document('---\nplan: pln_TEST\n---\n## Stream\nOriginal\n',submission='00000000-0000-4000-8000-000000000008')
        signed={'schema':'autoscribe.return.v1','record_id':'inp_ROUTE','route':{'kind':'repo','repo':str(repo),'path':'Results/new.md'}}
        signature='eff_'+hmac.new(secret,json.dumps(signed,sort_keys=True,separators=(',',':')).encode(),hashlib.sha256).hexdigest()
        value['baggage']['autoscribe_return']={**signed,'signature':signature}
        ingested=self.cli('ingest',payload=json.dumps(value)+'\n'); self.assertEqual(ingested.returncode,0,ingested.stderr)
        cid=json.loads(ingested.stdout)['call_id']; response_key=f'response:{cid}:content'
        self.client.hset(response_key,{'content':'# New output\nSynthetic body\n'})
        from autoscribe.ledger import record_response
        record_response(self.ledger,cid,response_key)
        response=json.loads(self.cli('response',cid).stdout)
        def effect(record):
            return subprocess.run([str(binaries/'srv-output'),'--policy',str(policy)],input=json.dumps(record)+'\n',text=True,capture_output=True,env=self.env)
        output=effect(response); self.assertEqual(output.returncode,0,output.stderr)
        for status in ['failed','running',None]:
            invalid=dict(response)
            if status is None: invalid.pop('status')
            else: invalid['status']=status
            rejected=effect(invalid); self.assertNotEqual(rejected.returncode,0); self.assertEqual(rejected.stdout,'')
        invalid=dict(response,failure={'code':'synthetic'}); self.assertNotEqual(effect(invalid).returncode,0)
        def apply():
            return subprocess.run([str(binaries/'srv-writeback'),'--policy',str(policy)],input=output.stdout,text=True,capture_output=True,env=self.env)
        first=apply(); self.assertEqual(first.returncode,0,first.stderr); self.assertEqual(apply().stdout,first.stdout)
        actual=subprocess.run([str(adapter),'-C',str(repo),'show','refs/heads/autoscribe-output:Results/new.md'],capture_output=True,text=True,check=True)
        self.assertEqual(actual.stdout,'# New output\nSynthetic body\n')

def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--report', type=Path, required=True)
    args=parser.parse_args(); case=Smoke(); case.setUp()
    try: result=case.runTest()
    finally: case.doCleanups()
    output=SignedOutput(); output.setUp()
    try: output.runTest()
    finally: output.doCleanups()
    result['signed_server_output']='passed: direct route, duplicate receipt, failed effect rejected'
    result['overall']='passed'
    args.report.write_text(json.dumps(result, indent=2)+'\n'); print(json.dumps(result, indent=2))
    return 0


if __name__=='__main__': raise SystemExit(main())
