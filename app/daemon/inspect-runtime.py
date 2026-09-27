#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ledger = Path(os.environ.get("AUTOSCRIBE_LEDGER_DB", str(Path.home() / "Data/ledger.sql")))
if len(sys.argv) > 1:
    call_id = sys.argv[1]
else:
    with sqlite3.connect(ledger) as db:
        row = db.execute("SELECT identity FROM calls_v1 ORDER BY rowid DESC LIMIT 1").fetchone()
    if not row:
        raise SystemExit("no calls in ledger")
    call_id = row[0]

keys = [
    f"call:{call_id}:record",
    f"job:{call_id}:record",
]
print(json.dumps({"call_identity": call_id, "keys": keys}, indent=2))
subprocess.run(["redis-cli", "--raw", "HGETALL", keys[0]], check=False)
subprocess.run(["redis-cli", "--raw", "HGETALL", keys[1]], check=False)
subprocess.run(["redis-cli", "--raw", "ZRANGE", "state:active:index", "0", "-1", "WITHSCORES"], check=False)
