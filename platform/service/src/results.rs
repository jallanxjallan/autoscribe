use crate::{error::stub, types::*, ServiceResult};
pub fn list_pending() -> ServiceResult<Vec<ResultRecord>> { stub("results.list_pending") }
pub fn retrieve(_identity: &DispatchId) -> ServiceResult<ResultRecord> { stub("results.retrieve") }
pub fn preview_write(_request: WritePreviewRequest) -> ServiceResult<WritePreview> { stub("results.preview_write") }
pub fn write(_request: WriteRequest) -> ServiceResult<WriteReport> { stub("results.write") }

