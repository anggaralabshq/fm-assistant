"""Live check (Phase 1c Task 2): season and recent form over the real form and squad ops.

Player uids == squad uids; every season rating is null or 1-10; concerns are a subset of squad uids; the form
op answers in under 60 s.

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
stray = set(f["concerns"]) - squad_uids
if stray:
    errors.append(f"concerns not in squad: {sorted(stray)}")
if errors:
    print("FAIL:\n  " + "\n  ".join(errors[:30]))
    sys.exit(1)
fl = form.flags(rows)
print(f"OK: {len(rows)} players in {took:.1f}s; low form {len(fl['low_form'])}, unused {len(fl['unused'])},"
      f" concerns {len(fl['concerns'])}; atmosphere {f.get('atmosphere')}")
