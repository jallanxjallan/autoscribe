#!/usr/bin/env python3
"""Canonical scoped immutable-release installer; requires an approved preflight payload.

Run only after verifying release hashes and deployment authorization. Never use
this command to repair an installed release in place or activate real submissions.
"""
from pathlib import Path
import hashlib,json,os,shutil,sqlite3,subprocess,sys,tarfile,tempfile

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
def db_replace(source,target):
 # Sources and targets are quiescent; old WAL state must not survive replacement.
 for suffix in ('-wal','-shm'):
  side=Path(str(target)+suffix)
  if side.exists():side.unlink()
 pending=target.with_name('.'+target.name+'.autoscribe-pending');assert not pending.exists()
 shutil.copyfile(source,pending);pending.chmod(0o600);os.chown(pending,1000,1000)
 with pending.open('rb') as stream:os.fsync(stream.fileno())
 os.replace(pending,target)

def main(stage,expected_manifest):
 stage=Path(stage)
 assert os.geteuid()==0 and stage.is_dir()
 assert sha(stage/'manifest.json')==expected_manifest
 m=json.loads((stage/'manifest.json').read_text());p=json.loads((stage/'install-input.json').read_text());old=json.loads((stage/'preflight.json').read_text())
 assert p['manifest_sha256']==expected_manifest
 for name,digest in p['payload_hashes'].items():assert sha(stage/name)==digest,name
 for path,info in m['runtime_dependencies'].items():assert sha(Path(path))==info['sha256'],path
 previous=Path(next(x['resolved'] for x in old['paths'] if x['path']=='/opt/autoscribe/services/current'))
 assert Path('/opt/autoscribe/services/current').resolve()==previous
 assert Path('/opt/autoscribe/app').resolve()==previous/'app'
 for path,entry in old['sqlite'].items():assert table_inventory(Path(path))==entry['tables'],path
 assert command(['/usr/bin/redis-cli','--raw','DBSIZE'])=='0'
 for unit in ['autoscribe-executor.service','autoscribe-worker.service','autoscribe-responses.service','autoscribe-dropbox-ingest.service','autoscribe-dropbox-export.service']:
  assert user('/usr/bin/systemctl','--user','show',unit,'-p','ActiveState','--value')=='inactive',unit
  assert user('/usr/bin/systemctl','--user','show',unit,'-p','UnitFileState','--value')=='masked',unit
 for entry in old['paths']:
  if entry.get('sha256') and Path(entry['path']).exists():assert sha(Path(entry['path']))==entry['sha256'],entry['path']
 # Pin preservation includes immutable content and exact shared symlink targets.
 protected_paths=[Path('/opt/autoscribe/publish/current'),Path('/opt/autoscribe/extensions/current'),Path('/opt/autoscribe/templates/current')]
 protected_links={str(x):str(x.readlink()) for x in protected_paths}
 protected_files={str(x):sha(x) for x in Path('/opt/autoscribe/publish/current').rglob('*') if x.is_file()}
 for name in ['publish-recovery.service','publish-recovery.timer']:
  fragment=user('/usr/bin/systemctl','--user','show',name,'-p','FragmentPath','--value')
  if fragment:protected_files[fragment]=sha(Path(fragment))
  for extra in user('/usr/bin/systemctl','--user','show',name,'-p','DropInPaths','--value').split():protected_files[extra]=sha(Path(extra))
 legacy=[Path(x) for x in p['legacy_paths']]
 expected_legacy={Path(e['path']).name:e['sha256'] for e in old['executables'] if Path(e['path']).name in ('srv-input','srv-export')}
 for path in legacy:assert path.exists() and sha(path)==expected_legacy[path.name],str(path)
 backup=Path('/var/backups')/('autoscribe-pre-'+m['release_id']+'.tar');assert not backup.exists()
 engine=Path(m['installed_engine']);assert not engine.exists()
 for name in ('extensions','templates'):
  assert not (Path('/opt/autoscribe')/name/'releases'/m['revisions'][name]).exists()
 event('preconditions_verified',release=m['release_id'])
 with tempfile.TemporaryDirectory(prefix='autoscribe-backup-') as temporary:
  temp=Path(temporary);temp.chmod(0o700)
  for path in old['sqlite']:
   with sqlite3.connect(Path(path).as_uri()+'?mode=ro',uri=True) as src,sqlite3.connect(temp/(Path(path).name+'.'+sha(Path(path))[:12]+'.sqlite')) as dst:src.backup(dst)
  (temp/'preflight.json').write_text(json.dumps(old,indent=2));(temp/'protected.json').write_text(json.dumps({'links':protected_links,'files':protected_files},indent=2))
  with tarfile.open(backup,'x') as archive:
   archive.add(temp,arcname='database-snapshots')
   paths=[Path('/home/jeremy/.config/autoscribe'),Path('/etc/autoscribe'),Path('/home/jeremy/.local/bin/asc'),Path('/opt/autoscribe/app'),Path('/opt/autoscribe/services/current'),*legacy]
   paths += list(Path('/home/jeremy/.config/systemd/user').glob('autoscribe-*'))
   # A normal snapshot retains the prior engine, while legacy backing binaries are explicit above.
   paths += [previous]
   for path in paths:
    if path.exists() or path.is_symlink():archive.add(path,arcname=str(path).lstrip('/'),recursive=True)
  backup.chmod(0o600)
 event('backup_completed',path=str(backup),sha256=sha(backup))
 # Stage immutable engine and independent dependency roots, with no shared-current changes.
 extract(stage/(m['release_id']+'.tar'),engine,check_runtime_engine)
 user(engine/'bin/asc','control','plans')
 for name in ('extensions','templates'):
  extract(stage/(name+'-'+m['revisions'][name]+'.tar'),Path('/opt/autoscribe')/name/'releases'/m['revisions'][name])
 for relative,digest in m['files'].items():
  if relative.startswith(m['release_id']+'/'):assert sha(engine/Path(relative).relative_to(m['release_id']))==digest,relative
 shutil.copyfile(stage/'manifest.json',engine/'manifest.json');(engine/'manifest.json').chmod(0o644)
 event('immutable_files_installed',engine=str(engine))
 # Fresh canonical stores, from reviewed/pinned schema; no migration or Redis reset.
 sys.path.insert(0,str(engine/'app'))
 from autoscribe.ssh_jobs import initialize
 fresh=stage/'fresh-ledger.sqlite';initialize(fresh)
 effects=stage/'fresh-effects.sqlite'
 with sqlite3.connect(effects) as db:
  db.execute('CREATE TABLE effect_receipts (effect_key TEXT PRIMARY KEY, kind TEXT NOT NULL, target TEXT NOT NULL, result TEXT NOT NULL, submission_id TEXT NOT NULL, call_id TEXT NOT NULL, baggage_json TEXT NOT NULL, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)')
 for source,target in [(fresh,Path('/home/jeremy/Data/ledger.sql')),(effects,Path('/var/lib/autoscribe/effects.sqlite')),(stage/'control.sqlite',Path('/var/lib/autoscribe/control.sqlite'))]:db_replace(source,target)
 with sqlite3.connect('/var/lib/autoscribe/control.sqlite') as db:
  assert dict(db.execute('SELECT key,value FROM control_meta'))['source_commit']==m['revisions']['control']
  assert db.execute("SELECT count(*) FROM plans WHERE id='pln_K9X7H2M4R6Q8V3TN'").fetchone()[0]==1
  assert db.execute('SELECT count(*) FROM plans').fetchone()[0]==14
 atomic_text(Path('/etc/autoscribe/services.toml'),p['services_policy'],0o644)
 envpath=Path('/home/jeremy/.config/autoscribe/autoscribe.env');values=dict(line.split('=',1) for line in envpath.read_text().splitlines() if '=' in line and not line.startswith('#'));values.update(m['selected_environment']);values.update(AUTOSCRIBE_SERVICES=str(engine/'bin'),AUTOSCRIBE_SERVICES_POLICY='/etc/autoscribe/services.toml')
 atomic_text(envpath,''.join(k+'='+v+'\n' for k,v in values.items()),0o600,1000,1000)
 # Remove actual obsolete aliases and backing executables, keeping masks as tombstones.
 for path in legacy:path.unlink()
 for name in ['autoscribe-dropbox-ingest.service','autoscribe-dropbox-export.service']:
  path=Path('/home/jeremy/.config/systemd/user')/name
  assert path.is_symlink() and path.readlink()==Path('/dev/null')
 atomic_link(Path('/opt/autoscribe/services/current'),engine)
 atomic_link(Path('/opt/autoscribe/app'),engine/'app',1000,1000)
 atomic_link(Path('/home/jeremy/.local/bin/asc'),engine/'bin/asc',1000,1000)
 user('/usr/bin/systemctl','--user','daemon-reload')
 for path,target in protected_links.items():assert str(Path(path).readlink())==target,path
 for path,digest in protected_files.items():assert sha(Path(path))==digest,path
 assert all(not x.exists() and not x.is_symlink() for x in legacy)
 assert command(['/usr/bin/redis-cli','--raw','DBSIZE'])=='0'
 for unit in ['autoscribe-executor.service','autoscribe-worker.service','autoscribe-responses.service','autoscribe-dropbox-ingest.service','autoscribe-dropbox-export.service']:
  assert user('/usr/bin/systemctl','--user','show',unit,'-p','ActiveState','--value')=='inactive'
  assert user('/usr/bin/systemctl','--user','show',unit,'-p','UnitFileState','--value')=='masked'
 result={'release':m['release_id'],'manifest_sha256':expected_manifest,'backup':str(backup),'backup_sha256':sha(backup),'protected_links':protected_links,'protected_file_hashes':protected_files,'removed_legacy':[str(x) for x in legacy],'status':'installed; no jobs submitted; all persistent AutoScribe units inactive/masked'}
 atomic_text(Path('/home/jeremy/.local/state/autoscribe')/('deployment-'+m['release_id']+'.json'),json.dumps(result,indent=2)+'\n',0o600,1000,1000)
 event('installation_verified',**result)


if __name__ == "__main__":
 main(sys.argv[1],sys.argv[2])
