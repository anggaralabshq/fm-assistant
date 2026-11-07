"""Live check for training_get / training_set_session (Task 5).

Changes one future session to Rest, verifies exactly that slot changed, restores it, verifies the calendar
equals the first read. Session names are the game's localized display text (owner plays in Indonesian).

Usage: uv run python check_training.py
"""
import sys
import time

from fmspike import FmClient, FmError

TARGET = "Istirahat"  # "Rest" in the owner's Indonesian UI
FIRST_DAY = 15        # day index in the month view; >= 15 is next week or later (today is index 7)

c = FmClient(timeout=95)


def cal() -> list:
    return [(d["label"], tuple(d["sessions"])) for d in c.call("training_get")["days"]]


def diff(a, b) -> list:
    return [(i, s, x, y) for i, (da, db) in enumerate(zip(a, b)) for s, (x, y) in enumerate(zip(da[1], db[1])) if x != y]


def main() -> int:
    c.call("ui_click_text", text="LATIHAN")
    time.sleep(3)
    first = cal()
    pick = next(((i, s, name) for i, (_, ss) in enumerate(first) if i >= FIRST_DAY
                 for s, name in enumerate(ss) if name not in (TARGET, "Perjalanan") and not name.startswith("vs ")), None)
    if pick is None:
        print("FAIL: no changeable session found")
        return 1
    i, s, orig = pick
    print(f"day {i} ({first[i][0]}) slot {s}: {orig!r} -> {TARGET!r}")

    r1 = c.call("training_set_session", index=i, slot=s, name=TARGET)
    changed = cal()
    d1 = diff(first, changed)
    r2 = c.call("training_set_session", index=i, slot=s, name=orig)
    restored = cal()

    errors = []
    if r1 != {"before": orig, "after": TARGET}:
        errors.append(f"set result {r1}")
    if d1 != [(i, s, orig, TARGET)]:
        errors.append(f"expected exactly one change, got {d1}")
    if r2 != {"before": TARGET, "after": orig}:
        errors.append(f"restore result {r2}")
    if restored != first:
        errors.append(f"calendar not restored: {diff(first, restored)}")

    c.call("ui_click_text", text="SKUAD")
    time.sleep(2.5)
    for op, args in (("training_set_session", dict(index=i, slot=s, name=TARGET)), ("training_get", {})):
        try:
            c.call(op, **args)
            errors.append(f"{op}: expected wrong-screen off the training screen")
        except FmError as e:
            if e.code != "wrong-screen":
                errors.append(f"{op}: expected wrong-screen, got {e.code}: {e.detail}")

    if errors:
        print("FAIL:\n  " + "\n  ".join(errors))
        return 1
    print(f"OK: changed {i}/{s} {orig} -> {TARGET} -> {orig}; calendar restored; wrong-screen off screen")
    return 0


if __name__ == "__main__":
    sys.exit(main())
