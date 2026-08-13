use crate::{error::stub, types::*, ServiceResult};
pub fn refresh(_request: CatalogRefreshRequest) -> ServiceResult<CatalogSnapshot> { stub("catalog.refresh") }
pub fn snapshot() -> ServiceResult<CatalogSnapshot> { stub("catalog.snapshot") }
pub fn resolve_instructions(_request: InstructionRequest) -> ServiceResult<Vec<ResolvedInstruction>> { stub("catalog.resolve_instructions") }

