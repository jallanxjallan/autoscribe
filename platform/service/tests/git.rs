use autoscribe_service::{
    ServiceError, git,
    types::{
        CommitPurpose, CommitRequest, DispatchId, LedgerSnapshotRequest, LedgerSource, PlanId,
        RestoreRequest, VersionRequest,
    },
};
use std::{
    fs,
    path::{Path, PathBuf},
    process::Command,
    time::{SystemTime, UNIX_EPOCH},
};

struct TestRepo(PathBuf);

impl TestRepo {
    fn new() -> Self {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let path = std::env::temp_dir().join(format!(
            "autoscribe-service-git-{}-{unique}",
            std::process::id()
        ));
        fs::create_dir(&path).unwrap();
        run(&path, ["init", "--quiet", "--initial-branch=main"]);
        run(&path, ["config", "user.email", "tests@autoscribe.local"]);
        run(&path, ["config", "user.name", "AutoScribe Tests"]);
        fs::write(path.join("one.md"), "---\nslug: cnt.one\n---\nOne\n").unwrap();
        fs::write(path.join("two.md"), "---\nslug: cnt.two\n---\nTwo\n").unwrap();
        run(&path, ["add", "--", "one.md", "two.md"]);
        run(&path, ["commit", "--quiet", "-m", "Initial"]);
        Self(path)
    }
}

impl Drop for TestRepo {
    fn drop(&mut self) {
        if self.0.starts_with(std::env::temp_dir()) {
            fs::remove_dir_all(&self.0).unwrap();
        }
    }
}

#[test]
fn inspect_and_read_version_use_repository_relative_paths() {
    let repo = TestRepo::new();
    fs::write(repo.0.join("one.md"), "changed\n").unwrap();

    let states = git::inspect(
        &repo.0,
        &[PathBuf::from("one.md"), PathBuf::from("missing.md")],
    )
    .unwrap();
    assert_eq!(states[0].tracked, true);
    assert_eq!(states[0].dirty, true);
    assert_eq!(states[1].tracked, false);
    assert_eq!(states[1].dirty, false);
    assert!(matches!(
        git::inspect(&repo.0, &[PathBuf::from("../outside")]),
        Err(ServiceError::InvalidInput(_))
    ));

    let original = git::read_version(
        &repo.0,
        VersionRequest {
            path: "one.md".into(),
            revision: "HEAD".into(),
        },
    )
    .unwrap();
    assert!(
        String::from_utf8(original)
            .unwrap()
            .contains("slug: cnt.one")
    );
}

#[test]
fn explicit_commit_leaves_unselected_working_changes_uncommitted() {
    let repo = TestRepo::new();
    fs::write(repo.0.join("one.md"), "One changed\n").unwrap();
    fs::write(repo.0.join("two.md"), "Two changed\n").unwrap();

    let commit = git::commit(
        &repo.0,
        CommitRequest {
            paths: vec!["one.md".into()],
            message: "Update one".into(),
            purpose: CommitPurpose::Version,
        },
    )
    .unwrap();

    assert_eq!(commit.0, output(&repo.0, ["rev-parse", "HEAD"]));
    assert_eq!(output(&repo.0, ["show", "HEAD:one.md"]), "One changed");
    assert!(output(&repo.0, ["show", "HEAD:two.md"]).contains("slug: cnt.two"));
    assert!(output(&repo.0, ["status", "--porcelain=v1", "--", "two.md"]).ends_with("two.md"));
}

#[test]
fn inflight_ledger_snapshots_worktree_bytes_without_switching_or_touching_index() {
    let repo = TestRepo::new();
    fs::write(repo.0.join("one.md"), "---\nslug: cnt.one\n---\nDraft changed\n").unwrap();
    let branch_before = output(&repo.0, ["branch", "--show-current"]);
    let status_before = output(&repo.0, ["status", "--porcelain=v1"]);

    let snapshot = git::append_inflight_snapshot(&repo.0, &LedgerSnapshotRequest {
        dispatch: DispatchId("dispatch-ledger-01".into()),
        plan: PlanId("plan.copy".into()),
        sources: vec![LedgerSource {
            slug: "cnt.one".into(),
            path: "one.md".into(),
            bytes: fs::read(repo.0.join("one.md")).unwrap(),
        }],
    }).unwrap();

    assert_eq!(snapshot.reference, "refs/heads/autoscribe/inflight");
    assert_eq!(output(&repo.0, ["branch", "--show-current"]), branch_before);
    assert_eq!(output(&repo.0, ["status", "--porcelain=v1"]), status_before);
    assert!(output(&repo.0, ["show", format!("{}:one.md", snapshot.commit.0).as_str()])
        .contains("Draft changed"));
    assert!(output(&repo.0, ["show", "HEAD:one.md"]).contains("One"));

    fs::write(repo.0.join("two.md"), "---\nslug: cnt.two\n---\nSecond draft\n").unwrap();
    let second = git::append_inflight_snapshot(&repo.0, &LedgerSnapshotRequest {
        dispatch: DispatchId("dispatch-ledger-02".into()),
        plan: PlanId("plan.copy".into()),
        sources: vec![LedgerSource {
            slug: "cnt.two".into(),
            path: "two.md".into(),
            bytes: fs::read(repo.0.join("two.md")).unwrap(),
        }],
    }).unwrap();
    assert_eq!(output(&repo.0, ["rev-parse", format!("{}^", second.commit.0).as_str()]), snapshot.commit.0);
    assert!(output(&repo.0, ["show", format!("{}:one.md", second.commit.0).as_str()]).contains("Draft changed"));
}

#[test]
fn response_snapshot_records_exact_bytes_without_touching_master() {
    let repo = TestRepo::new();
    let dispatch = git::append_inflight_snapshot(&repo.0, &LedgerSnapshotRequest {
        dispatch: DispatchId("dispatch-response-01".into()),
        plan: PlanId("plan.copy".into()),
        sources: vec![LedgerSource {
            slug: "cnt.one".into(),
            path: "one.md".into(),
            bytes: fs::read(repo.0.join("one.md")).unwrap(),
        }],
    }).unwrap();
    let head_before = output(&repo.0, ["rev-parse", "HEAD"]);
    let status_before = output(&repo.0, ["status", "--porcelain=v1"]);
    let response = b"---\nslug: cnt.one\nstatus: needs-review\nproducer: ai\n---\nResponse\n";

    let commit = git::append_response_snapshot(
        &repo.0,
        "dispatch-response-01",
        "result-one",
        "cnt.one",
        "accepted",
        Path::new("one.md"),
        response,
    ).unwrap();

    assert_eq!(output(&repo.0, ["rev-parse", "HEAD"]), head_before);
    assert_eq!(output(&repo.0, ["status", "--porcelain=v1"]), status_before);
    assert_eq!(output(&repo.0, ["rev-parse", "refs/heads/autoscribe/inflight"]), commit.0);
    assert_eq!(output(&repo.0, ["show", format!("{}:one.md", commit.0).as_str()]), String::from_utf8_lossy(response).trim());
    assert_eq!(output(&repo.0, ["rev-parse", format!("{}^", commit.0).as_str()]), dispatch.commit.0);
}

#[test]
fn config_sync_status_ignores_state_only_commits() {
    let repo = TestRepo::new();
    let plan = serde_json::json!({
        "record_type":"plan",
        "record_identity":"plan.test",
        "payload":{"steps":{"1":{"kind":"script","script":"test"}}}
    });
    let payload_commit = git::config_upsert_json(
        &repo.0,
        "plans",
        "plan.test",
        &plan,
        "AUTOSCRIBE CONFIG plan plan.test",
    ).unwrap();
    git::mark_config_synced(&repo.0, &payload_commit.0).unwrap();
    assert!(git::config_is_synced(&repo.0).unwrap());

    let state_commit = git::config_upsert_json(
        &repo.0,
        "state",
        "control",
        &serde_json::json!({"version":1,"config":{"current":true}}),
        "AUTOSCRIBE CONFIG control state",
    ).unwrap();
    assert_ne!(payload_commit.0, state_commit.0);
    assert!(git::config_is_synced(&repo.0).unwrap());

    let changed = serde_json::json!({
        "record_type":"plan",
        "record_identity":"plan.test",
        "payload":{"steps":{"1":{"kind":"script","script":"different"}}}
    });
    git::config_upsert_json(
        &repo.0,
        "plans",
        "plan.test",
        &changed,
        "AUTOSCRIBE CONFIG update plan.test",
    ).unwrap();
    assert!(!git::config_is_synced(&repo.0).unwrap());
}

#[test]
fn restore_requires_exact_confirmation() {
    let repo = TestRepo::new();
    let source = output(&repo.0, ["rev-parse", "HEAD"]);

    fs::write(repo.0.join("one.md"), "replacement\n").unwrap();
    git::commit(
        &repo.0,
        CommitRequest {
            paths: vec!["one.md".into()],
            message: "Replace one".into(),
            purpose: CommitPurpose::Version,
        },
    )
    .unwrap();
    assert!(matches!(
        git::restore_version(
            &repo.0,
            RestoreRequest {
                version: VersionRequest {
                    path: "one.md".into(),
                    revision: source.clone()
                },
                confirmation: "wrong".into(),
            }
        ),
        Err(ServiceError::InvalidInput(_))
    ));
    let confirmation = format!("RESTORE one.md FROM {source}");
    git::restore_version(
        &repo.0,
        RestoreRequest {
            version: VersionRequest {
                path: "one.md".into(),
                revision: source,
            },
            confirmation,
        },
    )
    .unwrap();
    assert!(
        fs::read_to_string(repo.0.join("one.md"))
            .unwrap()
            .contains("slug: cnt.one")
    );
}

fn run<I, S>(repo: &Path, args: I)
where
    I: IntoIterator<Item = S>,
    S: AsRef<std::ffi::OsStr>,
{
    let result = Command::new("/usr/bin/git")
        .args(args)
        .current_dir(repo)
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
}

fn output<I, S>(repo: &Path, args: I) -> String
where
    I: IntoIterator<Item = S>,
    S: AsRef<std::ffi::OsStr>,
{
    let result = Command::new("/usr/bin/git")
        .args(args)
        .current_dir(repo)
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    String::from_utf8_lossy(&result.stdout).trim().to_string()
}
