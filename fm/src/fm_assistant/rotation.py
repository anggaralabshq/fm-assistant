"""Rotation hints before congested fixtures (F4). Facts and options only: nobody is told to play or rest."""
from datetime import date

from .fixtures import days_until
from .positions import covers

MAX_OPTIONS = 3


def hints(fit_rows: list, squad_players: list, upcoming: list, today: date, form_rows: list,
          window_days: int = 7, condition_min: int = 90) -> dict:
    """matches_in_window: fixtures from today through today + window_days. With fewer than 2, nothing else is filled.
    at_risk: XI players injured or under condition_min. options: per at-risk slot, bench players who cover it."""
    n = sum(1 for f in upcoming or [] if (d := days_until(f, today)) is not None and 0 <= d <= window_days)
    out = {"matches_in_window": n, "at_risk": [], "options": {}}
    if n < 2:
        return out
    xi = {r["player"]["uid"] for r in fit_rows if r.get("player")}
    last5 = {r["uid"]: r.get("last5_rating") for r in form_rows or []}
    for r in fit_rows:
        cond = r.get("condition")
        if not r.get("player") or not (r.get("injured") or (isinstance(cond, (int, float)) and cond < condition_min)):
            continue
        out["at_risk"].append({"slot": r["index"], "position_label": r["position_label"], "player": r["player"],
                               "condition": cond, "injured": bool(r.get("injured"))})
        pool = []
        for p in squad_players:
            if p["uid"] in xi or p.get("injured"):
                continue
            try:
                ok = covers(p.get("position_mask") or 0, r["position_label"])
            except ValueError:
                ok = False
            if ok:
                pool.append({"uid": p["uid"], "name": p["name"], "condition": p.get("condition"),
                             "last5_rating": last5.get(p["uid"]), "natural": True})
        pool.sort(key=lambda o: (-(o["condition"] if isinstance(o["condition"], (int, float)) else -1),
                                 o["last5_rating"] is None, -(o["last5_rating"] or 0)))
        out["options"][r["index"]] = pool[:MAX_OPTIONS]
    return out


def text(h: dict, days: int) -> str:
    if h["matches_in_window"] < 2:
        return f"no congested fixtures in the next {days} days ({h['matches_in_window']} match(es))"
    lines = [f"{h['matches_in_window']} matches in the next {days} days"]
    if not h["at_risk"]:
        lines.append("XI: nobody injured or below the condition threshold")
    for r in h["at_risk"]:
        state = "injured" if r["injured"] else f"condition {r['condition']}%"
        opts = ", ".join(f"{o['name']} ({o['condition']}%, last 5 "
                         f"{'-' if o['last5_rating'] is None else format(o['last5_rating'], '.2f')})"
                         for o in h["options"][r["slot"]]) or "none found"
        lines.append(f"{r['position_label']}: {r['player']['name']} {state}; options: {opts}")
    return "\n".join(lines)
