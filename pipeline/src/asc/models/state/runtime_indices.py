from __future__ import annotations


class _RemovedRuntimeIndex:
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise RuntimeError(
            "runtime index helpers have been removed; Orchestrator now derives "
            "runtime keys from call identity and step number"
        )


RuntimeContentIndex = _RemovedRuntimeIndex
RuntimeStepIndex = _RemovedRuntimeIndex

__all__ = ["RuntimeContentIndex", "RuntimeStepIndex"]
