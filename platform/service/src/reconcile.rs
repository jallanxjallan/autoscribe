use crate::{error::stub, types::*, ServiceResult};
pub fn run(_request: ReconcileRequest) -> ServiceResult<ReconcileReport> { stub("reconcile.run") }
pub fn apply(_decision: ReconcileDecision) -> ServiceResult<ReconcileReport> { stub("reconcile.apply") }

