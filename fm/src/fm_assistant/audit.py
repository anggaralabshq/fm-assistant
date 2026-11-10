"""Append-only audit log: one JSON line per action, refusal or abort."""
import json
import os
from datetime import datetime
from pathlib import Path

LOG = Path(os.environ.get("FM_ASSISTANT_LOG") or Path.home() / ".fm-assistant" / "log.jsonl")


def write(entry: dict, path=None) -> None:
    p = Path(path or LOG)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(json.dumps({"time": datetime.now().isoformat(timespec="seconds"), **entry}, ensure_ascii=False) + "\n")


def tail(n: int = 20, path=None) -> list:
    p = Path(path or LOG)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()][-n:]
