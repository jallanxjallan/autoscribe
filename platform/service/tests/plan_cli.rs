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
fn plan_save_persists_authored_records_and_uploads_dependencies_before_plan() {
    let root = temp();
    let database = root.join("service.sqlite");
    let log = root.join("asc.log");
    let asc = root.join("asc");
    fs::write(&asc, format!(
        "#!/bin/sh\nif [ \"$1 $2\" = \"control snapshot\" ]; then printf '%s\\n' '{{\"registries\":{{\"instructions\":{{}},\"plans\":{{}}}}}}'; exit 0; fi\nprintf '%s\\n' \"$1 $2\" >> '{}'\ncat >> '{}.input'\n",
        log.display(), log.display())).unwrap();
    executable(&asc);
    let instruction = json!({"type":"instruction","identity":"tsk.pasted.test","content":"Pasted instruction","extra":{"title":"Pasted","scope":"task"}});
    let plan = json!({"record_type":"plan","record_identity":"plan.paste.test","payload":{"label":"Paste Test","type":"test","description":"","steps":{"1":{"index":1,"kind":"llm","label":"Step 1","engine":"engines.openai","model":"models.test","instruction_slugs":{"standing":[],"role":[],"context":[],"task":["tsk.pasted.test"]}}}}});
    let request =
        json!({"version":1,"database_path":database,"plan":plan,"instructions":[instruction]});
    let output = invoke(&root, &asc, "plan-save", Some(request));
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
    assert_eq!(
        fs::read_to_string(&log).unwrap(),
        "upload instructions\nupload plans\n"
    );
    let connection = Connection::open(&database).unwrap();
    let instructions: i64 = connection
        .query_row("SELECT count(*) FROM authored_instructions", [], |row| {
            row.get(0)
        })
        .unwrap();
    let plans: i64 = connection
        .query_row("SELECT count(*) FROM authored_plans", [], |row| row.get(0))
        .unwrap();
    assert_eq!((instructions, plans), (1, 1));

    let snapshot = invoke(&root, &asc, "define-plan-snapshot", None);
    assert!(snapshot.status.success());
    let response: Value = serde_json::from_slice(&snapshot.stdout).unwrap();
    assert_eq!(
        response["authored_instructions"][0]["identity"],
        "tsk.pasted.test"
    );
    assert_eq!(
        response["authored_plans"][0]["record_identity"],
        "plan.paste.test"
    );
    fs::remove_dir_all(root).unwrap();
}

fn invoke(root: &Path, asc: &Path, command: &str, input: Option<Value>) -> std::process::Output {
    let mut child = Command::new(env!("CARGO_BIN_EXE_svc"))
        .arg(command)
        .env("ASC_BIN", asc)
        .env("AUTOSCRIBE_DATABASE", root.join("service.sqlite"))
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    if let Some(input) = input {
        child
            .stdin
            .take()
            .unwrap()
            .write_all(input.to_string().as_bytes())
            .unwrap();
    }
    child.wait_with_output().unwrap()
}
fn temp() -> PathBuf {
    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let path = std::env::temp_dir().join(format!("autoscribe-plan-cli-{nonce}"));
    fs::create_dir(&path).unwrap();
    path
}
fn executable(path: &Path) {
    use std::os::unix::fs::PermissionsExt;
    let mut permissions = fs::metadata(path).unwrap().permissions();
    permissions.set_mode(0o755);
    fs::set_permissions(path, permissions).unwrap();
}
