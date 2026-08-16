use crate::{ServiceError, ServiceResult, types::ServiceConfig};
use rusqlite::Connection;
use std::path::Path;

#[derive(Debug)]
pub struct Database {
    connection: Connection,
}

impl Database {
    pub fn open_path(path: &Path) -> ServiceResult<Self> {
        let connection = Connection::open(path).map_err(storage)?;
        connection
            .busy_timeout(std::time::Duration::from_secs(5))
            .map_err(storage)?;
        connection
            .execute_batch("PRAGMA foreign_keys = ON; PRAGMA journal_mode = WAL;")
            .map_err(storage)?;
        Ok(Self { connection })
    }

    pub(crate) fn connection(&self) -> &Connection {
        &self.connection
    }
}

pub fn open(config: &ServiceConfig) -> ServiceResult<Database> {
    Database::open_path(&config.database_path)
}

pub fn migrate(db: &Database) -> ServiceResult<()> {
    db.connection()
        .execute_batch(
            "
            CREATE TABLE IF NOT EXISTS sync_outbox (
                dispatch_identity TEXT PRIMARY KEY,
                payload BLOB NOT NULL,
                payload_sha256 TEXT NOT NULL,
                state TEXT NOT NULL CHECK (state IN ('pending', 'uncertain', 'acknowledged')),
                attempt_count INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                created_at TEXT NOT NULL,
                acknowledged_at TEXT
            );

            CREATE TABLE IF NOT EXISTS sync_inbox (
                result_identity TEXT PRIMARY KEY,
                dispatch_identity TEXT NOT NULL,
                payload BLOB NOT NULL,
                received_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sync_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS notices (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL CHECK (
                    kind IN ('accepted', 'progress', 'completed', 'failed', 'needs_decision')
                ),
                operation TEXT NOT NULL,
                message TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS authored_instructions (
                instruction_identity TEXT PRIMARY KEY,
                record_json TEXT NOT NULL,
                content_sha256 TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS authored_plans (
                plan_identity TEXT PRIMARY KEY,
                record_json TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS inflight_dispatches (
                dispatch_identity TEXT PRIMARY KEY,
                plan_identity TEXT NOT NULL,
                ledger_ref TEXT NOT NULL,
                ledger_commit TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS inflight_sources (
                dispatch_identity TEXT NOT NULL REFERENCES inflight_dispatches(dispatch_identity),
                source_slug TEXT NOT NULL,
                source_path TEXT NOT NULL,
                blob_hash TEXT NOT NULL,
                PRIMARY KEY (dispatch_identity, source_path)
            );

            CREATE TABLE IF NOT EXISTS response_records (
                result_identity TEXT PRIMARY KEY,
                source_identity TEXT NOT NULL,
                call_identity TEXT NOT NULL,
                dispatch_identity TEXT NOT NULL,
                ledger_commit TEXT NOT NULL,
                source_blob TEXT NOT NULL,
                record_json TEXT NOT NULL,
                state TEXT NOT NULL CHECK (state IN ('pending', 'written', 'accepted', 'declined')),
                intended_outcome TEXT CHECK (intended_outcome IN ('accepted', 'declined')),
                source_path TEXT,
                writeback_commit TEXT,
                forensic_commit TEXT,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS sync_outbox_state
                ON sync_outbox(state, created_at);
            CREATE INDEX IF NOT EXISTS sync_inbox_dispatch
                ON sync_inbox(dispatch_identity);
            ",
        )
        .map_err(storage)?;
    let has_forensic = db.connection().prepare("PRAGMA table_info(response_records)").map_err(storage)?
        .query_map([], |row| row.get::<_, String>(1)).map_err(storage)?
        .collect::<Result<Vec<_>, _>>().map_err(storage)?
        .iter().any(|name| name == "forensic_commit");
    if !has_forensic {
        db.connection().execute("ALTER TABLE response_records ADD COLUMN forensic_commit TEXT", []).map_err(storage)?;
    }
    Ok(())
}

pub fn record_inflight(
    db: &Database,
    dispatch: &str,
    plan: &str,
    ledger_ref: &str,
    ledger_commit: &str,
    sources: &[(String, String, String)],
) -> ServiceResult<()> {
    let transaction = db.connection().unchecked_transaction().map_err(storage)?;
    transaction.execute(
        "INSERT INTO inflight_dispatches
         (dispatch_identity, plan_identity, ledger_ref, ledger_commit)
         VALUES (?1, ?2, ?3, ?4)",
        (dispatch, plan, ledger_ref, ledger_commit),
    ).map_err(storage)?;
    for (slug, path, blob) in sources {
        transaction.execute(
            "INSERT INTO inflight_sources
             (dispatch_identity, source_slug, source_path, blob_hash)
             VALUES (?1, ?2, ?3, ?4)",
            (dispatch, slug, path, blob),
        ).map_err(storage)?;
    }
    transaction.commit().map_err(storage)
}

pub fn clear_terminal_dispatch(db: &Database, dispatch: &str) -> ServiceResult<()> {
    ensure_terminal_ready(db, dispatch)?;
    let transaction = db.connection().unchecked_transaction().map_err(storage)?;
    transaction.execute("DELETE FROM sync_inbox WHERE dispatch_identity=?1", [dispatch]).map_err(storage)?;
    transaction.execute("DELETE FROM sync_outbox WHERE dispatch_identity=?1", [dispatch]).map_err(storage)?;
    transaction.execute("DELETE FROM inflight_sources WHERE dispatch_identity=?1", [dispatch]).map_err(storage)?;
    transaction.execute("DELETE FROM inflight_dispatches WHERE dispatch_identity=?1", [dispatch]).map_err(storage)?;
    transaction.commit().map_err(storage)
}
pub fn ensure_terminal_ready(db: &Database, dispatch: &str) -> ServiceResult<()> {
    let active: i64 = db.connection().query_row(
        "SELECT count(*) FROM response_records WHERE dispatch_identity=?1", [dispatch], |row| row.get(0),
    ).map_err(storage)?;
    if active != 0 {
        return Err(ServiceError::Conflict(format!("dispatch still has active responses: {dispatch}")));
    }
    Ok(())
}

pub fn system_counts(db: &Database) -> ServiceResult<serde_json::Value> {
    let scalar = |sql: &str| db.connection().query_row(sql, [], |row| row.get::<_, i64>(0)).map_err(storage);
    Ok(serde_json::json!({
        "active_dispatches":scalar("SELECT count(*) FROM inflight_dispatches")?,
        "pending_responses":scalar("SELECT count(*) FROM response_records")?,
        "pending_uploads":scalar("SELECT count(*) FROM sync_outbox WHERE state='pending'")?,
        "uncertain_uploads":scalar("SELECT count(*) FROM sync_outbox WHERE state='uncertain'")?
    }))
}

fn storage(error: rusqlite::Error) -> ServiceError {
    ServiceError::Storage(error.to_string())
}
