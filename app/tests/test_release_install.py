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
