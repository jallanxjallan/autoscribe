use serde_json::{json, Value};
use std::{fs, io::Write, path::{Path, PathBuf}, process::{Command, Stdio}, time::{SystemTime, UNIX_EPOCH}};

#[test]
fn git_files_inspect_commit_stash_and_restore_are_owned_by_service() {
    let root = repo();
    fs::write(root.join("one.md"), "changed\n").unwrap();
    let inspected = call(&root, json!({"version":1,"repository_path":root,"action":"inspect","paths":["one.md"]}));
    assert_eq!(inspected["items"][0]["committable"], true);
    let committed = call(&root, json!({"version":1,"repository_path":root,"action":"commit","paths":["one.md"],"message":"Editorial draft","purpose":"version"}));
    assert!(committed["commit"]["hash"].as_str().unwrap().len() >= 40);

    fs::write(root.join("one.md"), "temporary\n").unwrap();
    let stash = call(&root, json!({"version":1,"repository_path":root,"action":"stash-create","path":"one.md"}));
    let id = stash["item"]["id"].as_str().unwrap();
    fs::write(root.join("one.md"), "changed\n").unwrap();
    call(&root, json!({"version":1,"repository_path":root,"action":"stash-restore","path":"one.md","id":id}));
    assert_eq!(fs::read_to_string(root.join("one.md")).unwrap(), "temporary\n");
    fs::remove_dir_all(root).unwrap();
}

fn call(_root: &Path, request: Value) -> Value {
    let mut child = Command::new(env!("CARGO_BIN_EXE_svc")).arg("git-files")
        .stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped()).spawn().unwrap();
    child.stdin.take().unwrap().write_all(request.to_string().as_bytes()).unwrap();
    let output = child.wait_with_output().unwrap();
    assert!(output.status.success(), "{}", String::from_utf8_lossy(&output.stdout));
    serde_json::from_slice(&output.stdout).unwrap()
}
fn repo() -> PathBuf {
    let n = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos();
    let root = std::env::temp_dir().join(format!("autoscribe-git-files-{n}"));
    fs::create_dir(&root).unwrap();
    for args in [["init","--quiet","--initial-branch=main"], ["config","user.email","tests@autoscribe.local"], ["config","user.name","AutoScribe Tests"]] {
        assert!(Command::new("/usr/bin/git").args(args).current_dir(&root).status().unwrap().success());
    }
    fs::write(root.join("one.md"), "initial\n").unwrap();
    assert!(Command::new("/usr/bin/git").args(["add","one.md"]).current_dir(&root).status().unwrap().success());
    assert!(Command::new("/usr/bin/git").args(["commit","--quiet","-m","Initial"]).current_dir(&root).status().unwrap().success());
    root
}
