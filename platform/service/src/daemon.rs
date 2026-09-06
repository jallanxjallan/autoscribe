use crate::{
    ServiceError, ServiceResult,
    db::{self, Database},
    worker::Worker,
};
use std::{
    env, fs,
    io::Write,
    path::{Path, PathBuf},
    process::Command,
    time::{Duration, SystemTime, UNIX_EPOCH},
};

#[derive(Debug, Clone, Copy)]
pub enum DaemonKind {
    Dispatch,
    Responses,
}

impl DaemonKind {
    pub fn label(self) -> &'static str {
        match self {
            Self::Dispatch => "dispatch",
            Self::Responses => "responses",
        }
    }
}

pub fn run(kind: DaemonKind, asc: PathBuf, poll: Duration) -> ServiceResult<()> {
    if poll.is_zero() {
        return Err(ServiceError::InvalidInput(
            "daemon poll interval must be greater than zero".into(),
        ));
    }
    let worker = Worker::create(Database::client()?, asc)?;
    if matches!(kind, DaemonKind::Dispatch) {
        db::recover_attention(worker.database())?;
    }
    let mut responses = ResponseSchedule::default();
    loop {
        let delay = match kind {
            DaemonKind::Dispatch => {
                dispatch_pass(&worker, now_ms)?;
                poll
            }
            DaemonKind::Responses => {
                let result = worker.responses_once();
                if let Err(error) = &result {
                    eprintln!("svc: responses: {error}");
                }
                responses.after_pass(&result)
            }
        };
        std::thread::sleep(delay);
    }
}

fn now_ms() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis()
        .min(i64::MAX as u128) as i64
}

pub(crate) fn dispatch_pass(worker: &Worker, mut clock: impl FnMut() -> i64) -> ServiceResult<()> {
    for attention in db::due_attention(worker.database(), clock())? {
        eprintln!("svc: dispatch: inspecting {}", attention.root.display());
        match worker.dispatch_repository(&attention.root) {
            Ok(()) => db::clear_attention(worker.database(), &attention)?,
            Err(error) => {
                // Construction and reconciliation failures share the same durable retry.
                db::defer_attention(worker.database(), &attention, clock())?;
                eprintln!("svc: dispatch: {}: {error}", attention.root.display());
            }
        }
    }
    Ok(())
}

#[derive(Default)]
struct ResponseSchedule {
    delay_secs: u64,
}

impl ResponseSchedule {
    fn after_pass(&mut self, result: &ServiceResult<bool>) -> Duration {
        self.delay_secs = if matches!(result, Ok(true)) {
            1
        } else {
            self.delay_secs.saturating_mul(2).clamp(1, 30)
        };
        Duration::from_secs(self.delay_secs)
    }
}

pub fn plans_path() -> ServiceResult<PathBuf> {
    let base = env::var_os("XDG_CACHE_HOME")
        .map(PathBuf::from)
        .or_else(|| env::var_os("HOME").map(|home| PathBuf::from(home).join(".cache")))
        .ok_or_else(|| ServiceError::InvalidInput("HOME and XDG_CACHE_HOME are unset".into()))?;
    Ok(base.join("autoscribe/plans.json"))
}

pub fn refresh_plans(asc: &Path) -> ServiceResult<()> {
    let output = Command::new(asc)
        .args(["control", "plans"])
        .output()
        .map_err(|e| ServiceError::Io(e.to_string()))?;
    if !output.status.success() {
        return Err(ServiceError::Storage(format!(
            "asc control plans failed: {}",
            String::from_utf8_lossy(&output.stderr).trim()
        )));
    }
    serde_json::from_slice::<serde_json::Value>(&output.stdout).map_err(|e| {
        ServiceError::InvalidInput(format!("asc control plans did not emit valid JSON: {e}"))
    })?;
    let target = plans_path()?;
    fs::create_dir_all(target.parent().expect("cache path has parent"))
        .map_err(|e| ServiceError::Io(e.to_string()))?;
    let temporary = target.with_extension("json.tmp");
    {
        let mut file = fs::File::create(&temporary).map_err(|e| ServiceError::Io(e.to_string()))?;
        file.write_all(&output.stdout)
            .map_err(|e| ServiceError::Io(e.to_string()))?;
        file.sync_all()
            .map_err(|e| ServiceError::Io(e.to_string()))?;
    }
    fs::rename(&temporary, &target).map_err(|e| ServiceError::Io(e.to_string()))?;
    eprintln!("svc: plans: refreshed {}", target.display());
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn response_idle_and_failure_delays_are_bounded_and_work_resets_delay() {
        let mut schedule = ResponseSchedule::default();
        for expected in [1, 2, 4, 8, 16, 30, 30] {
            assert_eq!(
                schedule.after_pass(&Ok(false)),
                Duration::from_secs(expected)
            );
        }
        assert_eq!(schedule.after_pass(&Ok(true)), Duration::from_secs(1));
        for expected in [2, 4, 8, 16, 30, 30] {
            assert_eq!(
                schedule.after_pass(&Err(ServiceError::Io("offline".into()))),
                Duration::from_secs(expected)
            );
        }
    }
}
