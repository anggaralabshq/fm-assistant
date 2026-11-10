"""Live check (Phase 1b Task 2): contract and injury watch over the real squad and training ops.

squad.today equals training.today; every injured player of the squad appears in the watch's injured list; every
expiring end_date parses and lies within the window (and is not before today's window start by more than the
contract was already expired); injured rows have a consistent return_date.

Usage: uv run --project fm python fm/live/check_watch.py
"""
import sys
from datetime import date, timedelta

from fm_assistant import training, watch
from fm_assistant.client import FmClient

WITHIN = 180
c = FmClient(timeout=95)
errors = []
squad = c.call("squad", team="first")
cal = c.call("training")
if squad.get("today") != cal["today"]:
    errors.append(f"squad.today {squad.get('today')!r} != training.today {cal['today']!r}")
today = date.fromisoformat(squad["today"])
days = training.with_dates(cal)
players = squad["players"]

exp = watch.expiring(players, today, WITHIN)
for e in exp:
    try:
        end = date.fromisoformat(e["end_date"])
    except ValueError:
        errors.append(f"{e['name']}: end_date {e['end_date']!r} does not parse")
        continue
    if end > today + timedelta(days=WITHIN):
        errors.append(f"{e['name']}: {e['end_date']} beyond the {WITHIN}-day window")
    if e["days_left"] != (end - today).days:
        errors.append(f"{e['name']}: days_left {e['days_left']} wrong")

inj = watch.injuries(players, today, days)
want = {p["uid"] for p in players if p.get("injured")}
if {i["uid"] for i in inj} != want:
    errors.append(f"injured uids differ: squad {sorted(want)} vs watch {sorted(i['uid'] for i in inj)}")
for i in inj:
    if i["return_date"] is None:
        print(f"note: {i['name']} injured, return unknown ({i['description']!r})")
    elif i["return_date"] != (today + timedelta(days=i["return_days"])).isoformat():
        errors.append(f"{i['name']}: return_date {i['return_date']} != today + {i['return_days']}")
if errors:
    print("FAIL:\n  " + "\n  ".join(errors[:30]))
    sys.exit(1)
print(f"OK: today {today} (squad == training); {len(exp)} contract(s) ending within {WITHIN} days;"
      f" {len(inj)} injured, all in the watch")
