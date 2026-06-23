from dataclasses import dataclass


# Future modification note:
# step_count is currently retained as enqueue reporting metadata. Because the
# orchestrator call handler now reloads the plan and owns runtime step/index
# initialization, this field can be removed later if the CLI/reporting layer no
# longer displays it.


@dataclass(frozen=True, slots=True)
class EnqueuedCall:
    call: str
    source_identity: str
    call_key: str
    plan_key: str
    step_count: int


@dataclass(frozen=True, slots=True)
class EnqueueReport:
    records: tuple[EnqueuedCall, ...]

    @property
    def record_count(self) -> int:
        return len(self.records)

    @property
    def call_count(self) -> int:
        return len(self.records)


__all__ = ["EnqueuedCall", "EnqueueReport"]
