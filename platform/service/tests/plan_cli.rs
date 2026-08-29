use serde_json::{Value, json};
use std::{
    fs,
    io::Write,
    path::{Path, PathBuf},
    process::{Command, Stdio},
    time::{SystemTime, UNIX_EPOCH},
};

#[test]
fn plan_save_writes_only_config_ref_and_watch_config_syncs_committed_configuration() {
    let root = temp();
    init_git(&root);
    let instructions = root.join("Instructions");
    fs::create_dir(&instructions).unwrap();
    fs::write(instructions.join("Context.md"), "---\ntitle: Project Context\nslug: ctx.project.test\nrecord: instruction\ncomponent: context\n---\nLocal context\n").unwrap();
    git(&root, ["add", "Instructions/Context.md"]);
    git(&root, ["commit", "-q", "-m", "Add project context"]);
    let asc = fake_asc(&root);
    let plan = json!({"record_type":"plan","record_identity":"plan.local.test","payload":{"label":"Local","description":"","steps":{"1":{"index":1,"kind":"llm","label":"Step 1","engine":"engines.openai","model":"models.test","instruction_slugs":{"standing":[],"role":[],"context":["ctx.project.test"],"task":[]}}}}});

    let output = invoke(&root, &asc, "plan-save", Some(json!({"version":1,"plan":plan})));
    assert!(output.status.success(), "{}", String::from_utf8_lossy(&output.stdout));
    assert_eq!(fs::read_to_string(root.join("asc.log")).unwrap_or_default(), "");
    let response: Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(response["plan"], "plan.local.test");
    assert!(response["config_commit"].as_str().is_some());
    assert_eq!(git_output(&root, ["show", "refs/heads/autoscribe/config:plans/plan.local.test.json"])
        .contains("\"record_identity\": \"plan.local.test\""), true);
    assert_eq!(git_output(&root, ["log", "-1", "--format=%s", "HEAD"]).trim(), "Add project context");
    assert!(!root.join("plans").exists());
    assert!(!root.join(".autoscribe/plans").exists());

    let watcher = invoke(&root, &asc, "watch-config", None);
    assert!(watcher.status.success(), "{}", String::from_utf8_lossy(&watcher.stdout));
    let log = fs::read_to_string(root.join("asc.log")).unwrap();
    assert_eq!(log, "control snapshot\nupload instructions\nupload plans\ncontrol snapshot\n");
    assert!(git_output(&root, ["show", "refs/heads/autoscribe/config:instructions/ctx.project.test.json"])
        .contains("Local context"));
    let config = git_output(&root, ["rev-parse", "refs/heads/autoscribe/config"]);
    let synced = git_output(&root, ["rev-parse", "refs/autoscribe/config-synced"]);
    assert_ne!(config.trim(), synced.trim(), "state publication advances config without changing its payload");
    assert!(git_output(&root, ["show", "refs/heads/autoscribe/config:state/control.json"])
        .contains("\"current\": true"));
    assert_eq!(git_output(&root, ["ls-tree", "-r", "refs/heads/autoscribe/config", "--", "plans", "instructions"]),
        git_output(&root, ["ls-tree", "-r", "refs/autoscribe/config-synced", "--", "plans", "instructions"]));

    fs::remove_dir_all(root).unwrap();
}

#[test]
fn refresh_is_read_only_with_respect_to_configuration() {
    let root = temp();
    init_git(&root);
    let instructions = root.join("Instructions");
    fs::create_dir(&instructions).unwrap();
    fs::write(instructions.join("Context.md"), "---\ntitle: Project Context\nslug: ctx.project.test\nrecord: instruction\ncomponent: context\n---\nDirty uncommitted context\n").unwrap();
    let asc = fake_asc(&root);

    let refresh = invoke(&root, &asc, "refresh", None);
    assert!(refresh.status.success(), "{}", String::from_utf8_lossy(&refresh.stdout));
    assert_eq!(fs::read_to_string(root.join("asc.log")).unwrap(), "control snapshot\n");
    let config_ref = Command::new("git").current_dir(&root).args(["rev-parse", "--verify", "refs/heads/autoscribe/config"]).output().unwrap();
    assert!(config_ref.status.success());
    let response: Value = serde_json::from_slice(&refresh.stdout).unwrap();
    assert_eq!(response["catalogs"]["instructions"].as_array().unwrap().len(), 0);
    assert!(git_output(&root, ["show", "refs/heads/autoscribe/config:state/control.json"]).contains("\"version\": 1"));
    assert!(git_output(&root, ["ls-tree", "-r", "--name-only", "refs/heads/autoscribe/config", "--", "plans", "instructions"]).trim().is_empty());
    assert!(!root.join(".autoscribe/control-state.json").exists());
    assert_eq!(git_output(&root, ["log", "-1", "--format=%s", "HEAD"]).trim(), "initial");

    fs::remove_dir_all(root).unwrap();
}


#[test]
fn define_plan_snapshot_reads_published_git_state_without_pipeline_or_database() {
    let root = temp();
    init_git(&root);
    let asc = fake_asc(&root);
    let refresh = invoke(&root, &asc, "refresh", None);
    assert!(refresh.status.success(), "{}", String::from_utf8_lossy(&refresh.stdout));
    let _ = fs::remove_file(&asc);
    let _ = fs::remove_file(root.join("service.sqlite"));
    let snapshot = invoke(&root, &asc, "define-plan-snapshot", None);
    assert!(snapshot.status.success(), "{}", String::from_utf8_lossy(&snapshot.stdout));
    let response: Value = serde_json::from_slice(&snapshot.stdout).unwrap();
    assert_eq!(response["catalogs"]["engines"][0]["key"], "engines.openai");
    let remote = response["catalogs"]["plans"].as_array().unwrap().iter()
        .find(|plan| plan["record_identity"] == "plan.remote.test").unwrap();
    assert_eq!(remote["payload"]["label"], "Remote Plan");
    assert!(remote["payload"]["steps"].is_object());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn watch_config_rejects_plan_values_outside_the_captured_catalog_before_upload() {
    let root = temp();
    init_git(&root);
    let asc = fake_asc(&root);
    let plan = json!({
        "record_type":"plan",
        "record_identity":"plan.invalid.test",
        "payload":{"steps":{"1":{
            "index":1,"kind":"llm","engine":"engines.openai","model":"models.missing"
        }}}
    });
    let saved = invoke(&root, &asc, "plan-save", Some(json!({"version":1,"plan":plan})));
    assert!(saved.status.success());
    let watcher = invoke(&root, &asc, "watch-config", None);
    assert!(!watcher.status.success());
    assert_eq!(fs::read_to_string(root.join("asc.log")).unwrap(), "control snapshot\n");
    assert!(!root.join("asc.log.input").exists());
    let synced = Command::new("git").current_dir(&root)
        .args(["rev-parse", "--verify", "refs/autoscribe/config-synced"])
        .output().unwrap();
    assert!(!synced.status.success());
    fs::remove_dir_all(root).unwrap();
}


fn fake_asc(root: &Path) -> PathBuf {
    let path = root.join("asc");
    let log = root.join("asc.log");
    fs::write(&path, format!(r#"#!/bin/sh
printf '%s\n' "$1 $2" >> '{log}'
if [ "$1 $2" = "control snapshot" ]; then
  printf '%s\n' '{{"registries":{{"instructions":{{}},"plans":{{"plan.remote.test":{{"identity":"remote-version","content":{{"label":"Remote Plan","description":"","steps":{{"1":{{"index":1,"kind":"script","script":"prose_tics"}}}}}}}}}},"engines":{{"engines.openai":{{"key":"engines.openai","label":"OpenAI"}}}},"models":{{"models.test":{{"key":"models.test","label":"Test","engine":"engines.openai"}}}},"local_scripts":{{}},"rag_profiles":{{}}}}}}'
  exit 0
fi
cat >> '{log}.input'
"#, log=log.display())).unwrap();
    executable(&path);
    path
}

fn invoke(root: &Path, asc: &Path, command: &str, input: Option<Value>) -> std::process::Output {
    let mut cmd = Command::new(env!("CARGO_BIN_EXE_svc"));
    cmd.arg(command);
    if command == "watch-config" { cmd.arg("--once"); }
    let mut child = cmd.current_dir(root)
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

fn git_output<I, S>(root: &Path, args: I) -> String
where I: IntoIterator<Item = S>, S: AsRef<std::ffi::OsStr> {
    let output = Command::new("git").current_dir(root).args(args).output().unwrap();
    assert!(output.status.success(), "{}", String::from_utf8_lossy(&output.stderr));
    String::from_utf8(output.stdout).unwrap()
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
