use std::path::PathBuf;

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct DispatchId(pub String);
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct PlanId(pub String);
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct CommitId(pub String);
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct ResultId(pub String);

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ServiceConfig {
    pub database_path: PathBuf,
    pub repository_path: PathBuf,
    pub shadow_root: PathBuf,
    pub server_endpoint: String,
    pub poll_interval_seconds: u64,
    pub poll_limit: u32,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum DispatchState { Prepared, Transmitting, Polling, Succeeded, Uncertain, Cancelled, Failed }
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum NoticeKind { Accepted, Progress, Completed, Failed, NeedsDecision }
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum CommitPurpose { Version, Lock, DispatchWriteback, Restore }

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Notice { pub kind: NoticeKind, pub operation: String, pub message: String }
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SavedPayload { pub dispatch_id: DispatchId, pub bytes: Vec<u8>, pub sha256: String }
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DispatchView { pub id: DispatchId, pub state: DispatchState, pub attempts: u32, pub payload_sha256: String }
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AttemptRecord { pub dispatch_id: DispatchId, pub ordinal: u32, pub accepted_by_transport: bool }
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PlanSummary { pub id: PlanId, pub title: String, pub content_hash: String }
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PlanRecord { pub summary: PlanSummary, pub body: Vec<u8> }
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PlanDraft { pub title: String, pub body: Vec<u8> }
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ValidationReport { pub warnings: Vec<String>, pub errors: Vec<String> }
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FileStatus { pub path: PathBuf, pub tracked: bool, pub dirty: bool }
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CommitRequest { pub paths: Vec<PathBuf>, pub message: String, pub purpose: CommitPurpose }
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TagRequest { pub commit: CommitId, pub plan: PlanId, pub dispatch: DispatchId }
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct VersionRequest { pub path: PathBuf, pub revision: String }
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RestoreRequest { pub version: VersionRequest, pub confirmation: String }
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ShadowSyncRequest { pub document: PathBuf, pub shadow_root: PathBuf }
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Chunk { pub sentinel: String, pub path: PathBuf, pub bytes: Vec<u8>, pub sha256: String }
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ShadowSyncReport { pub chunks: Vec<Chunk>, pub changed: Vec<PathBuf> }
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ShadowApplyRequest { pub chunks: Vec<Chunk>, pub expected_base_hashes: Vec<(PathBuf, String)> }
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ShadowApplyReport { pub changed: Vec<PathBuf>, pub conflicts: Vec<PathBuf> }
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ShadowVerifyReport { pub missing: Vec<PathBuf>, pub changed: Vec<PathBuf>, pub orphaned: Vec<PathBuf> }
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CatalogRefreshRequest { pub cached_revision: Option<String> }
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct CatalogSnapshot { pub revision: String, pub engines: Vec<String>, pub models: Vec<String>, pub scripts: Vec<String>, pub instructions: Vec<String> }
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct InstructionRequest { pub references: Vec<String> }
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ResolvedInstruction { pub key: String, pub version: String, pub content: Vec<u8> }
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PlanDispatchValidation { pub plan: PlanId, pub records: Vec<PathBuf> }
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BuildPayloadRequest { pub plan: PlanRecord, pub files: Vec<(PathBuf, Vec<u8>)>, pub instructions: Vec<ResolvedInstruction>, pub directive: Option<String> }
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct VerifyPayloadRequest { pub dispatch_id: DispatchId, pub bytes: Vec<u8>, pub expected_sha256: String }
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PrepareDispatchRequest { pub plan: PlanId, pub files: Vec<PathBuf>, pub directive: Option<String> }
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ResultRecord { pub id: ResultId, pub dispatch: DispatchId, pub bytes: Vec<u8> }
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct WritePreviewRequest { pub result: ResultId }
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct WritePreview { pub token: String, pub writes: Vec<PathBuf>, pub conflicts: Vec<String> }
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct WriteRequest { pub preview_token: String }
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct WriteReport { pub commit: CommitId, pub changed: Vec<PathBuf> }
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct ReconcileRequest { pub dispatch: Option<DispatchId>, pub path: Option<PathBuf> }
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Discrepancy { pub code: String, pub description: String, pub choices: Vec<String> }
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ReconcileReport { pub discrepancies: Vec<Discrepancy> }
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ReconcileDecision { pub code: String, pub choice: String }
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DashboardOverview { pub pending_dispatches: u32, pub uncertain_dispatches: u32, pub pending_results: u32, pub failures: u32 }
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FileStateView { pub path: PathBuf, pub git: FileStatus, pub shadow_ok: bool, pub active_dispatch: Option<DispatchId> }
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct HistoryEntry { pub identity: String, pub label: String }
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Command { Dispatch(PrepareDispatchRequest), Retry(DispatchId), Cancel(DispatchId), Retrieve(DispatchId), Write(WriteRequest), Reconcile(ReconcileDecision) }
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CommandReceipt { pub operation_id: String, pub accepted: bool }
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Query { Overview, Dispatch(DispatchId), FileState(PathBuf), History(PathBuf), Plans, Catalog, NoticesSince(u64) }
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum QueryResponse { Overview(DashboardOverview), Dispatch(DispatchView), FileState(FileStateView), History(Vec<HistoryEntry>), Plans(Vec<PlanSummary>), Catalog(CatalogSnapshot), Notices(Vec<(u64, Notice)>) }

