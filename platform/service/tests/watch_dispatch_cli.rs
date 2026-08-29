use autoscribe_service::{db, db::Database, git, plan_repository};
use serde_json::{Value, json};
use std::{
    fs,
    path::{Path, PathBuf},
    process::Command,
    time::{SystemTime, UNIX_EPOCH},
};

#[test]
fn watcher_dispatches_declared_document_from_exact_commit_snapshot() {
    let root = temp("exact-snapshot");
    initialize_repo(&root);
    let content = root.join("Content");
    fs::create_dir(&content).unwrap();
    let document = content.join("One.md");
    let committed = "---\nslug: cnt.one\n---\nCommitted body\n";
    fs::write(&document, committed).unwrap();
    git(&root, ["add", "Content/One.md"]);
    git(&root, ["commit", "--quiet", "-m", "Editorial commit", "-m",
        "Autoscribe-Plan: plan.test\nAutoscribe-Document: cnt.one"]);

    // The live worktree is deliberately different. Dispatch must never read it.
    fs::write(&document, "---\nslug: cnt.one\n---\nDirty later edit\n").unwrap();
    let database = root.join("service.sqlite");
    save_plan(&root);
    let pandoc = fake_pandoc(&root);
    let asc = fake_asc(&root);

    let output = Command::new(env!("CARGO_BIN_EXE_svc"))
        .args(["watch-dispatch", "--once"])
        .current_dir(&root)
        .env("AUTOSCRIBE_DATABASE", &database)
        .env("AUTOSCRIBE_PANDOC_FILTER", root.join("filter.lua"))
        .env("AUTOSCRIBE_PANDOC_PARALLELISM", "2")
        .env("PANDOC_BIN", &pandoc)
        .env("ASC_BIN", &asc)
        .output().unwrap();
    assert!(output.status.success(), "{}", String::from_utf8_lossy(&output.stdout));
    let response: Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(response["events"][0]["status"], "dispatched");
    assert_eq!(response["events"][0]["records"], 1);
    assert_eq!(fs::read_to_string(root.join("pandoc.input")).unwrap(), committed);
    assert_eq!(git_output(&root, ["show", "refs/heads/autoscribe/inflight:Content/One.md"]), committed);
    assert_eq!(fs::read_to_string(root.join("asc.log")).unwrap(),
        "export list-pending --ndjson\nupload calls\nenqueue\n");

    fs::remove_dir_all(root).unwrap();
}

#[test]
fn malformed_dispatch_commit_is_retried_instead_of_advancing_cursor() {
    let root = temp("held-cursor");
    initialize_repo(&root);
    fs::write(root.join("One.md"), "---\nslug: cnt.one\n---\nBody\n").unwrap();
    git(&root, ["add", "One.md"]);
    git(&root, ["commit", "--quiet", "-m", "Broken dispatch", "-m", "Autoscribe-Plan: plan.test"]);
    let database = root.join("service.sqlite");
    save_plan(&root);

    let output = Command::new(env!("CARGO_BIN_EXE_svc"))
        .args(["watch-dispatch", "--once"])
        .current_dir(&root)
        .env("AUTOSCRIBE_DATABASE", &database)
        .output().unwrap();
    assert!(!output.status.success());
    let response: Value = serde_json::from_slice(&output.stdout).unwrap();
    assert!(response["error"].as_str().unwrap().contains("requires at least one Autoscribe-Document"));

    let db = Database::open_path(&database).unwrap();
    db::migrate(&db).unwrap();
    assert_eq!(db::meta_get(&db, "git.dispatch.cursor.main").unwrap(), None);
    drop(db);
    fs::remove_dir_all(root).unwrap();
}

fn save_plan(root: &Path) {
    let commit = plan_repository::save(root, &json!({
        "record_identity":"plan.test",
        "payload":{"steps":{"1":{"kind":"llm"}}}
    })).unwrap();
    git::mark_config_category_submitted(root, "plans", &commit).unwrap();
    git::mark_config_synced(root, &commit).unwrap();
}

fn fake_pandoc(root: &Path) -> PathBuf {
    let path = root.join("pandoc");
    fs::write(root.join("filter.lua"), "-- fixture\n").unwrap();
    fs::write(&path, format!(
        "#!/bin/sh\ncp -- \"$1\" '{}'\nprintf '%s\\n' '{{\"record_type\":\"content\",\"record_identity\":\"cnt.one\",\"payload\":{{\"content\":\"Committed body\"}}}}'\n",
        root.join("pandoc.input").display()
    )).unwrap();
    executable(&path);
    path
}

fn fake_asc(root: &Path) -> PathBuf {
    let path = root.join("asc");
    fs::write(&path, format!(
        "#!/bin/sh\nprintf '%s\\n' \"$*\" >> '{}'\nif [ \"$1 $2\" = \"export list-pending\" ]; then exit 0; fi\nif [ \"$1 $2\" = \"run status\" ]; then printf '%s\\n' '  worker=running pid=123'; exit 0; fi\ncat >> '{}.input'\n",
        root.join("asc.log").display(), root.join("asc.log").display()
    )).unwrap();
    executable(&path);
    path
}

fn initialize_repo(root: &Path) {
    git(root, ["init", "--quiet", "--initial-branch=main"]);
    git(root, ["config", "user.email", "tests@autoscribe.local"]);
    git(root, ["config", "user.name", "AutoScribe Tests"]);
    fs::write(root.join("README.md"), "fixture\n").unwrap();
    git(root, ["add", "README.md"]);
    git(root, ["commit", "--quiet", "-m", "Initial"]);
}

fn git<I, S>(root: &Path, args: I)
where I: IntoIterator<Item = S>, S: AsRef<std::ffi::OsStr> {
    assert!(Command::new("/usr/bin/git").args(args).current_dir(root).status().unwrap().success());
}

fn git_output<I, S>(root: &Path, args: I) -> String
where I: IntoIterator<Item = S>, S: AsRef<std::ffi::OsStr> {
    let output = Command::new("/usr/bin/git").args(args).current_dir(root).output().unwrap();
    assert!(output.status.success(), "{}", String::from_utf8_lossy(&output.stderr));
    String::from_utf8(output.stdout).unwrap()
}

fn temp(label: &str) -> PathBuf {
    let nonce = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos();
    let path = std::env::temp_dir().join(format!("autoscribe-watch-dispatch-{label}-{nonce}"));
    fs::create_dir(&path).unwrap();
    path
}

fn executable(path: &Path) {
    use std::os::unix::fs::PermissionsExt;
    let mut permissions = fs::metadata(path).unwrap().permissions();
    permissions.set_mode(0o755);
    fs::set_permissions(path, permissions).unwrap();
}
