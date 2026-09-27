from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from autoscribe.ledger import has_event, load_call, record_call


def sample_call():
    return {
        "schema": "autoscribe.call.v2",
        "created_at": "2026-09-27T00:00:00+00:00",
        "sources": [{"identity":"psg.test","path":"Note.md","blob":"b1","directive":None,"content":"Body\n"}],
        "source": {"repo": "/home/jeremy/Repos/X.git", "repo_name": "X", "commit": "abc", "ref": "refs/heads/master"},
        "plan": {"id": "p1", "ref": "plan.one", "label": "One", "plan_type": "test", "steps": []},
    }


class LedgerTests(unittest.TestCase):
    def test_record_is_idempotent_and_immutable(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "ledger.sql"
            first, created1 = record_call(db, sample_call())
            duplicate = sample_call()
            duplicate["created_at"] = "2026-09-27T00:00:01+00:00"
            second, created2 = record_call(db, duplicate)
            self.assertTrue(created1)
            self.assertFalse(created2)
            self.assertEqual(first, second)
            self.assertEqual(load_call(db, first), sample_call())
            self.assertTrue(has_event(db, first, "recorded"))

class ResponseLedgerTests(unittest.TestCase):
    def test_response_is_idempotent_by_task(self):
        from autoscribe.ledger import load_response, record_response
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "ledger.sql"
            call_id, _ = record_call(db, sample_call())
            rid1, c1 = record_response(db, call_identity=call_id, runtime_key="runtime:x:1", task_key="task:x:1:1", source_identity="psg.test", executor="extension", entrypoint="prepend-seen", content="I have seen this\n\nBody\n")
            rid2, c2 = record_response(db, call_identity=call_id, runtime_key="runtime:x:1", task_key="task:x:1:1", source_identity="psg.test", executor="extension", entrypoint="prepend-seen", content="different ignored duplicate")
            self.assertTrue(c1); self.assertFalse(c2); self.assertEqual(rid1, rid2)
            self.assertEqual(load_response(db, rid1)["content"], "I have seen this\n\nBody\n")
