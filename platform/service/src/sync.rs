use crate::{error::stub, types::*, ServiceResult};

pub fn run(_request: SyncRequest) -> ServiceResult<SyncReport> {
    stub("sync.run")
}

pub fn status() -> ServiceResult<SyncStatus> {
    stub("sync.status")
}
