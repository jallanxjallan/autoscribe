use autoscribe_service::{
    db::{self, Database},
    git,
    types::{DispatchId, LedgerSnapshotRequest, LedgerSource, PlanId},
};
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
fn write_responses_checkpoints_dirty_target_then_commits_review_copy() {
    let root = temp();
    run_git(&root, ["init", "--quiet", "--initial-branch=main"]);
    run_git(&root, ["config", "user.email", "tests@autoscribe.local"]);
    run_git(&root, ["config", "user.name", "AutoScribe Tests"]);
    fs::write(
        root.join("One.md"),
        "---\nslug: cnt.one\nstatus: draft\nproducer: human\naction: revise\n---\nOld\n",
    ).unwrap();
    run_git(&root, ["add", "One.md"]);
    run_git(&root, ["commit", "--quiet", "-m", "Initial"]);

    let db = root.join("service.sqlite");
    let database = Database::open_path(&db).unwrap();
    db::migrate(&database).unwrap();
    let ledger = git::append_inflight_snapshot(&root, &LedgerSnapshotRequest {
        dispatch: DispatchId("run-one".into()),
        plan: PlanId("plan.test".into()),
        sources: vec![LedgerSource {
            slug: "cnt.one".into(),
            path: "One.md".into(),
            bytes: fs::read(root.join("One.md")).unwrap(),
        }],
    }).unwrap();
    db::record_inflight(
        &database,
        "run-one",
        "plan.test",
        &ledger.reference,
        &ledger.commit.0,
        &[("cnt.one".into(), "One.md".into(), ledger.blobs[0].1.clone())],
    ).unwrap();
    drop(database);

    fs::write(
        root.join("One.md"),
        "---\nslug: cnt.one\nstatus: draft\nproducer: human\naction: revise\n---\nHuman edit\n",
    ).unwrap();
    let asc = fake_asc(&root);
    let written = invoke(&root, &asc, "write-responses", json!({"version":1}));
    assert!(written.status.success(), "{}", String::from_utf8_lossy(&written.stdout));
    let manifest: Value = serde_json::from_str(
        String::from_utf8_lossy(&written.stdout).lines().next().unwrap(),
    ).unwrap();
    assert_eq!(manifest["status"], "committed");
    assert!(manifest["checkpoint_commit"].as_str().is_some());
    assert!(manifest["commit"].as_str().is_some());
    assert_eq!(
        fs::read_to_string(root.join("One.md")).unwrap(),
        "---\nslug: cnt.one\nstatus: needs-review\nproducer: ai\naction: revise\n---\nNew\n"
    );
    assert!(git_output(&root, ["status", "--porcelain", "--", "One.md"]).trim().is_empty());
    let subjects = git_output(&root, ["log", "-2", "--format=%s"]);
    assert!(subjects.contains("Accept AutoScribe response cnt.one"));
    assert!(subjects.contains("Checkpoint before AutoScribe writeback cnt.one"));
    assert_eq!(
        fs::read_to_string(root.join("asc.log")).unwrap(),
        "export extract-pending\nexport update-exports call.one\n"
    );
    let connection = Connection::open(&db).unwrap();
    let count: i64 = connection.query_row(
        "SELECT count(*) FROM response_records WHERE result_identity='call.one'", [], |row| row.get(0),
    ).unwrap();
    assert_eq!(count, 0);
    fs::remove_dir_all(root).unwrap();
}

fn invoke(root: &Path, asc: &Path, command: &str, input: Value) -> std::process::Output {
    let mut child = Command::new(env!("CARGO_BIN_EXE_svc"))
        .arg(command)
        .env("ASC_BIN", asc)
        .env("AUTOSCRIBE_DATABASE", root.join("service.sqlite"))
        .current_dir(root)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn().unwrap();
    child.stdin.take().unwrap().write_all(input.to_string().as_bytes()).unwrap();
    child.wait_with_output().unwrap()
}

fn fake_asc(root: &Path) -> PathBuf {
    let path = root.join("asc");
    fs::write(&path, format!(
        "#!/bin/sh\nprintf '%s\\n' \"$*\" >> '{}'\nif [ \"$1 $2\" = \"export extract-pending\" ]; then printf '%s\\n' '{{\"identity\":\"call.one\",\"source_identity\":\"cnt.one\",\"record_content\":\"New\\n\"}}'; fi\n",
        root.join("asc.log").display()
    )).unwrap();
    executable(&path);
    path
}

fn temp() -> PathBuf {
    let n = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos();
    let path = std::env::temp_dir().join(format!("autoscribe-responses-{n}"));
    fs::create_dir(&path).unwrap();
    path
}

fn executable(path: &Path) {
    use std::os::unix::fs::PermissionsExt;
    let mut permissions = fs::metadata(path).unwrap().permissions();
    permissions.set_mode(0o755);
    fs::set_permissions(path, permissions).unwrap();
}

fn run_git<I, S>(repo: &Path, args: I)
where I: IntoIterator<Item = S>, S: AsRef<std::ffi::OsStr> {
    assert!(Command::new("/usr/bin/git").args(args).current_dir(repo).status().unwrap().success());
}

fn git_output<I, S>(repo: &Path, args: I) -> String
where I: IntoIterator<Item = S>, S: AsRef<std::ffi::OsStr> {
    let output = Command::new("/usr/bin/git").args(args).current_dir(repo).output().unwrap();
    assert!(output.status.success());
    String::from_utf8_lossy(&output.stdout).into_owned()
}
