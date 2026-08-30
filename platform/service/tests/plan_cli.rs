use std::{
    fs,
    path::{Path, PathBuf},
    process::Command,
    time::{SystemTime, UNIX_EPOCH},
};

#[test]
fn config_git_ipc_commands_are_retired() {
    let root = temp();
    init_git(&root);
    for command in ["watch-config", "plan-save", "instructions-stage", "instructions-state-snapshot"] {
        let output = Command::new(env!("CARGO_BIN_EXE_svc"))
            .arg(command)
            .current_dir(&root)
            .output().unwrap();
        assert!(!output.status.success(), "{command} unexpectedly succeeded");
        let stderr = String::from_utf8_lossy(&output.stderr);
        assert!(!stderr.contains(command), "retired command still advertised in usage: {stderr}");
    }
    fs::remove_dir_all(root).unwrap();
}

fn init_git(root: &Path) {
    assert!(Command::new("git").current_dir(root).args(["init", "-q", "--initial-branch=main"]).status().unwrap().success());
    assert!(Command::new("git").current_dir(root).args(["config", "user.email", "test@example.com"]).status().unwrap().success());
    assert!(Command::new("git").current_dir(root).args(["config", "user.name", "AutoScribe Test"]).status().unwrap().success());
    fs::write(root.join("README.md"), "test\n").unwrap();
    assert!(Command::new("git").current_dir(root).args(["add", "README.md"]).status().unwrap().success());
    assert!(Command::new("git").current_dir(root).args(["commit", "-q", "-m", "initial"]).status().unwrap().success());
}

fn temp() -> PathBuf {
    let nonce = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos();
    let path = std::env::temp_dir().join(format!("autoscribe-plan-cli-{nonce}"));
    fs::create_dir(&path).unwrap();
    path
}
