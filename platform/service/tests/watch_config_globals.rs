use serde_json::{json, Value};
use std::{
    fs,
    io::Write,
    path::{Path, PathBuf},
    process::{Command, Stdio},
    time::{SystemTime, UNIX_EPOCH},
};

#[test]
fn watch_config_submits_unrelated_project_records_and_global_instructions_independently() {
    let root = temp("project");
    let globals = temp("globals");
    init_git(&root);
    init_git(&globals);

    fs::create_dir(root.join("Instructions")).unwrap();
    fs::write(
        root.join("Instructions/Unused.md"),
        "---\ntitle: Unused Project Instruction\nslug: tsk.project.unused\nrecord: instruction\ncomponent: task\n---\nProject instruction body\n",
    ).unwrap();
    git(&root, ["add", "Instructions/Unused.md"]);
    git(&root, ["commit", "-q", "-m", "Add unrelated project instruction"]);

    fs::create_dir(globals.join("Instructions")).unwrap();
    fs::write(
        globals.join("Instructions/Global.md"),
        "---\ntitle: Global Instruction\nslug: tsk.global.example\nrecord: instruction\ncomponent: task\n---\nGlobal body one\n",
    ).unwrap();
    git(&globals, ["add", "Instructions/Global.md"]);
    git(&globals, ["commit", "-q", "-m", "Add global instruction"]);

    let asc = fake_asc(&root);
    let plan = json!({
        "record_type":"plan",
        "record_identity":"plan.unrelated.test",
        "payload":{"steps":{"1":{"index":1,"kind":"script","script":"anything"}}}
    });
    let saved = invoke(&root, &globals, &asc, "plan-save", Some(json!({"version":1,"plan":plan})));
    assert!(saved.status.success(), "{}", String::from_utf8_lossy(&saved.stderr));

    let first = invoke(&root, &globals, &asc, "watch-config", None);
    assert!(first.status.success(), "{}", String::from_utf8_lossy(&first.stderr));
    let log = fs::read_to_string(root.join("asc.log")).unwrap();
    assert_eq!(log, "upload instructions\nupload plans\nupload instructions\n");
    let input = fs::read_to_string(root.join("asc.log.input")).unwrap();
    assert!(input.contains("tsk.project.unused"));
    assert!(input.contains("plan.unrelated.test"));
    assert!(input.contains("tsk.global.example"));
    assert!(Command::new("git").current_dir(&globals)
        .args(["rev-parse", "--verify", "refs/autoscribe/instructions-submitted"])
        .output().unwrap().status.success());

    fs::write(
        globals.join("Instructions/Global.md"),
        "---\ntitle: Global Instruction\nslug: tsk.global.example\nrecord: instruction\ncomponent: task\n---\nGlobal body two\n",
    ).unwrap();
    git(&globals, ["add", "Instructions/Global.md"]);
    git(&globals, ["commit", "-q", "-m", "Modify global instruction"]);

    let second = invoke(&root, &globals, &asc, "watch-config", None);
    assert!(second.status.success(), "{}", String::from_utf8_lossy(&second.stderr));
    let log = fs::read_to_string(root.join("asc.log")).unwrap();
    assert_eq!(log, "upload instructions\nupload plans\nupload instructions\nupload instructions\n");
    let response: Value = serde_json::from_slice(&second.stdout).unwrap();
    assert_eq!(response["event"]["uploaded_instructions"], 0);
    assert_eq!(response["event"]["uploaded_plans"], 0);
    assert_eq!(response["event"]["globals"]["uploaded"], 1);

    fs::remove_dir_all(root).unwrap();
    fs::remove_dir_all(globals).unwrap();
}

fn fake_asc(root: &Path) -> PathBuf {
    let path = root.join("asc");
    let log = root.join("asc.log");
    fs::write(&path, format!(r#"#!/bin/sh
printf '%s\n' "$1 $2" >> '{log}'
cat >> '{log}.input'
exit 0
"#, log=log.display())).unwrap();
    executable(&path);
    path
}

fn invoke(root: &Path, globals: &Path, asc: &Path, command: &str, input: Option<Value>) -> std::process::Output {
    let mut cmd = Command::new(env!("CARGO_BIN_EXE_svc"));
    cmd.arg(command);
    if command == "watch-config" { cmd.arg("--once"); }
    let mut child = cmd.current_dir(root)
        .env("ASC_BIN", asc)
        .env("AUTOSCRIBE_GLOBALS_VAULT", globals)
        .env("AUTOSCRIBE_DATABASE", root.join("service.sqlite"))
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn().unwrap();
    if let Some(input) = input {
        child.stdin.take().unwrap().write_all(input.to_string().as_bytes()).unwrap();
    }
    child.wait_with_output().unwrap()
}

fn init_git(root: &Path) {
    assert!(Command::new("git").current_dir(root).args(["init", "-q", "--initial-branch=main"]).status().unwrap().success());
    assert!(Command::new("git").current_dir(root).args(["config", "user.email", "test@example.com"]).status().unwrap().success());
    assert!(Command::new("git").current_dir(root).args(["config", "user.name", "AutoScribe Test"]).status().unwrap().success());
    fs::write(root.join("README.md"), "test\n").unwrap();
    git(root, ["add", "README.md"]);
    git(root, ["commit", "-q", "-m", "initial"]);
}

fn git<I, S>(root: &Path, args: I)
where I: IntoIterator<Item = S>, S: AsRef<std::ffi::OsStr> {
    assert!(Command::new("git").current_dir(root).args(args).status().unwrap().success());
}

fn temp(label: &str) -> PathBuf {
    let nonce = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos();
    let path = std::env::temp_dir().join(format!("autoscribe-watch-config-{label}-{nonce}"));
    fs::create_dir(&path).unwrap();
    path
}

fn executable(path: &Path) {
    use std::os::unix::fs::PermissionsExt;
    let mut permissions = fs::metadata(path).unwrap().permissions();
    permissions.set_mode(0o755);
    fs::set_permissions(path, permissions).unwrap();
}
