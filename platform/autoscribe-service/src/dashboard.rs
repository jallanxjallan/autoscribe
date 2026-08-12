use crate::{error::stub, types::*, ServiceResult};
use std::path::Path;
pub fn overview() -> ServiceResult<DashboardOverview> { stub("dashboard.overview") }
pub fn file_state(_path: &Path) -> ServiceResult<FileStateView> { stub("dashboard.file_state") }
pub fn history(_path: &Path) -> ServiceResult<Vec<HistoryEntry>> { stub("dashboard.history") }

