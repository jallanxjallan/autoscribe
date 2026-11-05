"""Narrow v3/Pandoc/enqueue components. No engine or production transport runs."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from autoscribe import ssh_jobs as jobs
from autoscribe import assets
from autoscribe.enqueue import EnqueueError, enqueue_record, validate_input_record
from autoscribe.executor import ExecutorError, ordered_steps
from autoscribe.preprocess import interpret, prepare, PreprocessInfrastructureError
from autoscribe.redis_runtime import EXECUTOR_QUEUE_KEY
from test_enqueue import FakeRedis, make_control, record


def sha(data):
    return hashlib.sha256(data).hexdigest()


def envelope(raw, submission='sub_component_1'):
    vault = '/fixture/vault'
    digest = sha(raw.encode())
    value = {'schema': 'autoscribe.input.v3', 'source': {'kind': 'obsidian', 'path': 'Note.md',
        'vault_id': sha(vault.encode())}, 'raw_markdown': raw, 'raw_markdown_sha256': digest,
        'baggage': {'client': {'submission_id': submission, 'source_path': 'Note.md',
            'source': sha((vault + '\0Note.md').encode()), 'vault_id': sha(vault.encode()),
            'raw_markdown_sha256': digest}}}
    value['record_id'] = 'inp_' + sha(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':')).encode())[:32]
    return value


def package(root, value):
    dispatch = value['baggage']['client']['submission_id']
    path = root / dispatch
    path.mkdir()
    data = (json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n').encode()
    (path / 'request.ndjson').write_bytes(data)
    manifest = sha(data) + '  request.ndjson\n'
    (path / 'SHA256SUMS').write_text(manifest)
    digest = sha(manifest.encode())
    (path / '.package-sha256').write_text(digest)
    return path, dispatch, digest


class V3Components(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.control = self.root / 'control.sqlite'
        self.ledger = self.root / 'ledger.sqlite'
        make_control(self.control)
        self.redis = FakeRedis()
        self.raw = '---\r\nslug: psg_TEST\r\nplan: pln_TEST\r\n---\r\n\r\n**Exact** -- punctuation…\r\n'

    def test_envelope_identity_checksum_and_no_partial_acceptance(self):
        value = envelope(self.raw)
        self.assertEqual(validate_input_record(value), (value['record_id'], None))
        for change in ('raw_markdown_sha256', 'record_id'):
            changed = dict(value); changed[change] = 'bad'
            with self.assertRaises(EnqueueError):
                enqueue_record(record=changed, control_db=self.control, ledger_db=self.ledger, client=self.redis)
        self.assertFalse(self.redis.hashes)
        self.assertFalse(self.ledger.exists())
        stream = json.dumps(record()) + '\n{"schema":'
        environment = dict(os.environ, AUTOSCRIBE_LEDGER_DB=str(self.ledger),
                           AUTOSCRIBE_CONTROL_DB=str(self.control), AUTOSCRIBE_REDIS_PORT='1')
        checked = subprocess.run([sys.executable, '-B', str(Path(__file__).parents[1] / 'bin/asc'), 'enqueue'],
                                 input=stream, text=True, capture_output=True, env=environment, check=False)
        self.assertEqual(checked.returncode, 1)
        self.assertIn('line 2', checked.stderr)
        self.assertEqual(checked.stdout, '')
        self.assertFalse(self.ledger.exists())

    def test_real_pandoc_parse_write_metadata_assets_and_directives(self):
        raw = self.raw.replace('---\r\n\r\n', 'assets: ["/home/jeremy/Dropbox/Assets/a.png"]\r\n---\r\n\r\n')
        parsed = interpret(raw)
        self.assertNotIn('\r', parsed['content'])
        self.assertNotIn('slug:', parsed['content'])
        self.assertIn('Exact', parsed['content'])
        self.assertEqual(parsed['slug'], 'psg_TEST')
        self.assertEqual(parsed['plan_id'], 'pln_TEST')
        self.assertEqual(parsed['assets'], ['/home/jeremy/Dropbox/Assets/a.png'])
        directive = interpret(self.raw + '\n::: {#context .directive source="doc"}\ncontext\n:::\n')
        self.assertEqual(directive['directives'][0]['identifier'], 'context')
        self.assertEqual(directive['directives'][0]['attributes']['source'], 'doc')
        malformed = interpret(self.raw + '\n::: directive\ncontext\n:::\n')
        self.assertEqual(malformed['failure'], 'Unreadable')
        self.assertNotIn('failure', interpret(self.raw + '\n`==literal==`\n'))
        parsed = interpret('---\nslug: [unclosed\n---\nbody\n')
        self.assertEqual(parsed['failure'], 'Unreadable')

    def test_editorial_readiness_and_literal_examples(self):
        for body, failure in [('> [!note]\n> Check this fact.\n', 'Editorial callout'),
                              ('> [!custom]+ Review\n', 'Editorial callout'),
                              ('> [!warning]- Review\n', 'Editorial callout'),
                              ('The Sultan ==may have visited== here.\n', 'Editorial highlighting')]:
            with self.subTest(body=body):
                parsed = interpret(self.raw + body)
                self.assertEqual(parsed['failure'], failure)
                self.assertEqual(parsed['content'], '')
                self.assertIn('author review', parsed['reason'])
        for body in ['> Ordinary blockquote.\nUnhighlighted text.\n',
                     '```markdown\n> [!warning]+\n==literal==\n```\n> \\[!note] escaped\n',
                     '\n~~~markdown\n> [!note]-\n==literal==\n~~~\n',
                     '> \\[!warning] escaped\n\\==literal==\n',
                     '`==literal==`\n',
                     'some `literal\n> [!note]\nend`\n\n> \\[!note] escaped\n']:
            with self.subTest(literal=body):
                self.assertNotIn('failure', interpret(self.raw + body))

    def test_editorial_failures_direct_gate_without_executor(self):
        jobs.initialize(self.ledger)
        for index, (body, failure) in enumerate([('> [!note]+ Review\n', 'Editorial callout'),
                                                ('==Review this==\n', 'Editorial highlighting')]):
            value = envelope(self.raw + body, submission=f'sub_editorial_{index}')
            path, dispatch, digest = package(self.root, value)
            with patch.object(jobs, 'ROOT', self.root), patch.object(jobs, 'launch') as launch, \
                 patch.object(jobs, 'execute_task') as execute:
                outcome = jobs.submit(self.control, self.ledger, self.redis, dispatch, digest)
                response = json.loads((path / 'response.ndjson').read_text())
                self.assertEqual(response['failure'], failure)
                self.assertEqual(response['status'], 'failed')
                self.assertEqual(response['schema'], 'autoscribe.client-response.v1')
                self.assertEqual(response['baggage']['client']['submission_id'], dispatch)
                self.assertEqual(response['baggage']['client']['source'], value['baggage']['client']['source'])
                self.assertEqual(response['call_id'], outcome['call_id'])
                jobs.execute(self.ledger, self.redis, dispatch, digest)
                launch.assert_not_called(); execute.assert_not_called()
                call = json.loads(self.redis.hgetall(f"call:{outcome['call_id']}:content")['json'])
                self.assertEqual(call['input']['content'], '')
        self.assertFalse(self.redis.zsets)
        with sqlite3.connect(self.ledger) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM responses').fetchone()[0], 2)

    def test_existing_internal_call_and_success_response_without_execution(self):
        value = envelope(self.raw)
        path, dispatch, digest = package(self.root, value)
        jobs.initialize(self.ledger)
        with patch.object(jobs, 'ROOT', self.root), patch.object(jobs, 'launch', side_effect=lambda l,d,h: jobs.read_job(l,d,h)):
            accepted = jobs.submit(self.control, self.ledger, self.redis, dispatch, digest)
            content = json.loads(self.redis.hgetall(f"call:{accepted['call_id']}:content")['json'])
            self.assertEqual(content['schema'], 'autoscribe.call-content.v2')
            self.assertEqual(content['record_id'], value['record_id'])
            self.assertEqual(content['input']['content'], interpret(self.raw)['content'])
            self.assertNotIn('\r', content['input']['content'])
            self.assertEqual(content['source']['slug'], 'psg_TEST')
            self.assertNotIn('raw_markdown', content)
            baggage = json.loads(self.redis.hgetall(f"call:{accepted['call_id']}:baggage")['json'])
            self.assertNotIn('original_body', baggage['client'])
            self.assertNotIn('frontmatter', baggage['client'])
            self.assertNotIn('source_body_sha256', baggage['client'])
            self.assertEqual(baggage['client']['source'], value['baggage']['client']['source'])
            key = f"response:{accepted['call_id']}:content"
            self.redis.hset(key, {'content': 'Prepared response fixture'})
            completed = jobs.complete_response(self.ledger, self.redis, accepted)
            response = json.loads((path / 'response.ndjson').read_text())
            self.assertEqual(response['schema'], 'autoscribe.client-response.v1')
            self.assertEqual(response['status'], 'completed')
            self.assertEqual(response['source']['slug'], 'psg_TEST')
            self.assertEqual(response['metadata']['plan'], 'pln_TEST')
            self.assertEqual(response['result'], 'Prepared response fixture')
            self.assertEqual(response['baggage']['client']['source_slug'], 'psg_TEST')
            self.assertEqual(completed['call_id'], accepted['call_id'])
        self.assertFalse(self.redis.zsets)

    def test_terminal_failure_direct_receipt_replay_no_executor(self):
        value = envelope(self.raw + '\n::: directive\nmalformed\n:::\n')
        path, dispatch, digest = package(self.root, value)
        jobs.initialize(self.ledger)
        with patch.object(jobs, 'ROOT', self.root), patch.object(jobs, 'launch') as launch, patch.object(jobs, 'execute_task') as execute:
            failed = jobs.submit(self.control, self.ledger, self.redis, dispatch, digest)
            self.assertEqual(failed['state'], 'completed')
            response = json.loads((path / 'response.ndjson').read_text())
            self.assertEqual(response['status'], 'failed')
            self.assertEqual(response['failure'], 'Unreadable')
            self.assertEqual(response['result'], 'Unreadable')
            self.assertEqual(response['baggage']['client']['submission_id'], dispatch)
            self.assertEqual(response['baggage']['client']['raw_markdown_sha256'], value['raw_markdown_sha256'])
            again = jobs.submit(self.control, self.ledger, self.redis, dispatch, digest)
            self.assertEqual(again['call_id'], failed['call_id'])
            jobs.execute(self.ledger, self.redis, dispatch, digest)
            launch.assert_not_called(); execute.assert_not_called()
        call = json.loads(self.redis.hgetall(f"call:{failed['call_id']}:content")['json'])
        self.assertEqual(call['input']['content'], '')
        with self.assertRaises(ExecutorError): ordered_steps(call)
        self.assertFalse(self.redis.zsets)
        daemon_path = Path(__file__).parents[1] / 'daemon/responsed.py'
        spec = importlib.util.spec_from_file_location('response_gate_component', daemon_path)
        daemon = importlib.util.module_from_spec(spec); spec.loader.exec_module(daemon)
        with patch.object(daemon, 'route_info', return_value=(failed['call_id'], 'repo', ('repo', 'fixture'))), \
             patch.object(daemon, 'run_asc', return_value=subprocess.CompletedProcess([], 0,
                 stdout=json.dumps({'schema':'autoscribe.response.v1', 'failure':'Unreadable'}), stderr='')), \
             patch.object(daemon, 'run_command') as writable_effect:
            with self.assertRaises(daemon.ResponsesError): daemon.process_record(self.redis, {})
            writable_effect.assert_not_called()
        with sqlite3.connect(self.ledger) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM calls').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT count(*) FROM responses').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT count(*) FROM exports').fetchone()[0], 1)
        with patch('autoscribe.preprocess.interpret', side_effect=AssertionError('reprocessed retry')):
            again = enqueue_record(record=value, control_db=self.control, ledger_db=self.ledger, client=self.redis)
        self.assertEqual(again.failure, 'Unreadable')
        self.assertEqual(again.call_id, failed['call_id'])

    def test_empty_failure_vs_normal_unknown_plan_and_infrastructure(self):
        value = record(''); value['failure'] = 'Unreadable'
        result = enqueue_record(record=value, control_db=self.control, ledger_db=self.ledger, client=self.redis)
        self.assertEqual(result.failure, 'Unreadable')
        with self.assertRaises(EnqueueError): validate_input_record(record(''))
        unknown = envelope(self.raw.replace('pln_TEST', 'pln_UNKNOWN'))
        result = enqueue_record(record=unknown, control_db=self.control, ledger_db=self.ledger, client=self.redis)
        self.assertEqual(result.failure, 'Unreadable')
        with patch.dict(os.environ, {'AUTOSCRIBE_PANDOC': '/missing/pandoc'}):
            with self.assertRaises(PreprocessInfrastructureError): interpret(self.raw)
        with patch.dict(os.environ, {'TEMPLATES_ROOT': str(self.root / 'missing-templates')}):
            with self.assertRaises(PreprocessInfrastructureError): interpret(self.raw)
        self.assertFalse(self.redis.zsets)

    def test_existing_dropbox_handler_boundary_preserves_source_links(self):
        ref = '/home/jeremy/Dropbox/Assets/a.png'
        observed = []
        class Handler:
            def __init__(self, *args, **kwargs): pass
            def stage(self, references, work):
                observed.extend(references)
                return [SimpleNamespace(to_dict=lambda: {'requested_ref': references[0], 'original_path': 'assets/hash.png', 'sha256': 'a'*64})]
        catalog = SimpleNamespace(ResourceCatalog=SimpleNamespace(extensions=lambda root:
            SimpleNamespace(resolve=lambda kind, name: self.root / 'assets.py')))
        module = SimpleNamespace(DropboxAssetHandler=Handler)
        with patch.dict(os.environ, {'AUTOSCRIBE_RCLONE': '/usr/bin/true'}), patch.object(assets, '_module', side_effect=[catalog, module]):
            result = assets.stage_assets([ref], self.root)
        self.assertEqual(observed, ['dropbox:Assets/a.png'])
        self.assertEqual(result[0]['requested_ref'], ref)
        self.assertEqual(result[0]['original_path'], 'assets/hash.png')
