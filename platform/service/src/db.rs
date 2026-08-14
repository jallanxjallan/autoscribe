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

            CREATE INDEX IF NOT EXISTS sync_outbox_state
                ON sync_outbox(state, created_at);
            CREATE INDEX IF NOT EXISTS sync_inbox_dispatch
                ON sync_inbox(dispatch_identity);
            ",
        )
        .map_err(storage)
}

fn storage(error: rusqlite::Error) -> ServiceError {
    ServiceError::Storage(error.to_string())
}
