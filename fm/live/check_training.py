"""Live check (Task 9): op training reads the month view consistently and changes nothing.

- opened from another screen; every day has 3 slots; a slot is either a session (name + int type) or the match;
- day lists pair with day headers in order: weekday (DayIndex) == index % 7 for every day;
- dates assign uniquely around today (game date) and today is in the view;
- a second read is identical (read-only).

Usage: uv run --project fm python fm/live/check_training.py
"""
import sys

from fm_assistant import training
from fm_assistant.client import FmClient

c = FmClient(timeout=95)
errors = []
c.call("nav_open", panel="SquadScreen")
cal = c.call("training")
days = cal["days"]
if len(days) not in (35, 42):
    errors.append(f"{len(days)} days in month view")
for d in days:
    if len(d["sessions"]) != 3:
        errors.append(f"day {d['index']}: {len(d['sessions'])} slots")
    if d["weekday"] is not None and d["weekday"] != d["index"] % 7:
        errors.append(f"day {d['index']} ({d['day_label']}): weekday {d['weekday']}")
    for name, t in zip(d["sessions"], d["session_types"]):
        if (name is None) != (t is None) or (t is not None and not isinstance(t, int)):
            errors.append(f"day {d['index']}: slot {name!r}/{t!r}")
    if d["sessions"].count(None) != (1 if d["match"] else 0):
        errors.append(f"day {d['index']}: match {d['match']!r} vs slots {d['sessions']}")
try:
    dated = training.with_dates(cal)
    if cal["today"] not in {d["date"] for d in dated}:
        errors.append(f"today {cal['today']} not in view")
except ValueError as e:
    errors.append(f"dates: {e}")
if c.call("training") != cal:
    errors.append("second read differs")
if errors:
    print("FAIL:\n  " + "\n  ".join(errors[:30]))
    sys.exit(1)
print(f"OK: {len(days)} days x 3 slots, {dated[0]['date']}..{dated[-1]['date']}, today {cal['today']};"
      f" {sum(1 for d in days if d['match'])} matches; weekdays aligned; read twice identical")
