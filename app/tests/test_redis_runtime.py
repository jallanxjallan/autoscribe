from __future__ import annotations

import unittest

from autoscribe.redis_runtime import ACTIVE_KEY, activate_call


class FakeRedis:
    def __init__(self):
        self.hashes = {}
        self.expiries = {}
        self.zsets = {}
        self.pinged = False

    def ping(self): self.pinged = True
    def hset(self, key, fields): self.hashes[key] = dict(fields)
    def expire(self, key, seconds): self.expiries[key] = seconds
    def zadd(self, key, score, member): self.zsets.setdefault(key, {})[member] = score


class RuntimeTests(unittest.TestCase):
    def test_materializes_ordered_runtime_and_activates_job(self):
        call = {
            "schema": "autoscribe.call.v2",
            "created_at": "2026-09-27T00:00:00+00:00",
            "sources": [{"identity":"psg.test","path":"Note.md","blob":"b1","directive":None,"content":"Body\n"}],
        "source": {"repo": "/r.git", "repo_name": "r", "commit": "abc", "ref": "refs/heads/master"},
            "plan": {
                "id": "p1", "ref": "plan.one", "label": "Plan", "plan_type": "x",
                "steps": [{
                    "position": 1, "id": "s1", "ref": "plan.one#1", "label": "Step",
                    "executor": "chatgpt", "entrypoint": "sol",
                    "instructions": [
                        {"position": 1, "id": "i1", "ref": "rol.one", "label": "Role", "kind": "role", "body": "R"},
                        {"position": 2, "id": "i2", "ref": "ctx.one", "label": "Context", "kind": "context", "body": "C"},
                    ],
                }],
            },
        }
        redis = FakeRedis()
        activation = activate_call(redis, "01TEST", call)
        self.assertTrue(redis.pinged)
        self.assertEqual(activation.runtime_keys, ["runtime:01TEST:1"])
        self.assertEqual(redis.hashes["runtime:01TEST:1"]["engine"], "chatgpt")
        self.assertEqual(redis.hashes["runtime:01TEST:1"]["model"], "sol")
        self.assertIn("job:01TEST:record", redis.zsets[ACTIVE_KEY])
        self.assertEqual(redis.zsets[ACTIVE_KEY]["job:01TEST:record"], 0)
