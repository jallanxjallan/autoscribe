use crate::{error::stub, types::ServiceConfig, ServiceResult};
#[derive(Debug)] pub struct Database;
#[derive(Debug)] pub struct Transaction;
pub fn open(_config: &ServiceConfig) -> ServiceResult<Database> { stub("db.open") }
pub fn migrate(_db: &Database) -> ServiceResult<()> { stub("db.migrate") }
pub fn transaction(_db: &Database, _operation: &str) -> ServiceResult<Transaction> { stub("db.transaction") }

