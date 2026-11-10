"""Live check (Phase 1c Task 4): loans out and the youth intake.

len(out) == Club.PlayersOutOnLoanCount (read through `read`); none of the out uids is in the first-team squad;
intake.date >= today.

Usage: uv run --project fm python fm/live/check_loans.py
"""
import sys
from datetime import date

from fm_assistant import loans
from fm_assistant.client import FmClient

c = FmClient(timeout=95)
errors = []
res = c.call("loans")
count = c.call("read", ref="path", path="Human.Club", props=["PlayersOutOnLoanCount"]).get("PlayersOutOnLoanCount")
if len(res["out"]) != count:
    errors.append(f"len(out) {len(res['out'])} != PlayersOutOnLoanCount {count!r}")
squad_uids = {p["uid"] for p in c.call("squad", team="first")["players"]}
overlap = [l["name"] for l in res["out"] if l["uid"] in squad_uids]
if overlap:
    errors.append(f"out on loan but in the first-team squad: {overlap}")
intake = res.get("intake") or {}
if not intake.get("date") or intake["date"] < res["today"]:
    errors.append(f"intake.date {intake.get('date')!r} is before today {res['today']}")
if errors:
    print("FAIL:\n  " + "\n  ".join(errors))
    sys.exit(1)
flagged = loans.flags(loans.normalize(res)["out"], date.fromisoformat(res["today"]))
print(f"OK: {len(res['out'])} out on loan, {len(flagged)} flagged; {loans.intake_line(intake)}")
