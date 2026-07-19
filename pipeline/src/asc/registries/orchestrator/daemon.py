"""Compatibility entrypoint for the process daemon.

Run explicit daemons with:
    python -m asc.orchestrator.initiate
    python -m asc.orchestrator.process
    python -m asc.orchestrator.evaluate
"""

from .process import ProcessReport as OrchestratorRunReport
from .process import main, run_cycle, run_forever

__all__ = ["OrchestratorRunReport", "main", "run_cycle", "run_forever"]

if __name__ == "__main__":
    main()
