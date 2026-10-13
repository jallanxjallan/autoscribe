"""Isolated transport smoke: real Redis, candidate Rust binaries, no live queues."""
from __future__ import annotations
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import tempfile
import time
import unittest

from test_enqueue import make_control, record
from autoscribe.enqueue import enqueue_record
from autoscribe.executor import prepare_first_step
from autoscribe.ledger import record_response
from autoscribe.redis_runtime import RedisClient, EXECUTOR_QUEUE_KEY, load_json
from autoscribe.worker import execute_task, persist_redis_response


@unittest.skipUnless(os.environ.get('AUTOSCRIBE_SERVICES_BIN'), 'requires candidate Rust binaries')
class TransportSmoke(unittest.TestCase):
    def test_parsed_and_legacy_transport_real_redis_and_export(self):
        with tempfile.TemporaryDirectory(prefix='ndjson-smoke-') as td:
            root = Path(td)
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', 0)); port = probe.getsockname()[1]
            proc = subprocess.Popen(['/usr/bin/redis-server', '--bind', '127.0.0.1', '--port', str(port),
                '--save', '', '--appendonly', 'no', '--dir', str(root)], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            try:
                client = RedisClient(port=port)
                for _ in range(100):
                    try: client.ping(); break
                    except OSError: time.sleep(.02)
                else: self.fail('private Redis failed to start')
                control = root/'control.sqlite'; ledger = root/'ledger.sqlite'; make_control(control)
                with sqlite3.connect(control) as db:
                    db.execute("UPDATE steps SET engine_kind='script',engine='local',script='echo' WHERE id='stp_1'")
                extension = root/'echo'; extension.write_text('#!/bin/sh\ncat\n'); extension.chmod(0o755)
                value = record('::: directive\nPreserve inline\n:::\nBody ![pic](assets/pic.png)\n')
                value.update(schema='autoscribe.input.v2', content_format='markdown', directive_policy='inline.v1',
                    source={'kind':'obsidian','path':'Note.md','slug':'psg_TEST','vault_id':hashlib.sha256(b'vault').hexdigest()},
                    references=[{'path':'Note.md','slug':'psg_TEST','content_sha256':value['content_sha256']}],
                    assets=[{'path':'assets/pic.png','content_hex':'616263','sha256':hashlib.sha256(b'abc').hexdigest()}])
                value['baggage']['client'] = {'source_path':'Note.md','source_slug':'psg_TEST','vault_id':hashlib.sha256(b'vault').hexdigest(),
                    'source_body_sha256':value['content_sha256'],'frontmatter':'---\r\nslug: psg_TEST # keep\r\n---\r\n'}
                def enqueue(): return enqueue_record(record=value,control_db=control,ledger_db=ledger,client=client)
                with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                    results = list(pool.map(lambda _:enqueue(),range(4)))
                self.assertEqual(len({r.call_id for r in results}),1)
                self.assertEqual(sum(r.created for r in results),1)
                first=results[0]; self.assertEqual(client.zrange(EXECUTOR_QUEUE_KEY,0,-1),[first.call_id])
                client.zrem(EXECUTOR_QUEUE_KEY,first.call_id)
                self.assertFalse(enqueue().created)
                self.assertEqual(client.zrange(EXECUTOR_QUEUE_KEY,0,-1),[])
                content=load_json(client,first.content_key)
                self.assertEqual(content['input']['assets'],value['assets'])
                ready=prepare_first_step(client,first.call_id,first.content_key)
                response=execute_task(client,ready.task_key,{'echo':extension})
                self.assertEqual(response.content,value['content'])
                record_response(ledger,first.call_id,persist_redis_response(client,response))
                incoming=root/'incoming'; outgoing=root/'outgoing'; incoming.mkdir(); outgoing.mkdir()
                rclone=root/'rclone'
                rclone.write_text('''#!/usr/bin/python3
import os,sys,shutil
from pathlib import Path
root=Path(os.environ['SMOKE_DROPBOX'])
def path(s):
    prefix='dropbox:biznet/'
    if not s.startswith(prefix): raise ValueError('wrong remote')
    return root/s[len(prefix):]
cmd=sys.argv[1];args=sys.argv[2:]
if cmd=='lsf':
    print('\\n'.join(p.name for p in path(args[-1]).iterdir() if p.is_file()))
elif cmd=='cat': sys.stdout.buffer.write(path(args[0]).read_bytes())
elif cmd=='deletefile': path(args[0]).unlink()
elif cmd=='copyto': shutil.copyfile(args[0],path(args[1]))
elif cmd=='moveto': path(args[0]).replace(path(args[1]))
else: raise ValueError(cmd)
'''); rclone.chmod(0o755)
                key=root/'effect.key';key.write_text('0'*64+'\n');key.chmod(0o600)
                policy=root/'services.toml'
                policy.write_text('[paths]\nrepo_roots=['+json.dumps(str(root))+']\nfile_roots=[]\neffect_key_file='+json.dumps(str(key))+'\neffects_db='+json.dumps(str(root/'effects.sqlite'))+'\ncontrol_db='+json.dumps(str(control))+'\n')
                env={**os.environ,'AUTOSCRIBE_CONTROL_DB':str(control),'AUTOSCRIBE_LEDGER_DB':str(ledger),
                    'AUTOSCRIBE_REDIS_PORT':str(port),'AUTOSCRIBE_RCLONE':str(rclone),'SMOKE_DROPBOX':str(root),
                    'AUTOSCRIBE_ASC':os.environ.get('AUTOSCRIBE_SMOKE_ASC',str(Path(__file__).resolve().parents[1]/'bin/asc'))}
                bins=Path(os.environ['AUTOSCRIBE_SERVICES_BIN']).resolve()
                def run(name, okay=True):
                    cp=subprocess.run([str(bins/name),'--policy',str(policy),'--once'],env=env,text=True,capture_output=True)
                    if okay: self.assertEqual(cp.returncode,0,cp.stderr)
                    else: self.assertNotEqual(cp.returncode,0)
                    return cp
                batch=incoming/'parsed.ndjson';batch.write_text(json.dumps(value)+'\n')
                run('srv-input');self.assertFalse(batch.exists())
                self.assertEqual(client.zrange(EXECUTOR_QUEUE_KEY,0,-1),[]) # consumed retry
                bad=json.loads(json.dumps(value));bad['assets'][0]['sha256']='0'*64
                batch.write_text(json.dumps(bad)+'\n');run('srv-input',False);self.assertTrue(batch.exists());batch.unlink()
                # Existing unversioned clients retain exact inline directives.
                legacy={'content':'::: directive\nLegacy\n:::\nBody','plan':'pln_TEST','client':{'source_path':'Legacy.md'}}
                batch.write_text(json.dumps(legacy)+'\n');run('srv-input');self.assertFalse(batch.exists())
                self.assertEqual(len(client.zrange(EXECUTOR_QUEUE_KEY,0,-1)),1)
                run('srv-export'); exported=json.loads((outgoing/(first.call_id+'.ndjson')).read_text())
                self.assertEqual(exported['result'],value['content'])
                self.assertEqual(exported['baggage'],value['baggage'])
                run('srv-export');self.assertEqual(len(list(outgoing.iterdir())),1)
            finally:
                proc.terminate();proc.wait(timeout=5)
                if proc.stderr: proc.stderr.close()

if __name__ == '__main__': unittest.main()
