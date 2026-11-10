"""Live check (Phase 1c Task 1): contract details and wage structure over the real squad and club ops.

Every squad player has squad_status.code as an int; club.wage_structure has >= 1 row; each total.value is a
number; the squad op still answers in under 30 s.

Usage: uv run --project fm python fm/live/check_contracts.py
"""
import sys
import time
from datetime import date

from fm_assistant import contracts
from fm_assistant.client import FmClient

c = FmClient(timeout=95)
errors = []
t0 = time.time()
squad = c.call("squad", team="first")
took = time.time() - t0
if took >= 30:
    errors.append(f"squad took {took:.1f}s (>= 30 s)")
club = c.call("club")
structure = club.get("wage_structure") or []
if not structure:
    errors.append("wage_structure is empty")
for r in structure:
    v = (r.get("total") or {}).get("value")
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        errors.append(f"{r.get('status')!r}: total.value {v!r} is not a number")
for p in squad["players"]:
    code = ((p.get("contract") or {}).get("squad_status") or {}).get("code")
    if not isinstance(code, int) or isinstance(code, bool):
        errors.append(f"{p['name']}: squad_status.code {code!r} is not an int")
rows = contracts.table(squad["players"], structure, date.fromisoformat(squad["today"]))
unmatched = sorted({r["squad_status"]["display"] for r in rows if r["squad_status"] and r["advised_max"] is None})
if unmatched:
    print(f"note: statuses with no wage_structure row: {unmatched}")
codes = sorted({r["squad_status"]["code"] for r in rows if r["squad_status"]})
print(f"squad_status codes seen: {codes}")
if errors:
    print("FAIL:\n  " + "\n  ".join(errors[:30]))
    sys.exit(1)
print(f"OK: {len(rows)} players, {len(structure)} wage-structure rows, squad in {took:.1f}s")
