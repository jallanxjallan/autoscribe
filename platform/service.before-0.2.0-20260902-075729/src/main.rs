use autoscribe_service::{db, worker::Worker};
use std::{
    env,
    fs::OpenOptions,
    io::Write,
    path::PathBuf,
    process::ExitCode,
    time::Duration,
};

fn main() -> ExitCode {
    let mut args = env::args().skip(1).collect::<Vec<_>>();
    let command = args.first().map(String::as_str).unwrap_or("");
    if !matches!(command, "worker" | "scan") {
        eprintln!("usage: svc worker [--once] <vault>... | svc scan <vault>...");
        return ExitCode::FAILURE;
    }
    args.remove(0);
    let once = command == "scan" || take_flag(&mut args, "--once");
    let vaults = if args.is_empty() {
        env_vaults()
    } else {
        args.into_iter().map(PathBuf::from).collect()
    };
    let asc = env::var_os("AUTOSCRIBE_ASC")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("asc"));
    let poll = env::var("AUTOSCRIBE_WORKER_POLL_MS")
        .ok()
        .and_then(|value| value.parse::<u64>().ok())
        .unwrap_or(2_000);

    let _lock = match WorkerLock::acquire() {
        Ok(lock) => lock,
        Err(error) => {
            eprintln!("svc: {error}");
            return ExitCode::FAILURE;
        }
    };

    match Worker::new(vaults, asc, Duration::from_millis(poll)).and_then(|worker| {
        worker.run(once)?;
        if once {
            println!("{}", db::snapshot(worker.database())?);
        }
        Ok(())
    }) {
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

fn take_flag(args: &mut Vec<String>, flag: &str) -> bool {
    if let Some(index) = args.iter().position(|argument| argument == flag) {
        args.remove(index);
        true
    } else {
        false
    }
}

fn env_vaults() -> Vec<PathBuf> {
    env::var("AUTOSCRIBE_VAULTS")
        .unwrap_or_default()
        .split(':')
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(PathBuf::from)
        .collect()
}
