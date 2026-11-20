from pathlib import Path
import importlib.util
import os
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


class ReleaseRootTests(unittest.TestCase):
    def test_final_root_mode_and_runtime_access_before_atomic_publication(self):
        spec = importlib.util.spec_from_file_location('installer', ROOT/'install-release.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source = root/'source'; source.mkdir()
            (source/'entry').write_text('#!/bin/sh\nprintf verified\n'); (source/'entry').chmod(0o755)
            private = root/'private'; private.mkdir(mode=0o700)
            (private/'credentials.env').write_text('synthetic only'); (private/'credentials.env').chmod(0o600)
            archive = root/'release.tar'
            with tarfile.open(archive, 'w') as out: out.add(source/'entry', arcname='entry')
            target = root/'published'; observations = []
            def runtime_check(pending):
                self.assertFalse(target.exists())
                self.assertEqual(pending.stat().st_mode & 0o777, 0o755)
                # This process is the real local runtime user, never root.
                self.assertEqual(os.geteuid(), 1000)
                self.assertEqual(subprocess.check_output([str(pending/'entry')]), b'verified')
                observations.append(True)
            with patch.object(module.os, 'chown'):
                module.extract(archive, target, runtime_check)
            self.assertEqual(observations, [True])
            self.assertEqual(target.stat().st_mode & 0o777, 0o755)
            self.assertEqual((target/'entry').stat().st_mode & 0o777, 0o755)
            self.assertEqual(private.stat().st_mode & 0o777, 0o700)
            self.assertEqual((private/'credentials.env').stat().st_mode & 0o777, 0o600)
            rejected = root/'rejected'
            def deny_runtime(_): raise PermissionError('runtime cannot traverse')
            with patch.object(module.os, 'chown'), self.assertRaises(PermissionError):
                module.extract(archive, rejected, deny_runtime)
            self.assertFalse(rejected.exists())

class SelectionTests(unittest.TestCase):
    def test_selected_launcher_checks_payload_and_resources_before_import(self):
        import hashlib,json,sys
        spec=importlib.util.spec_from_file_location('release',ROOT/'release.py')
        release=importlib.util.module_from_spec(spec);spec.loader.exec_module(release)
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'selected';(root/'app/bin').mkdir(parents=True);(root/'bin').mkdir()
            app=root/'app/bin/asc';app.write_text('print("selected-only")\n')
            resource=Path(td)/'resource';resource.write_text('pinned')
            revisions={'autoscribe':'a'*40};selection={}
            wrapper=root/'bin/asc';wrapper.write_text(release.launcher(root,selection,revisions))
            sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
            manifest={'revisions':revisions,'files':{root.name+'/app/bin/asc':sha(app),root.name+'/bin/asc':sha(wrapper)},'resource_files':{str(resource):sha(resource)}}
            (root/'manifest.json').write_text(json.dumps(manifest))
            cp=subprocess.run([sys.executable,'-I','-B',str(wrapper)],capture_output=True,text=True)
            self.assertEqual(cp.returncode,0,cp.stderr);self.assertEqual(cp.stdout.strip(),'selected-only')
            resource.write_text('drift')
            cp=subprocess.run([sys.executable,'-I','-B',str(wrapper)],capture_output=True,text=True)
            self.assertNotEqual(cp.returncode,0);self.assertEqual(cp.stdout,'')
            resource.write_text('pinned');app.write_text('print("tampered")\n')
            cp=subprocess.run([sys.executable,'-I','-B',str(wrapper)],capture_output=True,text=True)
            self.assertNotEqual(cp.returncode,0);self.assertEqual(cp.stdout,'')
