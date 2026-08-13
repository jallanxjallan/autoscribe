use crate::{error::stub, types::*, ServiceResult};
pub fn list() -> ServiceResult<Vec<PlanSummary>> { stub("plans.list") }
pub fn get(_identity: &PlanId) -> ServiceResult<PlanRecord> { stub("plans.get") }
pub fn save(_draft: PlanDraft) -> ServiceResult<PlanSummary> { stub("plans.save") }
pub fn validate_for_dispatch(_request: PlanDispatchValidation) -> ServiceResult<ValidationReport> { stub("plans.validate_for_dispatch") }

