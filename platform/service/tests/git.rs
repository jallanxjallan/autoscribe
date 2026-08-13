use autoscribe_service::{
    ServiceError, git,
    types::{
        CommitPurpose, CommitRequest, CreateDispatchBranchRequest, DispatchId, DispatchSource,
        PlanId, RestoreRequest, TagRequest, VersionRequest,
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
fn dispatch_branch_is_reproducible_idempotent_and_does_not_switch_user_branch() {
    let repo = TestRepo::new();
    let source = output(&repo.0, ["rev-parse", "HEAD"]);
    let request = dispatch_request(&source, "hash-one");

    let created = git::create_dispatch_branch(&repo.0, &request).unwrap();
    assert_eq!(created.name, "autoscribe/run/dispatch-01");
    assert_eq!(output(&repo.0, ["branch", "--show-current"]), "main");
    assert_eq!(
        output(
            &repo.0,
            ["rev-parse", format!("{}^", created.commit.0).as_str()]
        ),
        source
    );
    let message = output(
        &repo.0,
        ["show", "-s", "--format=%B", created.commit.0.as_str()],
    );
    assert!(message.contains("Payload-SHA256: hash-one"));
    assert!(message.contains("Record: cnt.one\tone.md"));

    assert_eq!(
        git::create_dispatch_branch(&repo.0, &request).unwrap(),
        created
    );
    assert!(matches!(
        git::create_dispatch_branch(&repo.0, &dispatch_request(&source, "hash-two")),
        Err(ServiceError::Conflict(_))
    ));
}

#[test]
fn tags_are_idempotent_and_restore_requires_exact_confirmation() {
    let repo = TestRepo::new();
    let source = output(&repo.0, ["rev-parse", "HEAD"]);
    let branch =
        git::create_dispatch_branch(&repo.0, &dispatch_request(&source, "hash-one")).unwrap();
    let tag_request = TagRequest {
        commit: branch.commit,
        plan: PlanId("plan.copy.v1".into()),
        dispatch: DispatchId("dispatch-01".into()),
    };
    assert_eq!(
        git::tag_dispatch(&repo.0, tag_request.clone()).unwrap(),
        "autoscribe/dispatch/dispatch-01"
    );
    assert_eq!(
        git::tag_dispatch(&repo.0, tag_request).unwrap(),
        "autoscribe/dispatch/dispatch-01"
    );

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

fn dispatch_request(source: &str, hash: &str) -> CreateDispatchBranchRequest {
    CreateDispatchBranchRequest {
        dispatch: DispatchId("dispatch-01".into()),
        source_revision: source.into(),
        source_branch: "main".into(),
        plan: PlanId("plan.copy".into()),
        plan_version: "v1".into(),
        records: vec![DispatchSource {
            slug: "cnt.one".into(),
            path: "one.md".into(),
        }],
        payload_sha256: hash.into(),
    }
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
