"""Loans out and the youth intake (F7)."""
from datetime import date

UNUSED_AFTER_DAYS = 21


def _parse(s) -> date | None:
    try:
        return date.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def normalize(res: dict) -> dict:
    """A loanee with no appearances has rating None (the game's 0 means nothing played)."""
    return {**res, "out": [{**l, "rating": l.get("rating") if (l.get("apps") or 0) > 0 else None}
                           for l in res.get("out") or []]}


def flags(out: list, today: date) -> list[dict]:
    """Loanees with no appearances whose loan started at least 21 days ago. Unknown start -> never flagged."""
    flagged = []
    for l in out:
        start = _parse(l.get("start_date"))
        if start is not None and l.get("apps") == 0 and (today - start).days >= UNUSED_AFTER_DAYS:
            flagged.append(l)
    return flagged


def intake_line(intake: dict | None) -> str:
    intake = intake or {}
    if not intake.get("date"):
        return "Youth intake: unknown"
    days = intake.get("days")
    return f"Youth intake: {intake['date']}" + (f" (in {days} days)" if isinstance(days, int) else "")
