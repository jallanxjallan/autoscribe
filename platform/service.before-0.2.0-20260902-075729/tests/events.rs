use autoscribe_service::{
    db::{self, Database},
    events::{self, NoticeSink},
    types::{Notice, NoticeKind},
};
use std::{
    fs,
    path::PathBuf,
    time::{SystemTime, UNIX_EPOCH},
};

fn notice(kind: NoticeKind, message: &str) -> Notice {
    Notice {
        kind,
        operation: "dispatch.prepare".into(),
        message: message.into(),
    }
}

#[test]
fn notices_are_monotonic_and_incremental() {
    let db = Database::open_path(std::path::Path::new(":memory:")).unwrap();
    db::migrate(&db).unwrap();
    let sink = NoticeSink::new(&db);

    let first = events::publish(&sink, notice(NoticeKind::Accepted, "accepted")).unwrap();
    let second = events::publish(&sink, notice(NoticeKind::Completed, "completed")).unwrap();

    assert_eq!(second, first + 1);
    assert_eq!(events::list_since(&sink, second).unwrap(), vec![]);
    assert_eq!(
        events::list_since(&sink, first).unwrap(),
        vec![(second, notice(NoticeKind::Completed, "completed"))]
    );
}

#[test]
fn notices_survive_database_reopen() {
    let path = temporary_database_path();
    let sequence = {
        let db = Database::open_path(&path).unwrap();
        db::migrate(&db).unwrap();
        events::publish(
            &NoticeSink::new(&db),
            notice(NoticeKind::NeedsDecision, "delivery uncertain"),
        )
        .unwrap()
    };

    let db = Database::open_path(&path).unwrap();
    db::migrate(&db).unwrap();
    assert_eq!(
        events::list_since(&NoticeSink::new(&db), 0).unwrap(),
        vec![(
            sequence,
            notice(NoticeKind::NeedsDecision, "delivery uncertain")
        )]
    );
    drop(db);
    fs::remove_file(&path).unwrap();
}

fn temporary_database_path() -> PathBuf {
    let unique = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!("autoscribe-events-{unique}.sqlite"))
}
