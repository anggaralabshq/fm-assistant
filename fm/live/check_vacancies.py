"""Live check (Task 1, F11): staff vacancies agree with the game's own summaries and the staff search.

For every staff group whose game `summary` contains a digit run, that number equals the sum of `open` over the
group's jobs; every candidate uid is in the staff search result; unmapped jobs have no candidates.

Usage: uv run --project fm python fm/live/check_vacancies.py
"""
import sys

from fm_assistant import staff, vacancies
from fm_assistant.client import FmClient

c = FmClient(timeout=95)
errors = []
club = c.call("club")
res = c.call("staff_search", max=1000)
jobs = vacancies.fill(vacancies.open_jobs(club), res, staff.load_roles(), vacancies.load_job_roles())
uids = {r["uid"] for r in res["rows"]}
notes = []
for group, g in club["staff_slots"].items():
    digits = "".join(ch for ch in (g.get("summary") or "") if ch.isdigit())
    opened = sum(j["open"] for j in jobs if j["group"] == group)
    if digits:
        if int(digits) != opened:
            errors.append(f"{group}: summary {g['summary']!r} says {digits}, open sums to {opened}")
        notes.append(f"{group} {opened}")
for j in jobs:
    if not j["roles"] and j["candidates"]:
        errors.append(f"{j['job']} ({j['job_type']}): unmapped but has candidates")
    for cand in j["candidates"]:
        if cand["uid"] not in uids:
            errors.append(f"{j['job']}: candidate {cand['uid']} not in the staff search")
    if (j["count"], j["returned"], j["truncated"]) != (res["count"], res["returned"], res["truncated"]):
        errors.append(f"{j['job']}: truncation fields differ from the search")
if errors:
    print("FAIL:\n  " + "\n  ".join(errors[:30]))
    sys.exit(1)
print(f"OK: {len(jobs)} open jobs ({', '.join(notes) or 'no digit summaries'}); candidates all in the "
      f"{res['returned']}/{res['count']} searched rows; {sum(1 for j in jobs if not j['roles'])} unmapped")
