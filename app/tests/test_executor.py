import unittest
from pathlib import Path

from autoscribe.executor import prepare_step
from autoscribe.redis_state import WORKER_QUEUE_KEY, materialize_call, load_json


class FakeRedis:
    def __init__(self): self.hashes = {}; self.expiries = {}; self.zsets = {}
    def ping(self): pass
    def hset(self, key, fields): self.hashes.setdefault(key, {}).update({str(k): str(v) for k, v in fields.items()})
    def hgetall(self, key): return dict(self.hashes.get(key, {}))
    def hgetall(self, key): return dict(self.hashes.get(key, {}))
    def expire(self, key, seconds): self.expiries[key] = seconds
    def zadd(self, key, score, member): self.zsets.setdefault(key, {})[member] = score


def content():
    return {
        "schema": "autoscribe.call-content.v2",
        "input": {"content": "Body\n"},
        "plan": {"steps": [
            {"position": 1, "engine_kind": "llm", "engine": "chatgpt", "model": "luna", "args": {}, "instructions": []},
            {"position": 2, "engine_kind": "script", "engine": "local", "script": "cleanup", "args": {}, "instructions": []},
        ]},
    }


class ExecutorTests(unittest.TestCase):
    def test_later_instruction_receives_preceding_prepared_content(self):
        from autoscribe.worker import execute_task
        redis = FakeRedis()
        original = content()
        original['input']['content'] = '---\nsource: coordination\n---\nOriginal transport input'
        call = materialize_call(redis, "01TEST", original, {})
        preceding = 'A preceding step extracted and transformed this content.\n'
        redis.hset('result:01TEST:1:content', {'content': preceding})
        ready = prepare_step(redis, "01TEST", call.content_key, 2,
                             input_key='result:01TEST:1:content')
        result = execute_task(redis, ready.task_key, {'cleanup': Path('/usr/bin/cat')})
        self.assertEqual(result.content, preceding)
        self.assertNotEqual(result.content, original['input']['content'])



if __name__ == "__main__": unittest.main()
