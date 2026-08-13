use crate::{ServiceError, ServiceResult, db::Database, types::*};
use rusqlite::{OptionalExtension, params};
use std::time::{SystemTime, UNIX_EPOCH};

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum UploadOutcome {
    Acknowledged,
    NotSent(String),
    Uncertain(String),
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct InboundResult {
    pub identity: ResultId,
    pub dispatch_identity: DispatchId,
    pub payload: Vec<u8>,
}

pub trait SyncTransport {
    fn upload(&mut self, dispatch: &DispatchId, payload: &[u8]) -> ServiceResult<UploadOutcome>;
    fn download(&mut self) -> ServiceResult<Vec<InboundResult>>;
}

pub fn enqueue(db: &Database, payload: &SavedPayload) -> ServiceResult<()> {
    if payload.dispatch_id.0.trim().is_empty() || payload.sha256.trim().is_empty() {
        return Err(ServiceError::InvalidInput(
            "outbound dispatch identity and payload hash are required".into(),
        ));
    }

    let existing = db
        .connection()
        .query_row(
            "SELECT payload, payload_sha256 FROM sync_outbox WHERE dispatch_identity = ?1",
            [&payload.dispatch_id.0],
            |row| Ok((row.get::<_, Vec<u8>>(0)?, row.get::<_, String>(1)?)),
        )
        .optional()
        .map_err(storage)?;

    if let Some((bytes, hash)) = existing {
        if bytes == payload.bytes && hash == payload.sha256 {
            return Ok(());
        }
        return Err(ServiceError::Conflict(format!(
            "dispatch {} already has a different saved payload",
            payload.dispatch_id.0
        )));
    }

    db.connection()
        .execute(
            "INSERT INTO sync_outbox
             (dispatch_identity, payload, payload_sha256, state, created_at)
             VALUES (?1, ?2, ?3, 'pending', ?4)",
            params![payload.dispatch_id.0, payload.bytes, payload.sha256, now()],
        )
        .map_err(storage)?;
    Ok(())
}

pub fn run(
    db: &Database,
    transport: &mut dyn SyncTransport,
    _request: SyncRequest,
) -> ServiceResult<SyncReport> {
    let pending = pending_payloads(db)?;
    let mut uploads_sent = 0;

    for payload in pending {
        let outcome = transport.upload(&payload.dispatch_id, &payload.bytes)?;
        match outcome {
            UploadOutcome::Acknowledged => {
                set_outbox_state(db, &payload.dispatch_id, "acknowledged", None)?;
                uploads_sent += 1;
            }
            UploadOutcome::NotSent(reason) => {
                set_outbox_state(db, &payload.dispatch_id, "pending", Some(&reason))?;
            }
            UploadOutcome::Uncertain(reason) => {
                set_outbox_state(db, &payload.dispatch_id, "uncertain", Some(&reason))?;
            }
        }
    }

    let incoming = transport.download()?;
    let downloads_received = incoming.len() as u32;
    for result in incoming {
        store_inbound(db, &result)?;
    }

    let synced_at = now();
    db.connection()
        .execute(
            "INSERT INTO sync_meta(key, value) VALUES ('last_synced_at', ?1)
             ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            [&synced_at],
        )
        .map_err(storage)?;

    Ok(SyncReport {
        uploads_sent,
        downloads_received,
        pending_outbound: count_state(db, "pending")?,
        synced_at,
    })
}

pub fn status(db: &Database) -> ServiceResult<SyncStatus> {
    let last_synced_at = db
        .connection()
        .query_row(
            "SELECT value FROM sync_meta WHERE key = 'last_synced_at'",
            [],
            |row| row.get(0),
        )
        .optional()
        .map_err(storage)?;
    Ok(SyncStatus {
        last_synced_at,
        pending_outbound: count_state(db, "pending")?,
        uncertain_outbound: count_state(db, "uncertain")?,
    })
}

pub fn pending_payloads(db: &Database) -> ServiceResult<Vec<SavedPayload>> {
    let mut statement = db
        .connection()
        .prepare(
            "SELECT dispatch_identity, payload, payload_sha256
             FROM sync_outbox WHERE state = 'pending' ORDER BY created_at, dispatch_identity",
        )
        .map_err(storage)?;
    let rows = statement
        .query_map([], |row| {
            Ok(SavedPayload {
                dispatch_id: DispatchId(row.get(0)?),
                bytes: row.get(1)?,
                sha256: row.get(2)?,
            })
        })
        .map_err(storage)?;
    rows.collect::<Result<Vec<_>, _>>().map_err(storage)
}

pub fn pending_payload(db: &Database, identity: &DispatchId) -> ServiceResult<SavedPayload> {
    db.connection()
        .query_row(
            "SELECT payload, payload_sha256 FROM sync_outbox
             WHERE dispatch_identity = ?1 AND state = 'pending'",
            [&identity.0],
            |row| {
                Ok(SavedPayload {
                    dispatch_id: identity.clone(),
                    bytes: row.get(0)?,
                    sha256: row.get(1)?,
                })
            },
        )
        .optional()
        .map_err(storage)?
        .ok_or_else(|| {
            ServiceError::Conflict(format!("dispatch is absent or not pending: {}", identity.0))
        })
}

pub fn record_upload_outcome(
    db: &Database,
    identity: &DispatchId,
    outcome: UploadOutcome,
) -> ServiceResult<()> {
    match outcome {
        UploadOutcome::Acknowledged => set_outbox_state(db, identity, "acknowledged", None),
        UploadOutcome::NotSent(reason) => set_outbox_state(db, identity, "pending", Some(&reason)),
        UploadOutcome::Uncertain(reason) => {
            set_outbox_state(db, identity, "uncertain", Some(&reason))
        }
    }
}

pub fn inbound(db: &Database, identity: &ResultId) -> ServiceResult<Option<InboundResult>> {
    db.connection()
        .query_row(
            "SELECT dispatch_identity, payload FROM sync_inbox WHERE result_identity = ?1",
            [&identity.0],
            |row| {
                Ok(InboundResult {
                    identity: identity.clone(),
                    dispatch_identity: DispatchId(row.get(0)?),
                    payload: row.get(1)?,
                })
            },
        )
        .optional()
        .map_err(storage)
}

fn store_inbound(db: &Database, result: &InboundResult) -> ServiceResult<()> {
    db.connection()
        .execute(
            "INSERT INTO sync_inbox(result_identity, dispatch_identity, payload, received_at)
             VALUES (?1, ?2, ?3, ?4)
             ON CONFLICT(result_identity) DO UPDATE SET
                dispatch_identity = excluded.dispatch_identity,
                payload = excluded.payload",
            params![
                result.identity.0,
                result.dispatch_identity.0,
                result.payload,
                now()
            ],
        )
        .map_err(storage)?;
    Ok(())
}

fn set_outbox_state(
    db: &Database,
    identity: &DispatchId,
    state: &str,
    error: Option<&str>,
) -> ServiceResult<()> {
    let acknowledged_at = (state == "acknowledged").then(now);
    db.connection()
        .execute(
            "UPDATE sync_outbox SET state = ?2, attempt_count = attempt_count + 1,
             last_error = ?3, acknowledged_at = ?4 WHERE dispatch_identity = ?1",
            params![identity.0, state, error, acknowledged_at],
        )
        .map_err(storage)?;
    Ok(())
}

fn count_state(db: &Database, state: &str) -> ServiceResult<u32> {
    db.connection()
        .query_row(
            "SELECT COUNT(*) FROM sync_outbox WHERE state = ?1",
            [state],
            |row| row.get(0),
        )
        .map_err(storage)
}

fn now() -> String {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
        .to_string()
}

fn storage(error: rusqlite::Error) -> ServiceError {
    ServiceError::Storage(error.to_string())
}
