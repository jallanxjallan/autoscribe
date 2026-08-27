use rusqlite::Connection;
use serde_json::{Value, json};
use std::{
    fs,
    io::Write,
    path::{Path, PathBuf},
    process::{Command, Stdio},
    time::{SystemTime, UNIX_EPOCH},
};

#[test]
fn plan_save_keeps_only_plan_json_and_syncs_local_instruction_by_slug() {
    let root = temp();
    init_git(&root);
    let instructions = root.join("Instructions");
    fs::create_dir(&instructions).unwrap();
    fs::write(instructions.join("Context.md"), "---\ntitle: Project Context\nslug: ctx.project.test\nrecord: instruction\ncomponent: context\n---\nLocal context\n").unwrap();
    let asc = fake_asc(&root);
    let plan = json!({"record_type":"plan","record_identity":"plan.local.test","payload":{"label":"Local","type":"revise","description":"","steps":{"1":{"index":1,"kind":"llm","label":"Step 1","engine":"engines.openai","model":"models.test","instruction_slugs":{"standing":[],"role":[],"context":["ctx.project.test"],"task":[]}}}}});
    let output = invoke(&root, &asc, "plan-save", Some(json!({"version":1,"plan":plan})));
    assert!(output.status.success(), "{}", String::from_utf8_lossy(&output.stdout));

    let log = fs::read_to_string(root.join("asc.log")).unwrap();
    assert!(log.contains("upload instructions\n"));
    assert!(log.contains("upload plans\n"));
    let connection = Connection::open(root.join("service.sqlite")).unwrap();
    let plans: i64 = connection.query_row("SELECT count(*) FROM authored_plans", [], |row| row.get(0)).unwrap();
    let instruction_table: i64 = connection.query_row(
        "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='authored_instructions'", [], |row| row.get(0)
    ).unwrap();
    assert_eq!(plans, 1);
    assert_eq!(instruction_table, 0);
    let git_log = String::from_utf8(Command::new("git").current_dir(&root).args(["log", "-1", "--format=%s"]).output().unwrap().stdout).unwrap();
    assert_eq!(git_log.trim(), "initial");
    assert!(!String::from_utf8(Command::new("git").current_dir(&root).args(["status", "--porcelain", "--", "Instructions/Context.md"]).output().unwrap().stdout).unwrap().trim().is_empty());

    fs::write(root.join("asc.log"), "").unwrap();
    let snapshot = invoke(&root, &asc, "define-plan-snapshot", None);
    assert!(snapshot.status.success());
    assert_eq!(fs::read_to_string(root.join("asc.log")).unwrap(), "");
    let response: Value = serde_json::from_slice(&snapshot.stdout).unwrap();
    assert_eq!(response["catalogs"]["plans"][0]["record_identity"], "plan.local.test");
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn explicit_refresh_populates_context_catalog_and_snapshot_is_cache_only() {
    let root = temp();
    init_git(&root);
    let instructions = root.join("Instructions");
    fs::create_dir(&instructions).unwrap();
    fs::write(instructions.join("Context.md"), "---\ntitle: Project Context\nslug: ctx.project.test\nrecord: instruction\ncomponent: context\n---\nLocal context\n").unwrap();
    let asc = fake_asc(&root);

    let refresh = invoke(&root, &asc, "refresh", None);
    assert!(refresh.status.success(), "{}", String::from_utf8_lossy(&refresh.stdout));
    let response: Value = serde_json::from_slice(&refresh.stdout).unwrap();
    assert_eq!(response["catalogs"]["instructions"][0]["slug"], "ctx.project.test");
    assert_eq!(response["catalogs"]["instructions"][0]["scope"], "context");
    assert_eq!(response["uploaded_instructions"], 1);
    

    fs::write(root.join("asc.log"), "").unwrap();
    let snapshot = invoke(&root, &asc, "define-plan-snapshot", None);
    assert!(snapshot.status.success());
    assert_eq!(fs::read_to_string(root.join("asc.log")).unwrap(), "");
    let cached: Value = serde_json::from_slice(&snapshot.stdout).unwrap();
    assert_eq!(cached["catalogs"]["instructions"][0]["scope"], "context");
    fs::remove_dir_all(root).unwrap();
}

fn fake_asc(root: &Path) -> PathBuf {
    let path = root.join("asc");
    let log = root.join("asc.log");
    let state = root.join("instruction-uploaded");
    fs::write(&path, format!(r#"#!/bin/sh
if [ "$1 $2" = "control snapshot" ]; then
  if [ -f '{state}' ]; then
    printf '%s\n' '{{"registries":{{"instructions":{{"ctx.project.test":{{"record_identity":"ctx.project.test","extra":{{"title":"Project Context","scope":"context"}}}}}},"plans":{{}}}}}}'
  else
    printf '%s\n' '{{"registries":{{"instructions":{{}},"plans":{{}}}}}}'
  fi
  exit 0
fi
if [ "$1 $2" = "registry snapshot" ]; then printf '%s\n' '{{"registries":{{"engines":{{}},"models":{{}},"local_scripts":{{}},"rag_profiles":{{}}}}}}'; exit 0; fi
if [ "$1 $2" = "control instruction-manifest" ]; then printf '%s\n' '{{"instructions":{{}}}}'; exit 0; fi
printf '%s\n' "$1 $2" >> '{log}'
if [ "$1 $2" = "upload instructions" ]; then touch '{state}'; fi
cat >> '{log}.input'
"#, state=state.display(), log=log.display())).unwrap();
    executable(&path);
    path
}

fn invoke(root: &Path, asc: &Path, command: &str, input: Option<Value>) -> std::process::Output {
    let mut child = Command::new(env!("CARGO_BIN_EXE_svc"))
        .arg(command)
        .current_dir(root)
        .env("ASC_BIN", asc)
        .env("AUTOSCRIBE_DATABASE", root.join("service.sqlite"))
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn().unwrap();
    if let Some(input) = input { child.stdin.take().unwrap().write_all(input.to_string().as_bytes()).unwrap(); }
    child.wait_with_output().unwrap()
}

fn init_git(root: &Path) {
    assert!(Command::new("git").current_dir(root).args(["init", "-q"]).status().unwrap().success());
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
fn executable(path: &Path) {
    use std::os::unix::fs::PermissionsExt;
    let mut permissions = fs::metadata(path).unwrap().permissions(); permissions.set_mode(0o755); fs::set_permissions(path, permissions).unwrap();
}
