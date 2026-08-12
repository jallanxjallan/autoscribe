use crate::{error::stub, types::*, ServiceResult};
pub fn prepare(_request: PrepareDispatchRequest) -> ServiceResult<SavedPayload> { stub("dispatch.prepare") }
pub fn transmit(_identity: &DispatchId) -> ServiceResult<AttemptRecord> { stub("dispatch.transmit") }
pub fn poll(_identity: &DispatchId) -> ServiceResult<DispatchView> { stub("dispatch.poll") }
pub fn retry(_identity: &DispatchId) -> ServiceResult<AttemptRecord> { stub("dispatch.retry") }
pub fn cancel(_identity: &DispatchId) -> ServiceResult<DispatchView> { stub("dispatch.cancel") }
pub fn status(_identity: &DispatchId) -> ServiceResult<DispatchView> { stub("dispatch.status") }

