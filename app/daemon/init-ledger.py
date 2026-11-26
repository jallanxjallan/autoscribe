#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from asc.ledger import ensure_schema

from asc.settings import ledger_path
path = ledger_path()
ensure_schema(path)
print(path)
