"""Season and recent form (F2). A player with no matches has rating None, never 0.0."""

LOW_FORM = 6.5


def summary(form: dict) -> list[dict]:
    concerns = set(form.get("concerns") or [])
    rows = []
    for p in form["players"]:
        seasons = p.get("season") or []
        apps = sum(s.get("apps") or 0 for s in seasons)
        rated = [s for s in seasons if (s.get("apps") or 0) > 0 and s.get("rating") is not None]
        weight = sum(s["apps"] for s in rated)
        rating = round(sum(s["apps"] * s["rating"] for s in rated) / weight, 2) if apps > 0 and weight else None
        l5 = p.get("last5") or {}
        valid = bool(l5.get("valid"))
        known = [m for m in (l5.get("minutes") or []) if isinstance(m, int)]
        rows.append({"uid": p["uid"], "name": p["name"], "apps": apps, "rating": rating,
                     "last5_rating": l5.get("rating") if valid else None,
                     "last5_minutes": sum(known) if valid and known else None,
                     "concern": p["uid"] in concerns})
    return rows


def flags(rows: list[dict], min_apps: int = 3) -> dict:
    played = any(r["apps"] > 0 for r in rows)
    return {"low_form": [r for r in rows if r["last5_rating"] is not None and r["last5_rating"] < LOW_FORM
                         and r["apps"] >= min_apps],
            "unused": [r for r in rows if played and r["apps"] == 0],
            "concerns": [r for r in rows if r["concern"]]}
