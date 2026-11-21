"""Retained Native Services signed repository-effect boundaries; disposable repos."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import sqlite3
import subprocess
from test_runtime import RuntimeCase
from asc.models.call import Call


class SignedEffectsTests(RuntimeCase):
    def setUp(self):
        super().setUp()
        self.native=Path(os.environ['AUTOSCRIBE_TEST_NATIVE_ROOT'])
        self.shim=self.root/'shim';self.shim.mkdir()
        adapter=os.environ['AUTOSCRIBE_TEST_GIT_ADAPTER']
        wrapper=self.shim/'git';wrapper.write_text('#!/usr/bin/python3\nimport os,sys\nos.execv("/usr/bin/python3",["/usr/bin/python3",'+repr(adapter)+',*sys.argv[1:]])\n');wrapper.chmod(0o755)
        self.env_native=dict(os.environ,PATH=str(self.shim)+':'+os.environ['PATH'],VAULT_GIT_ADAPTER=str(wrapper))
        self.repos=self.root/'repos';self.repos.mkdir();self.repo=self.repos/'target.git'
        self.git('init','--bare','--initial-branch=master',str(self.repo))
        self.secret=b'synthetic-effect-key-012345678901234567890123456789'
        (self.root/'effect.key').write_bytes(self.secret);(self.root/'effect.key').chmod(0o600)
        self.policy=self.root/'policy.toml';self.policy.write_text('[paths]\nrepo_roots=['+json.dumps(str(self.repos))+']\neffect_key_file='+json.dumps(str(self.root/'effect.key'))+'\neffects_db='+json.dumps(str(self.root/'effects.sqlite'))+'\n')
        route={'schema':'autoscribe.return.v1','record_id':self.prepared['record_id'],'route':{'kind':'repo','repo':str(self.repo),'path':'Note.md','branch':'master'}}
        route['signature']='eff_'+hmac.new(self.secret,json.dumps(route,sort_keys=True,separators=(',',':')).encode(),hashlib.sha256).hexdigest()
        self.prepared['baggage']['autoscribe_return']=route
        from unittest.mock import patch
        with patch.object(__import__('asc.ssh_jobs',fromlist=['prepare_dropbox']),'prepare_dropbox',return_value=json.dumps(self.prepared)):self.accept()
        self.execute();self.record=Call.load(self.call_id,self.client).response_record()

    def git(self,*args):return subprocess.check_output(['/usr/bin/python3',os.environ['AUTOSCRIBE_TEST_GIT_ADAPTER'],*args],text=True)
    def command(self,name,value,success=True):
        result=subprocess.run([str(self.native/name),'--policy',str(self.policy)],input=json.dumps(value,ensure_ascii=False)+'\n',text=True,capture_output=True,env=self.env_native,timeout=30)
        self.assertEqual(result.returncode==0,success,result.stderr)
        return json.loads(result.stdout) if result.returncode==0 else result.stderr

    def test_signed_routes_effects_and_durable_replay(self):
        effect=self.command('srv-output',self.record)
        first=self.command('srv-writeback',effect)
        count=self.git('--git-dir',str(self.repo),'rev-list','--count','autoscribe-output')
        self.assertEqual(self.command('srv-writeback',effect),first)
        self.assertEqual(self.git('--git-dir',str(self.repo),'rev-list','--count','autoscribe-output'),count)
        # Recover interruption after commit/publication but before receipt insertion.
        with sqlite3.connect(self.root/'effects.sqlite') as db:db.execute('DELETE FROM effect_receipts WHERE effect_key=?',(effect['effect_key'],))
        recovered=self.command('srv-writeback',effect)
        self.assertEqual(recovered['result'],first['result'])
        self.assertEqual(self.git('--git-dir',str(self.repo),'rev-list','--count','autoscribe-output'),count)
        changed=dict(effect,content='changed')
        self.command('srv-writeback',changed,False)
        changed['content_sha256']=hashlib.sha256(b'changed').hexdigest()
        self.command('srv-writeback',changed,False)
        self.assertEqual(self.command('srv-writeback',effect),recovered)

    def test_missing_invalid_and_unauthorized_routes_fail(self):
        invalid=json.loads(json.dumps(self.record));invalid['baggage'].pop('autoscribe_return')
        self.command('srv-output',invalid,False)
        invalid=json.loads(json.dumps(self.record));invalid['baggage']['autoscribe_return']['signature']='eff_'+'0'*64
        self.command('srv-output',invalid,False)
        for path in ['../escape.md','/tmp/escape.md']:
            invalid=json.loads(json.dumps(self.record));route=invalid['baggage']['autoscribe_return'];route.pop('signature');route['route']['path']=path
            route['signature']='eff_'+hmac.new(self.secret,json.dumps(route,sort_keys=True,separators=(',',':')).encode(),hashlib.sha256).hexdigest()
            self.command('srv-output',invalid,False)
        effect=self.command('srv-output',self.record);effect['effect_key']='eff_'+'0'*64
        self.command('srv-writeback',effect,False)
        self.assertFalse((self.root/'effects.sqlite').exists())
