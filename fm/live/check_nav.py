"""Live check (Task 4): nav_open opens screens by panel id, no text matching, allowlist enforced.

Usage: uv run --project fm python fm/live/check_nav.py
"""
import sys

from fm_assistant.client import FmClient, FmError

c = FmClient(timeout=30)
errors = []
for panel in ("StaffSearchReport", "TrainingScreen", "SquadScreen"):
    try:
        r = c.call("nav_open", panel=panel)
    except FmError as e:
        errors.append(f"{panel}: {e.code}: {e.detail}")
        continue
    ids = [p["panel_id"] for p in c.call("panels")]
    if r != {"panel": panel, "open": True} or panel not in ids:
        errors.append(f"{panel}: result {r}, open panels {ids}")
try:
    c.call("nav_open", panel="MainMenu")
    errors.append("MainMenu: expected bad-request (not allowlisted)")
except FmError as e:
    if e.code != "bad-request":
        errors.append(f"MainMenu: got {e.code}")
if errors:
    print("FAIL:\n  " + "\n  ".join(errors))
    sys.exit(1)
print("OK: StaffSearchReport, TrainingScreen, SquadScreen opened by id; MainMenu refused")
