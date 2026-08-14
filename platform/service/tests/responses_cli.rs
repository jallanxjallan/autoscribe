use rusqlite::Connection;
use serde_json::{Value,json};
use std::{fs,io::Write,path::{Path,PathBuf},process::{Command,Stdio},time::{SystemTime,UNIX_EPOCH}};

#[test]
fn pending_response_uses_inflight_lineage_and_accept_commits_then_acknowledges(){
 let root=temp();git(&root,["init","--quiet","--initial-branch=main"]);git(&root,["config","user.email","tests@autoscribe.local"]);git(&root,["config","user.name","AutoScribe Tests"]);
 fs::write(root.join("One.md"),"---\nslug: cnt.one\naction: revise\n---\nOld\n").unwrap();git(&root,["add","One.md"]);git(&root,["commit","--quiet","-m","Initial"]);
 let db=root.join("service.sqlite");let payload="{\"version\":1}\n";let hash=autoscribe_service::dispatch::sha256_hex(payload.as_bytes());
 let prepared=invoke(&root,&root.join("missing-asc"),"dispatch-prepare",json!({"version":1,"database_path":db,"repository_path":root,"dispatch":"run-one","plan":"plan.test","plan_version":"v1","records":[{"slug":"cnt.one","path":"One.md"}],"payload":payload,"payload_sha256":hash,"commit_message":"unused"}));
 assert!(prepared.status.success(),"{}",String::from_utf8_lossy(&prepared.stdout));
 let asc=fake_asc(&root);let snapshot=invoke(&root,&asc,"responses-snapshot",json!({"version":1,"database_path":db,"repository_path":root}));
 assert!(snapshot.status.success(),"{}",String::from_utf8_lossy(&snapshot.stdout));let response:Value=serde_json::from_slice(&snapshot.stdout).unwrap();assert_eq!(response["responses"][0]["dispatch_identity"],"run-one");
 let replacement="---\nslug: cnt.one\naction: human-review\n---\nNew\n";let decision=invoke(&root,&asc,"response-decide",json!({"version":1,"database_path":db,"repository_path":root,"result_identity":"call.one","source_identity":"cnt.one","source_path":"One.md","outcome":"accepted","replacement_text":replacement}));
 assert!(decision.status.success(),"{}",String::from_utf8_lossy(&decision.stdout));assert_eq!(fs::read_to_string(root.join("One.md")).unwrap(),replacement);assert_eq!(fs::read_to_string(root.join("asc.log")).unwrap(),"export extract-pending\nexport update-exports call.one\n");
 let connection=Connection::open(&db).unwrap();let count:i64=connection.query_row("SELECT count(*) FROM response_records WHERE result_identity='call.one'",[],|row|row.get(0)).unwrap();assert_eq!(count,0);
 let ledger=git_output(&root,["show","-s","--format=%B","autoscribe/inflight"]);assert!(ledger.contains("AUTOSCRIBE RESPONSE accepted"));assert!(ledger.contains("Result: call.one"));assert!(ledger.contains("Outcome: accepted"));
 let finalized=invoke(&root,&asc,"dispatch-finalize",json!({"version":1,"database_path":db,"repository_path":root,"dispatch_identity":"run-one","outcome":"completed","reason":null}));assert!(finalized.status.success(),"{}",String::from_utf8_lossy(&finalized.stdout));
 let remaining:i64=connection.query_row("SELECT count(*) FROM inflight_dispatches WHERE dispatch_identity='run-one'",[],|row|row.get(0)).unwrap();assert_eq!(remaining,0);let terminal=git_output(&root,["show","-s","--format=%B","autoscribe/inflight"]);assert!(terminal.contains("AUTOSCRIBE DISPATCH completed"));fs::remove_dir_all(root).unwrap();
}
fn invoke(root:&Path,asc:&Path,command:&str,input:Value)->std::process::Output{let mut child=Command::new(env!("CARGO_BIN_EXE_svc")).arg(command).env("ASC_BIN",asc).current_dir(root).stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped()).spawn().unwrap();child.stdin.take().unwrap().write_all(input.to_string().as_bytes()).unwrap();child.wait_with_output().unwrap()}
fn fake_asc(root:&Path)->PathBuf{let path=root.join("asc");fs::write(&path,format!("#!/bin/sh\nprintf '%s\\n' \"$*\" >> '{}'\nif [ \"$1 $2\" = \"export extract-pending\" ]; then printf '%s\\n' '{{\"identity\":\"call.one\",\"source_identity\":\"cnt.one\",\"record_content\":\"New\"}}'; fi\n",root.join("asc.log").display())).unwrap();executable(&path);path}
fn temp()->PathBuf{let n=SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos();let path=std::env::temp_dir().join(format!("autoscribe-responses-{n}"));fs::create_dir(&path).unwrap();path}
fn executable(path:&Path){use std::os::unix::fs::PermissionsExt;let mut p=fs::metadata(path).unwrap().permissions();p.set_mode(0o755);fs::set_permissions(path,p).unwrap();}
fn git<I,S>(repo:&Path,args:I)where I:IntoIterator<Item=S>,S:AsRef<std::ffi::OsStr>{assert!(Command::new("/usr/bin/git").args(args).current_dir(repo).status().unwrap().success());}
fn git_output<I,S>(repo:&Path,args:I)->String where I:IntoIterator<Item=S>,S:AsRef<std::ffi::OsStr>{let output=Command::new("/usr/bin/git").args(args).current_dir(repo).output().unwrap();assert!(output.status.success());String::from_utf8_lossy(&output.stdout).into_owned()}
