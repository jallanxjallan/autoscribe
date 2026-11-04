"""Synthetic delivery interruptions through real queued and response daemons."""
from contextlib import ExitStack
import hashlib
import hmac
import json
import os
from pathlib import Path
import runpy
import signal
import sqlite3
import subprocess
import sys
import time
import tarfile

app = Path(sys.argv[1]).resolve()
services = Path(sys.argv[2]).resolve()
redis_server = Path(sys.argv[3]).resolve()
git_wrapper = Path(sys.argv[4]).resolve()
sys.path[:0] = [str(app), str(app / "tests")]
from autoscribe.enqueue import enqueue_record
from autoscribe.exporter import response_content
from autoscribe.redis_runtime import RedisClient
from test_enqueue import make_control, record

root = Path.cwd()
git = runpy.run_path(str(git_wrapper))["_git"]
shim = root / "shim"
shim.mkdir()
# Route application Git invocations through the required wrapper; introduce
# interruption only after the real command has performed its local operation.
(shim / "git").write_text("""#!/usr/bin/python3 -B
import os,runpy,signal,sys
from pathlib import Path
git=runpy.run_path(os.environ['TEST_GIT_WRAPPER'])['_git']
args=sys.argv[1:]
r=git(Path.cwd(),*args,check=False)
sys.stdout.write(r.stdout)
sys.stderr.write(r.stderr)
sys.stdout.flush()
marker=Path(os.environ['TEST_RUN'])/'git-interrupt'
if marker.exists() and r.returncode==0:
    operation=marker.read_text()
    if operation in args:
        marker.unlink()
        os.kill(os.getppid(),signal.SIGKILL)
sys.exit(r.returncode)
""")
(shim / "git").chmod(0o755)
os.environ.update(PATH=str(shim)+":/usr/bin:/bin", TEST_GIT_WRAPPER=str(git_wrapper), TEST_RUN=str(root))
repos = root / "Repos"
repos.mkdir()
secret = b"local-test-key-012345678901234567890123456789"
(root / "effect.key").write_bytes(secret)
(root / "effect.key").chmod(0o600)
policy = root / "services.toml"
policy.write_text(f"""[paths]
repo_roots = [{json.dumps(str(repos))}]
file_roots = [{json.dumps(str(root))}]
effect_key_file = {json.dumps(str(root/'effect.key'))}
effects_db = {json.dumps(str(root/'effects.sqlite'))}
control_db = {json.dumps(str(root/'control.sqlite'))}
""")
control = root / "control.sqlite"
ledger = root / "ledger.sqlite"
make_control(control)
with sqlite3.connect(control) as db:
    db.execute("UPDATE steps SET engine_kind='script',engine='extension',model=NULL,script='echo'")
registry = root / "registry.json"
registry.write_text(json.dumps({"echo": "/usr/bin/cat"}))
os.environ.update(
    AUTOSCRIBE_CONTROL_DB=str(control), AUTOSCRIBE_LEDGER_DB=str(ledger),
    AUTOSCRIBE_REDIS_HOST="127.0.0.1", AUTOSCRIBE_REDIS_PORT="16379",
    AUTOSCRIBE_EXTENSION_REGISTRY=str(registry), AUTOSCRIBE_WORKER_POLL_SECONDS="0.03",
    AUTOSCRIBE_EXECUTOR_POLL_SECONDS="0.03", AUTOSCRIBE_RESPONSE_SOCKET=str(root/"response.sock"),
    AUTOSCRIBE_SERVICES_POLICY=str(policy), AUTOSCRIBE_SERVICES=str(services),
    AUTOSCRIBE_ASC=str(app/"bin/asc"),
)
client = RedisClient("127.0.0.1", 16379)
prefix = "---\r\nslug: synthetic\r\ntitle: 'Keep exact bytes' # comment\r\n---\r\n".encode().decode("unicode_escape")

def wait_for(predicate, label):
    for _ in range(300):
        if predicate():
            return
        time.sleep(.03)
    raise RuntimeError(label)

def response(call):
    with sqlite3.connect(ledger) as db:
        return db.execute("SELECT 1 FROM responses WHERE call_id=?", (call,)).fetchone()

def exported(call):
    with sqlite3.connect(ledger) as db:
        return db.execute("SELECT 1 FROM exports WHERE call_id=?", (call,)).fetchone()

def seed(name):
    repo = repos / (name + ".git")
    git(root, "init", "--bare", "--initial-branch=master", str(repo))
    source = root / (name + "-seed")
    git(root, "init", "--initial-branch=master", str(source))
    target = source / "Note.md"
    target.write_bytes((prefix + "Original body\n").encode())
    git(source, "add", "Note.md")
    git(source, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
        "commit", "-m", "Seed")
    git(repo, "fetch", str(source), "master:master")
    git(repo, "symbolic-ref", "HEAD", "refs/heads/master")
    return repo

def submit(name, repo, failure=False):
    registry.write_text(json.dumps({"echo": "/usr/bin/false" if failure else "/usr/bin/cat"}))
    # Restart workers after registry changes because they load it at startup.
    value = record("Delivered body\n")
    value["record_id"] = "inp_" + name
    route = dict(kind="repo",repo=str(repo),path="Note.md",branch="master")
    envelope = dict(schema="autoscribe.return.v1", record_id=value["record_id"], route=route)
    canonical = json.dumps(envelope,sort_keys=True,separators=(",",":")).encode()
    envelope["signature"] = "eff_" + hmac.new(secret,canonical,hashlib.sha256).hexdigest()
    value["baggage"]["autoscribe_return"] = envelope
    return enqueue_record(record=value, control_db=control,ledger_db=ledger,client=client).call_id

def terminate(process):
    if process.poll() is None:
        process.terminate()
    process.wait(timeout=8)

bootstrap = root / "response-bootstrap.py"
bootstrap.write_text("""
import os,runpy,sys
from pathlib import Path
sys.path.insert(0,str(Path(sys.argv[1]).parent.parent))
namespace=runpy.run_path(sys.argv[1])
original=namespace['process_record'].__globals__['run_command']
stage=sys.argv[2]
def command(argv,**kwargs):
    label=Path(str(argv[0])).name
    if stage=='before_export' and label=='asc' and argv[1]=='response':
        os._exit(81)
    result=original(argv,**kwargs)
    if stage=='partial_export' and label=='srv-output' and result.returncode==0:
        result.stdout=result.stdout[:15]
    if stage=='after_export' and label=='srv-output' and result.returncode==0:
        os._exit(82)
    if stage=='before_ack' and label=='srv-writeback' and result.returncode==0:
        os._exit(83)
    return result
namespace['process_record'].__globals__['run_command']=command
sys.argv=[sys.argv[1],'--once']
raise SystemExit(namespace['main']())
""")

with ExitStack() as cleanup:
    def start(argv,name):
        stream = cleanup.enter_context((root/(name+".log")).open("wb"))
        process = subprocess.Popen(argv,stdout=stream,stderr=subprocess.STDOUT)
        cleanup.callback(terminate,process)
        return process
    def daemon(name,label):
        return start([sys.executable,"-B",str(app/"daemon"/name)],label)
    server = start([str(redis_server),"--bind","127.0.0.1","--port","16379",
                    "--dir",str(root),"--appendonly","yes","--appendfsync","everysec",
                    "--maxmemory-policy","noeviction"],"redis")
    def ping():
        try:
            client.ping()
            return True
        except OSError:
            return False
    wait_for(ping,"Redis did not start")
    for key,value in (("appendonly","yes"),("appendfsync","everysec"),("maxmemory-policy","noeviction")):
        assert client.command("CONFIG","GET",key)==[key,value]
    client.command("SET","restart-probe","retained")
    terminate(server)
    server = start([str(redis_server),"--bind","127.0.0.1","--port","16379",
                    "--dir",str(root),"--appendonly","yes","--appendfsync","everysec",
                    "--maxmemory-policy","noeviction"],"redis-restarted")
    wait_for(ping,"Redis did not restart")
    assert client.command("GET","restart-probe")=="retained"
    print("Redis version",client.command("INFO","server").split("redis_version:")[1].splitlines()[0],flush=True)
    executor = daemon("executord.py","executor")
    for phase in ("before_export","partial_export","after_export","during_apply","after_apply","before_ack","terminal_failure"):
        repo=seed(phase)
        call=submit(phase,repo,phase=="terminal_failure")
        worker=daemon("workerd.py","worker-"+phase)
        wait_for(lambda:response(call),"worker did not complete "+phase)
        terminate(worker)
        expected="Unreadable" if phase=="terminal_failure" else "Delivered body\n"
        assert response_content(ledger,client,call)==expected
        if phase in ("during_apply","after_apply"):
            (root/"git-interrupt").write_text("add" if phase=="during_apply" else "push")
        stage = "before_ack" if phase=="terminal_failure" else phase
        interrupted=start([sys.executable,"-B",str(bootstrap),str(app/"daemon/responsed.py"),stage],
                          "response-interrupted-"+phase)
        interrupted.wait(timeout=10)
        assert not exported(call),phase
        assert response_content(ledger,client,call)==expected
        resumed=start([sys.executable,"-B",str(app/"daemon/responsed.py"),"--once"],"response-resumed-"+phase)
        assert resumed.wait(timeout=10)==0
        assert exported(call), (phase,(root/("response-resumed-"+phase+".log")).read_text())
        actual=git(repo,"show","autoscribe-output:Note.md").stdout
        assert actual==prefix.replace("\r\n","\n")+expected,(phase,repr(actual))
        assert git(repo,"show","master:Note.md").stdout==prefix.replace("\r\n","\n")+"Original body\n"
        archive=root/(phase+"-output.tar")
        git(repo,"archive",f"--output={archive}","autoscribe-output","Note.md")
        with tarfile.open(archive) as exported_tree:
            assert exported_tree.extractfile("Note.md").read()==(prefix+expected).encode()
        # A later user edit must survive replay of the already applied receipt.
        human=root/(phase+"-human")
        git(root,"clone","--branch","autoscribe-output",str(repo),str(human))
        (human/"Note.md").write_bytes((prefix+"Later human edit\n").encode())
        git(human,"add","Note.md")
        git(human,"-c","user.name=Fixture","-c","user.email=fixture@example.invalid","commit","-m","Human edit")
        git(repo,"fetch",str(human),"autoscribe-output:autoscribe-output")
        count=git(repo,"rev-list","--count","autoscribe-output").stdout
        # Duplicate acknowledgment, replayed signed effect, and response daemon restart.
        effect=subprocess.run([str(services/"srv-output"),"--policy",str(policy)],
                              input=json.dumps(dict(schema="autoscribe.response.v1",call_id=call,
                                    content=expected,baggage=json.loads(client.hgetall(f"call:{call}:baggage")["json"]))),
                              text=True,capture_output=True,check=True)
        replay=subprocess.run([str(services/"srv-writeback"),"--policy",str(policy)],
                              input=effect.stdout,text=True,capture_output=True,check=True)
        assert json.loads(replay.stdout)["result"]
        assert git(repo,"rev-list","--count","autoscribe-output").stdout==count
        assert git(repo,"show","autoscribe-output:Note.md").stdout==prefix.replace("\r\n","\n")+"Later human edit\n"
        print(phase+": interrupted delivery recovered once, frontmatter and source preserved",flush=True)
