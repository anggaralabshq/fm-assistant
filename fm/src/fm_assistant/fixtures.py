"""Next fixtures and the assistant's threat note (F8). Reported as the game shows it; nothing is advised."""
from datetime import date


def days_until(fx: dict, today: date) -> int | None:
    try:
        return (date.fromisoformat(fx["date"]) - today).days
    except (TypeError, ValueError, KeyError):
        return None


def venue(fx: dict) -> str:
    return {True: "H", False: "A", None: "venue unknown"}[fx.get("home")]


def _when(n: int | None) -> str:
    if n is None:
        return "date unknown"
    return "today" if n == 0 else f"in {n} days" if n > 0 else f"{-n} days ago"


def line(fx: dict, today: date) -> str:
    v = venue(fx)
    return (f"{fx['date']} ({_when(days_until(fx, today))}) {(fx.get('opponent') or {}).get('name') or '?'} "
            f"{v if v == 'venue unknown' else '(' + v + ')'}" + (f" {fx['competition']}" if fx.get("competition") else ""))


def text(res: dict) -> str:
    today = date.fromisoformat(res["today"])
    nxt = res.get("next")
    if not nxt:
        return "no fixture scheduled"
    out = ["Next: " + line(nxt, today)]
    if res.get("threat"):
        out.append("Assistant: " + res["threat"])
    if res.get("report") is not None:
        out.append("Scouting report on the opponent: " + ("available" if res["report"] else "none yet"))
    if res.get("opponent_formation"):
        out.append("Most used formation: " + res["opponent_formation"])
    if res.get("upcoming"):
        out.append("\nUpcoming")
        out += ["  " + line(f, today) for f in res["upcoming"]]
    return "\n".join(out)
