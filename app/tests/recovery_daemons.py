from contextlib import ExitStack
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

from autoscribe.enqueue import enqueue_record
from autoscribe.redis_runtime import RedisClient, EXECUTOR_QUEUE_KEY, WORKER_QUEUE_KEY

app = Path(sys.argv[1])
fixtures = Path(sys.argv[2])
sys.path.append(str(fixtures))
from test_enqueue import make_control, record

root = Path.cwd()
control = root / 'control.sqlite'
ledger = root / 'ledger.sqlite'
make_control(control)
adapter = root / 'adapter'
adapter.write_text('#!/bin/sh\nif [ -e interrupt ]; then touch entered; sleep 2; fi\nexec /usr/bin/cat\n')
adapter.chmod(0o700)
registry = root / 'registry.json'
registry.write_text(json.dumps({'echo': str(adapter)}))
with sqlite3.connect(control) as db:
    db.execute("UPDATE steps SET engine_kind='script',engine='extension',model=NULL,script='echo'")
os.environ.update(AUTOSCRIBE_LEDGER_DB=str(ledger), AUTOSCRIBE_EXTENSION_REGISTRY=str(registry),
                  AUTOSCRIBE_REDIS_HOST='127.0.0.1', AUTOSCRIBE_REDIS_PORT='16379',
                  AUTOSCRIBE_WORKER_CLAIM_SECONDS='2', AUTOSCRIBE_EXECUTOR_POLL_SECONDS='0.05', AUTOSCRIBE_WORKER_POLL_SECONDS='0.05')
client = RedisClient('127.0.0.1', 16379)
def wait_for(predicate, label):
    for _ in range(150):
        if predicate():
            return
        time.sleep(.05)
    raise RuntimeError(label)
def ready():
    try:
        client.ping()
        return True
    except OSError:
        return False
def terminate(process):
    if process.poll() is None:
        process.terminate()
    process.wait(timeout=5)
def response(call):
    with sqlite3.connect(ledger) as db:
        return db.execute('SELECT redis_key FROM responses WHERE call_id=?',(call,)).fetchone()
def submit(name):
    data=record('Synthetic '+name)
    data['record_id']='inp_'+name
    return enqueue_record(record=data,control_db=control,ledger_db=ledger,client=client).call_id

with ExitStack() as cleanup:
    def start(argv, name):
        stream=cleanup.enter_context((root/(name+'.log')).open('wb'))
        p=subprocess.Popen(argv,stdout=stream,stderr=subprocess.STDOUT)
        cleanup.callback(terminate,p)
        return p
    def daemon(name, log):
        return start([sys.executable,'-B',str(app/'daemon'/name)],log)
    def redis(log):
        return start([os.environ.get('AUTOSCRIBE_TEST_REDIS_SERVER','/usr/bin/redis-server'),'--bind','127.0.0.1','--port','16379','--appendonly','yes','--appendfsync','everysec','--maxmemory-policy','noeviction'],log)
    server=redis('redis')
    wait_for(ready,'redis startup')
    for key, value in (("appendonly","yes"),("appendfsync","everysec"),("maxmemory-policy","noeviction")):
        assert client.command("CONFIG","GET",key)==[key,value]
    first=submit('pending')
    assert first in client.zrange(EXECUTOR_QUEUE_KEY,0,-1)
    client.expire(f"call:{first}:content",5)
    client.expire(f"call:{first}:baggage",5)
    terminate(server)
    redis('redis-restart')
    wait_for(ready,'redis restart')
    assert first in client.zrange(EXECUTOR_QUEUE_KEY,0,-1)
    executor_bootstrap = root / "crash_executor.py"
    executor_bootstrap.write_text("""
import os, runpy, sys
from autoscribe.redis_runtime import RedisClient, EXECUTOR_QUEUE_KEY
original = RedisClient.zrem
def zrem(self, key, member):
    if key == EXECUTOR_QUEUE_KEY:
        os._exit(73)
    return original(self, key, member)
RedisClient.zrem = zrem
runpy.run_path(sys.argv[1], run_name='__main__')
""")
    executor = start([sys.executable, "-B", str(executor_bootstrap), str(app/"daemon/executord.py")], "executor-crash")
    assert executor.wait(timeout=8) == 73
    assert first in client.zrange(EXECUTOR_QUEUE_KEY,0,-1)
    assert len(client.zrange(WORKER_QUEUE_KEY,0,-1)) == 1
    daemon('executord.py','executor')
    wait_for(lambda: not client.zrange(EXECUTOR_QUEUE_KEY,0,-1), 'executor did not resume handoff')
    wait_for(lambda: client.zrange(WORKER_QUEUE_KEY,0,-1),'worker selection')
    assert client.command("TTL",f"call:{first}:content")==-1
    assert client.command("TTL",f"call:{first}:baggage")==-1
    worker=daemon('workerd.py','worker')
    wait_for(lambda: response(first),'pending job response')
    print('Pending executor queue survived Redis restart and actual daemons recorded a response.',flush=True)
    (root/'interrupt').touch()
    interrupted=submit('interrupted')
    wait_for(lambda:(root/'entered').exists(),'adapter start')
    worker.kill()
    worker.wait(timeout=5)
    (root/'interrupt').unlink()
    restarted=daemon('workerd.py','worker-restarted')
    followup=submit('followup')
    wait_for(lambda:response(followup),'worker restart did not process followup')
    assert response(interrupted) is None
    def claim_state(call):
        return client.command("HGET",f"claim:task:{call}:1","state")
    wait_for(lambda:claim_state(interrupted)=="uncertain","interrupted claim not reconciled")
    assert not client.zrange(WORKER_QUEUE_KEY,0,-1)
    assert claim_state(followup)=="done"
    assert client.command("TTL",f"claim:task:{interrupted}:1")==-1
    print("Interrupted execution remained durably uncertain and was not replayed.", flush=True)
    # Inject exit immediately after durable claim, and after durable result.
    terminate(restarted)
    bootstrap = root / "crash_worker.py"
    bootstrap.write_text("""
import os, runpy, sys
from autoscribe.claims import Claim
original = Claim.transition
def transition(self, previous, state, **kwargs):
    if state == 'running' and sys.argv[2] == 'claimed':
        os._exit(71)
    if state == 'done' and sys.argv[2] == 'done':
        os._exit(72)
    result = original(self, previous, state, **kwargs)
    if result and state == sys.argv[2]:
        os._exit(72)
    return result
Claim.transition = transition
runpy.run_path(sys.argv[1], run_name='__main__')
""")
    for phase in ("claimed", "result", "done"):
        call = submit(phase)
        injected = start([sys.executable, "-B", str(bootstrap), str(app/"daemon/workerd.py"), phase], "crash-"+phase)
        assert injected.wait(timeout=8) == {"claimed":71,"result":72,"done":72}[phase]
        assert claim_state(call) == ("result" if phase == "done" else phase)
        if phase in {"result", "done"}:
            # If recovery invokes the adapter again, the missing executable will fail.
            adapter.write_text("#!/bin/sh\nexit 17\n")
        recovery = daemon("workerd.py","recover-"+phase)
        concurrent = daemon("workerd.py","concurrent-"+phase)
        wait_for(lambda:response(call),"recovery did not record response")
        task_key = f"task:{call}:1"
        wait_for(lambda:not client.zrange(WORKER_QUEUE_KEY,0,-1),"original queue item not acknowledged")
        client.zadd(WORKER_QUEUE_KEY,0,task_key)
        wait_for(lambda:not client.zrange(WORKER_QUEUE_KEY,0,-1),"duplicate queue item not acknowledged")
        from autoscribe.exporter import iter_pending_records, response_content
        assert call in {row["call_id"] for row in iter_pending_records(ledger,client)}
        assert response_content(ledger,client,call) == "Synthetic "+phase
        terminate(recovery)
        terminate(concurrent)
        adapter.write_text("#!/bin/sh\nexec /usr/bin/cat\n")
        print(f"{phase}: recovered response, rejected duplicate execution, and exposed pending export.",flush=True)
    adapter.write_text("#!/bin/sh\nexit 17\n")
    failed = submit("explicit_failure")
    daemon("workerd.py","terminal-failure")
    wait_for(lambda:response(failed),"explicit failure did not reach response ledger")
    assert response_content(ledger,client,failed) == "Unreadable"
    assert failed in {row["call_id"] for row in iter_pending_records(ledger,client)}
    wait_for(lambda:claim_state(failed)=="done","failure was not acknowledged")
    print("Explicit adapter failure reached the existing pending export channel as Unreadable.",flush=True)
    for key in (f"call:{interrupted}:content",f"call:{interrupted}:baggage",f"task:{interrupted}:1",f"claim:task:{interrupted}:1"):
        assert client.command("TTL",key)==-1, key
    for key in (f"response:{failed}:content",f"result:{failed}:1:content"):
        assert client.command("TTL",key)==-1, key
    import autoscribe.exporter as exporter
    exporter.FORENSIC_TTL=1
    assert not exporter.retain_delivered(ledger,client,failed)
    # Synthetic delivery acknowledgment tests retention only, not the delivery daemon.
    exporter.mark_exported(ledger,client,call_id=failed,receipt=dict(
        schema="autoscribe.receipt.v1",effect_key="synthetic",kind="repo",
        target="synthetic",result="applied"))
    assert client.command("TTL",f"claim:task:{failed}:1") >= 0
    time.sleep(1.2)
    assert not client.hgetall(f"claim:task:{failed}:1")
    client.hset(f"task:{failed}:1",{"call_id":failed})
    client.zadd(WORKER_QUEUE_KEY,0,f"task:{failed}:1")
    wait_for(lambda:not client.zrange(WORKER_QUEUE_KEY,0,-1),"expired claim duplicate was not rejected")
    print("Outstanding payload TTLs disabled; acknowledged retention expired; SQLite completion prevented replay.",flush=True)
