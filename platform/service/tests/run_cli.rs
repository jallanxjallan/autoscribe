use serde_json::{Value, json};
use std::{
    fs,
    io::Write,
    path::{Path, PathBuf},
    process::{Command, Stdio},
    time::{SystemTime, UNIX_EPOCH},
};

#[test]
fn dispatch_run_converts_uploads_and_enqueues_in_one_service_call() {
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
        "export list-pending --ndjson\nupload calls\nenqueue\n"
    );
    let input = fs::read_to_string(root.join("asc.log.input")).unwrap();
    assert!(input.contains("\"type\":\"call\""));
    assert!(input.contains("\"directive\":\"Use this\""));
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn conversion_failure_prevents_upload_and_enqueue() {
    let root = temp("failure");
    fs::write(root.join("One.md"), "Body\n").unwrap();
    let pandoc = root.join("pandoc");
    fs::write(&pandoc, "#!/bin/sh\necho bad >&2\nexit 9\n").unwrap();
    executable(&pandoc);
    let asc = fake_asc(&root);
    let output = invoke(&root, &pandoc, &asc);
    assert!(!output.status.success());
    assert!(!root.join("asc.log").exists());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn pending_response_blocks_dispatch_before_upload_and_enqueue() {
    let root = temp("pending");
    fs::write(root.join("One.md"), "Body\n").unwrap();
    let pandoc = root.join("pandoc");
    fs::write(&pandoc, "#!/bin/sh\nprintf '%s\\n' '{\"record_type\":\"content\",\"record_identity\":\"cnt.one\",\"payload\":{\"content\":\"Body\"}}'\n").unwrap();
    executable(&pandoc);
    let asc = root.join("asc");
    fs::write(&asc, format!("#!/bin/sh\nprintf '%s\\n' \"$*\" >> '{}'\nif [ \"$1 $2\" = \"export list-pending\" ]; then printf '%s\\n' '{{\"record_identity\":\"cnt.one\",\"call_identity\":\"call.one\",\"result_identity\":\"result.one\"}}'; fi\n", root.join("asc.log").display())).unwrap();
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
    let request = json!({"version":1,"database_path":root.join("service.sqlite"),"repository_path":root,"pandoc_binary":pandoc,
        "pandoc_filter":root.join("filter.lua"),"pandoc_parallelism":2,"plan":"plan.test","paths":["One.md"]});
    fs::write(root.join("filter.lua"), "-- fixture\n").unwrap();
    let mut child = Command::new(env!("CARGO_BIN_EXE_svc"))
        .arg("dispatch-run")
        .env("ASC_BIN", asc)
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
fn fake_asc(root: &Path) -> PathBuf {
    let path = root.join("asc");
    fs::write(
        &path,
        format!(
            "#!/bin/sh\nprintf '%s\\n' \"$*\" >> '{}'\nif [ \"$1 $2\" = \"export list-pending\" ]; then exit 0; fi\ncat >> '{}.input'\n",
            root.join("asc.log").display(),
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
fn git<I, S>(repo: &Path, args: I)
where I: IntoIterator<Item = S>, S: AsRef<std::ffi::OsStr> {
    assert!(Command::new("/usr/bin/git").args(args).current_dir(repo).status().unwrap().success());
}
