"""Live check (Task 6): op squad matches the Squad screen's own player list and reads sane values.

- the set of player uids equals the SquadScreen table's backing rows (first team);
- every outfield player has >= 10 attributes in 1-20, goalkeepers >= 10 too (GK attributes);
- contract end dates parse, wages are Money, condition is a number, injured players carry an injury.

Usage: uv run --project fm python fm/live/check_squad.py
"""
import datetime as dt
import sys

from fm_assistant.client import FmClient

c = FmClient(timeout=95)
errors = []
squad = c.call("squad", team="first")
c.call("nav_open", panel="SquadScreen")
lists = c.call("list_rows", panel="SquadScreen", index=1, max=200)
table = next((w for w in lists["widgets"] if w["name"] == "playertable"), None)
screen = {r["uid"] for r in lists["rows"] if isinstance(r, dict) and r.get("$ref") == "Person"}
ours = {p["uid"] for p in squad["players"]}
if not table or table["item_count"] != len(screen):
    errors.append(f"playertable rows not read fully: {table}, {len(screen)}")
if ours != screen:
    errors.append(f"uids differ: only op {sorted(ours - screen)}, only screen {sorted(screen - ours)}")
for p in squad["players"]:
    good = [v for v in p["attributes"].values() if isinstance(v, int) and 1 <= v <= 20]
    if len(good) < 10:
        errors.append(f"{p['name']}: {len(good)} attributes in 1-20")
    try:
        dt.date.fromisoformat(p["contract"]["end_date"])
    except (TypeError, ValueError):
        errors.append(f"{p['name']}: end_date {p['contract']['end_date']!r}")
    w = p["contract"]["wage"]
    if not w or not isinstance(w["value"], (int, float)) or not w["display"]:
        errors.append(f"{p['name']}: wage {w}")
    if not isinstance(p["condition"], (int, float)):
        errors.append(f"{p['name']}: condition {p['condition']!r}")
    if p["injured"] and not (p["injury"] or {}).get("description"):
        errors.append(f"{p['name']}: injured without injury detail")
if errors:
    print("FAIL:\n  " + "\n  ".join(errors[:30]))
    sys.exit(1)
inj = sum(1 for p in squad["players"] if p["injured"])
print(f"OK: {squad['team']['name']} {squad['count']} players == SquadScreen rows; attributes, dates, wages sane; {inj} injured")
