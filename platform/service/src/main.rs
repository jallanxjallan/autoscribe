use autoscribe_service::{
    daemon::{self, DaemonKind},
    db::{self, Database},
    git,
    worker::Worker,
};
use std::{env, fs::OpenOptions, io::Write, path::PathBuf, process::ExitCode, time::Duration};

fn main() -> ExitCode {
    let mut args = env::args().skip(1);
    let command = args.next().unwrap_or_default();
    let repositories = args.map(PathBuf::from).collect::<Vec<_>>();

    if command == "post-commit" && repositories.len() == 1 {
        let root = match git::root(&repositories[0]) {
            Ok(root) => root,
            Err(_) => return ExitCode::SUCCESS,
        };
        let head = git::head(&root).ok();
        let result = Database::client().and_then(|database| {
            db::record_attention(&database, &root, head.as_ref().map(|v| v.0.as_str()))
        });
        if let Err(error) = result {
            eprintln!("svc: post-commit: {error}");
        }
        return ExitCode::SUCCESS;
    }

    let asc = env::var_os("AUTOSCRIBE_ASC")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("asc"));
    let poll = env::var("AUTOSCRIBE_WORKER_POLL_MS")
        .ok()
        .and_then(|v| v.parse::<u64>().ok())
        .unwrap_or(250);

    if command == "plans" && repositories.is_empty() {
        return finish(daemon::refresh_plans(&asc));
    }

    let daemon_kind = match command.as_str() {
        "dispatch" => Some(DaemonKind::Dispatch),
        "responses" => Some(DaemonKind::Responses),
        _ => None,
    };
    if let Some(kind) = daemon_kind {
        if !repositories.is_empty() {
            return usage();
        }
        let _lock = match WorkerLock::acquire(kind.label()) {
            Ok(lock) => lock,
            Err(error) => {
                eprintln!("svc: {error}");
                return ExitCode::FAILURE;
            }
        };
        return finish(daemon::run(kind, asc, Duration::from_millis(poll)));
    }

    // Keep diagnostic scan during the transition; the old monolithic `worker`
    // command is intentionally retired so systemd cannot silently run both designs.
    if command == "scan" && !repositories.is_empty() {
        return finish(Worker::diagnostic(repositories, asc).and_then(|worker| {
            worker.run(true)?;
            println!("{}", db::snapshot(worker.database())?);
            Ok(())
        }));
    }

    if command == "dispatch-once" && repositories.len() == 1 {
        return finish(
            Worker::persistent(&repositories[0], asc).and_then(|worker| worker.dispatch_once()),
        );
    }

    if command == "status" && repositories.is_empty() {
        return finish(Database::client().and_then(|database| {
            println!("{}", db::snapshot(&database)?);
            Ok(())
        }));
    }

    usage()
}

fn usage() -> ExitCode {
    eprintln!(
        "usage: svc post-commit <repository> | svc dispatch | svc responses | svc plans | svc dispatch-once <repository> | svc status | svc scan <repository>..."
    );
    ExitCode::FAILURE
}

fn finish(result: autoscribe_service::ServiceResult<()>) -> ExitCode {
    match result {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("svc: {error}");
            ExitCode::FAILURE
        }
    }
}

struct WorkerLock {
    path: PathBuf,
}
impl WorkerLock {
    fn acquire(name: &str) -> Result<Self, String> {
        let directory = env::var_os("XDG_RUNTIME_DIR")
            .map(PathBuf::from)
            .unwrap_or_else(env::temp_dir);
        let path = directory.join(format!("autoscribe-{name}.pid"));
        loop {
            match OpenOptions::new().write(true).create_new(true).open(&path) {
                Ok(mut file) => {
                    writeln!(file, "{}", std::process::id()).map_err(|e| e.to_string())?;
                    return Ok(Self { path });
                }
                Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {
                    let pid = std::fs::read_to_string(&path)
                        .ok()
                        .and_then(|v| v.trim().parse::<u32>().ok());
                    if pid.is_some_and(|pid| PathBuf::from(format!("/proc/{pid}")).exists()) {
                        return Err(format!(
                            "{name} daemon is already running with pid {}",
                            pid.unwrap()
                        ));
                    }
                    std::fs::remove_file(&path).map_err(|e| e.to_string())?;
                }
                Err(error) => return Err(error.to_string()),
            }
        }
    }
}
impl Drop for WorkerLock {
    fn drop(&mut self) {
        let _ = std::fs::remove_file(&self.path);
    }
}
