"""Live check (Phase 1d Task 5): active tactic over the real tactic and squad ops.

OK when: there are 11 slots, slot player uids are a subset of the squad uids, and each position_label equals the
tactics screen label for that slot. The screen labels are not readable here: pass them in TACTICS_SCREEN_LABELS
(slot order, read once by the controller with ui_dump in dev mode) or the label comparison is skipped and printed.

Usage: uv run --project fm python fm/live/check_tactic.py
"""
import sys

from fm_assistant import rolefit
from fm_assistant.client import FmClient

# ponytail: TODO(controller) fill from the tactics screen, e.g. ["GK", "D (R)", ...]; None skips the comparison.
TACTICS_SCREEN_LABELS = None

c = FmClient(timeout=95)
errors = []
t = c.call("tactic")
squad = c.call("squad", team="first")
slots = t["slots"]
if len(slots) != 11:
    errors.append(f"{len(slots)} slots, expected 11")
if [s["index"] for s in slots] != list(range(len(slots))):
    errors.append(f"slot indexes not in order: {[s['index'] for s in slots]}")
uids = {p["uid"] for p in squad["players"]}
stray = [s["player"]["uid"] for s in slots if s["player"] and s["player"]["uid"] not in uids]
if stray:
    errors.append(f"slot players not in squad: {stray}")
if TACTICS_SCREEN_LABELS is not None:
    for s, want in zip(slots, TACTICS_SCREEN_LABELS):
        if s["position_label"] != want:
            errors.append(f"slot {s['index']}: label {s['position_label']!r} != screen {want!r}")
else:
    print("labels (compare with the tactics screen):", [s["position_label"] for s in slots])
rows = rolefit.check(t, squad)
if errors:
    print("FAIL:\n  " + "\n  ".join(errors))
    sys.exit(1)
fl = rolefit.flags(rows)
print(f"OK: {t['name']}, {sum(1 for s in slots if s['player'])} of {len(slots)} slots filled; "
      f"out of position {len(fl['out_of_position'])}, injured/tired {len(fl['injured_or_tired'])}")
