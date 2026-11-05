import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

from autoscribe.enqueue import EnqueueError, enqueue_record
from autoscribe.redis_runtime import EXECUTOR_QUEUE_KEY


class FakeRedis:
    def __init__(self): self.hashes = {}; self.expiries = {}; self.zsets = {}
    def command(self, *parts):
        if parts[0] == "GET": return self.hashes.get(parts[1])
        if parts[0] != "EVAL": raise AssertionError(parts)
        _, _, count, marker, content, baggage, queue, fingerprint, c, b, ttl, call, queued = parts
        if marker in self.hashes: return 0
        self.hset(content, {"json": c}); self.hset(baggage, {"json": b})
        if queued: self.zadd(queue, 0, call)
        self.hashes[marker] = fingerprint
        return 1
    def ping(self): pass
    def hset(self, key, fields): self.hashes.setdefault(key, {}).update({str(k): str(v) for k, v in fields.items()})
    def hgetall(self, key): return dict(self.hashes.get(key, {}))
    def expire(self, key, seconds): self.expiries[key] = seconds
    def zadd(self, key, score, member): self.zsets.setdefault(key, {})[member] = score


def make_control(path: Path):
    db = sqlite3.connect(path)
    db.executescript("""
    CREATE TABLE plans(id TEXT PRIMARY KEY,label TEXT,description TEXT,scope TEXT);
    CREATE TABLE steps(id TEXT PRIMARY KEY,label TEXT,engine_kind TEXT,engine TEXT,model TEXT,script TEXT,rag_profile TEXT,args_json TEXT);
    CREATE TABLE instructions(id TEXT PRIMARY KEY,label TEXT,kind TEXT,body TEXT);
    CREATE TABLE plan_steps(plan_id TEXT,step_id TEXT,position INTEGER);
    CREATE TABLE step_instructions(step_id TEXT,instruction_id TEXT,component TEXT,position INTEGER);
    """)
    db.execute("INSERT INTO plans VALUES ('pln_TEST','Test','','')")
    db.execute("INSERT INTO steps VALUES ('stp_1','Step','llm','chatgpt','luna',NULL,NULL,'{}')")
    db.execute("INSERT INTO plan_steps VALUES ('pln_TEST','stp_1',1)")
    db.commit(); db.close()


def record(content="Hello"):
    import json
    origin,submission='test_origin','sub_TEST'
    key=json.dumps([origin,submission],separators=(',',':')).encode()
    return {'schema':'autoscribe.prepared.v2','status':'ready',
            'record_id':'inp_'+hashlib.sha256(key).hexdigest()[:32],
            'call_id':'call_'+hashlib.sha1(f'{len(origin)}:{origin}:{submission}'.encode()).hexdigest(),
            'call_source':origin,'submission_id':submission,'plan':'pln_TEST',
            'content':content,'content_sha256':hashlib.sha256(content.encode()).hexdigest(),
            'source_format':'markdown','source':{'kind':'git','path':'Note.md'},
            'baggage':{'autoscribe_return':{'schema':'autoscribe.return.v1'}}}


class EnqueueTests(unittest.TestCase):
    def test_enqueue_materializes_and_queues_call(self):
        with tempfile.TemporaryDirectory() as td:
            control = Path(td) / "control.sqlite"; ledger = Path(td) / "ledger.sqlite"; make_control(control)
            redis = FakeRedis()
            result = enqueue_record(record=record(), control_db=control, ledger_db=ledger, client=redis)
            self.assertTrue(result.created)
            self.assertIn(result.call_id, redis.zsets[EXECUTOR_QUEUE_KEY])
            self.assertIn(result.content_key, redis.hashes)
            self.assertIn(result.baggage_key, redis.hashes)

    def test_retry_after_consumption_does_not_requeue_or_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            control = Path(td) / "control.sqlite"; ledger = Path(td) / "ledger.sqlite"; make_control(control)
            redis = FakeRedis()
            first = enqueue_record(record=record(), control_db=control, ledger_db=ledger, client=redis)
            redis.zsets[EXECUTOR_QUEUE_KEY].clear()
            redis.hashes.pop(f"enqueue:{first.call_id}")  # durable SQLite receipt survives Redis eviction
            before = dict(redis.hashes)
            control.unlink()  # retry must not depend on a changed/deleted plan
            again = enqueue_record(record=record(), control_db=control, ledger_db=ledger, client=redis)
            self.assertEqual(first.call_id, again.call_id)
            self.assertFalse(again.created)
            self.assertFalse(redis.zsets[EXECUTOR_QUEUE_KEY])
            self.assertEqual(redis.hashes, before)

    def test_record_id_collision_fails_before_redis_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            control = Path(td) / "control.sqlite"; ledger = Path(td) / "ledger.sqlite"; make_control(control)
            redis = FakeRedis()
            enqueue_record(record=record(), control_db=control, ledger_db=ledger, client=redis)
            before = dict(redis.hashes)
            with self.assertRaisesRegex(EnqueueError, "different input"):
                enqueue_record(record=record("Changed"), control_db=control, ledger_db=ledger, client=redis)
            self.assertEqual(redis.hashes, before)

    def test_legacy_raw_contract_rejected_before_storage(self):
        value=record();value['schema']='autoscribe.input.v3'
        with self.assertRaisesRegex(EnqueueError,'requires autoscribe.prepared.v2'):
            enqueue_record(record=value,control_db=Path('/unused'),ledger_db=Path('/unused'),client=FakeRedis())

    def test_bad_content_hash_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            control = Path(td) / "control.sqlite"; ledger = Path(td) / "ledger.sqlite"; make_control(control)
            value = record(); value["content_sha256"] = "0" * 64
            with self.assertRaisesRegex(EnqueueError, "content_sha256"):
                enqueue_record(record=value, control_db=control, ledger_db=ledger, client=FakeRedis())


if __name__ == "__main__": unittest.main()
