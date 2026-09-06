use autoscribe_service::{
    db::{self, Database},
    git, pandoc,
    types::{DispatchId, LedgerSnapshotRequest, LedgerSource, PandocJob, PlanId, VersionRequest},
};
use std::{
    fs,
    path::{Path, PathBuf},
    process::Command,
    time::{SystemTime, UNIX_EPOCH},
};

#[test]
fn in_memory_state_tracks_and_deactivates_repository_files() {
    let db = Database::memory().unwrap();
    let root = Path::new("/tmp/example-repository");
    db::file_seen(&db, root, Path::new("One.md"), Some("cnt.one"), Some("abc")).unwrap();
    assert_eq!(db::active_files(&db, root).unwrap().len(), 1);
    db::repository_removed(&db, root).unwrap();
    assert!(db::active_files(&db, root).unwrap().is_empty());
}

#[test]
fn inflight_history_preserves_source_without_moving_master() {
    let repository = TestRepository::new();
    fs::write(
        repository.path().join("One.md"),
        "---\nslug: cnt.one\n---\nOriginal\n",
    )
    .unwrap();
    repository.git(["add", "One.md"]);
    repository.git(["commit", "--quiet", "-m", "Original"]);
    let master = repository.output(["rev-parse", "master"]);

    let snapshot = git::append_inflight_snapshot(
        repository.path(),
        &LedgerSnapshotRequest {
            dispatch: DispatchId("dispatch-one".into()),
            plan: PlanId("plan.edit".into()),
            sources: vec![LedgerSource {
                slug: "cnt.one".into(),
                path: PathBuf::from("One.md"),
                bytes: b"---\nslug: cnt.one\n---\nOriginal\n".to_vec(),
            }],
        },
    )
    .unwrap();

    assert_eq!(repository.output(["rev-parse", "master"]), master);
    assert_eq!(
        git::read_version(
            repository.path(),
            VersionRequest {
                revision: snapshot.commit.0,
                path: "One.md".into()
            },
        )
        .unwrap(),
        b"---\nslug: cnt.one\n---\nOriginal\n"
    );
}

#[test]
fn pandoc_jobs_retain_input_order() {
    let jobs = ["first", "second"]
        .into_iter()
        .map(|identity| PandocJob {
            identity: identity.into(),
            working_directory: PathBuf::from("/tmp"),
            arguments: vec!["-c".into(), format!("printf {identity}")],
        })
        .collect();
    let outcomes = pandoc::run_parallel(Path::new("/bin/sh"), jobs, 2).unwrap();
    assert_eq!(outcomes[0].stdout, b"first");
    assert_eq!(outcomes[1].stdout, b"second");
}

struct TestRepository(PathBuf);

impl TestRepository {
    fn new() -> Self {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let path = std::env::temp_dir().join(format!("autoscribe-service-test-{nonce}"));
        fs::create_dir_all(&path).unwrap();
        let repository = Self(path);
        repository.git(["init", "--quiet", "--initial-branch=master"]);
        repository.git(["config", "user.email", "tests@autoscribe.local"]);
        repository.git(["config", "user.name", "AutoScribe Tests"]);
        repository
    }

    fn path(&self) -> &Path {
        &self.0
    }

    fn git<const N: usize>(&self, args: [&str; N]) {
        assert!(
            Command::new("git")
                .arg("-C")
                .arg(&self.0)
                .args(args)
                .status()
                .unwrap()
                .success()
        );
    }

    fn output<const N: usize>(&self, args: [&str; N]) -> String {
        let output = Command::new("git")
            .arg("-C")
            .arg(&self.0)
            .args(args)
            .output()
            .unwrap();
        assert!(output.status.success());
        String::from_utf8(output.stdout).unwrap().trim().into()
    }
}

impl Drop for TestRepository {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

#[test]
fn dispatch_cli_uses_path_pandoc_and_two_relative_defaults() {
    let repository = TestRepository::new();
    let root = repository.path();
    fs::write(root.join("One.md"), "---\nslug: cnt.one\n---\nOriginal\n").unwrap();
    repository.git(["add", "One.md"]);
    repository.git([
        "commit",
        "--quiet",
        "-m",
        "Dispatch\n\nAutoscribe-Plan: plan.test\nAutoscribe-Document: cnt.one",
    ]);
    let bin = root.join("bin");
    fs::create_dir(&bin).unwrap();
    let pandoc = bin.join("pandoc");
    let asc = bin.join("asc");
    fs::write(&pandoc, format!(r#"#!/bin/sh
printf '%s\n' "$@" > '{}'
printf '%s\n' "$PWD" > '{}'
cat "${{2#--defaults=}}" > '{}'
printf '%s\n' '{{"type":"call","identity":"cnt.one","content":"Body","plan":"plan.test","extra":{{}}}}'
"#, root.join("arguments").display(), root.join("cwd").display(), root.join("runtime.yaml").display())).unwrap();
    fs::write(
        &asc,
        "#!/bin/sh\nif [ \"$1\" = enqueue ]; then cat >/dev/null; fi\n",
    )
    .unwrap();
    use std::os::unix::fs::PermissionsExt;
    for path in [&pandoc, &asc] {
        fs::set_permissions(path, fs::Permissions::from_mode(0o700)).unwrap();
    }
    let output = Command::new(env!("CARGO_BIN_EXE_svc"))
        .args(["dispatch-once", root.to_str().unwrap()])
        .env("HOME", root)
        .env("AUTOSCRIBE_CLIENT_DB", root.join("client.sqlite"))
        .env("AUTOSCRIBE_ASC", &asc)
        .env("PATH", format!("{}:/usr/bin:/bin", bin.display()))
        .env_remove("AUTOSCRIBE_PANDOC")
        .env_remove("AUTOSCRIBE_PANDOC_DISPATCH_DEFAULTS")
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let arguments = fs::read_to_string(root.join("arguments")).unwrap();
    let args = arguments.lines().collect::<Vec<_>>();
    assert_eq!(args.len(), 2);
    assert_eq!(args[0], "--defaults=dispatch.yaml");
    assert!(args[1].starts_with("--defaults=autoscribe-dispatch-"));
    assert!(!args[1].contains('/'));
    let cwd = fs::read_to_string(root.join("cwd")).unwrap();
    assert!(
        !Path::new(cwd.trim())
            .join(args[1].trim_start_matches("--defaults="))
            .exists()
    );
    let runtime = fs::read_to_string(root.join("runtime.yaml")).unwrap();
    assert!(runtime.contains("/worktree/One.md"));
    assert!(runtime.contains("plan: \"plan.test\""));
}
