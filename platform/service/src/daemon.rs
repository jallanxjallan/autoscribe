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
    time::Duration,
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
    let database = Database::client()?;
    if matches!(kind, DaemonKind::Dispatch) {
        for root in db::known_repositories(&database)? {
            db::record_attention(&database, &root, None)?;
        }
    }
    loop {
        match kind {
            DaemonKind::Dispatch => dispatch_pass(&database, &asc)?,
            DaemonKind::Responses => responses_pass(&database, &asc),
        }
        std::thread::sleep(poll);
    }
}

fn dispatch_pass(database: &Database, asc: &Path) -> ServiceResult<()> {
    for root in db::pending_repositories(database)? {
        eprintln!("svc: dispatch: inspecting {}", root.display());
        match Worker::persistent(&root, asc.to_path_buf())?.dispatch_once() {
            Ok(()) => db::clear_attention(database, &root)?,
            Err(error) => eprintln!("svc: dispatch: {}: {error}", root.display()),
        }
    }
    Ok(())
}

fn responses_pass(database: &Database, asc: &Path) {
    for root in db::known_repositories(database).unwrap_or_default() {
        if let Err(error) =
            Worker::persistent(&root, asc.to_path_buf()).and_then(|w| w.responses_once())
        {
            eprintln!("svc: responses: {}: {error}", root.display());
        }
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
