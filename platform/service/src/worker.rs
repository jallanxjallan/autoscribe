use crate::{
    ServiceError, ServiceResult,
    db::{self, Database},
    git, pandoc,
    types::{DispatchId, LedgerSnapshotRequest, LedgerSource, PandocJob, PlanId, VersionRequest},
};
use serde_json::Value;
use std::{
    cell::RefCell,
    collections::{BTreeMap, BTreeSet},
    fs::{File, OpenOptions},
    io::Write,
    path::{Path, PathBuf},
    process::{Command, Stdio},
    sync::atomic::{AtomicU64, Ordering},
};

#[derive(Debug)]
pub struct Worker {
    db: Database,
    repositories: RefCell<BTreeMap<PathBuf, RepositorySession>>,
    asc: PathBuf,
    pandoc: PathBuf,
    pandoc_dispatch_defaults: PathBuf,
}

#[derive(Debug)]
struct RepositorySession {
    initialized: bool,
}

#[derive(Debug)]
struct ScannedFile {
    path: PathBuf,
    slug: Option<String>,
    blob: Option<String>,
}

#[derive(Debug)]
struct DispatchTrailers {
    plan: Option<String>,
    documents: Vec<String>,
}

impl Worker {
    /// Create an isolated one-pass diagnostic worker.
    pub fn diagnostic(repositories: Vec<PathBuf>, asc: PathBuf) -> ServiceResult<Self> {
        if repositories.is_empty() {
            return Err(ServiceError::InvalidInput(
                "scan requires at least one repository path".into(),
            ));
        }
        let worker = Self::create(Database::memory()?, asc)?;
        for path in repositories {
            worker.register_repository(&path)?;
        }
        Ok(worker)
    }

    pub(crate) fn create(db: Database, asc: PathBuf) -> ServiceResult<Self> {
        Ok(Self {
            db,
            repositories: RefCell::new(BTreeMap::new()),
            asc,
            pandoc: std::env::var_os("AUTOSCRIBE_PANDOC")
                .map(PathBuf::from)
                .unwrap_or_else(|| PathBuf::from("pandoc")),
            pandoc_dispatch_defaults: std::env::var_os("AUTOSCRIBE_PANDOC_DISPATCH_DEFAULTS")
                .map(PathBuf::from)
                .unwrap_or_else(|| PathBuf::from("dispatch.yaml")),
        })
    }

    /// Create a one-repository worker using the central client ledger.
    pub fn persistent(repository: &Path, asc: PathBuf) -> ServiceResult<Self> {
        let worker = Self::create(Database::client()?, asc)?;
        worker.register_repository(repository)?;
        Ok(worker)
    }

    pub(crate) fn dispatch_repository(&self, repository: &Path) -> ServiceResult<()> {
        let root = self.register_repository(repository)?;
        self.scan_registered(&root)?;
        self.reconcile_dispatches(&root)
    }

    pub fn dispatch_once(&self) -> ServiceResult<()> {
        for root in self.repository_paths() {
            self.dispatch_repository(&root)?;
        }
        Ok(())
    }

    /// Query exports once globally; no repository work while the result is empty.
    pub fn responses_once(&self) -> ServiceResult<bool> {
        let ready = pending_export_slugs(&self.asc)?;
        db::replace_export_ready(&self.db, ready.iter())?;
        if ready.is_empty() {
            return Ok(false);
        }
        let mut failed_roots = BTreeSet::new();
        let mut failure = None;
        // Refresh routes only when there is response work. Keep duplicate-slug
        // checks across the registry; a stale/missing root never routes a write.
        let roots = db::known_repositories(&self.db)?
            .into_iter()
            .chain(self.repository_paths())
            .collect::<BTreeSet<_>>();
        for root in roots {
            if let Err(error) = self
                .register_repository(&root)
                .and_then(|root| self.scan_registered(&root))
            {
                eprintln!("svc: responses: {}: {error}", root.display());
                failed_roots.insert(root);
                failure = Some(error);
            }
        }
        for slug in ready {
            let result = self.reconcile_export(&slug, &failed_roots);
            if let Err(error) = result {
                eprintln!("svc: responses: {slug}: {error}");
                failure = Some(error);
            }
        }
        match failure {
            Some(error) => Err(error),
            None => Ok(true),
        }
    }

    pub fn register_repository(&self, path: &Path) -> ServiceResult<PathBuf> {
        if self.repositories.borrow().contains_key(path) {
            return Ok(path.to_path_buf());
        }
        let root = git::root(path)?;
        let previously_seen = db::latest_repository_head(&self.db, &root)?.is_some();
        self.repositories
            .borrow_mut()
            .entry(root.clone())
            .or_insert(RepositorySession {
                initialized: previously_seen,
            });
        Ok(root)
    }

    pub fn database(&self) -> &Database {
        &self.db
    }

    pub fn startup(&self) -> ServiceResult<()> {
        db::worker_event(&self.db, "started", None)?;
        self.dispatch_once()?;
        self.responses_once()?;
        Ok(())
    }

    fn repository_paths(&self) -> Vec<PathBuf> {
        self.repositories.borrow().keys().cloned().collect()
    }

    fn scan_registered(&self, repository: &Path) -> ServiceResult<()> {
        let startup = self
            .repositories
            .borrow()
            .get(repository)
            .is_some_and(|session| !session.initialized);
        self.scan_repository(repository, startup)?;
        if let Some(session) = self.repositories.borrow_mut().get_mut(repository) {
            session.initialized = true;
        }
        for (slug, copies) in db::duplicate_slugs(&self.db)? {
            if !db::integrity_event_seen(&self.db, "duplicate_slug", Some(&slug), None, None)? {
                db::integrity_event(
                    &self.db,
                    "duplicate_slug",
                    Some(&slug),
                    None,
                    None,
                    &format!("{copies} active copies"),
                )?;
            }
        }
        Ok(())
    }

    fn scan_repository(&self, repository: &Path, startup: bool) -> ServiceResult<()> {
        let head = git::head(repository)?.0;
        if startup {
            let scanned = scan_markdown(repository)?;
            for item in &scanned {
                db::file_seen(
                    &self.db,
                    repository,
                    &item.path,
                    item.slug.as_deref(),
                    item.blob.as_deref(),
                )?;
            }
            self.missing_slug_neighbors(repository, &scanned)?;
            db::repository_event(&self.db, repository, "startup_observed", Some(&head), None)?;
            return Ok(());
        }

        let previous_head = db::latest_repository_head(&self.db, repository)?;
        let mut changed = dirty_markdown_paths(repository)?;
        if previous_head.as_deref() != Some(head.as_str()) {
            if let Some(previous) = previous_head.as_deref() {
                changed.extend(changed_markdown_paths(repository, previous, &head)?);
            } else {
                changed.extend(scan_markdown(repository)?.into_iter().map(|item| item.path));
            }
        }

        let previous = db::active_files(&self.db, repository)?
            .into_iter()
            .map(|(path, slug, blob)| (path, (slug, blob)))
            .collect::<BTreeMap<_, _>>();

        for path in changed {
            let absolute = repository.join(&path);
            if !absolute.is_file() {
                if previous.contains_key(&path) {
                    db::file_removed(&self.db, repository, &path)?;
                }
                continue;
            }
            let bytes = std::fs::read(&absolute).map_err(io)?;
            let text = String::from_utf8_lossy(&bytes);
            let slug = frontmatter_slug(&text);
            let blob = git_blob(repository, &path).ok();
            let prior = previous.get(&path);
            let changed_value = prior
                .map(|(old_slug, old_blob)| {
                    old_slug.as_deref() != slug.as_deref() || old_blob.as_deref() != blob.as_deref()
                })
                .unwrap_or(true);
            if changed_value {
                db::file_seen(
                    &self.db,
                    repository,
                    &path,
                    slug.as_deref(),
                    blob.as_deref(),
                )?;
                if let Some(slug) = slug.as_deref() {
                    self.once_only_duplicate_check(repository, slug)?;
                }
                self.check_neighbor_dir(repository, &path)?;
            }
        }

        if previous_head.as_deref() != Some(head.as_str()) {
            db::repository_event(&self.db, repository, "head_observed", Some(&head), None)?;
        }
        Ok(())
    }

    fn check_neighbor_dir(&self, repository: &Path, path: &Path) -> ServiceResult<()> {
        let parent = path.parent().unwrap_or(Path::new(""));
        let directory = repository.join(parent);
        let mut siblings = Vec::new();
        let entries = match std::fs::read_dir(&directory) {
            Ok(entries) => entries,
            Err(_) => return Ok(()),
        };
        for entry in entries {
            let entry = entry.map_err(io)?;
            let sibling = entry.path();
            if sibling.extension().and_then(|value| value.to_str()) != Some("md")
                || !sibling.is_file()
            {
                continue;
            }
            let text = std::fs::read_to_string(&sibling).map_err(io)?;
            siblings.push((
                sibling.file_name().map(PathBuf::from).unwrap_or_default(),
                frontmatter_slug(&text),
            ));
        }
        let with_slug = siblings.iter().filter(|(_, slug)| slug.is_some()).count();
        if with_slug < 2 {
            return Ok(());
        }
        for (name, slug) in siblings {
            if slug.is_some() {
                continue;
            }
            let relative = parent.join(name);
            if !db::integrity_event_seen(
                &self.db,
                "missing_slug_suspected",
                None,
                Some(repository),
                Some(&relative),
            )? {
                db::integrity_event(
                    &self.db,
                    "missing_slug_suspected",
                    None,
                    Some(repository),
                    Some(&relative),
                    "sibling Markdown files carry slugs",
                )?;
            }
        }
        Ok(())
    }

    fn once_only_duplicate_check(&self, repository: &Path, slug: &str) -> ServiceResult<()> {
        let needle = format!("slug: {slug}");
        let mut hits = Vec::new();
        let output = Command::new("rg")
            .current_dir(&repository)
            .args(["-l", "-F", &needle, "-g", "*.md", "-g", "!.git/**"])
            .output()
            .map_err(io)?;
        if !output.status.success() && output.status.code() != Some(1) {
            return Err(ServiceError::Storage(
                String::from_utf8_lossy(&output.stderr).trim().into(),
            ));
        }
        for relative in String::from_utf8_lossy(&output.stdout).lines() {
            let path = repository.join(relative);
            if std::fs::read_to_string(&path)
                .ok()
                .and_then(|text| frontmatter_slug(&text))
                .as_deref()
                == Some(slug)
            {
                hits.push(path);
            }
        }
        if hits.len() > 1
            && !db::integrity_event_seen(&self.db, "duplicate_slug", Some(slug), None, None)?
        {
            db::integrity_event(
                &self.db,
                "duplicate_slug",
                Some(slug),
                None,
                None,
                &hits
                    .iter()
                    .map(|path| path.display().to_string())
                    .collect::<Vec<_>>()
                    .join(", "),
            )?;
        }
        Ok(())
    }

    fn missing_slug_neighbors(
        &self,
        repository: &Path,
        files: &[ScannedFile],
    ) -> ServiceResult<()> {
        let mut dirs: BTreeMap<PathBuf, Vec<&ScannedFile>> = BTreeMap::new();
        for file in files {
            dirs.entry(file.path.parent().unwrap_or(Path::new("")).to_path_buf())
                .or_default()
                .push(file);
        }
        for siblings in dirs.into_values() {
            let with_slug = siblings.iter().filter(|file| file.slug.is_some()).count();
            if with_slug < 2 {
                continue;
            }
            for file in siblings.into_iter().filter(|file| file.slug.is_none()) {
                if !db::integrity_event_seen(
                    &self.db,
                    "missing_slug_suspected",
                    None,
                    Some(repository),
                    Some(&file.path),
                )? {
                    db::integrity_event(
                        &self.db,
                        "missing_slug_suspected",
                        None,
                        Some(repository),
                        Some(&file.path),
                        "sibling Markdown files carry slugs",
                    )?;
                }
            }
        }
        Ok(())
    }

    fn reconcile_dispatches(&self, repository: &Path) -> ServiceResult<()> {
        let mut failure = None;
        for commit in dispatch_commits(&repository)? {
            let message = git_text(&repository, &["show", "-s", "--format=%B", &commit])?;
            let trailers = dispatch_trailers(&message)?;
            let Some(plan) = trailers.plan else {
                continue;
            };
            let dispatch = format!(
                "git-{}-{}",
                &commit[..commit.len().min(16)],
                safe_dispatch_part(&plan)
            );
            if db::dispatch_event_seen(&self.db, &dispatch, "submitted")?
                || db::dispatch_event_seen(&self.db, &dispatch, "submitted_recovered")?
            {
                continue;
            }
            if !db::dispatch_event_seen(&self.db, &dispatch, "observed")? {
                db::dispatch_event(
                    &self.db,
                    &repository,
                    &dispatch,
                    "observed",
                    Some(&plan),
                    Some(&commit),
                    None,
                    None,
                )?;
            }

            let sources = source_records_at(&self.db, &repository, &commit, &trailers.documents)?;
            let inflight_commit =
                self.ensure_inflight_snapshot(&repository, &dispatch, &plan, &sources)?;
            for (slug, path, blob, _bytes) in &sources {
                db::dispatch_source(
                    &self.db,
                    &dispatch,
                    &repository,
                    slug,
                    path,
                    blob,
                    &commit,
                    &inflight_commit,
                )?;
            }

            if dispatch_submitted_in_git(&repository, &dispatch)? {
                db::dispatch_event(
                    &self.db,
                    &repository,
                    &dispatch,
                    "submitted_recovered",
                    Some(&plan),
                    Some(&commit),
                    Some(&inflight_commit),
                    None,
                )?;
                continue;
            }

            match self.submit_dispatch(&repository, &commit, &dispatch, &plan, &sources) {
                Ok(()) => {
                    db::expect_dispatch_responses(&self.db, &dispatch)?;
                    let event_commit =
                        git::append_dispatch_event(&repository, &dispatch, "submitted", None)?;
                    db::dispatch_event(
                        &self.db,
                        &repository,
                        &dispatch,
                        "submitted",
                        Some(&plan),
                        Some(&commit),
                        Some(&event_commit.0),
                        None,
                    )?;
                }
                Err(error) => {
                    db::dispatch_event(
                        &self.db,
                        &repository,
                        &dispatch,
                        "submit_failed",
                        Some(&plan),
                        Some(&commit),
                        Some(&inflight_commit),
                        Some(&error.to_string()),
                    )?;
                    failure = Some(error);
                }
            }
        }
        match failure {
            Some(error) => Err(error),
            None => Ok(()),
        }
    }

    fn ensure_inflight_snapshot(
        &self,
        repository: &Path,
        dispatch: &str,
        plan: &str,
        sources: &[(String, PathBuf, String, Vec<u8>)],
    ) -> ServiceResult<String> {
        if let Some(commit) = inflight_snapshot_for_dispatch(repository, dispatch)? {
            return Ok(commit);
        }
        let ledger = git::append_inflight_snapshot(
            repository,
            &LedgerSnapshotRequest {
                dispatch: DispatchId(dispatch.to_string()),
                plan: PlanId(plan.to_string()),
                sources: sources
                    .iter()
                    .map(|(slug, path, _blob, bytes)| LedgerSource {
                        slug: slug.clone(),
                        path: path.clone(),
                        bytes: bytes.clone(),
                    })
                    .collect(),
            },
        )?;
        Ok(ledger.commit.0)
    }

    fn submit_dispatch(
        &self,
        repository: &Path,
        commit: &str,
        _dispatch: &str,
        plan: &str,
        sources: &[(String, PathBuf, String, Vec<u8>)],
    ) -> ServiceResult<()> {
        let pending = pending_export_slugs(&self.asc)?;
        let blocked = sources
            .iter()
            .map(|(slug, _, _, _)| slug)
            .filter(|slug| pending.contains(slug.as_str()))
            .cloned()
            .collect::<Vec<_>>();
        if !blocked.is_empty() {
            return Err(ServiceError::Conflict(format!(
                "dispatch blocked by pending unexported responses: {}",
                blocked.join(", ")
            )));
        }

        let temporary = std::env::temp_dir().join(format!(
            "autoscribe-worker-{}-{}",
            std::process::id(),
            &commit[..commit.len().min(12)]
        ));
        let _ = std::fs::remove_dir_all(&temporary);
        std::fs::create_dir_all(&temporary).map_err(io)?;
        let worktree = temporary.join("worktree");
        let add = Command::new("git")
            .arg("-C")
            .arg(repository)
            .args(["worktree", "add", "--quiet", "--detach"])
            .arg(&worktree)
            .arg(commit)
            .output()
            .map_err(io)?;
        if !add.status.success() {
            return Err(ServiceError::Storage(format!(
                "could not create dispatch worktree: {}",
                String::from_utf8_lossy(&add.stderr).trim()
            )));
        }

        let result = self
            .build_calls(&worktree, plan, sources)
            .and_then(|calls| {
                let bytes = ndjson(&calls)?;
                run_asc(&self.asc, &["enqueue"], &bytes)?;
                Ok(())
            });

        let _ = Command::new("git")
            .arg("-C")
            .arg(repository)
            .args(["worktree", "remove", "--force"])
            .arg(&worktree)
            .output();
        let _ = std::fs::remove_dir_all(&temporary);
        result
    }

    fn build_calls(
        &self,
        worktree: &Path,
        plan: &str,
        sources: &[(String, PathBuf, String, Vec<u8>)],
    ) -> ServiceResult<Vec<Value>> {
        let mut jobs = Vec::new();
        let mut runtime_defaults = Vec::new();
        for (slug, relative, _, _) in sources {
            let source = worktree.join(relative);
            let temporary_defaults = DispatchDefaultsFile::create(&source, plan)?;
            jobs.push(PandocJob {
                identity: slug.clone(),
                working_directory: std::env::temp_dir(),
                arguments: dispatch_pandoc_arguments(
                    &self.pandoc_dispatch_defaults,
                    temporary_defaults.path(),
                ),
            });
            runtime_defaults.push(temporary_defaults);
        }
        let parallelism = std::thread::available_parallelism()
            .map(usize::from)
            .unwrap_or(2)
            .max(2);
        let outcomes = pandoc::run_parallel(&self.pandoc, jobs, parallelism)?;
        let mut calls = Vec::new();
        for ((expected_slug, relative, _, _), outcome) in sources.iter().zip(outcomes) {
            if outcome.exit_code != Some(0) || outcome.error.is_some() {
                let detail = outcome
                    .error
                    .unwrap_or_else(|| String::from_utf8_lossy(&outcome.stderr).trim().into());
                return Err(ServiceError::Storage(format!(
                    "{}: Pandoc conversion failed: {detail}",
                    relative.display()
                )));
            }
            calls.extend(validate_completed_calls(
                &outcome.stdout,
                expected_slug,
                plan,
                relative,
            )?);
        }
        drop(runtime_defaults);
        Ok(calls)
    }

    fn reconcile_export(&self, slug: &str, failed_roots: &BTreeSet<PathBuf>) -> ServiceResult<()> {
        let route = db::route_slug(&self.db, slug)?.ok_or_else(|| {
            ServiceError::Conflict(format!("pending export {slug} has no unique active route"))
        })?;
        if failed_roots.contains(&route.repository_root) {
            return Err(ServiceError::Storage(format!(
                "repository unavailable: {}",
                route.repository_root.display()
            )));
        }
        let dispatch = route
            .dispatch_identity
            .as_deref()
            .ok_or_else(|| ServiceError::Conflict(format!("{slug}: no dispatch lineage")))?;
        let revision = route
            .inflight_commit
            .as_deref()
            .ok_or_else(|| ServiceError::Conflict(format!("{slug}: no inflight source")))?;
        let source = String::from_utf8(git::read_version(
            &route.repository_root,
            VersionRequest {
                revision: revision.to_string(),
                path: route.source_path.clone(),
            },
        )?)
        .map_err(|error| ServiceError::InvalidInput(error.to_string()))?;
        // Validate before extraction, response events, Git writes, or receipts.
        if frontmatter_slug(&source).as_deref() != Some(slug) {
            return Err(ServiceError::InvalidInput(format!(
                "{slug}: dispatch snapshot slug does not match pending export"
            )));
        }
        let records = extract_slug(&self.asc, slug)?;
        for record in records {
            let result = first_string(&record, &["result_identity", "identity", "call_identity"])?;
            let call = first_string(&record, &["call_identity", "identity"])?;
            let content = record
                .get("record_content")
                .or_else(|| record.get("content"))
                .and_then(Value::as_str)
                .ok_or_else(|| {
                    ServiceError::InvalidInput(
                        "export record is missing record_content/content".into(),
                    )
                })?;
            let replacement = preserve_frontmatter(&source, content)?;
            let snapshot = if let Some(existing) =
                response_snapshot_for_result(&route.repository_root, &result)?
            {
                existing
            } else {
                git::append_response_snapshot(
                    &route.repository_root,
                    dispatch,
                    &result,
                    slug,
                    "saved",
                    &route.source_path,
                    replacement.as_bytes(),
                )?
                .0
            };
            db::response_event(
                &self.db,
                &route.repository_root,
                slug,
                "materialized",
                Some(&result),
                Some(&call),
                Some(&snapshot),
                None,
            )?;
            db::response_observed(&self.db, dispatch, slug, true)?;
            run_asc(&self.asc, &["export", "update-exports", &result], &[])?;
            db::response_event(
                &self.db,
                &route.repository_root,
                slug,
                "receipt_recorded",
                Some(&result),
                Some(&call),
                Some(&snapshot),
                None,
            )?;
        }
        Ok(())
    }
}

static DISPATCH_DEFAULTS_SEQUENCE: AtomicU64 = AtomicU64::new(0);

struct DispatchDefaultsFile {
    path: PathBuf,
}

impl DispatchDefaultsFile {
    fn create(source: &Path, plan: &str) -> ServiceResult<Self> {
        if !source.is_absolute() {
            return Err(ServiceError::InvalidInput(format!(
                "dispatch source path must be absolute: {}",
                source.display()
            )));
        }
        if !valid_dispatch_slug(plan) {
            return Err(ServiceError::InvalidInput(
                "dispatch plan must be a valid slug".into(),
            ));
        }

        for _ in 0..128 {
            let sequence = DISPATCH_DEFAULTS_SEQUENCE.fetch_add(1, Ordering::Relaxed);
            let timestamp = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default()
                .as_nanos();
            let path = std::env::temp_dir().join(format!(
                "autoscribe-dispatch-{}-{timestamp}-{sequence}.yaml",
                std::process::id()
            ));
            let mut options = OpenOptions::new();
            options.write(true).create_new(true);
            #[cfg(unix)]
            {
                use std::os::unix::fs::OpenOptionsExt;
                options.mode(0o600);
            }
            let mut file = match options.open(&path) {
                Ok(file) => file,
                Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
                Err(error) => return Err(io(error)),
            };
            let temporary = Self { path };
            write_dispatch_defaults(&mut file, source, plan)?;
            file.flush().map_err(io)?;
            file.sync_all().map_err(io)?;
            return Ok(temporary);
        }
        Err(ServiceError::Io(
            "could not allocate a unique dispatch defaults file".into(),
        ))
    }

    fn path(&self) -> &Path {
        &self.path
    }
}

impl Drop for DispatchDefaultsFile {
    fn drop(&mut self) {
        let _ = std::fs::remove_file(&self.path);
    }
}

fn write_dispatch_defaults(file: &mut File, source: &Path, plan: &str) -> ServiceResult<()> {
    let source = serde_json::to_string(&source.to_string_lossy().into_owned())
        .map_err(|error| ServiceError::InvalidInput(error.to_string()))?;
    let plan = serde_json::to_string(plan)
        .map_err(|error| ServiceError::InvalidInput(error.to_string()))?;
    write!(
        file,
        "input-files:\n  - {source}\nmetadata:\n  plan: {plan}\n"
    )
    .map_err(io)
}

fn dispatch_pandoc_arguments(static_defaults: &Path, runtime_defaults: &Path) -> Vec<String> {
    vec![
        format!("--defaults={}", static_defaults.display()),
        format!(
            "--defaults={}",
            runtime_defaults
                .file_name()
                .expect("runtime filename")
                .to_string_lossy()
        ),
    ]
}

fn validate_completed_calls(
    bytes: &[u8],
    expected_slug: &str,
    expected_plan: &str,
    source: &Path,
) -> ServiceResult<Vec<Value>> {
    let text = std::str::from_utf8(bytes)
        .map_err(|error| ServiceError::InvalidInput(error.to_string()))?;
    let mut calls = Vec::new();
    for (index, line) in text
        .lines()
        .filter(|line| !line.trim().is_empty())
        .enumerate()
    {
        let record: Value = serde_json::from_str(line).map_err(|error| {
            ServiceError::InvalidInput(format!(
                "{}: Pandoc NDJSON row {} is invalid: {error}",
                source.display(),
                index + 1
            ))
        })?;
        let object = record.as_object().ok_or_else(|| {
            ServiceError::InvalidInput(format!(
                "{}: Pandoc NDJSON row {} must be an object",
                source.display(),
                index + 1
            ))
        })?;
        if object.get("type").and_then(Value::as_str) != Some("call") {
            return Err(ServiceError::InvalidInput(format!(
                "{}: Pandoc NDJSON row {} must have type call",
                source.display(),
                index + 1
            )));
        }
        let identity = object
            .get("identity")
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .ok_or_else(|| {
                ServiceError::InvalidInput(format!(
                    "{}: Pandoc NDJSON row {} has no identity",
                    source.display(),
                    index + 1
                ))
            })?;
        if identity != expected_slug {
            return Err(ServiceError::Conflict(format!(
                "{}: dispatch requested slug {}, Pandoc emitted {}",
                source.display(),
                expected_slug,
                identity
            )));
        }
        let content = object.get("content").and_then(Value::as_str).unwrap_or("");
        if content.trim().is_empty() {
            return Err(ServiceError::InvalidInput(format!(
                "{identity}: Pandoc call content is blank"
            )));
        }
        let plan = object
            .get("plan")
            .and_then(Value::as_str)
            .map(str::trim)
            .unwrap_or("");
        if plan != expected_plan {
            return Err(ServiceError::Conflict(format!(
                "{identity}: Pandoc emitted plan {plan:?}, expected {expected_plan:?}"
            )));
        }
        if !object.get("extra").is_some_and(Value::is_object) {
            return Err(ServiceError::InvalidInput(format!(
                "{identity}: Pandoc call extra must be an object"
            )));
        }
        if object
            .get("directive")
            .is_some_and(|value| !value.is_string())
        {
            return Err(ServiceError::InvalidInput(format!(
                "{identity}: Pandoc call directive must be a string"
            )));
        }
        calls.push(record);
    }
    if calls.is_empty() {
        return Err(ServiceError::InvalidInput(format!(
            "{}: Pandoc emitted no call records",
            source.display()
        )));
    }
    Ok(calls)
}

fn scan_markdown(repository: &Path) -> ServiceResult<Vec<ScannedFile>> {
    let output = Command::new("rg")
        .current_dir(repository)
        .args(["--files", "-g", "*.md", "-g", "!.git/**"])
        .output()
        .map_err(io)?;
    if !output.status.success() {
        return Err(ServiceError::Storage(format!(
            "rg --files failed: {}",
            String::from_utf8_lossy(&output.stderr).trim()
        )));
    }
    let mut files = Vec::new();
    for line in String::from_utf8_lossy(&output.stdout)
        .lines()
        .filter(|line| !line.trim().is_empty())
    {
        let path = PathBuf::from(line);
        let bytes = std::fs::read(repository.join(&path)).map_err(io)?;
        let text = String::from_utf8_lossy(&bytes);
        files.push(ScannedFile {
            path: path.clone(),
            slug: frontmatter_slug(&text),
            blob: git_blob(repository, &path).ok(),
        });
    }
    Ok(files)
}

fn frontmatter_slug(text: &str) -> Option<String> {
    markdown_frontmatter_value(text, "slug")
}

fn markdown_frontmatter_value(text: &str, key: &str) -> Option<String> {
    if !text.starts_with("---\n") && !text.starts_with("---\r\n") {
        return None;
    }
    let mut lines = text.lines();
    lines.next()?;
    for line in lines {
        if line.trim() == "---" {
            break;
        }
        if let Some((name, value)) = line.split_once(':') {
            if name.trim() == key {
                let value = value.trim().trim_matches(['\'', '"']);
                if !value.is_empty() {
                    return Some(value.to_string());
                }
            }
        }
    }
    None
}

fn preserve_frontmatter(old: &str, response: &str) -> ServiceResult<String> {
    let mut lines = old.split_inclusive('\n');
    if !lines
        .next()
        .is_some_and(|line| line.trim_end_matches(['\r', '\n']) == "---")
    {
        return Err(ServiceError::InvalidInput(
            "source has no YAML frontmatter".into(),
        ));
    }
    let mut end = old.find('\n').map_or(old.len(), |index| index + 1);
    for line in lines {
        end += line.len();
        if line.trim_end_matches(['\r', '\n']) == "---" {
            // Keep the complete raw YAML block, including its original newline bytes.
            let separator = if old[..end].ends_with('\n') { "" } else { "\n" };
            return Ok(format!("{}{separator}{response}", &old[..end]));
        }
    }
    Err(ServiceError::InvalidInput(
        "source has unterminated YAML frontmatter".into(),
    ))
}

fn dispatch_commits(repository: &Path) -> ServiceResult<Vec<String>> {
    let output = Command::new("git")
        .arg("-C")
        .arg(repository)
        .args([
            "log",
            "--reverse",
            "--format=%H",
            "--grep=Autoscribe-Dispatch:",
            "--grep=Autoscribe-Plan:",
            "master",
        ])
        .output()
        .map_err(io)?;
    if !output.status.success() {
        return Err(ServiceError::Storage(format!(
            "could not inspect master dispatch commits: {}",
            String::from_utf8_lossy(&output.stderr).trim()
        )));
    }
    Ok(String::from_utf8_lossy(&output.stdout)
        .lines()
        .map(str::trim)
        .filter(|line| !line.is_empty())
        .map(str::to_string)
        .collect())
}

fn dispatch_trailers(message: &str) -> ServiceResult<DispatchTrailers> {
    let mut plans = Vec::new();
    let mut documents = Vec::new();
    for line in message.lines() {
        if let Some(value) = line.strip_prefix("Autoscribe-Plan:") {
            let value = value.trim();
            if value.is_empty() || !valid_dispatch_slug(value) {
                return Err(ServiceError::InvalidInput(
                    "Autoscribe-Plan trailer requires one valid slug".into(),
                ));
            }
            plans.push(value.to_string());
        }
        if let Some(value) = line.strip_prefix("Autoscribe-Document:") {
            let value = value.trim();
            if !value.is_empty() {
                documents.push(value.to_string());
            }
        }
    }
    documents.sort();
    documents.dedup();
    let plan = match plans.len() {
        0 => {
            return Err(ServiceError::InvalidInput(
                "dispatch commit is missing Autoscribe-Plan trailer".into(),
            ));
        }
        1 => plans.into_iter().next(),
        _ => {
            return Err(ServiceError::InvalidInput(
                "a dispatch commit must contain exactly one Autoscribe-Plan trailer".into(),
            ));
        }
    };
    if plan.is_some() && documents.is_empty() {
        return Err(ServiceError::InvalidInput(
            "Autoscribe-Plan trailer requires at least one Autoscribe-Document trailer".into(),
        ));
    }
    Ok(DispatchTrailers { plan, documents })
}

fn valid_dispatch_slug(value: &str) -> bool {
    !value.is_empty()
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'-' | b'_'))
}

fn safe_dispatch_part(value: &str) -> String {
    let mut out = value
        .chars()
        .map(|character| {
            if character.is_ascii_alphanumeric() {
                character
            } else {
                '-'
            }
        })
        .collect::<String>();
    while out.contains("--") {
        out = out.replace("--", "-");
    }
    out.trim_matches('-').chars().take(48).collect()
}

fn source_records_at(
    database: &Database,
    repository: &Path,
    commit: &str,
    documents: &[String],
) -> ServiceResult<Vec<(String, PathBuf, String, Vec<u8>)>> {
    let duplicates = db::duplicate_slugs(database)?
        .into_iter()
        .map(|(slug, _)| slug)
        .collect::<BTreeSet<_>>();
    let indexed = db::active_files(database, repository)?
        .into_iter()
        .filter_map(|(path, slug, _)| slug.map(|slug| (slug, path)))
        .collect::<BTreeMap<_, _>>();
    let mut records = Vec::new();
    for slug in documents {
        if duplicates.contains(slug) {
            return Err(ServiceError::Conflict(format!(
                "document slug is duplicated: {slug}"
            )));
        }
        let path = indexed.get(slug).cloned().ok_or_else(|| {
            ServiceError::Conflict(format!(
                "document slug has no unique indexed filepath: {slug}"
            ))
        })?;
        let spec = format!("{commit}:{}", path.to_string_lossy());
        let bytes = git_bytes(repository, &["show", &spec])?;
        if frontmatter_slug(&String::from_utf8_lossy(&bytes)).as_deref() != Some(slug.as_str()) {
            return Err(ServiceError::InvalidInput(format!(
                "{slug}: committed source slug does not match dispatch"
            )));
        }
        let blob = git_text(repository, &["rev-parse", &spec])?
            .trim()
            .to_string();
        records.push((slug.clone(), path, blob, bytes));
    }
    Ok(records)
}

fn dirty_markdown_paths(repository: &Path) -> ServiceResult<BTreeSet<PathBuf>> {
    let output = Command::new("git")
        .env("GIT_OPTIONAL_LOCKS", "0")
        .arg("-C")
        .arg(repository)
        .args([
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
            "--no-renames",
            "--",
            "*.md",
        ])
        .output()
        .map_err(io)?;
    if !output.status.success() {
        return Err(ServiceError::Storage(format!(
            "git status failed: {}",
            String::from_utf8_lossy(&output.stderr).trim()
        )));
    }
    let mut paths = BTreeSet::new();
    for record in output
        .stdout
        .split(|byte| *byte == 0)
        .filter(|record| !record.is_empty())
    {
        if record.len() < 4 {
            continue;
        }
        let raw = String::from_utf8_lossy(&record[3..]).trim().to_string();
        let path = raw.split(" -> ").last().unwrap_or(&raw);
        if path.ends_with(".md") {
            paths.insert(PathBuf::from(path));
        }
    }
    Ok(paths)
}

fn changed_markdown_paths(
    repository: &Path,
    old: &str,
    new: &str,
) -> ServiceResult<BTreeSet<PathBuf>> {
    let range = format!("{old}..{new}");
    let output = Command::new("git")
        .arg("-C")
        .arg(repository)
        .args(["diff", "--name-only", "-z", &range, "--", "*.md"])
        .output()
        .map_err(io)?;
    if !output.status.success() {
        return Err(ServiceError::Storage(format!(
            "git diff failed: {}",
            String::from_utf8_lossy(&output.stderr).trim()
        )));
    }
    Ok(output
        .stdout
        .split(|byte| *byte == 0)
        .filter(|record| !record.is_empty())
        .map(|record| PathBuf::from(String::from_utf8_lossy(record).into_owned()))
        .collect())
}

fn pending_export_slugs(asc: &Path) -> ServiceResult<BTreeSet<String>> {
    let output = Command::new(asc)
        .args(["export", "list-pending"])
        .output()
        .map_err(io)?;
    if !output.status.success() {
        return Err(ServiceError::Storage(format!(
            "asc export list-pending failed: {}",
            String::from_utf8_lossy(&output.stderr).trim()
        )));
    }
    Ok(String::from_utf8_lossy(&output.stdout)
        .lines()
        .map(str::trim)
        .filter(|line| !line.is_empty())
        .map(str::to_string)
        .collect())
}

fn extract_slug(asc: &Path, slug: &str) -> ServiceResult<Vec<Value>> {
    let output = Command::new(asc)
        .args(["export", "extract-selected", slug, "--no-receipt"])
        .output()
        .map_err(io)?;
    if !output.status.success() {
        return Err(ServiceError::Storage(format!(
            "asc export extract-selected failed for {slug}: {}",
            String::from_utf8_lossy(&output.stderr).trim()
        )));
    }
    let mut records = Vec::new();
    for line in String::from_utf8_lossy(&output.stdout)
        .lines()
        .map(str::trim)
        .filter(|line| !line.is_empty())
    {
        records.push(
            serde_json::from_str(line)
                .map_err(|error| ServiceError::InvalidInput(error.to_string()))?,
        );
    }
    Ok(records)
}

fn first_string(record: &Value, fields: &[&str]) -> ServiceResult<String> {
    fields
        .iter()
        .find_map(|field| record.get(*field).and_then(Value::as_str))
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_string)
        .ok_or_else(|| {
            ServiceError::InvalidInput(format!("export record is missing {}", fields.join("/")))
        })
}

fn inflight_snapshot_for_dispatch(
    repository: &Path,
    dispatch: &str,
) -> ServiceResult<Option<String>> {
    git_log_match(repository, &format!("AUTOSCRIBE INFLIGHT {dispatch}"))
}

fn response_snapshot_for_result(repository: &Path, result: &str) -> ServiceResult<Option<String>> {
    git_log_match(repository, &format!("Result: {result}"))
}

fn dispatch_submitted_in_git(repository: &Path, dispatch: &str) -> ServiceResult<bool> {
    let exists = Command::new("git")
        .arg("-C")
        .arg(repository)
        .args([
            "show-ref",
            "--verify",
            "--quiet",
            "refs/heads/autoscribe/inflight",
        ])
        .status()
        .map_err(io)?;
    if !exists.success() {
        return Ok(false);
    }
    let dispatch_line = format!("Dispatch: {dispatch}");
    let output = Command::new("git")
        .arg("-C")
        .arg(repository)
        .args([
            "log",
            "-1",
            "--format=%H",
            "--all-match",
            "--fixed-strings",
            "--grep",
            "AUTOSCRIBE DISPATCH submitted",
            "--grep",
            &dispatch_line,
            "refs/heads/autoscribe/inflight",
        ])
        .output()
        .map_err(io)?;
    if !output.status.success() {
        return Err(ServiceError::Storage(
            String::from_utf8_lossy(&output.stderr).trim().into(),
        ));
    }
    Ok(!String::from_utf8_lossy(&output.stdout).trim().is_empty())
}

fn git_log_match(repository: &Path, needle: &str) -> ServiceResult<Option<String>> {
    let exists = Command::new("git")
        .arg("-C")
        .arg(repository)
        .args([
            "show-ref",
            "--verify",
            "--quiet",
            "refs/heads/autoscribe/inflight",
        ])
        .status()
        .map_err(io)?;
    if !exists.success() {
        return Ok(None);
    }
    let output = Command::new("git")
        .arg("-C")
        .arg(repository)
        .args([
            "log",
            "-1",
            "--format=%H",
            "--fixed-strings",
            "--grep",
            needle,
            "refs/heads/autoscribe/inflight",
        ])
        .output()
        .map_err(io)?;
    if !output.status.success() {
        return Err(ServiceError::Storage(
            String::from_utf8_lossy(&output.stderr).trim().into(),
        ));
    }
    let value = String::from_utf8_lossy(&output.stdout).trim().to_string();
    Ok((!value.is_empty()).then_some(value))
}

fn git_blob(repository: &Path, path: &Path) -> ServiceResult<String> {
    let output = Command::new("git")
        .arg("-C")
        .arg(repository)
        .args(["hash-object", "--"])
        .arg(path)
        .output()
        .map_err(io)?;
    if !output.status.success() {
        return Err(ServiceError::Storage(
            String::from_utf8_lossy(&output.stderr).trim().into(),
        ));
    }
    Ok(String::from_utf8_lossy(&output.stdout).trim().to_string())
}

fn git_text(repository: &Path, args: &[&str]) -> ServiceResult<String> {
    String::from_utf8(git_bytes(repository, args)?)
        .map_err(|error| ServiceError::InvalidInput(error.to_string()))
}

fn git_bytes(repository: &Path, args: &[&str]) -> ServiceResult<Vec<u8>> {
    let output = Command::new("git")
        .arg("-C")
        .arg(repository)
        .args(args)
        .output()
        .map_err(io)?;
    if !output.status.success() {
        return Err(ServiceError::Storage(format!(
            "git {} failed: {}",
            args.join(" "),
            String::from_utf8_lossy(&output.stderr).trim()
        )));
    }
    Ok(output.stdout)
}

fn run_asc(asc: &Path, args: &[&str], input: &[u8]) -> ServiceResult<Vec<u8>> {
    let mut child = Command::new(asc)
        .args(args)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(io)?;
    if let Some(mut stdin) = child.stdin.take() {
        use std::io::Write;
        stdin.write_all(input).map_err(io)?;
    }
    let output = child.wait_with_output().map_err(io)?;
    if !output.status.success() {
        return Err(ServiceError::Storage(format!(
            "asc {} failed: {}",
            args.join(" "),
            String::from_utf8_lossy(&output.stderr).trim()
        )));
    }
    Ok(output.stdout)
}

fn ndjson(records: &[Value]) -> ServiceResult<Vec<u8>> {
    let mut bytes = Vec::new();
    for record in records {
        serde_json::to_writer(&mut bytes, record)
            .map_err(|error| ServiceError::InvalidInput(error.to_string()))?;
        bytes.push(b'\n');
    }
    Ok(bytes)
}

fn io(error: impl std::fmt::Display) -> ServiceError {
    ServiceError::Io(error.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        fs,
        sync::Mutex,
        time::{SystemTime, UNIX_EPOCH},
    };

    static TEST_SEQUENCE: AtomicU64 = AtomicU64::new(0);
    static ENV_LOCK: Mutex<()> = Mutex::new(());

    struct TestDirectory(PathBuf);

    impl TestDirectory {
        fn new(label: &str) -> Self {
            let sequence = TEST_SEQUENCE.fetch_add(1, Ordering::Relaxed);
            let timestamp = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos();
            let path = std::env::temp_dir().join(format!(
                "autoscribe-dispatch-test-{label}-{}-{timestamp}-{sequence}",
                std::process::id()
            ));
            fs::create_dir_all(&path).unwrap();
            Self(path)
        }

        fn path(&self) -> &Path {
            &self.0
        }
    }

    impl Drop for TestDirectory {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }

    fn worker(root: &Path, pandoc: PathBuf) -> Worker {
        let defaults = root.join("defaults/dispatch.yaml");
        fs::create_dir_all(defaults.parent().unwrap()).unwrap();
        fs::write(&defaults, "fixture\n").unwrap();
        Worker {
            db: Database::memory().unwrap(),
            repositories: RefCell::new(BTreeMap::new()),
            asc: PathBuf::from("/bin/true"),
            pandoc,
            pandoc_dispatch_defaults: defaults,
        }
    }

    fn executable(path: &Path, contents: &str) {
        fs::write(path, contents).unwrap();
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let mut permissions = fs::metadata(path).unwrap().permissions();
            permissions.set_mode(0o755);
            fs::set_permissions(path, permissions).unwrap();
        }
    }

    fn git(root: &Path, arguments: &[&str]) {
        let output = Command::new("git")
            .arg("-C")
            .arg(root)
            .args(arguments)
            .output()
            .unwrap();
        assert!(
            output.status.success(),
            "git {} failed: {}",
            arguments.join(" "),
            String::from_utf8_lossy(&output.stderr)
        );
    }

    fn source(root: &Path) -> (String, PathBuf, String, Vec<u8>) {
        let relative = PathBuf::from("Content/One.md");
        fs::create_dir_all(root.join("Content")).unwrap();
        fs::write(root.join(&relative), "---\nslug: cnt.one\n---\nBody\n").unwrap();
        ("cnt.one".into(), relative, "blob".into(), Vec::new())
    }

    #[test]
    fn dispatch_trailers_require_one_valid_plan() {
        let valid =
            dispatch_trailers("Autoscribe-Plan: plan.test-1\nAutoscribe-Document: cnt.one\n")
                .unwrap();
        assert_eq!(valid.plan.as_deref(), Some("plan.test-1"));
        assert_eq!(valid.documents, ["cnt.one"]);

        for message in [
            "Autoscribe-Document: cnt.one\n",
            "Autoscribe-Plan:\nAutoscribe-Document: cnt.one\n",
            "Autoscribe-Plan: not a slug\nAutoscribe-Document: cnt.one\n",
            "Autoscribe-Plan: plan.one\nAutoscribe-Plan: plan.one\nAutoscribe-Document: cnt.one\n",
            "Autoscribe-Plan: plan.one\nAutoscribe-Plan: plan.two\nAutoscribe-Document: cnt.one\n",
        ] {
            assert!(dispatch_trailers(message).is_err(), "accepted {message:?}");
        }
    }

    #[test]
    fn temporary_defaults_are_exact_private_unique_and_cleaned_up() {
        let source = Path::new("/tmp/Source with spaces.md");
        let temporary = DispatchDefaultsFile::create(source, "plan.test").unwrap();
        let path = temporary.path().to_path_buf();
        assert_eq!(
            fs::read_to_string(&path).unwrap(),
            "input-files:\n  - \"/tmp/Source with spaces.md\"\nmetadata:\n  plan: \"plan.test\"\n"
        );
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            assert_eq!(
                fs::metadata(&path).unwrap().permissions().mode() & 0o777,
                0o600
            );
        }
        let other = DispatchDefaultsFile::create(source, "plan.test").unwrap();
        assert_ne!(path, other.path());
        drop(temporary);
        assert!(!path.exists());
    }

    #[test]
    fn concurrent_defaults_never_collide() {
        let guards = (0..16)
            .map(|_| {
                std::thread::spawn(|| {
                    let guard = DispatchDefaultsFile::create(
                        Path::new("/tmp/concurrent.md"),
                        "plan.concurrent",
                    )
                    .unwrap();
                    (guard.path().to_path_buf(), guard)
                })
            })
            .map(|thread| thread.join().unwrap())
            .collect::<Vec<_>>();
        let paths = guards
            .iter()
            .map(|(path, _)| path.clone())
            .collect::<BTreeSet<_>>();
        assert_eq!(paths.len(), guards.len());
        assert!(paths.iter().all(|path| path.is_file()));
        drop(guards);
        assert!(paths.iter().all(|path| !path.exists()));
    }

    #[test]
    fn pandoc_receives_only_static_and_runtime_defaults() {
        let _lock = ENV_LOCK.lock().unwrap();
        let root = TestDirectory::new("success");
        let worktree = root.path().join("worktree");
        fs::create_dir(&worktree).unwrap();
        let arguments_log = root.path().join("arguments");
        let defaults_copy = root.path().join("runtime.yaml");
        let runtime_path_log = root.path().join("runtime-path");
        let pandoc = root.path().join("pandoc");
        executable(
            &pandoc,
            &format!(
                "#!/bin/sh\nprintf '%s\\n' \"$@\" > '{}'\nruntime=${{2#--defaults=}}\nprintf '%s' \"$runtime\" > '{}'\ncp -- \"$runtime\" '{}'\nprintf '%s\\n' '{{\"type\":\"call\",\"identity\":\"cnt.one\",\"content\":\"Body\",\"plan\":\"plan.test\",\"extra\":{{}}}}'\n",
                arguments_log.display(),
                runtime_path_log.display(),
                defaults_copy.display()
            ),
        );
        let worker = worker(root.path(), pandoc);
        let calls = worker
            .build_calls(&worktree, "plan.test", &[source(&worktree)])
            .unwrap();
        assert_eq!(calls.len(), 1);
        let arguments = fs::read_to_string(arguments_log).unwrap();
        let lines = arguments.lines().collect::<Vec<_>>();
        assert_eq!(lines.len(), 2);
        assert_eq!(
            lines[0],
            format!("--defaults={}", worker.pandoc_dispatch_defaults.display())
        );
        assert!(lines[1].starts_with("--defaults=autoscribe-dispatch-"));
        assert_eq!(
            fs::read_to_string(defaults_copy).unwrap(),
            format!(
                "input-files:\n  - {}\nmetadata:\n  plan: \"plan.test\"\n",
                serde_json::to_string(&worktree.join("Content/One.md").to_string_lossy()).unwrap()
            )
        );
        let runtime_path = std::env::temp_dir().join(fs::read_to_string(runtime_path_log).unwrap());
        assert!(!runtime_path.exists());
    }

    #[test]
    fn temporary_defaults_are_cleaned_after_pandoc_failure() {
        let root = TestDirectory::new("failure");
        let worktree = root.path().join("worktree");
        fs::create_dir(&worktree).unwrap();
        let runtime_path_log = root.path().join("runtime-path");
        let pandoc = root.path().join("pandoc");
        executable(
            &pandoc,
            &format!(
                "#!/bin/sh\nruntime=${{2#--defaults=}}\nprintf '%s' \"$runtime\" > '{}'\nexit 9\n",
                runtime_path_log.display()
            ),
        );
        let worker = worker(root.path(), pandoc);
        assert!(
            worker
                .build_calls(&worktree, "plan.test", &[source(&worktree)])
                .is_err()
        );
        let runtime_path = std::env::temp_dir().join(fs::read_to_string(runtime_path_log).unwrap());
        assert!(!runtime_path.exists());
    }

    #[test]
    fn structurally_valid_multiple_calls_are_forwarded_without_reconstruction() {
        let bytes = br#"{"type":"call","identity":"cnt.one","content":"First","plan":"plan.test","extra":{}}
{"type":"call","identity":"cnt.one","content":"Second","plan":"plan.test","extra":{}}
"#;
        let calls =
            validate_completed_calls(bytes, "cnt.one", "plan.test", Path::new("Content/One.md"))
                .unwrap();
        assert_eq!(calls.len(), 2);
        assert_eq!(calls[1]["content"], "Second");
    }

    #[test]
    fn fixture_dispatch_indexes_path_and_enqueues_completed_pandoc_call() {
        let root = TestDirectory::new("end-to-end");
        git(root.path(), &["init", "--quiet", "--initial-branch=master"]);
        git(
            root.path(),
            &["config", "user.email", "tests@autoscribe.local"],
        );
        git(root.path(), &["config", "user.name", "AutoScribe Tests"]);
        let document = root.path().join("Content/One.md");
        fs::create_dir_all(document.parent().unwrap()).unwrap();
        fs::write(
            &document,
            "---\nslug: cnt.one\ntitle: Fixture\n---\nCommitted body\n",
        )
        .unwrap();
        git(root.path(), &["add", "Content/One.md"]);
        git(root.path(), &["commit", "--quiet", "-m", "Fixture source"]);
        git(
            root.path(),
            &[
                "commit",
                "--quiet",
                "--allow-empty",
                "-m",
                "Dispatch fixture",
                "-m",
                "Autoscribe-Dispatch: 1\nAutoscribe-Plan: plan.test\nAutoscribe-Document: cnt.one",
            ],
        );

        let runtime_copy = root.path().join("runtime.yaml");
        let pandoc = root.path().join("pandoc");
        executable(
            &pandoc,
            &format!(
                "#!/bin/sh\nruntime=${{2#--defaults=}}\ncp -- \"$runtime\" '{}'\nprintf '%s\\n' '{{\"type\":\"call\",\"identity\":\"cnt.one\",\"content\":\"Committed body\",\"plan\":\"plan.test\",\"extra\":{{\"metadata\":{{\"title\":\"Fixture\"}}}}}}'\n",
                runtime_copy.display()
            ),
        );
        let enqueue = root.path().join("enqueue.ndjson");
        let asc = root.path().join("asc");
        executable(
            &asc,
            &format!(
                "#!/bin/sh\nif [ \"$1 $2\" = \"export list-pending\" ]; then exit 0; fi\nif [ \"$1\" = \"enqueue\" ]; then cat > '{}'; exit 0; fi\nexit 1\n",
                enqueue.display()
            ),
        );

        let mut worker = worker(root.path(), pandoc);
        worker.asc = asc;
        worker.register_repository(root.path()).unwrap();
        worker.dispatch_once().unwrap();

        let runtime = fs::read_to_string(runtime_copy).unwrap();
        assert!(runtime.lines().any(|line| {
            line.starts_with("  - \"") && line.ends_with("/worktree/Content/One.md\"")
        }));
        assert!(runtime.contains("  plan: \"plan.test\""));
        let call: Value =
            serde_json::from_str(fs::read_to_string(enqueue).unwrap().trim()).unwrap();
        assert_eq!(call["type"], "call");
        assert_eq!(call["identity"], "cnt.one");
        assert_eq!(call["plan"], "plan.test");
        assert_eq!(call["content"], "Committed body");
    }
    fn committed_repository(root: &Path, slug: &str) -> String {
        git(root, &["init", "--quiet", "--initial-branch=master"]);
        git(root, &["config", "user.email", "tests@autoscribe.local"]);
        git(root, &["config", "user.name", "AutoScribe Tests"]);
        let text = format!(
            "---\r\nslug: {slug}\r\n# retain this comment\r\nstatus: draft\r\nproducer: human\r\ntitle: 'Raw: title'\r\n---\r\nOriginal body\r\n"
        );
        fs::write(root.join("One.md"), &text).unwrap();
        git(root, &["add", "One.md"]);
        git(root, &["commit", "--quiet", "-m", "Original"]);
        text
    }

    #[test]
    fn empty_exports_do_not_construct_repositories_or_write_database() {
        let root = TestDirectory::new("idle");
        let asc = root.path().join("asc");
        let log = root.path().join("calls");
        executable(
            &asc,
            &format!("#!/bin/sh\nprintf '%s\\n' \"$*\" >> '{}'\n", log.display()),
        );
        let worker = Worker::create(Database::memory().unwrap(), asc).unwrap();
        for index in 0..32 {
            db::record_attention(
                &worker.db,
                &root.path().join(format!("missing-{index}")),
                None,
            )
            .unwrap();
        }
        let before = worker.db.connection().total_changes();
        for _ in 0..10 {
            assert!(!worker.responses_once().unwrap());
        }
        assert!(worker.repositories.borrow().is_empty());
        assert_eq!(worker.db.connection().total_changes(), before);
        let calls = fs::read_to_string(log).unwrap();
        assert_eq!(calls.lines().count(), 10);
        assert!(calls.lines().all(|line| line == "export list-pending"));
        println!(
            "idle: 32 registered roots, 10 response checks, 10 asc calls, 0 repository sessions, 0 SQLite row changes"
        );
    }

    #[test]
    fn persistent_submission_failure_is_backed_off_and_missing_repo_is_isolated() {
        for fail_pandoc in [true, false] {
            let root = TestDirectory::new("retry-dispatch");
            let original = committed_repository(root.path(), "cnt.one");
            git(
                root.path(),
                &[
                    "commit",
                    "--quiet",
                    "--allow-empty",
                    "-m",
                    "Dispatch\n\nAutoscribe-Plan: plan.test\nAutoscribe-Document: cnt.one",
                ],
            );
            let master = git::head(root.path()).unwrap().0;
            // Include dirty user bytes to verify scans and detached worktrees never alter them.
            fs::write(root.path().join("One.md"), format!("{original}User edit\n")).unwrap();
            let user_bytes = fs::read(root.path().join("One.md")).unwrap();
            let index = fs::read(root.path().join(".git/index")).unwrap();
            let pandoc = root.path().join("pandoc");
            let log = root.path().join("attempts");
            executable(
                &pandoc,
                &format!(
                    "#!/bin/sh\nprintf 'pandoc\\n' >> '{}'\n{}\n",
                    log.display(),
                    if fail_pandoc {
                        "exit 9"
                    } else {
                        "printf '%s\\n' '{\"type\":\"call\",\"identity\":\"cnt.one\",\"content\":\"Body\",\"plan\":\"plan.test\",\"extra\":{}}'"
                    }
                ),
            );
            let mut worker = worker(root.path(), pandoc);
            worker.asc = root.path().join("asc");
            executable(
                &worker.asc,
                &format!(
                    "#!/bin/sh\nif [ \"$1\" = enqueue ]; then printf 'enqueue\\n' >> '{}'; cat >/dev/null; exit 7; fi\nexit 0\n",
                    log.display()
                ),
            );
            let healthy = TestDirectory::new("healthy");
            committed_repository(healthy.path(), "cnt.healthy");
            let missing = root.path().join("missing");
            for repository in [
                &missing,
                &root.path().to_path_buf(),
                &healthy.path().to_path_buf(),
            ] {
                db::record_attention(&worker.db, repository, None).unwrap();
            }
            crate::daemon::dispatch_pass(&worker, || 0).unwrap();
            let pending = db::due_attention(&worker.db, 1_000).unwrap();
            assert_eq!(pending.len(), 2);
            assert!(
                pending
                    .iter()
                    .all(|attention| attention.root != healthy.path())
            );
            let first = fs::read_to_string(&log).unwrap();
            assert_eq!(first.lines().filter(|line| *line == "pandoc").count(), 1);
            for now in [0, 250, 500, 999] {
                crate::daemon::dispatch_pass(&worker, || now).unwrap();
            }
            assert_eq!(fs::read_to_string(&log).unwrap(), first);
            crate::daemon::dispatch_pass(&worker, || 1_000).unwrap();
            assert!(db::due_attention(&worker.db, 2_999).unwrap().is_empty());
            assert_eq!(db::due_attention(&worker.db, 3_000).unwrap().len(), 2);
            assert_eq!(
                fs::read_to_string(&log)
                    .unwrap()
                    .lines()
                    .filter(|line| *line == "pandoc")
                    .count(),
                2
            );
            // Repair the dependency and prove due work is acknowledged, not lost
            // or submitted again once it succeeds.
            executable(
                &worker.pandoc,
                "#!/bin/sh\nprintf '%s\\n' '{\"type\":\"call\",\"identity\":\"cnt.one\",\"content\":\"Body\",\"plan\":\"plan.test\",\"extra\":{}}'\n",
            );
            executable(
                &worker.asc,
                "#!/bin/sh\nif [ \"$1\" = enqueue ]; then cat >/dev/null; fi\n",
            );
            crate::daemon::dispatch_pass(&worker, || 3_000).unwrap();
            let remaining = db::due_attention(&worker.db, i64::MAX).unwrap();
            assert_eq!(remaining.len(), 1);
            assert_eq!(remaining[0].root, missing);
            let inflight = git_text(root.path(), &["rev-parse", "autoscribe/inflight"]).unwrap();
            crate::daemon::dispatch_pass(&worker, || 3_250).unwrap();
            assert_eq!(
                git_text(root.path(), &["rev-parse", "autoscribe/inflight"]).unwrap(),
                inflight
            );
            assert_eq!(git::head(root.path()).unwrap().0, master);
            assert_eq!(fs::read(root.path().join("One.md")).unwrap(), user_bytes);
            assert_eq!(fs::read(root.path().join(".git/index")).unwrap(), index);
            assert_eq!(
                worker
                    .db
                    .connection()
                    .query_row(
                        "SELECT COUNT(*) FROM dispatch_events WHERE event='submitted'",
                        [],
                        |row| row.get::<_, i64>(0)
                    )
                    .unwrap(),
                1
            );
        }
    }

    fn response_route(worker: &Worker, root: &Path, slug: &str, snapshot_slug: &str) -> String {
        let bytes = format!(
            "---\r\nslug: {snapshot_slug}\r\n# exact\r\nstatus: draft\r\nproducer: human\r\n---\r\nOriginal\r\n"
        );
        let snapshot = git::append_inflight_snapshot(
            root,
            &LedgerSnapshotRequest {
                dispatch: DispatchId(format!("dispatch-{slug}")),
                plan: PlanId("plan.test".into()),
                sources: vec![LedgerSource {
                    slug: slug.into(),
                    path: "One.md".into(),
                    bytes: bytes.as_bytes().to_vec(),
                }],
            },
        )
        .unwrap();
        db::record_attention(&worker.db, root, None).unwrap();
        db::file_seen(
            &worker.db,
            root,
            Path::new("One.md"),
            Some(slug),
            Some("blob"),
        )
        .unwrap();
        db::dispatch_source(
            &worker.db,
            &format!("dispatch-{slug}"),
            root,
            slug,
            Path::new("One.md"),
            "blob",
            &git::head(root).unwrap().0,
            &snapshot.commit.0,
        )
        .unwrap();
        bytes
    }

    #[test]
    fn mismatch_fails_before_any_response_write_and_other_repositories_continue() {
        let bad = TestDirectory::new("bad-response");
        committed_repository(bad.path(), "cnt.bad");
        let good = TestDirectory::new("good-response");
        committed_repository(good.path(), "cnt.good");
        let mut worker = worker(good.path(), PathBuf::from("pandoc"));
        let calls = good.path().join("asc-calls");
        worker.asc = good.path().join("asc");
        executable(
            &worker.asc,
            &format!(
                r#"#!/bin/sh
printf '%s\n' "$*" >> '{}'
case "$2" in
list-pending) printf 'cnt.bad\ncnt.good\ncnt.missing\n' ;;
extract-selected) printf '%s\n' '{{"result_identity":"result.good","call_identity":"call.good","record_content":"Replacement\n"}}' ;;
update-exports) exit 0 ;;
esac
"#,
                calls.display()
            ),
        );
        response_route(&worker, bad.path(), "cnt.bad", "cnt.wrong");
        let source = response_route(&worker, good.path(), "cnt.good", "cnt.good");
        let missing = TestDirectory::new("missing-response");
        let former = missing.path().join("repository");
        fs::create_dir(&former).unwrap();
        committed_repository(&former, "cnt.missing");
        response_route(&worker, &former, "cnt.missing", "cnt.missing");
        worker.register_repository(&former).unwrap();
        fs::rename(&former, missing.path().join("renamed")).unwrap();
        let bad_ref = git_text(bad.path(), &["rev-parse", "autoscribe/inflight"]).unwrap();
        let before = worker.db.connection().total_changes();
        assert!(
            worker
                .reconcile_export("cnt.bad", &BTreeSet::new())
                .is_err()
        );
        assert_eq!(worker.db.connection().total_changes(), before);
        assert!(!calls.exists());
        let master = git::head(good.path()).unwrap().0;
        let index = fs::read(good.path().join(".git/index")).unwrap();
        let user_bytes = fs::read(good.path().join("One.md")).unwrap();
        assert!(worker.responses_once().is_err());
        assert_eq!(
            git_text(bad.path(), &["rev-parse", "autoscribe/inflight"]).unwrap(),
            bad_ref
        );
        let log = fs::read_to_string(&calls).unwrap();
        assert_eq!(
            log.lines()
                .filter(|line| *line == "export list-pending")
                .count(),
            1
        );
        assert!(!log.contains("extract-selected cnt.bad"));
        assert!(!log.contains("extract-selected cnt.missing"));
        assert!(log.contains("update-exports result.good"));
        let output = git::read_version(
            good.path(),
            VersionRequest {
                revision: "autoscribe/inflight".into(),
                path: "One.md".into(),
            },
        )
        .unwrap();
        let expected = source.replace("Original\r\n", "Replacement\n");
        assert_eq!(output, expected.as_bytes());
        assert_eq!(git::head(good.path()).unwrap().0, master);
        assert_eq!(fs::read(good.path().join(".git/index")).unwrap(), index);
        assert_eq!(fs::read(good.path().join("One.md")).unwrap(), user_bytes);
        assert_eq!(
            worker
                .db
                .connection()
                .query_row(
                    "SELECT COUNT(*) FROM response_events WHERE source_slug='cnt.bad'",
                    [],
                    |row| row.get::<_, i64>(0)
                )
                .unwrap(),
            0
        );
    }

    #[test]
    fn frontmatter_bytes_are_preserved_and_malformed_blocks_fail() {
        for source in [
            "---\nslug: cnt.one\n# comment\nstatus: draft\n---\nold",
            "---\r\nslug: cnt.one\r\nquoted: 'a: b'\r\n---\r\nold",
        ] {
            assert_eq!(
                preserve_frontmatter(source, " new\n").unwrap(),
                source.replace("old", " new\n")
            );
        }
        assert!(preserve_frontmatter("---\nslug: cnt.one\n", "body").is_err());
    }
    #[test]
    fn dispatch_source_mismatch_fails_before_inflight_write() {
        let root = TestDirectory::new("dispatch-mismatch");
        committed_repository(root.path(), "cnt.original");
        git(
            root.path(),
            &[
                "commit",
                "--quiet",
                "--allow-empty",
                "-m",
                "Dispatch\n\nAutoscribe-Plan: plan.test\nAutoscribe-Document: cnt.one",
            ],
        );
        fs::write(
            root.path().join("One.md"),
            "---\nslug: cnt.one\n---\nUser edit\n",
        )
        .unwrap();
        let worker = worker(root.path(), PathBuf::from("pandoc"));
        worker.register_repository(root.path()).unwrap();
        let error = worker.dispatch_once().unwrap_err().to_string();
        assert!(
            error.contains("committed source slug does not match"),
            "{error}"
        );
        assert!(
            git_text(
                root.path(),
                &["rev-parse", "--verify", "autoscribe/inflight"]
            )
            .is_err()
        );
    }
}
