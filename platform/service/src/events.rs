use crate::{error::stub, types::Notice, ServiceResult};
#[derive(Debug)] pub struct NoticeSink;
pub fn publish(_sink: &NoticeSink, _notice: Notice) -> ServiceResult<u64> { stub("events.publish") }
pub fn list_since(_sink: &NoticeSink, _sequence: u64) -> ServiceResult<Vec<(u64, Notice)>> { stub("events.list_since") }

