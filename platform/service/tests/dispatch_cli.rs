use serde_json::json;
use std::{
    fs,
    io::Write,
    path::Path,
    process::{Command, Stdio},
    time::{SystemTime, UNIX_EPOCH},
};

#[test]
fn dispatch_prepare_command_returns_stable_json() {
    let unique = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let root = std::env::temp_dir().join(format!("autoscribe-dispatch-cli-{unique}"));
    fs::create_dir(&root).unwrap();
    git(&root, ["init", "--quiet", "--initial-branch=main"]);
    git(&root, ["config", "user.email", "tests@autoscribe.local"]);
    git(&root, ["config", "user.name", "AutoScribe Tests"]);
    fs::write(root.join("one.md"), "---\nslug: cnt.one\n---\nOne\n").unwrap();
    git(&root, ["add", "one.md"]);
    git(&root, ["commit", "--quiet", "-m", "Initial"]);

    let payload = "{\"version\":1,\"calls\":[],\"enqueue\":[]}\n";
    let request = json!({
        "version": 1,
        "database_path": root.join("service.sqlite"),
        "repository_path": root,
        "dispatch": "run-cli-test",
        "plan": "plan.test",
        "plan_version": "v1",
        "records": [{"slug": "cnt.one", "path": "one.md"}],
        "payload": payload,
        "payload_sha256": autoscribe_service::dispatch::sha256_hex(payload.as_bytes()),
        "commit_message": "Lock CLI dispatch"
    });
    let mut child = Command::new(env!("CARGO_BIN_EXE_svc"))
        .arg("dispatch-prepare")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    child
        .stdin
        .take()
        .unwrap()
        .write_all(request.to_string().as_bytes())
        .unwrap();
    let output = child.wait_with_output().unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let response: serde_json::Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(response["ok"], true);
    assert_eq!(response["operation"], "dispatch.prepare");
    assert_eq!(response["branch"], "autoscribe/run/run-cli-test");
    assert!(root.join("service.sqlite").is_file());
    fs::remove_dir_all(root).unwrap();
}

fn git<I, S>(repo: &Path, args: I)
where
    I: IntoIterator<Item = S>,
    S: AsRef<std::ffi::OsStr>,
{
    assert!(
        Command::new("/usr/bin/git")
            .args(args)
            .current_dir(repo)
            .status()
            .unwrap()
            .success()
    );
}
