use autoscribe_service::{dispatch::sha256_hex, instruction_sync};
use serde_json::json;
use std::{fs, io::Write, path::PathBuf, process::{Command, Stdio}, time::{SystemTime, UNIX_EPOCH}};

#[test]
fn timestamps_short_circuit_and_uncertain_rows_fall_back_to_hashes(){
 let root=temp();fs::create_dir(root.join("tasks")).unwrap();
 fs::write(root.join("tasks/One.md"),"---\ntitle: One\nslug: tsk.one\ntype: instruction\n---\nOne body\n").unwrap();
 fs::write(root.join("tasks/Two.md"),"---\ntitle: Two\nslug: tsk.two\ntype: instruction\n---\nTwo body\n").unwrap();
 fs::write(root.join("Dashboard.md"),"# Not an instruction\n").unwrap();
 let local=instruction_sync::scan(&root).unwrap();assert_eq!(local.len(),2);
 let one=local.iter().find(|item|item.slug=="tsk.one").unwrap();let two=local.iter().find(|item|item.slug=="tsk.two").unwrap();
 let manifest=json!({"instructions":{
   "tsk.one":{"source_modified_ns":one.modified_ns.to_string(),"source_size":one.size.to_string(),"content_sha256":"unused"},
   "tsk.two":{"source_modified_ns":"1","source_size":"1","content_sha256":sha256_hex(two.body.trim().as_bytes())}
 }});
 let plan=instruction_sync::plan(local,&manifest).unwrap();assert_eq!(plan.upload.len(),0);assert_eq!(plan.hashes_compared,1);
 assert!(plan.items.iter().any(|item|item.slug=="tsk.one"&&item.reason=="timestamp and size match"));
 assert!(plan.items.iter().any(|item|item.slug=="tsk.two"&&item.reason=="content hash matches"));
 fs::remove_dir_all(root).unwrap();
}

#[test]
fn changed_and_missing_instructions_are_uploaded(){
 let root=temp();fs::write(root.join("Changed.md"),"---\nslug: tsk.changed\ntype: instruction\n---\nChanged\n").unwrap();
 fs::write(root.join("Missing.md"),"---\nslug: tsk.missing\ntype: instruction\n---\nMissing\n").unwrap();
 let plan=instruction_sync::plan(instruction_sync::scan(&root).unwrap(),&json!({"instructions":{"tsk.changed":{"source_modified_ns":"1","source_size":"1","content_sha256":"00"}}})).unwrap();
 assert_eq!(plan.upload.len(),2);assert_eq!(plan.hashes_compared,1);fs::remove_dir_all(root).unwrap();
}

#[test]
fn missing_server_instruction_is_reuploaded_without_consulting_prior_state(){
 let root=temp();
 fs::write(root.join("Expired.md"),"---\nslug: global.expired\ntype: instruction\n---\nStill authoritative locally\n").unwrap();
 let plan=instruction_sync::plan(
   instruction_sync::scan(&root).unwrap(),
   &json!({"instructions":{}}),
 ).unwrap();
 assert_eq!(plan.upload.len(),1);
 assert_eq!(plan.upload[0].slug,"global.expired");
 assert_eq!(plan.hashes_compared,0);
 assert!(plan.items.iter().any(|item|
   item.slug=="global.expired"&&item.status=="upload"&&item.reason=="missing remotely"
 ));
 fs::remove_dir_all(root).unwrap();
}

#[test]
fn service_sync_uploads_only_selected_instruction_paths(){
 let root=temp();
 fs::write(root.join("One.md"),"---\nslug: tsk.one\ntype: instruction\n---\nOne\n").unwrap();
 fs::write(root.join("Two.md"),"---\nslug: tsk.two\ntype: instruction\n---\nTwo\n").unwrap();
 let asc=root.join("asc");let log=root.join("asc.input");
 fs::write(&asc,format!("#!/bin/sh\nif [ \"$1 $2\" = \"control instruction-manifest\" ]; then printf '%s\\n' '{{\"instructions\":{{}}}}'; exit 0; fi\ncat >> '{}'\n",log.display())).unwrap();
 executable(&asc);
 let request=json!({"version":1,"root":root,"paths":["One.md"]});
 let mut child=Command::new(env!("CARGO_BIN_EXE_svc")).arg("instructions-sync").env("ASC_BIN",&asc)
   .stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped()).spawn().unwrap();
 child.stdin.take().unwrap().write_all(request.to_string().as_bytes()).unwrap();
 let output=child.wait_with_output().unwrap();
 assert!(output.status.success(),"{}",String::from_utf8_lossy(&output.stderr));
 let response:serde_json::Value=serde_json::from_slice(&output.stdout).unwrap();
 assert_eq!(response["selected"],1);assert_eq!(response["uploaded"],1);
 let uploaded=fs::read_to_string(&log).unwrap();assert!(uploaded.contains("tsk.one"));assert!(!uploaded.contains("tsk.two"));
 fs::remove_dir_all(root).unwrap();
}
fn temp()->PathBuf{let n=SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos();let path=std::env::temp_dir().join(format!("autoscribe-instruction-sync-{n}"));fs::create_dir(&path).unwrap();path}
fn executable(path:&std::path::Path){use std::os::unix::fs::PermissionsExt;let mut p=fs::metadata(path).unwrap().permissions();p.set_mode(0o755);fs::set_permissions(path,p).unwrap();}
