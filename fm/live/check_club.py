"""Live check (Task 5): op club returns budgets formatted like the UI, a consistent wage headroom, staff slots.

The ClubScreen overview shows money in the owner's currency; our display strings must use the same currency
notation (the game's own formatter, BindableTranslationUtils.FormatCashValue). Exact on-screen equality is not
required: tiles round the last digit and the overview's transfer tile can differ from TransferBudget by ~1%.

Usage: uv run --project fm python fm/live/check_club.py
"""
import re
import sys

from fm_assistant.client import FmClient

c = FmClient(timeout=60)
errors = []
club = c.call("club")
again = c.call("club")
if club != again:
    errors.append("two reads differ")
money = {k: v for k, v in club.items() if isinstance(v, dict) and "display" in v}
for k in ("balance", "transfer_budget", "wage_budget", "wage_committed", "wage_remaining"):
    m = money.get(k)
    if not m or not isinstance(m["value"], (int, float)) or not re.search(r"\d", m["display"] or ""):
        errors.append(f"{k}: {m}")
if not errors and club["wage_budget"]["value"] - club["wage_committed"]["value"] != club["wage_remaining"]["value"]:
    errors.append(f"wage budget - committed != remaining: {money}")
for g in ("coaching", "recruitment", "medical"):
    s = club["staff_slots"].get(g)
    if not s or not all(isinstance(s[x], int) for x in ("used", "max")) or not s["jobs"]:
        errors.append(f"staff_slots.{g}: {s}")

c.call("nav_open", panel="ClubScreen")
texts = []


def walk(n):
    if isinstance(n, list):
        for x in n:
            walk(x)
        return
    if n.get("text"):
        texts.append(n["text"])
    for ch in n.get("children", []):
        walk(ch)


walk(c.call("ui_dump", panel="ClubScreen", depth=40, max=4000))
prefix = re.match(r"\D*", club["balance"]["display"]).group(0)
on_screen = [t for t in texts if re.match(re.escape(prefix) + r"\d", t)] if prefix else []
if not on_screen:
    errors.append(f"no ClubScreen money text uses currency prefix {prefix!r}")
if errors:
    print("FAIL:\n  " + "\n  ".join(errors))
    sys.exit(1)
print(f"OK: club {club['name']}: " + ", ".join(f"{k} {v['display']}" for k, v in money.items())
      + f"; prefix {prefix!r} matches {len(on_screen)} on-screen texts; headroom consistent; 3 slot groups")
