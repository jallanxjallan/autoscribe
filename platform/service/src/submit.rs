use crate::{error::stub, types::*, ServiceResult};

/// Durable Git ledger for files submitted to external targets.
///
/// The implementation must update this ref through Git plumbing and must not
/// switch the user's active branch.
pub const BRANCH_REF: &str = "refs/heads/autoscribe/submit";

pub fn submit(_request: ExternalFileRequest) -> ServiceResult<ExternalFileReceipt> {
    stub("submit.submit")
}
