from pathlib import Path
import importlib.util
import json
import sqlite3
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'extensions/smoke-test.py'
VALID = b'AUTOSCRIBE_LLM_SMOKE_V1\nROLE=PASS\nCONTEXT=PASS\nTASK=PASS\nINPUT=AUTOSCRIBE_SMOKE_INPUT_V1'


class SmokeVerifierTests(unittest.TestCase):
    def test_valid_five_lines_are_preserved(self):
        for data in (VALID, VALID+b'\n', (VALID+b'\n').replace(b'\n', b'\r\n')):
            with self.subTest(data=data):
                result = subprocess.run([str(SCRIPT)], input=data, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, data)
                self.assertEqual(result.stderr, b'')

    def test_invalid_protocol_never_produces_success_output(self):
        cases = [b'', VALID+b'\n\n', VALID+b'\nExtra', b'```\n'+VALID+b'\n```',
                 VALID.replace(b'ROLE=PASS', b'CONTEXT=PASS'), VALID.replace(b'TASK=PASS', b'TASK=FAIL'),
                 VALID.replace(b'INPUT=AUTOSCRIBE_SMOKE_INPUT_V1', b'INPUT=wrong'),
                 VALID.replace(b'ROLE=PASS', b' ROLE=PASS'), VALID.replace(b'\n', b'\r'),
                 b'AUTOSCRIBE_SMOKE_BAD_INPUT', VALID+b'\xff', b'x'*1048577]
        cases += [b'\n'.join(VALID.split(b'\n')[:i]+VALID.split(b'\n')[i+1:]) for i in range(5)]
        for data in cases:
            with self.subTest(data=data[:100]):
                result = subprocess.run([str(SCRIPT)], input=data, capture_output=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, b'')
                self.assertIn(b'smoke-test:', result.stderr)


class CatalogueScriptsTests(unittest.TestCase):
    def test_packaged_registry_resolves_all_script_steps_or_fails_closed(self):
        spec = importlib.util.spec_from_file_location('release_builder', ROOT/'release.py')
        release = importlib.util.module_from_spec(spec); spec.loader.exec_module(release)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); engine = root/'engine'; (engine/'extensions').mkdir(parents=True)
            installed = Path('/opt/autoscribe/services/releases/synthetic')
            db = root/'control.sqlite'
            with sqlite3.connect(db) as conn:
                conn.execute('CREATE TABLE steps(id TEXT,engine_kind TEXT,script TEXT)')
                conn.execute("INSERT INTO steps VALUES ('step_test','script','smoke-test')")
            script = engine/'extensions/smoke-test.py'; script.write_text('#!/usr/bin/python3\n'); script.chmod(0o755)
            path = engine/'extensions/registry.json'; path.write_text(json.dumps({'smoke-test':'/opt/autoscribe/extensions/smoke-test.py'}))
            registry = release.relocate_registry(engine, installed)
            result = release.validate_catalogue_scripts(db, registry, installed, engine)
            self.assertEqual(result[0]['script'], 'smoke-test')
            self.assertEqual(result[0]['sha256'], release.sha(script))
            with self.assertRaisesRegex(ValueError, 'unregistered'):
                release.validate_catalogue_scripts(db, {}, installed, engine)
            script.chmod(0o644)
            with self.assertRaisesRegex(ValueError, 'not executable'):
                release.validate_catalogue_scripts(db, registry, installed, engine)
            script.unlink()
            with self.assertRaisesRegex(ValueError, 'missing'):
                release.validate_catalogue_scripts(db, registry, installed, engine)
            with self.assertRaises(ValueError):
                release.validate_catalogue_scripts(db, {'smoke-test':'/outside/script'}, installed, engine)
