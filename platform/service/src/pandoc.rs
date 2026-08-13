use crate::{ServiceError, ServiceResult, types::*};
use std::{
    process::Command,
    sync::{
        Arc, Mutex,
        atomic::{AtomicUsize, Ordering},
    },
    thread,
};

/// Run a batch of independent Pandoc operations concurrently.
///
/// Results retain input order even though subprocesses finish out of order.
/// A failed Pandoc invocation is returned as an outcome so that one bad
/// document does not discard successful work from the rest of the batch.
pub fn run_parallel(
    executable: &std::path::Path,
    jobs: Vec<PandocJob>,
    max_parallel: usize,
) -> ServiceResult<Vec<PandocOutcome>> {
    if !executable.is_absolute() {
        return Err(ServiceError::InvalidInput(
            "Pandoc executable must be an absolute path".into(),
        ));
    }
    if jobs.len() > 1 && max_parallel < 2 {
        return Err(ServiceError::InvalidInput(
            "Pandoc batches require parallelism of at least two".into(),
        ));
    }
    if jobs.is_empty() {
        return Ok(Vec::new());
    }
    if let Some(job) = jobs.iter().find(|job| !job.working_directory.is_absolute()) {
        return Err(ServiceError::InvalidInput(format!(
            "Pandoc job {} requires an absolute working directory",
            job.identity
        )));
    }

    let worker_count = jobs.len().min(max_parallel.max(1));
    let jobs = Arc::new(jobs);
    let next = Arc::new(AtomicUsize::new(0));
    let outcomes = Arc::new(Mutex::new(
        std::iter::repeat_with(|| None)
            .take(jobs.len())
            .collect::<Vec<Option<PandocOutcome>>>(),
    ));

    thread::scope(|scope| {
        for _ in 0..worker_count {
            let jobs = Arc::clone(&jobs);
            let next = Arc::clone(&next);
            let outcomes = Arc::clone(&outcomes);
            scope.spawn(move || loop {
                let index = next.fetch_add(1, Ordering::Relaxed);
                let Some(job) = jobs.get(index) else { break };
                let outcome = execute(executable, job);
                outcomes.lock().expect("Pandoc result lock poisoned")[index] = Some(outcome);
            });
        }
    });

    let mut guard = outcomes
        .lock()
        .map_err(|_| ServiceError::Io("Pandoc result lock poisoned".into()))?;
    guard
        .drain(..)
        .map(|outcome| outcome.ok_or_else(|| ServiceError::Io("Pandoc worker returned no result".into())))
        .collect()
}

fn execute(executable: &std::path::Path, job: &PandocJob) -> PandocOutcome {
    let output = Command::new(executable)
        .current_dir(&job.working_directory)
        .args(&job.arguments)
        .output();

    match output {
        Ok(output) => PandocOutcome {
            identity: job.identity.clone(),
            exit_code: output.status.code(),
            stdout: output.stdout,
            stderr: output.stderr,
            error: None,
        },
        Err(error) => PandocOutcome {
            identity: job.identity.clone(),
            exit_code: None,
            stdout: Vec::new(),
            stderr: Vec::new(),
            error: Some(error.to_string()),
        },
    }
}
