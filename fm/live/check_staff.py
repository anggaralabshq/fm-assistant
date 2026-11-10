"""Live check (Task 7): op staff_search navigates itself and returns every row of the Staff Search table.

Starts from another screen (Squad) so the op's own navigation is exercised; max=1000 must finish in the op
timeout; the result count equals the on-screen "people found" number, and the returned uids equal the table's
backing rows. (Name cells are not rendered as text on build 27.0.0.2493426, so names cannot be compared.)

Usage: uv run --project fm python fm/live/check_staff.py
"""
import sys
import time

from fm_assistant.client import FmClient

c = FmClient(timeout=95)
errors = []
c.call("nav_open", panel="SquadScreen")
t0 = time.monotonic()
res = c.call("staff_search", max=1000)
took = time.monotonic() - t0
rows = res["rows"]
if res["returned"] != len(rows) or res["truncated"] != (len(rows) < res["count"]):
    errors.append(f"count/returned/truncated inconsistent: {res['count']}/{res['returned']}/{res['truncated']}")
if res["count"] <= 1000 and len(rows) != res["count"]:
    errors.append(f"returned {len(rows)} of {res['count']} with max=1000")
count_text = []


def walk(n):
    if isinstance(n, list):
        for x in n:
            walk(x)
        return
    if n.get("bind") == "personsearch.PersonListCount" and n.get("text"):
        count_text.append(n["text"])
    for k in n.get("children", []):
        walk(k)


walk(c.call("ui_dump", panel="StaffSearchReport", depth=60, max=5000))
digits = "".join(ch for ch in (count_text or [""])[0] if ch.isdigit())
if not digits or int(digits) != res["count"]:
    errors.append(f"on-screen count {count_text} != {res['count']}")
backing = c.call("list_rows", panel="StaffSearchReport", max=1000)["rows"]
if {r["uid"] for r in backing if isinstance(r, dict)} != {r["uid"] for r in rows}:
    errors.append("returned uids differ from the table's backing rows")
for r in rows:
    good = [v for v in r["attributes"].values() if isinstance(v, int) and 1 <= v <= 20]
    if len(good) < 15:
        errors.append(f"{r['name']}: {len(good)} attributes in 1-20")
if errors:
    print("FAIL:\n  " + "\n  ".join(errors[:30]))
    sys.exit(1)
print(f"OK: {len(rows)}/{res['count']} rows in {took:.1f}s from SquadScreen; count matches screen {count_text[0]!r};"
      f" uids == table rows; {sum(1 for r in rows if r['current_wage'])} with current wage, wage_demand unknown")
