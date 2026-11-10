"""Contract advisor data (F5): contracts against the game's own wage structure. Reads only; no advice."""
from datetime import date


def _parse(s) -> date | None:
    try:
        return date.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def _clause(m):
    """Release clause Money, or None when absent (the op sends null; a 0 / "-" Money never means a price)."""
    if not m or not m.get("value") or m.get("display") == "-":
        return None
    return m


def table(players: list, structure: list, today: date) -> list[dict]:
    """One row per player, soonest contract end first, missing end date last."""
    advised: dict = {}
    for r in structure:  # the same status text can appear twice with different advice: then it is ambiguous
        a = r.get("advised_max")
        advised[r["status"]] = a if advised.get(r["status"], a) == a else None
    rows = []
    for p in players:
        c = p.get("contract") or {}
        end = _parse(c.get("end_date"))
        status = c.get("squad_status")
        rows.append({"uid": p["uid"], "name": p["name"], "age": p.get("age"), "squad_status": status,
                     "end_date": end.isoformat() if end else None,
                     "days_left": (end - today).days if end else None, "wage": c.get("wage"),
                     "release_clause": _clause(c.get("release_clause")), "renewal_offer": c.get("renewal_offer"),
                     "advised_max": advised.get(status["display"]) if status else None})
    return sorted(rows, key=lambda r: (r["end_date"] is None, r["end_date"] or ""))
