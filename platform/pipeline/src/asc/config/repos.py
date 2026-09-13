"""Git repository configuration for the deployed AutoScribe pipeline.

The pipeline knows only the authoritative published Control repository and the
branches it consumes or owns. Workstation authoring repositories and safety
backups are deployment concerns and deliberately do not appear here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ControlRepoConfig:
    path: Path
    config_branch: str
    git_name: str
    git_email: str


CONTROL = ControlRepoConfig(
    path=Path("/home/jeremy/Work/Control"),
    config_branch="master",
    git_name="AutoScribe Control",
    git_email="autoscribe@localhost",
)

__all__ = ["CONTROL", "ControlRepoConfig"]
