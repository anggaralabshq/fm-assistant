"""Live check (Phase 1c Task 2): season and recent form over the real form and squad ops.

Player uids == squad uids; every season rating is null or 1-10; concerns are a subset of squad uids; the form
op answers in under 60 s.

Phase 1d Task 3: every first-team player has morale set (or both null when the game hides it), value in
MORALE_RANGE.

Usage: uv run --project fm python fm/live/check_form.py
"""
import sys
import time

from fm_assistant import form
from fm_assistant.client import FmClient

c = FmClient(timeout=95)
errors = []
squad = c.call("squad", team="first")
t0 = time.time()
f = c.call("form", team="first")
took = time.time() - t0
if took >= 60:
    errors.append(f"form took {took:.1f}s (>= 60 s)")
squad_uids = {p["uid"] for p in squad["players"]}
form_uids = {p["uid"] for p in f["players"]}
if form_uids != squad_uids:
    errors.append(f"uids differ: only squad {sorted(squad_uids - form_uids)}, only form {sorted(form_uids - squad_uids)}")
rows = form.summary(f)
for r in rows:
    for key in ("rating", "last5_rating"):
        v = r[key]
        if v is not None and not (1 <= v <= 10):
            errors.append(f"{r['name']}: {key} {v!r} outside 1-10")
# ponytail: TODO(controller) set to the range recorded live in docs/protocol.md (discovery saw about 10-13 for own players).
MORALE_RANGE = (0, 20)
for p in f["players"]:
    m, h = p.get("morale"), p.get("happiness")
    if m is None and h is not None:
        errors.append(f"{p['name']}: happiness visible but morale null")   # visible player must have morale
    if m is not None and not (MORALE_RANGE[0] <= m["value"] <= MORALE_RANGE[1]):
        errors.append(f"{p['name']}: morale {m['value']} outside {MORALE_RANGE}")
    if (m is None) != (h is None):
        errors.append(f"{p['name']}: morale and happiness should be both set or both null (CanViewHappinessInfo)")
severities = sorted({a["severity"] for p in f["players"] for a in (p.get("happiness") or {}).values()})
print("happiness severities seen (record in docs/protocol.md, set form.UNHAPPY_SEVERITY):", severities)
stray = set(f["concerns"]) - squad_uids
if stray:
    errors.append(f"concerns not in squad: {sorted(stray)}")
if errors:
    print("FAIL:\n  " + "\n  ".join(errors[:30]))
    sys.exit(1)
fl = form.flags(rows)
print(f"OK: {len(rows)} players in {took:.1f}s; low form {len(fl['low_form'])}, unused {len(fl['unused'])},"
      f" concerns {len(fl['concerns'])}; atmosphere {f.get('atmosphere')}")
