"""Exercise the proposed Redis 7 live configuration change and rollback."""
from pathlib import Path
import shutil
import subprocess
import sys
import time

server = Path(sys.argv[1]).resolve()
cli = server.with_name("redis-cli")
root = Path.cwd()
conf = root / "redis.conf"
conf.write_text(f"""port 0
unixsocket {root}/redis.sock
dir {root}
save 3600 1 300 100 60 10000
appendonly no
appendfsync everysec
maxmemory-policy noeviction
""")
def command(*args):
    return subprocess.check_output([str(cli),"--raw","-s",str(root/"redis.sock"),*args],
                                   text=True,stderr=subprocess.DEVNULL).strip()
def start():
    log=(root/"redis.log").open("ab")
    p=subprocess.Popen([str(server),str(conf)],stdout=log,stderr=log)
    for _ in range(100):
        if p.poll() is not None:
            raise RuntimeError("Redis startup failed")
        try:
            if command("PING")=="PONG":
                return p
        except subprocess.CalledProcessError:
            pass
        time.sleep(.03)
    raise RuntimeError("Redis startup timeout")
def stop(p):
    p.terminate()
    assert p.wait(timeout=10)==0

process=start()
try:
    command("CLIENT","SETNAME","phase10b-fixture")
    command("SET","unrelated-client-key","preserved")
    command("ZADD","queue:executor","0","pending")
    command("HSET","claim:task:test","state","running","owner","attempt")
    assert command("SAVE")=="OK"
    shutil.copy2(root/"dump.rdb",root/"before-conversion.rdb")
    shutil.copy2(conf,root/"before-conversion.conf")
    assert command("CONFIG","SET","appendonly","yes")=="OK"
    for _ in range(300):
        info=command("INFO","persistence")
        if all(value in info for value in ("aof_enabled:1","aof_rewrite_in_progress:0",
               "aof_rewrite_scheduled:0","aof_last_bgrewrite_status:ok","aof_last_write_status:ok")):
            assert int(next(row.split(":")[1] for row in info.splitlines() if row.startswith("aof_current_size:")))>0
            break
        time.sleep(.03)
    else:
        raise RuntimeError("AOF initialization incomplete")
    assert command("CONFIG","REWRITE")=="OK"
    assert command("GET","unrelated-client-key")=="preserved"
    stop(process)
    process=start()
    assert command("CONFIG","GET","appendonly").splitlines()==["appendonly","yes"]
    assert command("CONFIG","GET","appendfsync").splitlines()==["appendfsync","everysec"]
    assert command("CONFIG","GET","maxmemory-policy").splitlines()==["maxmemory-policy","noeviction"]
    assert command("GET","unrelated-client-key")=="preserved"
    assert command("ZRANGE","queue:executor","0","-1")=="pending"
    assert command("HGET","claim:task:test","state")=="running"
    print("Redis 7 AOF everysec conversion, config persistence and normal restart passed.",flush=True)
    # Return to RDB using a snapshot of current live state, never an older backup.
    command("SET","new-after-aof","preserve-on-rollback")
    assert command("SAVE")=="OK"
    assert command("CONFIG","SET","appendonly","no")=="OK"
    assert command("CONFIG","REWRITE")=="OK"
    stop(process)
    process=start()
    assert command("CONFIG","GET","appendonly").splitlines()==["appendonly","no"]
    assert command("GET","new-after-aof")=="preserve-on-rollback"
    assert command("GET","unrelated-client-key")=="preserved"
    assert command("HGET","claim:task:test","state")=="running"
    print("Live rollback with a current snapshot preserved all tested state.",flush=True)
finally:
    if process.poll() is None:
        stop(process)
