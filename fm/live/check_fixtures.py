"""Live check (Phase 1c Task 3): fixtures against the training calendar.

upcoming dates ascending and >= today; upcoming[0] == next; every match day in `training` (current month) that
has a match also appears in upcoming, or lies after its last date.

Usage: uv run --project fm python fm/live/check_fixtures.py
"""
import sys
from datetime import date

from fm_assistant import training
from fm_assistant.client import FmClient

c = FmClient(timeout=95)
errors = []
res = c.call("fixtures", n=10)
today = date.fromisoformat(res["today"])
up = res["upcoming"]
dates = [f["date"] for f in up]
if dates != sorted(dates):
    errors.append(f"upcoming not ascending: {dates}")
if any(d < today.isoformat() for d in dates):
    errors.append(f"upcoming before today {today}: {dates}")
if (up[0] if up else None) != res["next"]:
    errors.append(f"upcoming[0] {up[0] if up else None!r} != next {res['next']!r}")
cal = c.call("training")
match_days = [d["date"] for d in training.with_dates(cal) if d.get("match") and d["date"] >= today.isoformat()]
last = dates[-1] if dates else None
for d in match_days:
    if d not in dates and (last is None or d <= last):
        errors.append(f"training shows a match on {d} that fixtures lacks (upcoming: {dates})")
if errors:
    print("FAIL:\n  " + "\n  ".join(errors))
    sys.exit(1)
print(f"OK: today {today}; {len(up)} upcoming ({dates[:1]}..{dates[-1:]}); next {res['next'] and res['next']['opponent']['name']};"
      f" {len(match_days)} training match day(s) consistent")
