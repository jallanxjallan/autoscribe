use autoscribe_service::plan_repository;
use serde_json::{Value, json};
use std::{
    fs,
    io::Write,
    path::{Path, PathBuf},
    process::{Command, Stdio},
    time::{SystemTime, UNIX_EPOCH},
};

#[test]
fn dispatch_run_converts_and_enqueues_inline_calls() {
    let root = temp("success");
    fs::write(root.join("One.md"), "---\nslug: cnt.one\n---\nBody\n").unwrap();
    git(&root, ["init", "--quiet", "--initial-branch=main"]);
    git(&root, ["config", "user.email", "tests@autoscribe.local"]);
    git(&root, ["config", "user.name", "AutoScribe Tests"]);
    git(&root, ["add", "One.md"]);
    git(&root, ["commit", "--quiet", "-m", "Initial"]);
    let pandoc = root.join("pandoc");
    fs::write(&pandoc, "#!/bin/sh\nprintf '%s\\n' '{\"record_type\":\"content\",\"record_identity\":\"cnt.one\",\"payload\":{\"slug\":\"cnt.one\",\"content\":\"Body\"},\"directive\":\"Use this\"}'\n").unwrap();
    executable(&pandoc);
    let asc = fake_asc(&root);
    let output = invoke(&root, &pandoc, &asc);
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
    let response: Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(response["records"], 1);
    assert_eq!(
        fs::read_to_string(root.join("asc.log")).unwrap(),
        "export list-pending --ndjson\nenqueue\n"
    );
    let input = fs::read_to_string(root.join("asc.log.input")).unwrap();
    assert!(input.contains("\"type\":\"call\""));
    assert!(input.contains("\"directive\":\"Use this\""));
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn conversion_failure_prevents_enqueue() {
    let root = temp("failure");
    fs::write(root.join("One.md"), "---\nslug: cnt.one\n---\nBody\n").unwrap();
    initialize_repo(&root);
    let pandoc = root.join("pandoc");
    fs::write(&pandoc, "#!/bin/sh\necho bad >&2\nexit 9\n").unwrap();
    executable(&pandoc);
    let asc = fake_asc(&root);
    let output = invoke(&root, &pandoc, &asc);
    assert!(!output.status.success());
    assert!(!root.join("asc.log").exists());
    assert!(Command::new("/usr/bin/git").current_dir(&root)
        .args(["rev-parse", "--verify", "refs/heads/autoscribe/inflight"])
        .output().unwrap().status.success());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn pending_response_blocks_dispatch_before_enqueue() {
    let root = temp("pending");
    fs::write(root.join("One.md"), "---\nslug: cnt.one\n---\nBody\n").unwrap();
    initialize_repo(&root);
    let pandoc = root.join("pandoc");
    fs::write(&pandoc, "#!/bin/sh\nprintf '%s\\n' '{\"record_type\":\"content\",\"record_identity\":\"cnt.one\",\"payload\":{\"content\":\"Body\"}}'\n").unwrap();
    executable(&pandoc);
    let asc = root.join("asc");
    fs::write(&asc, format!("#!/bin/sh\nprintf '%s\\n' \"$*\" >> '{}'\nif [ \"$1 $2\" = \"control snapshot\" ]; then printf '%s\\n' '{{\"registries\":{{\"instructions\":{{}},\"plans\":{{\"plan.test\":{{\"record_identity\":\"plan.test\"}}}}}}}}'; exit 0; fi\nif [ \"$1 $2\" = \"export list-pending\" ]; then printf '%s\\n' '{{\"record_identity\":\"cnt.one\",\"call_identity\":\"call.one\",\"result_identity\":\"result.one\"}}'; fi\n", root.join("asc.log").display())).unwrap();
    executable(&asc);
    let output = invoke(&root, &pandoc, &asc);
    assert!(!output.status.success());
    let response: Value = serde_json::from_slice(&output.stdout).unwrap();
    assert!(response["error"].as_str().unwrap().contains("cnt.one"));
    assert_eq!(
        fs::read_to_string(root.join("asc.log")).unwrap(),
        "export list-pending --ndjson\n"
    );
    fs::remove_dir_all(root).unwrap();
}

fn invoke(root: &Path, pandoc: &Path, asc: &Path) -> std::process::Output {
    save_plan(root);
    let request = json!({"version":1,"plan":"plan.test","documents":["cnt.one"]});
    fs::write(root.join("filter.lua"), "-- fixture\n").unwrap();
    let mut child = Command::new(env!("CARGO_BIN_EXE_svc"))
        .arg("__dispatch-run")
        .env("ASC_BIN", asc)
        .env("AUTOSCRIBE_DATABASE", root.join("service.sqlite"))
        .env("AUTOSCRIBE_PANDOC_FILTER", root.join("filter.lua"))
        .env("AUTOSCRIBE_PANDOC_PARALLELISM", "2")
        .env("PANDOC_BIN", pandoc)
        .current_dir(root)
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
    child.wait_with_output().unwrap()
}
fn save_plan(root: &Path) {
    plan_repository::save(root, &json!({
        "record_identity":"plan.test",
        "payload":{"steps":{"1":{"kind":"llm"}}}
    })).unwrap();
}

fn fake_asc(root: &Path) -> PathBuf {
    fake_asc_with_status(root, "  worker=running pid=123")
}
fn fake_asc_with_status(root: &Path, status: &str) -> PathBuf {
    let path = root.join("asc");
    fs::write(
        &path,
        format!(
            "#!/bin/sh\nprintf '%s\\n' \"$*\" >> '{}'\nif [ \"$1 $2\" = \"control snapshot\" ]; then printf '%s\\n' '{{\"registries\":{{\"instructions\":{{}},\"plans\":{{\"plan.test\":{{\"record_identity\":\"plan.test\"}}}}}}}}'; exit 0; fi\nif [ \"$1 $2\" = \"export list-pending\" ]; then exit 0; fi\nif [ \"$1 $2\" = \"run status\" ]; then printf '%s\\n' '{}'; exit 0; fi\ncat >> '{}.input'\n",
            root.join("asc.log").display(),
            status,
            root.join("asc.log").display()
        ),
    )
    .unwrap();
    executable(&path);
    path
}
fn temp(label: &str) -> PathBuf {
    let n = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let path = std::env::temp_dir().join(format!("autoscribe-run-{label}-{n}"));
    fs::create_dir(&path).unwrap();
    path
}
fn executable(path: &Path) {
    use std::os::unix::fs::PermissionsExt;
    let mut p = fs::metadata(path).unwrap().permissions();
    p.set_mode(0o755);
    fs::set_permissions(path, p).unwrap();
}
fn initialize_repo(root: &Path) {
    git(root, ["init", "--quiet", "--initial-branch=main"]);
    git(root, ["config", "user.email", "tests@autoscribe.local"]);
    git(root, ["config", "user.name", "AutoScribe Tests"]);
    git(root, ["add", "One.md"]);
    git(root, ["commit", "--quiet", "-m", "Initial"]);
}
fn git<I, S>(repo: &Path, args: I)
where I: IntoIterator<Item = S>, S: AsRef<std::ffi::OsStr> {
    assert!(Command::new("/usr/bin/git").args(args).current_dir(repo).status().unwrap().success());
}
