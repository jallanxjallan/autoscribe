use crate::{error::stub, types::*, ServiceResult};
pub fn sync_for_dispatch(_request: ShadowSyncRequest) -> ServiceResult<ShadowSyncReport> { stub("shadow.sync_for_dispatch") }
pub fn apply_response(_request: ShadowApplyRequest) -> ServiceResult<ShadowApplyReport> { stub("shadow.apply_response") }
pub fn verify(_request: ShadowSyncRequest) -> ServiceResult<ShadowVerifyReport> { stub("shadow.verify") }

