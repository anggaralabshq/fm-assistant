"""Live check for op `staff_search_visible` (Task 4). Navigates by Indonesian tab text — spike only;
Phase 1 must navigate by panel id / element name.

Usage: uv run python check_staff.py
"""
import sys
import time

from fmspike import FmClient, FmError

c = FmClient(timeout=95)


def click(*texts):
    for t in texts:
        c.call("ui_click_text", text=t)
        time.sleep(2.5)


def on_screen_names() -> list:
    names = []

    def walk(n):
        if isinstance(n, str):
            return
        if n.get("bind") == "primarytext" and n.get("text"):
            names.append(n["text"])
        for k in n.get("children", []):
            walk(k)

    for root in c.call("ui_dump", panel="StaffSearchReport", depth=60, max=3000):
        walk(root)
    return names


def main() -> int:
    click("KLUB", "Staf", "Seluruh dunia")
    res = c.call("staff_search_visible", max=500)
    rows = res["rows"]
    got = {r["name"] for r in rows}
    seen = on_screen_names()
    errors = [f"on screen but not returned: {n!r}" for n in seen if n not in got]
    if not seen:
        errors.append("no names visible on screen")
    for r in rows[:300]:
        a = r["attributes"]
        if len([v for v in a.values() if isinstance(v, (int, float)) and 1 <= v <= 20]) < 3:
            errors.append(f"{r['name']}: <3 attributes in 1-20: {a}")
    for r in rows[:3]:
        print("  sample:", {k: r[k] for k in ("name", "age", "role", "club", "attributes")})

    click("SKUAD")
    try:
        c.call("staff_search_visible")
        errors.append("expected wrong-screen on Squad screen")
    except FmError as e:
        if e.code != "wrong-screen":
            errors.append(f"expected wrong-screen, got {e.code}: {e.detail}")
        else:
            print("  squad screen ->", e.code, "|", e.detail)

    if errors:
        print("FAIL:\n  " + "\n  ".join(errors[:30]))
        return 1
    print(f"OK: {res['returned']}/{res['count']} staff rows, {len(seen)} on-screen names all present")
    return 0


if __name__ == "__main__":
    sys.exit(main())
