"""Contract expiry (F2) and injury return vs fixtures (F5)."""
from datetime import date, timedelta


def _parse(s) -> date | None:
    try:
        return date.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def expiring(players: list, today: date, within_days: int = 180) -> list[dict]:
    """Players whose contract ends within within_days of today, soonest first. No parseable end_date -> skipped."""
    out = []
    for p in players:
        contract = p.get("contract") or {}
        end = _parse(contract.get("end_date"))
        if end is None:
            continue
        left = (end - today).days
        if left <= within_days:
            out.append({"uid": p["uid"], "name": p["name"], "age": p.get("age"), "end_date": end.isoformat(),
                        "days_left": left, "wage": contract.get("wage")})
    return sorted(out, key=lambda e: e["days_left"])


def injuries(players: list, today: date, days: list) -> list[dict]:
    """Injured players with their return date and the matches (from days) they miss before it.
    beyond_view: a day before the return lies after the last day in days, so matches_missed is a lower bound."""
    last = _parse(days[-1]["date"]) if days else None
    out = []
    for p in players:
        if not p.get("injured"):
            continue
        inj = p.get("injury") or {}
        rd = inj.get("return_days")
        row = {"uid": p["uid"], "name": p["name"], "description": inj.get("description"), "return_days": rd,
               "return_date": None, "matches_missed": None, "beyond_view": False}
        if isinstance(rd, int):
            ret = today + timedelta(days=rd)
            row["return_date"] = ret.isoformat()
            row["matches_missed"] = sum(1 for d in days if d.get("match") and today.isoformat() <= d["date"] < ret.isoformat())
            row["beyond_view"] = last is not None and ret > last + timedelta(days=1)
        out.append(row)
    return out
