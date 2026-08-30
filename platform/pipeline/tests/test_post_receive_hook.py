from __future__ import annotations

import os
import subprocess
from pathlib import Path


def test_post_receive_invokes_ingest_for_config_ref(tmp_path):
    bare = tmp_path / "server.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    log = tmp_path / "asc.log"
    fake = tmp_path / "asc"
    fake.write_text(f"#!/bin/sh\nprintf '%s\\n' \"$*\" >> '{log}'\n")
    fake.chmod(0o755)
    hook = Path(__file__).parents[2] / "server" / "hooks" / "post-receive"
    old = "1" * 40
    new = "2" * 40
    env = os.environ.copy()
    env["ASC_BIN"] = str(fake)
    subprocess.run(
        [str(hook)],
        cwd=bare,
        input=f"{old} {new} refs/heads/autoscribe/config\n{old} {new} refs/heads/main\n",
        text=True,
        env=env,
        check=True,
    )
    assert log.read_text().strip() == f"ingest {bare} {new} --base {old}"


def test_post_receive_full_ingest_on_first_config_push(tmp_path):
    bare = tmp_path / "server.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    log = tmp_path / "asc.log"
    fake = tmp_path / "asc"
    fake.write_text(f"#!/bin/sh\nprintf '%s\\n' \"$*\" >> '{log}'\n")
    fake.chmod(0o755)
    hook = Path(__file__).parents[2] / "server" / "hooks" / "post-receive"
    zero = "0" * 40
    new = "2" * 40
    env = os.environ.copy()
    env["ASC_BIN"] = str(fake)
    subprocess.run([str(hook)], cwd=bare, input=f"{zero} {new} refs/heads/autoscribe/config\n", text=True, env=env, check=True)
    assert log.read_text().strip() == f"ingest {bare} {new} --full"
