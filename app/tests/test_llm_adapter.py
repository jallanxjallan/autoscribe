"""One provider-free check of the registered adapter's typed stdio boundary."""
from contextlib import redirect_stdout
import hashlib
import io
import os
from pathlib import Path
import runpy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from asc import worker
from asc.models.call import Call, Plan, Source, Step, StepExecution, StepResult, digest
from biznet_common import llm


class ModelAdapterInterface(unittest.TestCase):
    def test_registered_stdio_preserves_identity_and_provider_facts(self):
        submission = '00000000-0000-4000-8000-000000000003'
        identity = 'call_' + hashlib.sha1(submission.encode()).hexdigest()
        text = 'Synthetic input'
        call = Call(identity=identity, submission_id=submission,
            record_id='inp_' + digest(submission)[:32], release_id='fixture-release',
            fingerprint=digest(text), requested_plan_id='pln_TEST', retention_period_seconds=259200,
            source=Source(original_text=text, original_sha256=digest(text),
                processing_text=text, processing_sha256=digest(text), format='markdown'),
            plan=Plan(id='pln_TEST', label='Test', description='', revision='a' * 40,
                steps=(Step(position=1, id='stp_1', label='Model', engine_kind='llm',
                    engine='chatgpt', model='luna', source_commit='a' * 40,
                    content_sha256='b' * 64),)), baggage={})
        stored = [call]
        adapter = Path(os.environ['EXTENSIONS_ROOT']) / 'scripts/llm.py'
        registry = worker.load_registry(Path(os.environ['EXTENSIONS_ROOT']) / 'registry.json')
        self.assertTrue(Path(registry['luna']).name == adapter.name)
        self.assertTrue(set(llm.MODELS) | set(llm.MODELS.values()) <= set(registry))

        def load(cls, selected, client=None):
            self.assertEqual(selected, identity)
            return stored[0]

        def save(current, client=None):
            stored[0] = Call.model_validate(current.model_dump(mode='json', by_alias=True))
            return current

        def respond(service, component, content, **kwargs):
            self.assertEqual((service, component, content), ('autoscribe-worker', 'luna', text))
            self.assertEqual(kwargs['timeout'], 120.0)
            kwargs['on_request']({'model': llm.MODELS['luna'], 'input': content})
            return llm.Response(text='Synthetic result', provider='OpenAI',
                model=llm.MODELS['luna'], status='completed', response_id='synthetic-response',
                request_id='synthetic-request', usage={'total_tokens': 9})

        def stdio(argv, **kwargs):
            self.assertEqual(argv, [str(adapter)])
            self.assertEqual(kwargs['env']['AUTOSCRIBE_LLM_TIMEOUT_SECONDS'], '120.0')
            self.assertEqual(kwargs['timeout'], 125.0)
            output = io.StringIO()
            with patch('sys.stdin', io.StringIO(kwargs['input'])), redirect_stdout(output):
                runpy.run_path(str(adapter), run_name='__main__')
            self.assertEqual(len(output.getvalue().splitlines()), 1)
            parsed = StepResult.model_validate_json(output.getvalue())
            self.assertEqual(parsed.call_id, identity)
            return SimpleNamespace(returncode=0, stdout=output.getvalue(), stderr='')

        with patch.object(Call, 'load', classmethod(load)), patch.object(Call, 'save', save), \
             patch.object(llm, 'respond', side_effect=respond) as provider, \
             patch.object(worker.subprocess, 'run', side_effect=stdio) as process, \
             patch.dict(os.environ, {'AUTOSCRIBE_RELEASE_ROOT': '/tmp/fixture-release'}):
            result = worker.execute(call.invocation(1), None, {'luna': adapter})
        self.assertEqual(provider.call_count, 1)
        self.assertEqual(process.call_count, 1)
        self.assertEqual((result.call_id, result.step_id, result.position, result.component,
                          result.release_id), (identity, 'stp_1', 1, 'luna', 'fixture-release'))
        self.assertEqual(result.text, 'Synthetic result')
        self.assertEqual(result.provider.usage, {'total_tokens': 9})
        self.assertEqual(result.provider.request_id, 'synthetic-request')
        state = stored[0].steps['1']
        self.assertEqual(state.result, result)
        self.assertEqual(state.request.payload['model'], llm.MODELS['luna'])
        self.assertEqual(state.request.timeout_seconds, 120.0)
        self.assertEqual(state.request.baseline.input.text, text)
        self.assertEqual(state.request.retrieval_positions, ())


if __name__ == '__main__':
    unittest.main()
