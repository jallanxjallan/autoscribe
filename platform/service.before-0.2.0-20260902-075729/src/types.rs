use std::path::PathBuf;

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct DispatchId(pub String);

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct PlanId(pub String);

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct CommitId(pub String);

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LedgerSource {
    pub slug: String,
    pub path: PathBuf,
    pub bytes: Vec<u8>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LedgerSnapshotRequest {
    pub dispatch: DispatchId,
    pub plan: PlanId,
    pub sources: Vec<LedgerSource>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LedgerSnapshot {
    pub reference: String,
    pub commit: CommitId,
    pub blobs: Vec<(PathBuf, String)>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct VersionRequest {
    pub path: PathBuf,
    pub revision: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PandocJob {
    pub identity: String,
    pub working_directory: PathBuf,
    pub arguments: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PandocOutcome {
    pub identity: String,
    pub exit_code: Option<i32>,
    pub stdout: Vec<u8>,
    pub stderr: Vec<u8>,
    pub error: Option<String>,
}
