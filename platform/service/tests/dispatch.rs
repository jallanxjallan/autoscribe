use autoscribe_service::{
    ServiceError,
    db::{self, Database},
    dispatch,
    events::{self, NoticeSink},
    sync,
    types::{DispatchId, DispatchSource, PlanId, PrepareSavedDispatchRequest},
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
            "autoscribe-dispatch-{}-{unique}",
            std::process::id()
        ));
        fs::create_dir(&path).unwrap();
        run(&path, ["init", "--quiet", "--initial-branch=main"]);
        run(&path, ["config", "user.email", "tests@autoscribe.local"]);
        run(&path, ["config", "user.name", "AutoScribe Tests"]);
        fs::write(path.join("one.md"), "One\n").unwrap();
        fs::write(path.join("two.md"), "Two\n").unwrap();
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

fn database() -> Database {
    let db = Database::open_path(Path::new(":memory:")).unwrap();
    db::migrate(&db).unwrap();
    db
}

#[test]
fn all_clean_dispatch_uses_head_without_creating_source_commit() {
    let repo = TestRepo::new();
    let db = database();
    let before = output(&repo.0, ["rev-parse", "HEAD"]);

    let prepared = dispatch::prepare(&db, &repo.0, request("clean-dispatch")).unwrap();

    assert_eq!(prepared.source_revision.0, before);
    assert!(prepared.committed_paths.is_empty());
    assert_eq!(output(&repo.0, ["branch", "--show-current"]), "main");
    assert_eq!(sync::pending_payloads(&db).unwrap().len(), 1);
    let notices = events::list_since(&NoticeSink::new(&db), 0).unwrap();
    assert_eq!(notices.len(), 2);
}

#[test]
fn mixed_dispatch_commits_only_dirty_selected_files_and_preserves_other_work() {
    let repo = TestRepo::new();
    let db = database();
    fs::write(repo.0.join("one.md"), "One changed\n").unwrap();
    fs::write(repo.0.join("unselected.md"), "leave me alone\n").unwrap();

    let prepared = dispatch::prepare(&db, &repo.0, request("mixed-dispatch")).unwrap();

    assert_eq!(prepared.committed_paths, vec![PathBuf::from("one.md")]);
    assert_eq!(output(&repo.0, ["show", "HEAD:one.md"]), "One changed");
    assert_eq!(output(&repo.0, ["show", "HEAD:two.md"]), "Two");
    assert!(repo.0.join("unselected.md").is_file());
    assert!(
        output(&repo.0, ["status", "--porcelain=v1", "--", "unselected.md"])
            .ends_with("unselected.md")
    );
}

#[test]
fn payload_hash_mismatch_has_no_git_or_sqlite_side_effects() {
    let repo = TestRepo::new();
    let db = database();
    let before = output(&repo.0, ["rev-parse", "HEAD"]);
    let mut request = request("bad-hash");
    request.payload_sha256 = "00".repeat(32);

    assert!(matches!(
        dispatch::prepare(&db, &repo.0, request),
        Err(ServiceError::Conflict(_))
    ));
    assert_eq!(output(&repo.0, ["rev-parse", "HEAD"]), before);
    assert!(sync::pending_payloads(&db).unwrap().is_empty());
}

#[test]
fn sha256_matches_standard_vectors() {
    assert_eq!(
        dispatch::sha256_hex(b""),
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    );
    assert_eq!(
        dispatch::sha256_hex(b"abc"),
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    );
}

fn request(identity: &str) -> PrepareSavedDispatchRequest {
    let payload = b"{\"call\":\"cnt.one\"}\n{\"call\":\"cnt.two\"}\n".to_vec();
    PrepareSavedDispatchRequest {
        dispatch: DispatchId(identity.into()),
        plan: PlanId("plan.copy".into()),
        plan_version: "v1".into(),
        records: vec![
            DispatchSource {
                slug: "cnt.one".into(),
                path: "one.md".into(),
            },
            DispatchSource {
                slug: "cnt.two".into(),
                path: "two.md".into(),
            },
        ],
        payload_sha256: dispatch::sha256_hex(&payload),
        payload,
        commit_message: "Lock selected dispatch sources".into(),
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
