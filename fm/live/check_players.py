"""Live check (Task 8): op player_search returns every Player Database row as the manager sees it.

- opens the Player Database itself (starting from the Squad screen) and returns all rows (count = on-screen count);
- check_knowledge_parity: for every rendered table row, the wage cell text equals the op's wage display
  (or "T/A" when the op has none) in table order; attribute values are only ints 1-20, "a-b" ranges or "-"
  (the game's own knowledge masking — no true values leak for unscouted players);
- at least one unscouted player shows "-" or ranges, proving masking is live.

Usage: uv run --project fm python fm/live/check_players.py
"""
import re
import sys
import time

from fm_assistant.client import FmClient

c = FmClient(timeout=95)
errors = []
c.call("nav_open", panel="SquadScreen")
t0 = time.monotonic()
res = c.call("player_search", max=1000)
took = time.monotonic() - t0
rows = res["rows"]


def find(n, key):
    if isinstance(n, list):
        for x in n:
            r = find(x, key)
            if r:
                return r
        return None
    if (n.get("name") or n.get("type")) == key:
        return n
    for k in n.get("children", []):
        r = find(k, key)
        if r:
            return r
    return None


def texts(n, out):
    if n.get("text"):
        out.append((n.get("bind"), n["text"]))
    for k in n.get("children", []):
        texts(k, out)
    return out


dump = c.call("ui_dump", panel="PlayerSearchReport", depth=60, max=8000)
count_text = [t for b, t in texts({"children": dump}, []) if b == "personsearch.PersonListCount"]
if not count_text or int(re.sub(r"\D", "", count_text[0]) or -1) != res["count"]:
    errors.append(f"on-screen count {count_text} != {res['count']}")
if res["count"] <= 1000 and len(rows) != res["count"]:
    errors.append(f"returned {len(rows)} of {res['count']}")
view = find(find(dump, "playertable"), "View")
rendered = [[t for b, t in texts(r, []) if b == "binding.DisplayValue"] for r in view["children"]]
for i, cell in enumerate(rendered):
    want = (rows[i]["wage"] or {}).get("display", "T/A")
    if cell != [want]:
        errors.append(f"row {i} ({rows[i]['name']}): wage cell {cell} != {want!r}")
ok_value = re.compile(r"^(-|\d{1,2}-\d{1,2})$")
masked = 0
for r in rows:
    vals = list(r["attributes"].values())
    bad = [v for v in vals if not ((isinstance(v, int) and 1 <= v <= 20) or (isinstance(v, str) and ok_value.match(v)))]
    if bad:
        errors.append(f"{r['name']}: unexpected attribute values {bad[:3]}")
    masked += any(isinstance(v, str) for v in vals)
if not masked:
    errors.append("no player has masked attributes; knowledge masking not observed")
if errors:
    print("FAIL:\n  " + "\n  ".join(errors[:30]))
    sys.exit(1)
print(f"OK: {len(rows)}/{res['count']} rows in {took:.1f}s; {len(rendered)} rendered wage cells match in order;"
      f" {masked} players with masked attributes; values only 1-20 / ranges / '-'")
