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
    path::{Path, PathBuf},
    process::{Command, Stdio},
    time::{Duration, Instant},
};

#[derive(Debug)]
pub struct Worker {
    db: Database,
    repositories: RefCell<BTreeMap<PathBuf, RepositorySession>>,
    asc: PathBuf,
    pandoc: PathBuf,
    pandoc_filter: PathBuf,
    poll: Duration,
    repository_ttl: Duration,
}

#[derive(Debug)]
struct RepositorySession {
    initialized: bool,
    activity_score: u64,
    last_attention: Instant,
    last_activity: Instant,
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
    /// Create a one-pass worker for diagnostics without opening the system
    /// attention socket.
    pub fn diagnostic(repositories: Vec<PathBuf>, asc: PathBuf) -> ServiceResult<Self> {
        if repositories.is_empty() {
            return Err(ServiceError::InvalidInput(
                "scan requires at least one repository path".into(),
            ));
        }
        let worker = Self::create(
            Database::memory()?,
            asc,
            Duration::ZERO,
            Duration::from_secs(u64::MAX),
        )?;
        for path in repositories {
            worker.register_repository(&path)?;
        }
        Ok(worker)
    }

    fn create(
        db: Database,
        asc: PathBuf,
        poll: Duration,
        repository_ttl: Duration,
    ) -> ServiceResult<Self> {
        if repository_ttl.is_zero() {
            return Err(ServiceError::InvalidInput(
                "repository TTL must be greater than zero".into(),
            ));
        }
        let pandoc = std::env::var_os("AUTOSCRIBE_PANDOC")
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from("/usr/bin/pandoc"));
        let pandoc_filter = std::env::var_os("AUTOSCRIBE_PANDOC_FILTER")
            .map(PathBuf::from)
            .unwrap_or_else(|| {
                std::env::var_os("HOME")
                    .map(PathBuf::from)
                    .unwrap_or_default()
                    .join("Work/Loom/platform/pandoc/filters/emit/emit_ndjson.lua")
            });
        Ok(Self {
            db,
            repositories: RefCell::new(BTreeMap::new()),
            asc,
            pandoc,
            pandoc_filter,
            poll,
            repository_ttl,
        })
    }

    /// Create a one-vault worker backed by that vault's permanent client database.
    pub fn persistent(repository: &Path, asc: PathBuf) -> ServiceResult<Self> {
        let root = git::root(repository)?;
        let db = Database::client()?;
        let worker = Self::create(db, asc, Duration::ZERO, Duration::from_secs(u64::MAX))?;
        worker.register_repository(&root)?;
        Ok(worker)
    }

    /// Inspect a signalled vault and submit any newly declared dispatches.
    pub fn dispatch_once(&self) -> ServiceResult<()> {
        self.scan_all()?;
        self.reconcile_dispatches()
    }

    /// Inspect a signalled vault, load pending export-ready slugs, and materialize responses.
    pub fn responses_once(&self) -> ServiceResult<()> {
        self.scan_all()?;
        let ready = pending_export_slugs(&self.asc)?;
        db::replace_export_ready(&self.db, ready.iter())?;
        self.reconcile_exports()
    }

    pub fn register_repository(&self, path: &Path) -> ServiceResult<PathBuf> {
        let root = git::root(path)?;
        let now = Instant::now();
        let previously_seen = db::latest_repository_head(&self.db, &root)?.is_some();
        self.repositories
            .borrow_mut()
            .entry(root.clone())
            .and_modify(|session| session.last_attention = now)
            .or_insert(RepositorySession {
                initialized: previously_seen,
                activity_score: 0,
                last_attention: now,
                last_activity: now,
            });
        Ok(root)
    }

    pub fn database(&self) -> &Database {
        &self.db
    }

    pub fn startup(&self) -> ServiceResult<()> {
        db::worker_event(&self.db, "started", None)?;
        self.scan_all()?;
        if self.repository_paths().is_empty() {
            return Ok(());
        }
        self.reconcile_dispatches()?;
        self.reconcile_exports()?;
        Ok(())
    }

    pub fn run(&self, once: bool) -> ServiceResult<()> {
        self.startup()?;
        if once {
            return Ok(());
        }
        loop {
            self.pass()?;
            std::thread::sleep(self.poll);
        }
    }

    pub fn pass(&self) -> ServiceResult<()> {
        self.expire_repositories()?;
        self.scan_all()?;
        if self.repository_paths().is_empty() {
            return db::worker_event(&self.db, "pass_completed", Some("no repositories"));
        }
        self.reconcile_dispatches()?;
        self.reconcile_exports()?;
        db::worker_event(&self.db, "pass_completed", None)
    }

    fn expire_repositories(&self) -> ServiceResult<()> {
        let now = Instant::now();
        let mut expired = Vec::new();
        self.repositories.borrow_mut().retain(|path, session| {
            let last_signal = session.last_attention.max(session.last_activity);
            let keep = now.duration_since(last_signal) < self.repository_ttl;
            if !keep {
                expired.push(path.clone());
            }
            keep
        });
        for path in expired {
            db::repository_removed(&self.db, &path)?;
            db::worker_event(
                &self.db,
                "repository_expired",
                Some(&path.to_string_lossy()),
            )?;
        }
        Ok(())
    }

    fn repository_paths(&self) -> Vec<PathBuf> {
        let mut repositories = self
            .repositories
            .borrow()
            .iter()
            .map(|(path, session)| (path.clone(), session.activity_score))
            .collect::<Vec<_>>();
        repositories.sort_by(|(left_path, left_score), (right_path, right_score)| {
            right_score
                .cmp(left_score)
                .then_with(|| left_path.cmp(right_path))
        });
        repositories
            .into_iter()
            .map(|(path, _score)| path)
            .collect()
    }

    fn scan_all(&self) -> ServiceResult<()> {
        let repositories = self.repository_paths();
        for repository in &repositories {
            let startup = self
                .repositories
                .borrow()
                .get(repository)
                .is_some_and(|session| !session.initialized);
            let activity = self.scan_repository(repository, startup)?;
            let now = Instant::now();
            if let Some(session) = self.repositories.borrow_mut().get_mut(repository) {
                session.initialized = true;
                session.activity_score = session.activity_score.saturating_mul(3) / 4;
                session.activity_score = session.activity_score.saturating_add(activity);
                if activity > 0 {
                    session.last_activity = now;
                }
                db::repository_activity(&self.db, repository, session.activity_score, activity)?;
            }
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

    fn scan_repository(&self, repository: &Path, startup: bool) -> ServiceResult<u64> {
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
            return Ok(0);
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

        let mut activity = 0_u64;
        for path in changed {
            let absolute = repository.join(&path);
            if !absolute.is_file() {
                if previous.contains_key(&path) {
                    db::file_removed(&self.db, repository, &path)?;
                    activity = activity.saturating_add(15);
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
                activity = activity.saturating_add(if prior.is_some() { 10 } else { 15 });
                if let Some(slug) = slug.as_deref() {
                    self.once_only_duplicate_check(slug)?;
                }
                self.check_neighbor_dir(repository, &path)?;
            }
        }

        if previous_head.as_deref() != Some(head.as_str()) {
            db::repository_event(&self.db, repository, "head_observed", Some(&head), None)?;
        }
        Ok(activity)
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

    fn once_only_duplicate_check(&self, slug: &str) -> ServiceResult<()> {
        let needle = format!("slug: {slug}");
        let mut hits = Vec::new();
        for repository in self.repository_paths() {
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

    fn reconcile_dispatches(&self) -> ServiceResult<()> {
        for repository in self.repository_paths() {
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

                let sources = source_records_at(&repository, &commit, &trailers.documents)?;
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

                match self.submit_dispatch(
                    &repository,
                    &commit,
                    &dispatch,
                    &plan,
                    &trailers.documents,
                ) {
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
                    }
                }
            }
        }
        Ok(())
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
        documents: &[String],
    ) -> ServiceResult<()> {
        let pending = pending_export_slugs(&self.asc)?;
        let blocked = documents
            .iter()
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
            .build_calls(&worktree, plan, documents)
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
        documents: &[String],
    ) -> ServiceResult<Vec<Value>> {
        if !self.pandoc_filter.is_file() {
            return Err(ServiceError::InvalidInput(format!(
                "Pandoc filter not found: {}",
                self.pandoc_filter.display()
            )));
        }
        let resolved = resolve_slugs_in_tree(worktree, documents)?;
        let mut jobs = Vec::new();
        for (slug, relative) in &resolved {
            let source = worktree.join(relative);
            jobs.push(PandocJob {
                identity: slug.clone(),
                working_directory: worktree.to_path_buf(),
                arguments: vec![
                    source.to_string_lossy().into_owned(),
                    "--from=markdown+yaml_metadata_block+fenced_divs".into(),
                    format!("--lua-filter={}", self.pandoc_filter.display()),
                    "--to=native".into(),
                    "--output=/dev/null".into(),
                ],
            });
        }
        let parallelism = std::thread::available_parallelism()
            .map(usize::from)
            .unwrap_or(2)
            .max(2);
        let outcomes = pandoc::run_parallel(&self.pandoc, jobs, parallelism)?;
        let mut calls = Vec::new();
        for ((expected_slug, relative), outcome) in resolved.iter().zip(outcomes) {
            if outcome.exit_code != Some(0) || outcome.error.is_some() {
                let detail = outcome
                    .error
                    .unwrap_or_else(|| String::from_utf8_lossy(&outcome.stderr).trim().into());
                return Err(ServiceError::Storage(format!(
                    "{}: Pandoc conversion failed: {detail}",
                    relative.display()
                )));
            }
            let text = std::str::from_utf8(&outcome.stdout)
                .map_err(|error| ServiceError::InvalidInput(error.to_string()))?;
            let line = text
                .lines()
                .find(|line| line.trim_start().starts_with('{'))
                .ok_or_else(|| {
                    ServiceError::InvalidInput(format!(
                        "{}: Pandoc emitted no NDJSON record",
                        relative.display()
                    ))
                })?;
            let record: Value = serde_json::from_str(line)
                .map_err(|error| ServiceError::InvalidInput(error.to_string()))?;
            let identity = record
                .get("record_identity")
                .and_then(Value::as_str)
                .unwrap_or("")
                .trim();
            if identity != expected_slug {
                return Err(ServiceError::Conflict(format!(
                    "{}: expected slug {}, Pandoc emitted {}",
                    relative.display(),
                    expected_slug,
                    identity
                )));
            }
            let payload = record
                .get("payload")
                .and_then(Value::as_object)
                .ok_or_else(|| {
                    ServiceError::InvalidInput(format!(
                        "{identity}: Pandoc payload must be an object"
                    ))
                })?;
            let content = payload.get("content").and_then(Value::as_str).unwrap_or("");
            if content.trim().is_empty() {
                return Err(ServiceError::InvalidInput(format!(
                    "{identity}: Pandoc content is blank"
                )));
            }
            let metadata = payload
                .iter()
                .filter(|(key, _)| key.as_str() != "content")
                .map(|(key, value)| (key.clone(), value.clone()))
                .collect::<serde_json::Map<_, _>>();
            let mut call = serde_json::json!({
                "type":"call",
                "identity":identity,
                "content":content,
                "plan":plan,
                "extra":{
                    "filename_hint":relative.file_name().and_then(|name|name.to_str()).unwrap_or(expected_slug),
                    "source_path":relative.to_string_lossy().replace('\\',"/"),
                    "metadata":metadata
                }
            });
            if let Some(directive) = record
                .get("directive")
                .and_then(Value::as_str)
                .map(str::trim)
                .filter(|value| !value.is_empty())
            {
                call["directive"] = Value::String(directive.into());
            }
            calls.push(call);
        }
        Ok(calls)
    }

    fn reconcile_exports(&self) -> ServiceResult<()> {
        for slug in pending_export_slugs(&self.asc)? {
            let Some(route) = db::route_slug(&self.db, &slug)? else {
                db::integrity_event(
                    &self.db,
                    "unroutable_export",
                    Some(&slug),
                    None,
                    None,
                    "pending export slug did not resolve to exactly one active repository",
                )?;
                continue;
            };
            let Some(dispatch) = route.dispatch_identity.as_deref() else {
                db::integrity_event(
                    &self.db,
                    "unroutable_export",
                    Some(&slug),
                    Some(&route.repository_root),
                    Some(&route.source_path),
                    "slug has no dispatch lineage in worker memory",
                )?;
                continue;
            };
            let Some(inflight_source_commit) = route.inflight_commit.as_deref() else {
                continue;
            };
            db::response_event(
                &self.db,
                &route.repository_root,
                &slug,
                "export_seen",
                None,
                None,
                None,
                None,
            )?;
            let records = extract_slug(&self.asc, &slug)?;
            for record in records {
                let result =
                    first_string(&record, &["result_identity", "identity", "call_identity"])?;
                let call = first_string(&record, &["call_identity", "identity"])?;
                let content = first_string(&record, &["record_content", "content"])?;
                let source_bytes = git::read_version(
                    &route.repository_root,
                    VersionRequest {
                        revision: inflight_source_commit.to_string(),
                        path: route.source_path.clone(),
                    },
                )?;
                let source = String::from_utf8(source_bytes)
                    .map_err(|error| ServiceError::InvalidInput(error.to_string()))?;
                if frontmatter_slug(&source).as_deref() != Some(slug.as_str()) {
                    db::integrity_event(
                        &self.db,
                        "response_source_mismatch",
                        Some(&slug),
                        Some(&route.repository_root),
                        Some(&route.source_path),
                        "dispatch snapshot slug does not match pending export",
                    )?;
                    continue;
                }
                let replacement =
                    set_document_review_metadata(&preserve_frontmatter(&source, &content)?)?;
                let snapshot = if let Some(existing) =
                    response_snapshot_for_result(&route.repository_root, &result)?
                {
                    existing
                } else {
                    git::append_response_snapshot(
                        &route.repository_root,
                        dispatch,
                        &result,
                        &slug,
                        "saved",
                        &route.source_path,
                        replacement.as_bytes(),
                    )?
                    .0
                };
                db::response_event(
                    &self.db,
                    &route.repository_root,
                    &slug,
                    "materialized",
                    Some(&result),
                    Some(&call),
                    Some(&snapshot),
                    None,
                )?;
                db::response_observed(&self.db, dispatch, &slug, true)?;
                run_asc(&self.asc, &["export", "update-exports", &result], &[])?;
                db::response_event(
                    &self.db,
                    &route.repository_root,
                    &slug,
                    "receipt_recorded",
                    Some(&result),
                    Some(&call),
                    Some(&snapshot),
                    None,
                )?;
            }
        }
        Ok(())
    }
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
    let Some(start) = old.find("---") else {
        return Ok(response.to_string());
    };
    if start != 0 {
        return Ok(response.to_string());
    }
    let rest = &old[3..];
    let Some(end) = rest.find("\n---") else {
        return Ok(response.to_string());
    };
    let frontmatter = &old[..3 + end + 4];
    Ok(format!(
        "{}\n\n{}",
        frontmatter.trim_end(),
        response.trim_start()
    ))
}

fn set_document_review_metadata(text: &str) -> ServiceResult<String> {
    if !text.starts_with("---\n") && !text.starts_with("---\r\n") {
        return Ok(text.to_string());
    }
    let newline = if text.starts_with("---\r\n") {
        "\r\n"
    } else {
        "\n"
    };
    let first_end = text
        .find(newline)
        .ok_or_else(|| ServiceError::InvalidInput("malformed frontmatter".into()))?
        + newline.len();
    let marker = format!("{newline}---");
    let rest = &text[first_end..];
    let Some(relative_end) = rest.find(&marker) else {
        return Err(ServiceError::InvalidInput("malformed frontmatter".into()));
    };
    let end = first_end + relative_end;
    let mut fields = text[first_end..end]
        .lines()
        .filter(|line| {
            let key = line
                .split_once(':')
                .map(|(key, _)| key.trim())
                .unwrap_or("");
            !matches!(key, "status" | "producer")
        })
        .map(str::to_string)
        .collect::<Vec<_>>();
    fields.push("status: needs-review".into());
    fields.push("producer: ai".into());
    let suffix = &text[end + newline.len()..];
    Ok(format!(
        "---{newline}{}{newline}{suffix}",
        fields.join(newline)
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
            if !value.is_empty() {
                plans.push(value.to_string());
            }
        }
        if let Some(value) = line.strip_prefix("Autoscribe-Document:") {
            let value = value.trim();
            if !value.is_empty() {
                documents.push(value.to_string());
            }
        }
    }
    plans.sort();
    plans.dedup();
    documents.sort();
    documents.dedup();
    let plan = match plans.len() {
        0 => None,
        1 => plans.into_iter().next(),
        _ => {
            return Err(ServiceError::InvalidInput(
                "a commit may contain only one distinct Autoscribe-Plan trailer".into(),
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
    repository: &Path,
    commit: &str,
    documents: &[String],
) -> ServiceResult<Vec<(String, PathBuf, String, Vec<u8>)>> {
    let mut records = Vec::new();
    for slug in documents {
        let path = resolve_slug_at(repository, commit, slug)?;
        let spec = format!("{commit}:{}", path.to_string_lossy());
        let bytes = git_bytes(repository, &["show", &spec])?;
        let blob = git_text(repository, &["rev-parse", &spec])?
            .trim()
            .to_string();
        records.push((slug.clone(), path, blob, bytes));
    }
    Ok(records)
}

fn resolve_slug_at(repository: &Path, commit: &str, slug: &str) -> ServiceResult<PathBuf> {
    let needle = format!("slug: {slug}");
    let output = Command::new("git")
        .arg("-C")
        .arg(repository)
        .args(["grep", "-l", "-F", &needle, commit, "--", "*.md"])
        .output()
        .map_err(io)?;
    if !output.status.success() && output.status.code() != Some(1) {
        return Err(ServiceError::Storage(format!(
            "git grep failed for {slug}: {}",
            String::from_utf8_lossy(&output.stderr).trim()
        )));
    }
    let mut matches = Vec::new();
    for raw in String::from_utf8_lossy(&output.stdout).lines() {
        let path_text = raw
            .split_once(':')
            .map(|(_, path)| path)
            .unwrap_or(raw)
            .trim();
        if path_text.is_empty() {
            continue;
        }
        let spec = format!("{commit}:{path_text}");
        let text = String::from_utf8(git_bytes(repository, &["show", &spec])?)
            .map_err(|error| ServiceError::InvalidInput(error.to_string()))?;
        if frontmatter_slug(&text).as_deref() == Some(slug) {
            matches.push(PathBuf::from(path_text));
        }
    }
    match matches.as_slice() {
        [path] => Ok(path.clone()),
        [] => Err(ServiceError::Conflict(format!(
            "document slug was not found at {commit}: {slug}"
        ))),
        _ => Err(ServiceError::Conflict(format!(
            "document slug is duplicated at {commit}: {slug}"
        ))),
    }
}

fn resolve_slugs_in_tree(
    tree: &Path,
    documents: &[String],
) -> ServiceResult<Vec<(String, PathBuf)>> {
    let scanned = scan_markdown(tree)?;
    let mut by_slug: BTreeMap<String, Vec<PathBuf>> = BTreeMap::new();
    for file in scanned {
        if let Some(slug) = file.slug {
            by_slug.entry(slug).or_default().push(file.path);
        }
    }
    documents
        .iter()
        .map(
            |slug| match by_slug.get(slug).map(Vec::as_slice).unwrap_or(&[]) {
                [path] => Ok((slug.clone(), path.clone())),
                [] => Err(ServiceError::Conflict(format!(
                    "document slug was not found: {slug}"
                ))),
                _ => Err(ServiceError::Conflict(format!(
                    "document slug is duplicated: {slug}"
                ))),
            },
        )
        .collect()
}

fn dirty_markdown_paths(repository: &Path) -> ServiceResult<BTreeSet<PathBuf>> {
    let output = Command::new("git")
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
