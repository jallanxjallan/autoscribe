use autoscribe_service::{
    ServiceError,
    db::{self, Database},
    sync::{self, InboundResult, SyncTransport, UploadOutcome},
    types::{DispatchId, ResultId, SavedPayload, SyncRequest},
};
use std::{collections::VecDeque, path::Path};

#[derive(Default)]
struct TestTransport {
    outcomes: VecDeque<UploadOutcome>,
    uploads: Vec<(DispatchId, Vec<u8>)>,
    downloads: Vec<InboundResult>,
}

impl SyncTransport for TestTransport {
    fn upload(
        &mut self,
        dispatch: &DispatchId,
        payload: &[u8],
    ) -> autoscribe_service::ServiceResult<UploadOutcome> {
        self.uploads.push((dispatch.clone(), payload.to_vec()));
        Ok(self
            .outcomes
            .pop_front()
            .unwrap_or(UploadOutcome::Acknowledged))
    }

    fn download(&mut self) -> autoscribe_service::ServiceResult<Vec<InboundResult>> {
        Ok(std::mem::take(&mut self.downloads))
    }
}

fn database() -> Database {
    let db = Database::open_path(Path::new(":memory:")).unwrap();
    db::migrate(&db).unwrap();
    db
}

fn payload(bytes: &[u8]) -> SavedPayload {
    SavedPayload {
        dispatch_id: DispatchId("dispatch-1".into()),
        bytes: bytes.to_vec(),
        sha256: "fixed-hash".into(),
    }
}

#[test]
fn transient_failure_keeps_exact_payload_for_retry() {
    let db = database();
    let saved = payload(b"exact original bytes");
    sync::enqueue(&db, &saved).unwrap();
    sync::enqueue(&db, &saved).unwrap();
    assert_eq!(sync::pending_payloads(&db).unwrap().len(), 1);

    let mut offline = TestTransport {
        outcomes: VecDeque::from([UploadOutcome::NotSent("offline".into())]),
        ..Default::default()
    };
    let first = sync::run(&db, &mut offline, SyncRequest::default()).unwrap();
    assert_eq!(first.uploads_sent, 0);
    assert_eq!(first.pending_outbound, 1);

    let mut online = TestTransport::default();
    let second = sync::run(&db, &mut online, SyncRequest::default()).unwrap();
    assert_eq!(second.uploads_sent, 1);
    assert_eq!(second.pending_outbound, 0);
    assert_eq!(online.uploads, vec![(saved.dispatch_id, saved.bytes)]);
}

#[test]
fn uncertain_upload_waits_for_an_explicit_decision() {
    let db = database();
    sync::enqueue(&db, &payload(b"possibly delivered")).unwrap();
    let mut transport = TestTransport {
        outcomes: VecDeque::from([UploadOutcome::Uncertain("connection dropped".into())]),
        ..Default::default()
    };

    sync::run(&db, &mut transport, SyncRequest::default()).unwrap();
    let status = sync::status(&db).unwrap();
    assert_eq!(status.pending_outbound, 0);
    assert_eq!(status.uncertain_outbound, 1);

    let mut next_sync = TestTransport::default();
    sync::run(&db, &mut next_sync, SyncRequest::default()).unwrap();
    assert!(next_sync.uploads.is_empty());
}

#[test]
fn downloaded_results_are_retained_locally() {
    let db = database();
    let result = InboundResult {
        identity: ResultId("result-1".into()),
        dispatch_identity: DispatchId("dispatch-1".into()),
        payload: b"downloaded bytes".to_vec(),
    };
    let mut transport = TestTransport {
        downloads: vec![result.clone()],
        ..Default::default()
    };

    let report = sync::run(&db, &mut transport, SyncRequest::default()).unwrap();
    assert_eq!(report.downloads_received, 1);
    assert_eq!(sync::inbound(&db, &result.identity).unwrap(), Some(result));
}

#[test]
fn dispatch_identity_cannot_be_reused_for_different_bytes() {
    let db = database();
    sync::enqueue(&db, &payload(b"first")).unwrap();
    let mut changed = payload(b"second");
    changed.sha256 = "different-hash".into();

    assert!(matches!(
        sync::enqueue(&db, &changed),
        Err(ServiceError::Conflict(_))
    ));
}
