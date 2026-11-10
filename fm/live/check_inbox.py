"""Live check (Phase 1d Task 2): inbox over the real inbox op.

OK when: `unread` equals the number of unread items in the all-tab list, dates are non-increasing, `since` = today
returns only today's items, and one run takes under 5 s.

Usage: uv run --project fm python fm/live/check_inbox.py
"""
import sys
import time

from fm_assistant.client import FmClient

c = FmClient(timeout=95)
errors = []
t0 = time.time()
allm = c.call("inbox", since=None, tab="all", max=200)
took = time.time() - t0
if took >= 5:
    errors.append(f"inbox took {took:.1f}s (>= 5 s)")
items = allm["items"]
unread_items = sum(1 for i in items if not i["read"])
if len(items) < 200 and allm["unread"] != unread_items:  # a truncated list may miss unread items
    errors.append(f"unread {allm['unread']} != unread items in list {unread_items}")
dates = [(i["date"], i["time"] or "") for i in items]
if dates != sorted(dates, reverse=True):
    errors.append("items are not newest first")
today = c.call("inbox", since=allm["today"], tab="all", max=200)
stray = [i["date"] for i in today["items"] if i["date"] != allm["today"]]
if stray:
    errors.append(f"since=today returned other dates: {sorted(set(stray))}")
if any(len(i["body"]) > 600 for i in items):
    errors.append("a body is longer than 600 characters")
if errors:
    print("FAIL:\n  " + "\n  ".join(errors))
    sys.exit(1)
print(f"OK: {len(items)} items, {allm['unread']} unread, {len(today['items'])} today, {took:.1f}s")
