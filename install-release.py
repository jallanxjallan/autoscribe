#!/usr/bin/env python3
"""Canonical scoped immutable-release installer; requires an approved preflight payload.

Run only after verifying release hashes and deployment authorization. Never use
this command to repair an installed release in place or activate real submissions.
"""
from pathlib import Path
import hashlib,json,os,shutil,sqlite3,subprocess,sys,tarfile,tempfile,runpy

if not __debug__:
 raise RuntimeError("Installation requires validation enabled")
sys.dont_write_bytecode=True
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def event(phase,**values):print(json.dumps({'phase':phase,**values}),flush=True)
def command(args,**kwargs):return subprocess.run([str(v) for v in args],check=True,capture_output=True,text=True,**kwargs).stdout.strip()
def user(*args):return command(['/usr/sbin/runuser','-u','jeremy','--','/usr/bin/env','XDG_RUNTIME_DIR=/run/user/1000','DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus',*args])
def table_inventory(path):
 with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db:
  db.execute('PRAGMA query_only=ON')
  return {n:{'schema':s,'count':db.execute('SELECT count(*) FROM "'+n.replace('"','""')+'"').fetchone()[0]} for n,s in db.execute("SELECT name,sql FROM sqlite_master WHERE type='table' ORDER BY name")}
def atomic_text(path,text,mode,uid=0,gid=0):
 with tempfile.NamedTemporaryFile('w',dir=path.parent,delete=False) as stream:
  pending=Path(stream.name);stream.write(text);stream.flush();os.fsync(stream.fileno())
 pending.chmod(mode);os.chown(pending,uid,gid);os.replace(pending,path)
def atomic_link(path,target,uid=0,gid=0):
 pending=path.with_name('.'+path.name+'.autoscribe-pending');assert not pending.exists() and not pending.is_symlink()
 pending.symlink_to(target);os.chown(pending,uid,gid,follow_symlinks=False);os.replace(pending,path)
def check_runtime_tree(root):
 code = "from pathlib import Path; import os,sys; root=Path(sys.argv[1]); assert os.geteuid()==1000; assert os.access(root,os.R_OK|os.X_OK); paths=list(root.rglob('*')); assert all(os.access(p,os.R_OK|os.X_OK) if p.is_dir() else os.access(p,os.R_OK) for p in paths)"
 user('/usr/bin/python3','-B','-c',code,str(root))


def check_runtime_engine(root):
 check_runtime_tree(root)
 user('/opt/autoscribe/.venv/bin/python','-B',root/'app/bin/asc','control','plans')


def extract(archive,destination,runtime_check=check_runtime_tree):
 assert not destination.exists(),str(destination)
 pending=Path(tempfile.mkdtemp(prefix='.'+destination.name+'-',dir=destination.parent))
 with tarfile.open(archive) as files:files.extractall(pending,filter='data')
 for p in [pending,*pending.rglob('*')]:
  assert not p.is_symlink(),str(p)
  os.chown(p,0,0)
 # Only this public release root receives its intended final mode. Private
 # staging/configuration/backup paths and all child modes remain unchanged.
 pending.chmod(0o755)
 runtime_check(pending)
 os.replace(pending,destination)
def configured_ledger():
 return runpy.run_path(str(Path(__file__).parent/'app/asc/settings.py'))['ledger_path']()

def quiescent(ledger):
 with sqlite3.connect(ledger.as_uri()+'?mode=ro',uri=True) as db:
  db.execute('PRAGMA query_only=ON')
  assert db.execute("SELECT count(*) FROM ssh_jobs WHERE state!='cleaned'").fetchone()[0]==0, 'Non-cleaned jobs block activation'
  assert db.execute('SELECT count(*) FROM responses r LEFT JOIN exports e USING(call_id) WHERE e.call_id IS NULL').fetchone()[0]==0, 'Pending delivery blocks activation'
  assert db.execute('SELECT count(*) FROM calls c LEFT JOIN ssh_jobs j USING(call_id) WHERE j.call_id IS NULL').fetchone()[0]==0, 'Unowned accepted calls block activation'
 for key in ('queue:executor','queue:worker'):
  assert command(['/usr/bin/redis-cli','--raw','ZCARD',key])=='0', key
 assert not command(['/usr/bin/redis-cli','--raw','KEYS','claim:*']), 'Runtime claims block activation'
 units=user('/usr/bin/systemctl','--user','list-units','--all','asc-*','--no-legend','--plain')
 assert not units.strip(), 'Transient processing units block activation'
 for unit in ('autoscribe-worker.service','autoscribe-executor.service','autoscribe-responses.service'):
  assert user('/usr/bin/systemctl','--user','show',unit,'-p','ActiveState','--value')=='inactive', unit


def verify_payload(stage, manifest):
 assert manifest.get('runtime_configuration',{}).get('ledger_parameter')=='paths.ledger_db', 'Runtime must resolve the configured ledger'
 assert 'AUTOSCRIBE_LEDGER_DB' not in manifest['selected_environment'], 'Ledger path must not be embedded in a release'
 for name,digest in manifest['files'].items():
  path=stage/name
  assert path.resolve().is_relative_to(stage.resolve()), 'Payload path escape'
  assert path.is_file() and not path.is_symlink() and sha(path)==digest, name
 for name,source in manifest['source_provenance'].items():
  assert source['commit']==manifest['revisions'][name]
  assert sha(stage/(name+'-source.tar'))==source['archive_sha256']
 assert manifest['selected_environment']['AUTOSCRIBE_EXTENSION_REGISTRY']==str(Path(manifest['installed_engine'])/'extensions/registry.json')
 assert manifest['protocols']['runtime']=='asc.call.v1' and manifest['protocols']['component']=='asc.component.v1'
 assert manifest['release_id']+'/app/asc/models/call.py' in manifest['files']
 assert not any(name.startswith(manifest['release_id']+'/app/autoscribe/') for name in manifest['files'])
 for retired in ('app/daemon/workerd.py','app/daemon/executord.py'):
  assert manifest['release_id']+'/'+retired not in manifest['files'], retired


def bind_native(engine, previous, selection=Path('/opt/autoscribe/services/current')):
 """Retire the selected old CLI without changing native service implementation."""
 engine=Path(engine);previous=Path(previous);selection=Path(selection)
 assert selection.resolve()==previous.resolve(), 'Native selection changed'
 wanted=json.loads((engine/'manifest.json').read_text())
 prior=json.loads((previous/'manifest.json').read_text())
 assert wanted['revisions']['services']==prior['revisions']['services'], 'Native revision differs'
 for name in wanted['native_binaries']:
  assert sha(engine/'bin'/name)==sha(previous/'bin'/name), 'Native binary differs: '+name
 quiescent(configured_ledger())
 atomic_link(selection,engine)


def main(stage,expected_manifest):
 stage=Path(stage).resolve()
 assert __debug__ and os.geteuid()==0 and stage.is_dir()
 assert sha(stage/'manifest.json')==expected_manifest
 m=json.loads((stage/'manifest.json').read_text())
 preflight=json.loads((stage/'preflight.json').read_text())
 verify_payload(stage,m)
 for path,entry in m['runtime_dependencies'].items():assert sha(Path(path))==entry['sha256'],path
 for path,target in preflight['expected_links'].items():assert str(Path(path).readlink())==target,path
 for path,digest in preflight['protected_hashes'].items():assert sha(Path(path))==digest,path
 ledger=configured_ledger()
 control=Path(m['selected_environment']['AUTOSCRIBE_CONTROL_DB'])
 with sqlite3.connect(control.as_uri()+'?mode=ro',uri=True) as db:
  meta=dict(db.execute('SELECT key,value FROM control_meta'))
  assert meta['source_commit']==m['revisions']['control'] and meta['schema_version']=='3', 'Control binding changed'
  labels={row[0] for row in db.execute('SELECT DISTINCT model FROM steps WHERE model IS NOT NULL')}
  assert labels <= set(m['model_catalogue']) | set(m['model_catalogue'].values()), 'Retired Control model label'
 native=Path('/opt/autoscribe/services/current').resolve()
 assert json.loads((native/'manifest.json').read_text())['revisions']['services']==m['revisions']['services'], 'Native Services binding changed'
 quiescent(ledger)
 before={path:table_inventory(Path(path)) for path in preflight['databases']}
 engine=Path(m['installed_engine']);assert not engine.exists()
 assert engine.parent==Path('/opt/autoscribe/services/releases')
 previous=Path('/opt/autoscribe/app').resolve()
 # Preserve previous selections explicitly. No ledger, Control, policy or shared
 # publishing/agent/native-service selection is ever replaced by this installer.
 backup=Path('/var/backups')/('autoscribe-pre-'+m['release_id']+'.json')
 assert not backup.exists()
 atomic_text(backup,json.dumps(preflight,indent=2)+'\n',0o600)
 allowed_retirements={'/home/jeremy/Repos/Dispatch-Test.git/hooks/post-receive',
                      '/usr/local/bin/srv-typst','/home/jeremy/deploy-autoscribe','/home/jeremy/smoke-autoscribe'}
 retired=preflight.get('retirements',{})
 assert set(retired)<=allowed_retirements, 'Unreviewed retirement path'
 for path,digest in retired.items():assert sha(Path(path))==digest,path
 retired_backup=Path('/var/backups')/('autoscribe-retired-'+m['release_id']+'.tar')
 with tarfile.open(retired_backup,'x') as archive:
  for path in retired:archive.add(path,arcname=str(Path(path)).lstrip('/'),recursive=False)
 retired_backup.chmod(0o600)
 for name in ('extensions','templates'):
  target=Path(m['selected_environment']['EXTENSIONS_ROOT' if name=='extensions' else 'TEMPLATES_ROOT'])
  if not target.exists():extract(stage/(name+'-'+m['revisions'][name]+'.tar'),target)
 extract(stage/(m['release_id']+'.tar'),engine,check_runtime_tree)
 shutil.copy2(stage/'manifest.json',engine/'manifest.json');(engine/'manifest.json').chmod(0o644)
 prefix=m['release_id']+'/'
 for name,digest in m['files'].items():
  if name.startswith(prefix):assert sha(engine/name[len(prefix):])==digest,name
 for path,digest in m['resource_files'].items():assert sha(Path(path))==digest,path
 check_runtime_engine(engine)
 user(engine/'bin/asc','control','plans')
 quiescent(ledger)
 assert {path:table_inventory(Path(path)) for path in before}==before
 for path,digest in preflight['protected_hashes'].items():assert sha(Path(path))==digest,path
 # CLI follows the single app selection; native Services and Plan Manager retain
 # their independent release bindings. Jobs retain their accepting immutable root.
 cli=Path('/home/jeremy/.local/bin/asc')
 atomic_link(cli,Path('/opt/autoscribe/app/../bin/asc'),1000,1000)
 try:
  bind_native(engine,native)
  atomic_link(Path('/opt/autoscribe/app'),engine/'app',1000,1000)
  assert Path('/opt/autoscribe/app').resolve()==engine/'app'
  user(cli,'control','plans')
  for path,digest in preflight['protected_hashes'].items():assert sha(Path(path))==digest,path
 except BaseException:
  atomic_link(Path('/opt/autoscribe/services/current'),native)
  atomic_link(Path('/opt/autoscribe/app'),previous,1000,1000)
  atomic_link(cli,Path(preflight['expected_links'][str(cli)]),1000,1000)
  raise
 for path,digest in retired.items():
  assert sha(Path(path))==digest,path
  Path(path).unlink()
 event('installation_verified',release=m['release_id'],manifest_sha256=expected_manifest,
       backup=str(backup),retired_backup=str(retired_backup),retired=list(retired),
       status='installed; existing ledger and Control preserved; no jobs submitted')


if __name__ == '__main__':
 main(sys.argv[1],sys.argv[2])
