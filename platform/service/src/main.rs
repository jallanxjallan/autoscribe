use autoscribe_service::{attention, db, worker::Worker};
use std::{
    env,
    fs::OpenOptions,
    io::Write,
    path::PathBuf,
    process::ExitCode,
    time::Duration,
};

fn main() -> ExitCode {
    let mut args = env::args().skip(1);
    let command = args.next().unwrap_or_default();
    let repositories = args.map(PathBuf::from).collect::<Vec<_>>();

    if command == "attention" {
        return match attention::send(&repositories) {
            Ok(()) => ExitCode::SUCCESS,
            Err(error) => {
                eprintln!("svc: {error}");
                ExitCode::FAILURE
            }
        };
    }
    if !matches!(command.as_str(), "worker" | "scan")
        || (command == "worker" && !repositories.is_empty())
    {
        eprintln!("usage: svc worker | svc attention <repository>... | svc scan <repository>...");
        return ExitCode::FAILURE;
    }
    let asc = env::var_os("AUTOSCRIBE_ASC")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("asc"));
    let poll = env::var("AUTOSCRIBE_WORKER_POLL_MS")
        .ok()
        .and_then(|value| value.parse::<u64>().ok())
        .unwrap_or(2_000);
    let repository_ttl = env::var("AUTOSCRIBE_REPOSITORY_TTL_SECS")
        .ok()
        .and_then(|value| value.parse::<u64>().ok())
        .unwrap_or(3_600);

    let _lock = match WorkerLock::acquire() {
        Ok(lock) => lock,
        Err(error) => {
            eprintln!("svc: {error}");
            return ExitCode::FAILURE;
        }
    };

    let result = if command == "worker" {
        Worker::system(
            asc,
            Duration::from_millis(poll),
            Duration::from_secs(repository_ttl),
        )
        .and_then(|worker| worker.run(false))
    } else {
        Worker::diagnostic(repositories, asc).and_then(|worker| {
            worker.run(true)?;
            println!("{}", db::snapshot(worker.database())?);
            Ok(())
        })
    };

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
    fn acquire() -> Result<Self, String> {
        let directory = env::var_os("XDG_RUNTIME_DIR")
            .map(PathBuf::from)
            .unwrap_or_else(env::temp_dir);
        let path = directory.join("autoscribe-system-worker.pid");
        loop {
            match OpenOptions::new().write(true).create_new(true).open(&path) {
                Ok(mut file) => {
                    writeln!(file, "{}", std::process::id()).map_err(|error| error.to_string())?;
                    return Ok(Self { path });
                }
                Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {
                    let pid = std::fs::read_to_string(&path)
                        .ok()
                        .and_then(|value| value.trim().parse::<u32>().ok());
                    if pid.is_some_and(|pid| PathBuf::from(format!("/proc/{pid}")).exists()) {
                        return Err(format!(
                            "system worker is already running with pid {}",
                            pid.unwrap()
                        ));
                    }
                    std::fs::remove_file(&path).map_err(|error| error.to_string())?;
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
