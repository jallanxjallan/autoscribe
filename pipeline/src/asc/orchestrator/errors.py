from __future__ import annotations


class OrchestratorContractError(RuntimeError):
    """Raised when a runtime handoff violates orchestration invariants."""


class ScrivenerContractError(OrchestratorContractError):
    """Backward-compatible alias for older imports."""
