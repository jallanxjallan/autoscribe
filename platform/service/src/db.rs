use crate::{ServiceError, ServiceResult};
use rusqlite::{Connection, OptionalExtension, params};
use std::{
    env, fs,
    path::{Path, PathBuf},
};

#[derive(Debug)]
pub struct Database {
    connection: Connection,
}

#[derive(Debug, Clone)]
pub struct SlugRoute {
    pub repository_root: PathBuf,
    pub source_path: PathBuf,
    pub dispatch_identity: Option<String>,
    pub source_commit: Option<String>,
    pub inflight_commit: Option<String>,
}

impl Database {
    pub fn memory() -> ServiceResult<Self> {
        let connection = Connection::open_in_memory().map_err(storage)?;
        Self::from_connection(connection)
    }

    /// Open the installation-wide client operational ledger.
    pub fn client() -> ServiceResult<Self> {
        let path = client_database_path()?;
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).map_err(|error| ServiceError::Io(error.to_string()))?;
        }
        let connection = Connection::open(&path).map_err(storage)?;
        connection
            .busy_timeout(std::time::Duration::from_secs(5))
            .map_err(storage)?;
        connection
            .execute_batch("PRAGMA journal_mode = WAL; PRAGMA foreign_keys = ON;")
            .map_err(storage)?;
        Self::from_connection(connection)
    }

    fn from_connection(connection: Connection) -> ServiceResult<Self> {
        connection
            .execute_batch("PRAGMA foreign_keys = ON;")
            .map_err(storage)?;
        let db = Self { connection };
        db.migrate()?;
        Ok(db)
    }

    pub(crate) fn connection(&self) -> &Connection {
        &self.connection
    }

    fn migrate(&self) -> ServiceResult<()> {
        self.connection.execute_batch(r#"
            CREATE TABLE IF NOT EXISTS worker_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event TEXT NOT NULL,
                detail TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS repositories (
                repository_id INTEGER PRIMARY KEY,
                canonical_root TEXT NOT NULL UNIQUE,
                last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS repository_attention (
                repository_id INTEGER PRIMARY KEY REFERENCES repositories(repository_id) ON DELETE CASCADE,
                attention_created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_commit_seen TEXT
            );

            CREATE TABLE IF NOT EXISTS repository_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                repository_root TEXT NOT NULL,
                event TEXT NOT NULL,
                head TEXT,
                detail TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS repository_activity (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                repository_root TEXT NOT NULL,
                activity_score INTEGER NOT NULL,
                activity_delta INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS file_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                repository_root TEXT NOT NULL,
                source_path TEXT NOT NULL,
                event TEXT NOT NULL CHECK (event IN ('seen','removed')),
                slug TEXT,
                blob_hash TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS integrity_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,
                slug TEXT,
                repository_root TEXT,
                source_path TEXT,
                detail TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS dispatch_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                repository_root TEXT NOT NULL,
                dispatch_identity TEXT NOT NULL,
                event TEXT NOT NULL,
                plan_identity TEXT,
                source_commit TEXT,
                inflight_commit TEXT,
                detail TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS dispatch_sources (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                dispatch_identity TEXT NOT NULL,
                repository_root TEXT NOT NULL,
                source_slug TEXT NOT NULL,
                source_path TEXT NOT NULL,
                source_blob TEXT NOT NULL,
                source_commit TEXT NOT NULL,
                inflight_commit TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS expected_responses (
                dispatch_identity TEXT NOT NULL,
                source_slug TEXT NOT NULL,
                repository_root TEXT NOT NULL,
                dispatched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                response_seen_at TEXT,
                written_at TEXT,
                state TEXT NOT NULL DEFAULT 'expected',
                PRIMARY KEY(dispatch_identity, source_slug)
            );

            CREATE TABLE IF NOT EXISTS response_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                repository_root TEXT NOT NULL,
                source_slug TEXT NOT NULL,
                event TEXT NOT NULL,
                result_identity TEXT,
                call_identity TEXT,
                inflight_commit TEXT,
                detail TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS export_ready (
                source_slug TEXT PRIMARY KEY,
                observed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE VIEW IF NOT EXISTS active_files AS
            WITH latest AS (
                SELECT repository_root, source_path, MAX(sequence) AS sequence
                FROM file_events GROUP BY repository_root, source_path
            )
            SELECT f.repository_root, f.source_path, f.slug, f.blob_hash, f.sequence
            FROM file_events f JOIN latest l USING(repository_root, source_path, sequence)
            WHERE f.event='seen';

            CREATE VIEW IF NOT EXISTS duplicate_slugs AS
            SELECT slug, COUNT(*) AS copies
            FROM active_files
            WHERE slug IS NOT NULL AND slug <> ''
            GROUP BY slug HAVING COUNT(*) > 1;

            CREATE VIEW IF NOT EXISTS unique_slug_routes AS
            SELECT slug, MIN(repository_root) AS repository_root, MIN(source_path) AS source_path
            FROM active_files
            WHERE slug IS NOT NULL AND slug <> ''
            GROUP BY slug HAVING COUNT(*) = 1;

            CREATE VIEW IF NOT EXISTS latest_dispatch_for_slug AS
            SELECT ds.source_slug, ds.dispatch_identity, ds.repository_root, ds.source_path, ds.source_commit, ds.inflight_commit
            FROM dispatch_sources ds
            WHERE ds.sequence = (
                SELECT MAX(ds2.sequence) FROM dispatch_sources ds2
                WHERE ds2.source_slug = ds.source_slug
            );

            CREATE VIEW IF NOT EXISTS slug_routes AS
            SELECT d.source_slug AS slug, d.repository_root, d.source_path,
                   d.dispatch_identity, d.source_commit, d.inflight_commit
            FROM latest_dispatch_for_slug d
            JOIN unique_slug_routes active
              ON active.slug=d.source_slug
             AND active.repository_root=d.repository_root
             AND active.source_path=d.source_path
            LEFT JOIN duplicate_slugs duplicates ON duplicates.slug=d.source_slug
            WHERE duplicates.slug IS NULL;


            CREATE VIEW IF NOT EXISTS missing_responses AS
            SELECT d.dispatch_identity, d.repository_root, d.source_slug, d.source_path,
                   d.source_commit, d.inflight_commit
            FROM latest_dispatch_for_slug d
            LEFT JOIN export_ready e ON e.source_slug=d.source_slug
            WHERE e.source_slug IS NULL;
        "#).map_err(storage)
    }
}

pub fn record_attention(db: &Database, root: &Path, head: Option<&str>) -> ServiceResult<()> {
    let root = root.to_string_lossy();
    db.connection.execute(
        "INSERT INTO repositories(canonical_root,last_seen_at) VALUES(?1,CURRENT_TIMESTAMP) ON CONFLICT(canonical_root) DO UPDATE SET last_seen_at=CURRENT_TIMESTAMP",
        [root.as_ref()],
    ).map_err(storage)?;
    db.connection.execute(
        "INSERT INTO repository_attention(repository_id,last_commit_seen) SELECT repository_id,?2 FROM repositories WHERE canonical_root=?1 ON CONFLICT(repository_id) DO UPDATE SET last_commit_seen=excluded.last_commit_seen",
        params![root.as_ref(), head],
    ).map_err(storage)?;
    Ok(())
}

pub fn pending_repositories(db: &Database) -> ServiceResult<Vec<PathBuf>> {
    let mut statement = db.connection.prepare(
        "SELECT r.canonical_root FROM repository_attention a JOIN repositories r USING(repository_id) ORDER BY a.attention_created_at"
    ).map_err(storage)?;
    statement
        .query_map([], |row| row.get::<_, String>(0))
        .map_err(storage)?
        .map(|row| row.map(PathBuf::from).map_err(storage))
        .collect()
}

pub fn known_repositories(db: &Database) -> ServiceResult<Vec<PathBuf>> {
    let mut statement = db
        .connection
        .prepare("SELECT canonical_root FROM repositories ORDER BY canonical_root")
        .map_err(storage)?;
    statement
        .query_map([], |row| row.get::<_, String>(0))
        .map_err(storage)?
        .map(|row| row.map(PathBuf::from).map_err(storage))
        .collect()
}

pub fn clear_attention(db: &Database, root: &Path) -> ServiceResult<()> {
    db.connection.execute(
        "DELETE FROM repository_attention WHERE repository_id=(SELECT repository_id FROM repositories WHERE canonical_root=?1)",
        [root.to_string_lossy().as_ref()],
    ).map_err(storage)?;
    Ok(())
}

pub fn worker_event(db: &Database, event: &str, detail: Option<&str>) -> ServiceResult<()> {
    db.connection
        .execute(
            "INSERT INTO worker_events(event,detail) VALUES(?1,?2)",
            params![event, detail],
        )
        .map_err(storage)?;
    Ok(())
}

pub fn repository_event(
    db: &Database,
    root: &Path,
    event: &str,
    head: Option<&str>,
    detail: Option<&str>,
) -> ServiceResult<()> {
    db.connection
        .execute(
            "INSERT INTO repository_events(repository_root,event,head,detail) VALUES(?1,?2,?3,?4)",
            params![root.to_string_lossy(), event, head, detail],
        )
        .map_err(storage)?;
    Ok(())
}

pub fn repository_activity(
    db: &Database,
    root: &Path,
    score: u64,
    delta: u64,
) -> ServiceResult<()> {
    let score = score.min(i64::MAX as u64) as i64;
    let delta = delta.min(i64::MAX as u64) as i64;
    db.connection.execute(
        "INSERT INTO repository_activity(repository_root,activity_score,activity_delta) VALUES(?1,?2,?3)",
        params![root.to_string_lossy(), score, delta],
    ).map_err(storage)?;
    Ok(())
}

pub fn file_seen(
    db: &Database,
    root: &Path,
    path: &Path,
    slug: Option<&str>,
    blob: Option<&str>,
) -> ServiceResult<()> {
    db.connection.execute("INSERT INTO file_events(repository_root,source_path,event,slug,blob_hash) VALUES(?1,?2,'seen',?3,?4)",
        params![root.to_string_lossy(), path.to_string_lossy(), slug, blob]).map_err(storage)?;
    Ok(())
}

pub fn file_removed(db: &Database, root: &Path, path: &Path) -> ServiceResult<()> {
    db.connection
        .execute(
            "INSERT INTO file_events(repository_root,source_path,event) VALUES(?1,?2,'removed')",
            params![root.to_string_lossy(), path.to_string_lossy()],
        )
        .map_err(storage)?;
    Ok(())
}

pub fn repository_removed(db: &Database, root: &Path) -> ServiceResult<()> {
    for (path, _slug, _blob) in active_files(db, root)? {
        file_removed(db, root, &path)?;
    }
    Ok(())
}

pub fn latest_repository_head(db: &Database, root: &Path) -> ServiceResult<Option<String>> {
    db.connection.query_row(
        "SELECT head FROM repository_events WHERE repository_root=?1 AND head IS NOT NULL ORDER BY sequence DESC LIMIT 1",
        [root.to_string_lossy().as_ref()],
        |row| row.get(0),
    ).optional().map_err(storage)
}

pub fn active_files(
    db: &Database,
    root: &Path,
) -> ServiceResult<Vec<(PathBuf, Option<String>, Option<String>)>> {
    let mut statement = db
        .connection
        .prepare("SELECT source_path,slug,blob_hash FROM active_files WHERE repository_root=?1")
        .map_err(storage)?;
    statement
        .query_map([root.to_string_lossy().as_ref()], |row| {
            Ok((
                PathBuf::from(row.get::<_, String>(0)?),
                row.get(1)?,
                row.get(2)?,
            ))
        })
        .map_err(storage)?
        .map(|row| row.map_err(storage))
        .collect()
}

pub fn route_slug(db: &Database, slug: &str) -> ServiceResult<Option<SlugRoute>> {
    db.connection.query_row("SELECT repository_root,source_path,dispatch_identity,source_commit,inflight_commit FROM slug_routes WHERE slug=?1", [slug], |row| {
        Ok(SlugRoute { repository_root: PathBuf::from(row.get::<_,String>(0)?), source_path: PathBuf::from(row.get::<_,String>(1)?), dispatch_identity: row.get(2)?, source_commit: row.get(3)?, inflight_commit: row.get(4)? })
    }).optional().map_err(storage)
}

pub fn duplicate_slugs(db: &Database) -> ServiceResult<Vec<(String, u32)>> {
    let mut statement = db
        .connection
        .prepare("SELECT slug,copies FROM duplicate_slugs ORDER BY slug")
        .map_err(storage)?;
    statement
        .query_map([], |row| Ok((row.get(0)?, row.get::<_, u32>(1)?)))
        .map_err(storage)?
        .map(|row| row.map_err(storage))
        .collect()
}

pub fn integrity_event_seen(
    db: &Database,
    kind: &str,
    slug: Option<&str>,
    root: Option<&Path>,
    path: Option<&Path>,
) -> ServiceResult<bool> {
    let count: i64 = db.connection.query_row(
        "SELECT COUNT(*) FROM integrity_events WHERE kind=?1 AND COALESCE(slug,'')=COALESCE(?2,'') AND COALESCE(repository_root,'')=COALESCE(?3,'') AND COALESCE(source_path,'')=COALESCE(?4,'')",
        params![kind, slug, root.map(|p| p.to_string_lossy().into_owned()), path.map(|p| p.to_string_lossy().into_owned())],
        |row| row.get(0),
    ).map_err(storage)?;
    Ok(count > 0)
}

pub fn integrity_event(
    db: &Database,
    kind: &str,
    slug: Option<&str>,
    root: Option<&Path>,
    path: Option<&Path>,
    detail: &str,
) -> ServiceResult<()> {
    db.connection.execute("INSERT INTO integrity_events(kind,slug,repository_root,source_path,detail) VALUES(?1,?2,?3,?4,?5)", params![
        kind, slug, root.map(|p| p.to_string_lossy().into_owned()), path.map(|p| p.to_string_lossy().into_owned()), detail
    ]).map_err(storage)?;
    Ok(())
}

pub fn dispatch_event(
    db: &Database,
    root: &Path,
    dispatch: &str,
    event: &str,
    plan: Option<&str>,
    source_commit: Option<&str>,
    inflight_commit: Option<&str>,
    detail: Option<&str>,
) -> ServiceResult<()> {
    db.connection.execute("INSERT INTO dispatch_events(repository_root,dispatch_identity,event,plan_identity,source_commit,inflight_commit,detail) VALUES(?1,?2,?3,?4,?5,?6,?7)",
        params![root.to_string_lossy(), dispatch, event, plan, source_commit, inflight_commit, detail]).map_err(storage)?;
    Ok(())
}

pub fn dispatch_source(
    db: &Database,
    dispatch: &str,
    root: &Path,
    slug: &str,
    path: &Path,
    blob: &str,
    source_commit: &str,
    inflight_commit: &str,
) -> ServiceResult<()> {
    db.connection.execute("INSERT INTO dispatch_sources(dispatch_identity,repository_root,source_slug,source_path,source_blob,source_commit,inflight_commit) VALUES(?1,?2,?3,?4,?5,?6,?7)",
        params![dispatch, root.to_string_lossy(), slug, path.to_string_lossy(), blob, source_commit, inflight_commit]).map_err(storage)?;
    Ok(())
}

pub fn dispatch_event_seen(db: &Database, dispatch: &str, event: &str) -> ServiceResult<bool> {
    let count: i64 = db
        .connection
        .query_row(
            "SELECT COUNT(*) FROM dispatch_events WHERE dispatch_identity=?1 AND event=?2",
            params![dispatch, event],
            |row| row.get(0),
        )
        .map_err(storage)?;
    Ok(count > 0)
}

pub fn expect_dispatch_responses(db: &Database, dispatch: &str) -> ServiceResult<()> {
    db.connection.execute(
        "INSERT OR IGNORE INTO expected_responses(dispatch_identity,source_slug,repository_root) SELECT dispatch_identity,source_slug,repository_root FROM dispatch_sources WHERE dispatch_identity=?1",
        [dispatch],
    ).map_err(storage)?;
    Ok(())
}

pub fn response_observed(
    db: &Database,
    dispatch: &str,
    slug: &str,
    written: bool,
) -> ServiceResult<()> {
    db.connection.execute(
        "UPDATE expected_responses SET response_seen_at=COALESCE(response_seen_at,CURRENT_TIMESTAMP), written_at=CASE WHEN ?3 THEN CURRENT_TIMESTAMP ELSE written_at END, state=CASE WHEN ?3 THEN 'written' ELSE 'observed' END WHERE dispatch_identity=?1 AND source_slug=?2",
        params![dispatch, slug, written],
    ).map_err(storage)?;
    Ok(())
}

pub fn response_event(
    db: &Database,
    root: &Path,
    slug: &str,
    event: &str,
    result: Option<&str>,
    call: Option<&str>,
    inflight_commit: Option<&str>,
    detail: Option<&str>,
) -> ServiceResult<()> {
    db.connection.execute("INSERT INTO response_events(repository_root,source_slug,event,result_identity,call_identity,inflight_commit,detail) VALUES(?1,?2,?3,?4,?5,?6,?7)",
        params![root.to_string_lossy(), slug, event, result, call, inflight_commit, detail]).map_err(storage)?;
    Ok(())
}

pub fn replace_export_ready<'a>(
    db: &Database,
    slugs: impl IntoIterator<Item = &'a String>,
) -> ServiceResult<()> {
    db.connection
        .execute("DELETE FROM export_ready", [])
        .map_err(storage)?;
    for slug in slugs {
        db.connection.execute("INSERT OR REPLACE INTO export_ready(source_slug,observed_at) VALUES(?1,CURRENT_TIMESTAMP)", [slug]).map_err(storage)?;
    }
    Ok(())
}

pub fn missing_response_slugs(db: &Database) -> ServiceResult<Vec<String>> {
    let mut statement = db
        .connection
        .prepare("SELECT source_slug FROM missing_responses ORDER BY source_slug")
        .map_err(storage)?;
    statement
        .query_map([], |row| row.get(0))
        .map_err(storage)?
        .map(|row| row.map_err(storage))
        .collect()
}

pub fn snapshot(db: &Database) -> ServiceResult<serde_json::Value> {
    let scalar = |sql: &str| {
        db.connection
            .query_row(sql, [], |row| row.get::<_, i64>(0))
            .map_err(storage)
    };
    Ok(serde_json::json!({
        "repositories": scalar("SELECT COUNT(DISTINCT repository_root) FROM active_files")?,
        "repository_activity_events": scalar("SELECT COUNT(*) FROM repository_activity")?,
        "files": scalar("SELECT COUNT(*) FROM active_files")?,
        "unique_slugs": scalar("SELECT COUNT(*) FROM unique_slug_routes")?,
        "duplicate_slugs": scalar("SELECT COUNT(*) FROM duplicate_slugs")?,
        "dispatch_events": scalar("SELECT COUNT(*) FROM dispatch_events")?,
        "response_events": scalar("SELECT COUNT(*) FROM response_events")?,
        "expected_responses": scalar("SELECT COUNT(*) FROM expected_responses")?,
        "late_responses": scalar("SELECT COUNT(*) FROM expected_responses WHERE response_seen_at IS NULL AND dispatched_at < datetime('now','-10 minutes')")?,
        "integrity_events": scalar("SELECT COUNT(*) FROM integrity_events")?
    }))
}

fn storage(error: rusqlite::Error) -> ServiceError {
    ServiceError::Storage(error.to_string())
}

/// Deterministic vault-scoped state path. No registry is required.
pub fn client_database_path() -> ServiceResult<PathBuf> {
    if let Some(path) = env::var_os("AUTOSCRIBE_CLIENT_DB") {
        return Ok(PathBuf::from(path));
    }
    let home = env::var_os("HOME")
        .map(PathBuf::from)
        .ok_or_else(|| ServiceError::InvalidInput("HOME is not set".into()))?;
    Ok(home.join(".local/share/autoscribe/service.sqlite"))
}

pub fn vault_key(repository_root: &Path) -> ServiceResult<String> {
    let name = repository_root
        .file_name()
        .and_then(|v| v.to_str())
        .ok_or_else(|| {
            ServiceError::InvalidInput(format!(
                "vault has no usable directory name: {}",
                repository_root.display()
            ))
        })?;
    let snake = snake_case(name);
    if snake.is_empty() {
        Err(ServiceError::InvalidInput(
            "empty normalized vault name".into(),
        ))
    } else {
        Ok(snake)
    }
}

fn snake_case(value: &str) -> String {
    let mut out = String::new();
    let mut prev_sep = false;
    for ch in value.chars() {
        if ch.is_ascii_alphanumeric() {
            if ch.is_ascii_uppercase()
                && !out.is_empty()
                && !prev_sep
                && out.chars().last().is_some_and(|c| c.is_ascii_lowercase())
            {
                out.push('_');
            }
            out.push(ch.to_ascii_lowercase());
            prev_sep = false;
        } else if !out.is_empty() && !prev_sep {
            out.push('_');
            prev_sep = true;
        }
    }
    while out.ends_with('_') {
        out.pop();
    }
    out
}
