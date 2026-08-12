use crate::{error::stub, types::*, ServiceResult};
use std::path::Path;

#[derive(Debug)]
pub struct Service;

impl Service {
    pub fn start(_config_path: &Path) -> ServiceResult<Self> { stub("service.start") }
    pub fn execute(&self, _command: Command) -> ServiceResult<CommandReceipt> { stub("service.execute") }
    pub fn query(&self, _query: Query) -> ServiceResult<QueryResponse> { stub("service.query") }
    pub fn shutdown(self) -> ServiceResult<()> { stub("service.shutdown") }
}

