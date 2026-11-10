"""Training calendar helpers: real dates for the month view, weekly load."""
from collections import Counter
from datetime import date, timedelta

CONDITION_MIN = 85   # percent; below this a player counts as tired


def assign_dates(day_numbers: list[int], today: date) -> list[date]:
    """The unique run of consecutive dates containing today whose day-of-month sequence equals day_numbers."""
    fits = []
    for i, d in enumerate(day_numbers):
        if d != today.day:
            continue
        start = today - timedelta(days=i)
        if [(start + timedelta(days=k)).day for k in range(len(day_numbers))] == day_numbers:
            fits.append(start)
    if not fits:
        raise ValueError(f"no consecutive dates through today ({today}) match the calendar's day numbers")
    if len(fits) > 1:
        raise ValueError(f"ambiguous calendar: {len(fits)} date runs through today ({today}) match")
    return [fits[0] + timedelta(days=k) for k in range(len(day_numbers))]


def with_dates(cal: dict) -> list[dict]:
    """training op result -> its days, each with "date" (ISO)."""
    dates = assign_dates([d["day_of_month"] for d in cal["days"]], date.fromisoformat(cal["today"]))
    return [{**d, "date": dt.isoformat()} for d, dt in zip(cal["days"], dates)]


def week_load(days: list, squad: list, fatigue_max: float | None = None) -> dict:
    """{"weeks": {"YYYY-Www": {"matches", "sessions": {name: count}}}, "tired": [player]}.
    Tired = condition below CONDITION_MIN, or fatigue above fatigue_max when given. Squad state is current,
    so it is reported once, not per week."""
    weeks: dict[str, dict] = {}
    for d in days:
        y, w, _ = date.fromisoformat(d["date"]).isocalendar()
        wk = weeks.setdefault(f"{y}-W{w:02d}", {"matches": 0, "sessions": Counter()})
        wk["matches"] += 1 if d.get("match") else 0
        wk["sessions"].update(s for s in d["sessions"] if s)
    tired = [p for p in squad
             if (p.get("condition") is not None and p["condition"] < CONDITION_MIN)
             or (fatigue_max is not None and p.get("fatigue") is not None and p["fatigue"] > fatigue_max)]
    return {"weeks": {k: {"matches": v["matches"], "sessions": dict(v["sessions"])} for k, v in weeks.items()},
            "tired": tired}
