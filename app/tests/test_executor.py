import unittest
from autoscribe.executor import prepare_first_step
from autoscribe.redis_runtime import activate_call
class FakeRedis:
    def __init__(self): self.hashes={}; self.zsets={}
    def ping(self): pass
    def hset(self,key,fields): self.hashes.setdefault(key,{}).update({str(k):str(v) for k,v in fields.items()})
    def hgetall(self,key): return dict(self.hashes.get(key,{}))
    def expire(self,key,seconds): pass
    def zadd(self,key,score,member): self.zsets.setdefault(key,{})[member]=score
    def zrem(self,key,member): self.zsets.setdefault(key,{}).pop(member,None)
class ExecutorTests(unittest.TestCase):
    def test_prepares_from_canonical_ingested_sources_without_git(self):
        call={"schema":"autoscribe.call.v2","created_at":"2026-09-27T00:00:00+00:00","source":{"repo":"/does/not/matter","repo_name":"fixture","commit":"abc","ref":"refs/heads/master"},"sources":[{"identity":"psg.test","path":"Note.md","blob":"blob-id","directive":None,"content":"Body\n"}],"plan":{"id":"plan-id","ref":"plan.test","label":"Test","plan_type":"test","steps":[{"id":"step-id","ref":"plan.test#1","label":"Step","position":1,"executor":"chatgpt","entrypoint":"sol","instructions":[{"id":"rol_x","ref":"rol.test","label":"Role","kind":"role","position":1,"body":"Role body"}]}]}}
        redis=FakeRedis(); activate_call(redis,"01TEST",call); ready=prepare_first_step(redis,"01TEST",call)
        self.assertEqual(ready.source_identities,["psg.test"]); self.assertEqual(redis.hashes[ready.task_keys[0]]["input"],"Body\n"); self.assertIn(ready.task_keys[0],redis.zsets["state:ready:index"])
if __name__=="__main__": unittest.main()
