use crate::{
    ServiceError, ServiceResult,
    db::Database,
    types::{Notice, NoticeKind},
};
use rusqlite::params;

#[derive(Debug)]
pub struct NoticeSink<'a> {
    db: &'a Database,
}

impl<'a> NoticeSink<'a> {
    pub fn new(db: &'a Database) -> Self {
        Self { db }
    }
}

pub fn publish(sink: &NoticeSink<'_>, notice: Notice) -> ServiceResult<u64> {
    sink.db
        .connection()
        .execute(
            "INSERT INTO notices(kind, operation, message) VALUES (?1, ?2, ?3)",
            params![kind_name(&notice.kind), notice.operation, notice.message],
        )
        .map_err(storage)?;
    u64::try_from(sink.db.connection().last_insert_rowid())
        .map_err(|_| ServiceError::Storage("notice sequence was negative".into()))
}

pub fn list_since(sink: &NoticeSink<'_>, sequence: u64) -> ServiceResult<Vec<(u64, Notice)>> {
    let sequence = i64::try_from(sequence)
        .map_err(|_| ServiceError::InvalidInput("notice sequence is too large".into()))?;
    let mut statement = sink
        .db
        .connection()
        .prepare(
            "SELECT sequence, kind, operation, message
             FROM notices WHERE sequence > ?1 ORDER BY sequence",
        )
        .map_err(storage)?;
    let rows = statement
        .query_map([sequence], |row| {
            let sequence: i64 = row.get(0)?;
            let kind: String = row.get(1)?;
            Ok((sequence, kind, row.get(2)?, row.get(3)?))
        })
        .map_err(storage)?;

    rows.map(|row| {
        let (sequence, kind, operation, message) = row.map_err(storage)?;
        let sequence = u64::try_from(sequence)
            .map_err(|_| ServiceError::Storage("notice sequence was negative".into()))?;
        Ok((
            sequence,
            Notice {
                kind: parse_kind(&kind)?,
                operation,
                message,
            },
        ))
    })
    .collect()
}

fn kind_name(kind: &NoticeKind) -> &'static str {
    match kind {
        NoticeKind::Accepted => "accepted",
        NoticeKind::Progress => "progress",
        NoticeKind::Completed => "completed",
        NoticeKind::Failed => "failed",
        NoticeKind::NeedsDecision => "needs_decision",
    }
}

fn parse_kind(value: &str) -> ServiceResult<NoticeKind> {
    match value {
        "accepted" => Ok(NoticeKind::Accepted),
        "progress" => Ok(NoticeKind::Progress),
        "completed" => Ok(NoticeKind::Completed),
        "failed" => Ok(NoticeKind::Failed),
        "needs_decision" => Ok(NoticeKind::NeedsDecision),
        other => Err(ServiceError::Storage(format!(
            "unknown persisted notice kind: {other}"
        ))),
    }
}

fn storage(error: rusqlite::Error) -> ServiceError {
    ServiceError::Storage(error.to_string())
}
