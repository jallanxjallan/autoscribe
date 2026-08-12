use crate::{error::stub, types::*, ServiceResult};
use std::path::{Path, PathBuf};
pub fn inspect(_repo: &Path, _paths: &[PathBuf]) -> ServiceResult<Vec<FileStatus>> { stub("git.inspect") }
pub fn commit(_repo: &Path, _request: CommitRequest) -> ServiceResult<CommitId> { stub("git.commit") }
pub fn tag_dispatch(_repo: &Path, _request: TagRequest) -> ServiceResult<String> { stub("git.tag_dispatch") }
pub fn read_version(_repo: &Path, _request: VersionRequest) -> ServiceResult<Vec<u8>> { stub("git.read_version") }
pub fn restore_version(_repo: &Path, _request: RestoreRequest) -> ServiceResult<CommitId> { stub("git.restore_version") }

