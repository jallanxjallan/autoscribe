from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from autoscribe.worker import WorkerError, execute_task, load_registry, run_extension


class FakeRedis:
    def __init__(self): self.hashes={}
    def hgetall(self,key): return dict(self.hashes.get(key,{}))


class WorkerTests(unittest.TestCase):
    def test_extension_prepends_seen(self):
        with tempfile.TemporaryDirectory() as td:
            script=Path(td)/"prepend.py"
            script.write_text("#!/usr/bin/env python3\nimport sys\nsys.stdout.write('I have seen this\\n\\n'+sys.stdin.read())\n")
            script.chmod(0o755)
            self.assertEqual(run_extension(script,"Body\n"),"I have seen this\n\nBody\n")

    def test_execute_task_uses_registry_not_task_path(self):
        with tempfile.TemporaryDirectory() as td:
            script=Path(td)/"extension.py"
            script.write_text("#!/usr/bin/env python3\nimport sys\nsys.stdout.write('I have seen this\\n\\n'+sys.stdin.read())\n")
            script.chmod(0o755)
            r=FakeRedis()
            r.hashes['task:1']={"state":"ready","call_identity":"01","runtime_key":"runtime:01:1","source_identity":"psg.test","input":"Hello\n"}
            r.hashes['runtime:01:1']={"engine":"extension","model":"prepend-seen"}
            result=execute_task(r,'task:1',{'prepend-seen':script})
            self.assertEqual(result.content,"I have seen this\n\nHello\n")

    def test_unregistered_extension_rejected(self):
        r=FakeRedis(); r.hashes['task:1']={"state":"ready","call_identity":"01","runtime_key":"runtime:01:1","source_identity":"x","input":"x"}; r.hashes['runtime:01:1']={"engine":"extension","model":"arbitrary/path"}
        with self.assertRaisesRegex(WorkerError,'unregistered extension'): execute_task(r,'task:1',{})
