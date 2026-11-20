#!/usr/bin/env python3
"""Inspect a known canonical call; never scan keys or hydrate from SQLite."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from asc.models.call import Call
if len(sys.argv)!=2:raise SystemExit('usage: inspect-runtime.py CALL_ID')
print(Call.load(sys.argv[1]).model_dump_json(indent=2,by_alias=True))
