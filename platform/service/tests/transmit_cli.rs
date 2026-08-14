use autoscribe_service::{
    db::{self, Database},
    dispatch, sync,
    types::{DispatchId, SavedPayload},
};
use serde_json::json;
use std::{
    fs,
    path::Path,
    process::Command,
    time::{SystemTime, UNIX_EPOCH},
};

#[test]
fn transmit_streams_saved_records_and_acknowledges_only_after_both_commands() {
    let root = temp("success");
    let database = root.join("service.sqlite");
    let log = root.join("asc.log");
    let fake = root.join("asc");
    fs::write(
        &fake,
        format!(
            "#!/bin/sh\nprintf '%s\\n' \"$*\" >> '{}'\nif [ \"$1 $2\" = \"run status\" ]; then printf '%s\\n' '  worker=running pid=123'; exit 0; fi\ncat >> '{}'.input\n",
            log.display(),
            log.display()
        ),
    )
    .unwrap();
    executable(&fake);
    save(&database, "run-success");
    let output = Command::new(env!("CARGO_BIN_EXE_svc"))
        .args(["dispatch-transmit", "run-success"])
        .env("AUTOSCRIBE_DATABASE", &database)
        .env("ASC_BIN", &fake)
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let response: serde_json::Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(response["state"], "acknowledged");
    assert_eq!(fs::read_to_string(&log).unwrap(), "upload calls\nenqueue\nrun status\n");
    let db = Database::open_path(&database).unwrap();
    db::migrate(&db).unwrap();
    assert!(sync::pending_payloads(&db).unwrap().is_empty());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn started_failure_becomes_uncertain_and_is_not_automatically_pending() {
    let root = temp("failure");
    let database = root.join("service.sqlite");
    let fake = root.join("asc");
    fs::write(&fake, "#!/bin/sh\nexit 9\n").unwrap();
    executable(&fake);
    save(&database, "run-failure");
    let output = Command::new(env!("CARGO_BIN_EXE_svc"))
        .args(["dispatch-transmit", "run-failure"])
        .env("AUTOSCRIBE_DATABASE", &database)
        .env("ASC_BIN", &fake)
        .output()
        .unwrap();
    assert!(!output.status.success());
    let db = Database::open_path(&database).unwrap();
    db::migrate(&db).unwrap();
    assert!(sync::pending_payloads(&db).unwrap().is_empty());
    let status = sync::status(&db).unwrap();
    assert_eq!(status.uncertain_outbound, 1);
    fs::remove_dir_all(root).unwrap();
}

fn save(path: &Path, identity: &str) {
    let payload = serde_json::to_vec(&json!({"version":1,"calls":[{"type":"call","identity":"cnt.one","content":"Body","extra":{}}],"enqueue":[{"call":"cnt.one","plan":"plan.test"}]})).unwrap();
    let db = Database::open_path(path).unwrap();
    db::migrate(&db).unwrap();
    sync::enqueue(
        &db,
        &SavedPayload {
            dispatch_id: DispatchId(identity.into()),
            sha256: dispatch::sha256_hex(&payload),
            bytes: payload,
        },
    )
    .unwrap();
}
fn temp(label: &str) -> std::path::PathBuf {
    let n = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let p = std::env::temp_dir().join(format!("autoscribe-transmit-{label}-{n}"));
    fs::create_dir(&p).unwrap();
    p
}
fn executable(path: &Path) {
    use std::os::unix::fs::PermissionsExt;
    let mut p = fs::metadata(path).unwrap().permissions();
    p.set_mode(0o755);
    fs::set_permissions(path, p).unwrap();
}
