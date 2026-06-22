from typing import ClassVar

from pydantic import ConfigDict, Field

from asc.core.timestamp import timestamp
from asc.redis.model_base import RedisModel


class Committed(RedisModel):
    """Marker that a scrivener ledger write completed successfully.

    This is intentionally lighter than worker result records such as
    Response and Failure. It does not carry step payload content; it only
    tells the orchestrator that a ledger-side effect has been committed
    and that routing may continue.
    """

    model_config = ConfigDict(extra="forbid")

    kind: ClassVar[str] = "committed"
    identity: str
    task_key: str
    cursor_key: str
    action: str
    created_at: int = Field(default_factory=timestamp)


__all__ = ["Committed"]