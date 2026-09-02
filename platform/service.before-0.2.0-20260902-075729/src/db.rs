use crate::{ServiceError, ServiceResult};
use rusqlite::{Connection, OptionalExtension, params};
use std::path::{Path, PathBuf};

#[derive(Debug)]
pub struct Database {
    connection: Connection,
}

#[derive(Debug, Clone)]
pub struct SlugRoute {
    pub vault_root: PathBuf,
    pub source_path: PathBuf,
    pub dispatch_identity: Option<String>,
    pub source_commit: Option<String>,
    pub inflight_commit: Option<String>,
}

impl Database {
    pub fn memory() -> ServiceResult<Self> {
        let connection = Connection::open_in_memory().map_err(storage)?;
        connection.execute_batch("PRAGMA foreign_keys = ON;").map_err(storage)?;
        let db = Self { connection };
        db.migrate()?;
        Ok(db)
    }

    pub(crate) fn connection(&self) -> &Connection { &self.connection }

    fn migrate(&self) -> ServiceResult<()> {
        self.connection.execute_batch(r#"
            CREATE TABLE worker_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event TEXT NOT NULL,
                detail TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE vault_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                vault_root TEXT NOT NULL,
                event TEXT NOT NULL,
                head TEXT,
                detail TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE file_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                vault_root TEXT NOT NULL,
                source_path TEXT NOT NULL,
                event TEXT NOT NULL CHECK (event IN ('seen','removed')),
                slug TEXT,
                blob_hash TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE integrity_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,
                slug TEXT,
                vault_root TEXT,
                source_path TEXT,
                detail TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE dispatch_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                vault_root TEXT NOT NULL,
                dispatch_identity TEXT NOT NULL,
                event TEXT NOT NULL,
                plan_identity TEXT,
                source_commit TEXT,
                inflight_commit TEXT,
                detail TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE dispatch_sources (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                dispatch_identity TEXT NOT NULL,
                vault_root TEXT NOT NULL,
                source_slug TEXT NOT NULL,
                source_path TEXT NOT NULL,
                source_blob TEXT NOT NULL,
                source_commit TEXT NOT NULL,
                inflight_commit TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE response_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                vault_root TEXT NOT NULL,
                source_slug TEXT NOT NULL,
                event TEXT NOT NULL,
                result_identity TEXT,
                call_identity TEXT,
                inflight_commit TEXT,
                detail TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE VIEW active_files AS
            WITH latest AS (
                SELECT vault_root, source_path, MAX(sequence) AS sequence
                FROM file_events GROUP BY vault_root, source_path
            )
            SELECT f.vault_root, f.source_path, f.slug, f.blob_hash, f.sequence
            FROM file_events f JOIN latest l USING(vault_root, source_path, sequence)
            WHERE f.event='seen';

            CREATE VIEW duplicate_slugs AS
            SELECT slug, COUNT(*) AS copies
            FROM active_files
            WHERE slug IS NOT NULL AND slug <> ''
            GROUP BY slug HAVING COUNT(*) > 1;

            CREATE VIEW unique_slug_routes AS
            SELECT slug, MIN(vault_root) AS vault_root, MIN(source_path) AS source_path
            FROM active_files
            WHERE slug IS NOT NULL AND slug <> ''
            GROUP BY slug HAVING COUNT(*) = 1;

            CREATE VIEW latest_dispatch_for_slug AS
            SELECT ds.source_slug, ds.dispatch_identity, ds.vault_root, ds.source_path, ds.source_commit, ds.inflight_commit
            FROM dispatch_sources ds
            WHERE ds.sequence = (
                SELECT MAX(ds2.sequence) FROM dispatch_sources ds2
                WHERE ds2.source_slug = ds.source_slug
            );

            CREATE VIEW slug_routes AS
            SELECT d.source_slug AS slug, d.vault_root, d.source_path,
                   d.dispatch_identity, d.source_commit, d.inflight_commit
            FROM latest_dispatch_for_slug d
            LEFT JOIN duplicate_slugs duplicates ON duplicates.slug=d.source_slug
            WHERE duplicates.slug IS NULL;
        "#).map_err(storage)
    }
}

pub fn worker_event(db: &Database, event: &str, detail: Option<&str>) -> ServiceResult<()> {
    db.connection.execute("INSERT INTO worker_events(event,detail) VALUES(?1,?2)", params![event, detail]).map_err(storage)?;
    Ok(())
}

pub fn vault_event(db: &Database, root: &Path, event: &str, head: Option<&str>, detail: Option<&str>) -> ServiceResult<()> {
    db.connection.execute("INSERT INTO vault_events(vault_root,event,head,detail) VALUES(?1,?2,?3,?4)",
        params![root.to_string_lossy(), event, head, detail]).map_err(storage)?;
    Ok(())
}

pub fn file_seen(db: &Database, root: &Path, path: &Path, slug: Option<&str>, blob: Option<&str>) -> ServiceResult<()> {
    db.connection.execute("INSERT INTO file_events(vault_root,source_path,event,slug,blob_hash) VALUES(?1,?2,'seen',?3,?4)",
        params![root.to_string_lossy(), path.to_string_lossy(), slug, blob]).map_err(storage)?;
    Ok(())
}

pub fn file_removed(db: &Database, root: &Path, path: &Path) -> ServiceResult<()> {
    db.connection.execute("INSERT INTO file_events(vault_root,source_path,event) VALUES(?1,?2,'removed')",
        params![root.to_string_lossy(), path.to_string_lossy()]).map_err(storage)?;
    Ok(())
}

pub fn latest_vault_head(db: &Database, root: &Path) -> ServiceResult<Option<String>> {
    db.connection.query_row(
        "SELECT head FROM vault_events WHERE vault_root=?1 AND head IS NOT NULL ORDER BY sequence DESC LIMIT 1",
        [root.to_string_lossy().as_ref()],
        |row| row.get(0),
    ).optional().map_err(storage)
}

pub fn active_files(db: &Database, root: &Path) -> ServiceResult<Vec<(PathBuf, Option<String>, Option<String>)>> {
    let mut statement = db.connection.prepare("SELECT source_path,slug,blob_hash FROM active_files WHERE vault_root=?1").map_err(storage)?;
    statement.query_map([root.to_string_lossy().as_ref()], |row| Ok((PathBuf::from(row.get::<_,String>(0)?), row.get(1)?, row.get(2)?)))
        .map_err(storage)?.map(|row| row.map_err(storage)).collect()
}

pub fn route_slug(db: &Database, slug: &str) -> ServiceResult<Option<SlugRoute>> {
    db.connection.query_row("SELECT vault_root,source_path,dispatch_identity,source_commit,inflight_commit FROM slug_routes WHERE slug=?1", [slug], |row| {
        Ok(SlugRoute { vault_root: PathBuf::from(row.get::<_,String>(0)?), source_path: PathBuf::from(row.get::<_,String>(1)?), dispatch_identity: row.get(2)?, source_commit: row.get(3)?, inflight_commit: row.get(4)? })
    }).optional().map_err(storage)
}

pub fn duplicate_slugs(db: &Database) -> ServiceResult<Vec<(String,u32)>> {
    let mut statement = db.connection.prepare("SELECT slug,copies FROM duplicate_slugs ORDER BY slug").map_err(storage)?;
    statement.query_map([], |row| Ok((row.get(0)?,row.get::<_,u32>(1)?))).map_err(storage)?
        .map(|row| row.map_err(storage)).collect()
}

pub fn integrity_event_seen(db: &Database, kind: &str, slug: Option<&str>, root: Option<&Path>, path: Option<&Path>) -> ServiceResult<bool> {
    let count: i64 = db.connection.query_row(
        "SELECT COUNT(*) FROM integrity_events WHERE kind=?1 AND COALESCE(slug,'')=COALESCE(?2,'') AND COALESCE(vault_root,'')=COALESCE(?3,'') AND COALESCE(source_path,'')=COALESCE(?4,'')",
        params![kind, slug, root.map(|p| p.to_string_lossy().into_owned()), path.map(|p| p.to_string_lossy().into_owned())],
        |row| row.get(0),
    ).map_err(storage)?;
    Ok(count > 0)
}

pub fn integrity_event(db: &Database, kind: &str, slug: Option<&str>, root: Option<&Path>, path: Option<&Path>, detail: &str) -> ServiceResult<()> {
    db.connection.execute("INSERT INTO integrity_events(kind,slug,vault_root,source_path,detail) VALUES(?1,?2,?3,?4,?5)", params![
        kind, slug, root.map(|p| p.to_string_lossy().into_owned()), path.map(|p| p.to_string_lossy().into_owned()), detail
    ]).map_err(storage)?;
    Ok(())
}

pub fn dispatch_event(db: &Database, root: &Path, dispatch: &str, event: &str, plan: Option<&str>, source_commit: Option<&str>, inflight_commit: Option<&str>, detail: Option<&str>) -> ServiceResult<()> {
    db.connection.execute("INSERT INTO dispatch_events(vault_root,dispatch_identity,event,plan_identity,source_commit,inflight_commit,detail) VALUES(?1,?2,?3,?4,?5,?6,?7)",
        params![root.to_string_lossy(), dispatch, event, plan, source_commit, inflight_commit, detail]).map_err(storage)?;
    Ok(())
}

pub fn dispatch_source(db: &Database, dispatch: &str, root: &Path, slug: &str, path: &Path, blob: &str, source_commit: &str, inflight_commit: &str) -> ServiceResult<()> {
    db.connection.execute("INSERT INTO dispatch_sources(dispatch_identity,vault_root,source_slug,source_path,source_blob,source_commit,inflight_commit) VALUES(?1,?2,?3,?4,?5,?6,?7)",
        params![dispatch, root.to_string_lossy(), slug, path.to_string_lossy(), blob, source_commit, inflight_commit]).map_err(storage)?;
    Ok(())
}

pub fn dispatch_event_seen(db: &Database, dispatch: &str, event: &str) -> ServiceResult<bool> {
    let count: i64 = db.connection.query_row(
        "SELECT COUNT(*) FROM dispatch_events WHERE dispatch_identity=?1 AND event=?2",
        params![dispatch, event], |row| row.get(0),
    ).map_err(storage)?;
    Ok(count > 0)
}

pub fn response_event(db: &Database, root: &Path, slug: &str, event: &str, result: Option<&str>, call: Option<&str>, inflight_commit: Option<&str>, detail: Option<&str>) -> ServiceResult<()> {
    db.connection.execute("INSERT INTO response_events(vault_root,source_slug,event,result_identity,call_identity,inflight_commit,detail) VALUES(?1,?2,?3,?4,?5,?6,?7)",
        params![root.to_string_lossy(), slug, event, result, call, inflight_commit, detail]).map_err(storage)?;
    Ok(())
}

pub fn snapshot(db: &Database) -> ServiceResult<serde_json::Value> {
    let scalar = |sql: &str| db.connection.query_row(sql, [], |row| row.get::<_,i64>(0)).map_err(storage);
    Ok(serde_json::json!({
        "vaults": scalar("SELECT COUNT(DISTINCT vault_root) FROM active_files")?,
        "files": scalar("SELECT COUNT(*) FROM active_files")?,
        "unique_slugs": scalar("SELECT COUNT(*) FROM unique_slug_routes")?,
        "duplicate_slugs": scalar("SELECT COUNT(*) FROM duplicate_slugs")?,
        "dispatch_events": scalar("SELECT COUNT(*) FROM dispatch_events")?,
        "response_events": scalar("SELECT COUNT(*) FROM response_events")?,
        "integrity_events": scalar("SELECT COUNT(*) FROM integrity_events")?
    }))
}

fn storage(error: rusqlite::Error) -> ServiceError { ServiceError::Storage(error.to_string()) }
