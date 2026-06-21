class OrchestratorContractError(RuntimeError):
    """Raised when a posted key violates the runtime queue contract."""


class OrchestratorNeedsAttention(RuntimeError):
    """Raised for a posted failure that should stop the normal route."""
