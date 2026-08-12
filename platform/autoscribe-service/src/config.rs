use crate::{error::stub, types::ServiceConfig, ServiceResult};
use std::path::Path;
pub fn load(_path: &Path) -> ServiceResult<ServiceConfig> { stub("config.load") }
pub fn validate(_config: ServiceConfig) -> ServiceResult<ServiceConfig> { stub("config.validate") }

