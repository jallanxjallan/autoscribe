use crate::{error::stub, types::*, ServiceResult};
pub fn build(_request: BuildPayloadRequest) -> ServiceResult<SavedPayload> { stub("payloads.build") }
pub fn verify_saved(_request: VerifyPayloadRequest) -> ServiceResult<SavedPayload> { stub("payloads.verify_saved") }

