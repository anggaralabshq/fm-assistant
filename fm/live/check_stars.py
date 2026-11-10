"""Live check (Phase 1d Task 4): scouted star ranges over the real squad, player_search and loans ops.

OK when: all stars_raw values are within -1..20 (op maps -1/-1 to null and drops others with a warning), first-team
players have min == max, and unscouted search rows give null.

Usage: uv run --project fm python fm/live/check_stars.py
"""
import sys

from fm_assistant.client import FmClient

c = FmClient(timeout=95)
errors = []


def values(row):
    raw = row.get("stars_raw") or {}
    for kind in ("current", "potential"):
        r = raw.get(kind)
        if r is not None:
            yield kind, r["min"], r["max"]


squad = c.call("squad", team="first")
search = c.call("player_search", max=500)
loans = c.call("loans")
for label, rows in (("squad", squad["players"]), ("search", search["rows"]), ("loans", loans["out"])):
    for r in rows:
        if "stars_raw" not in r:
            errors.append(f"{label} {r.get('name')}: no stars_raw")
        for kind, lo, hi in values(r):
            if not (0 <= lo <= hi <= 20):
                errors.append(f"{label} {r['name']}: {kind} {lo}-{hi} outside 0..20")
for r in squad["players"]:
    cur = (r.get("stars_raw") or {}).get("current")
    if cur is not None and cur["min"] != cur["max"]:
        errors.append(f"squad {r['name']}: current range {cur['min']}-{cur['max']} (expected min == max)")
null_rows = [r for r in search["rows"] if (r.get("stars_raw") or {}).get("current") is None]
print(f"search rows with unscouted (null) current stars: {len(null_rows)} of {len(search['rows'])}")
if search["rows"] and not null_rows:
    errors.append("expected some unscouted search rows with null stars")
for label, res in (("squad", squad), ("search", search), ("loans", loans)):
    for w in res.get("warnings") or []:
        print(f"warning ({label}): {w}")
if errors:
    print("FAIL:\n  " + "\n  ".join(errors[:30]))
    sys.exit(1)
print(f"OK: {len(squad['players'])} squad, {len(search['rows'])} search, {len(loans['out'])} loans")
