"""Session briefing (F1-lite): one summary over the read ops. A failed part is {"error": code}; the rest still runs."""
from datetime import date

from . import fixtures as fixtures_mod, form as form_mod, loans as loans_mod, training as training_mod
from . import vacancies as vacancies_mod, watch as watch_mod

PARTS = ("squad", "training", "fixtures", "form", "club", "loans")
MAX_LINES = 12


def _ok(p) -> bool:
    return isinstance(p, dict) and "error" not in p


def build(parts: dict) -> dict:
    sq, tr, fx, fo, cl, lo = (parts.get(k) for k in PARTS)
    today_s = next((p["today"] for p in (sq, tr, fx) if _ok(p) and p.get("today")), None)
    today = date.fromisoformat(today_s) if today_s else None
    days = training_mod.with_dates(tr) if _ok(tr) else []
    b: dict = {"today": today_s}
    if _ok(fx):
        nxt = fx.get("next")
        b["next_fixture"] = nxt and {**nxt, "days_until": fixtures_mod.days_until(nxt, today) if today else None,
                                     "threat": fx.get("threat")}
    else:
        b["next_fixture"] = fx or {"error": "missing"}
    if _ok(sq) and today:
        players = sq["players"]
        inj = watch_mod.injuries(players, today, days)
        if not days:  # no calendar: a match count would be a guess
            inj = [{**i, "matches_missed": None, "beyond_view": False} for i in inj]
        b["injuries"] = inj
        b["expiring"] = watch_mod.expiring(players, today, 180)
        b["tired"] = [{"uid": p["uid"], "name": p["name"], "condition": p["condition"]} for p in players
                      if not p.get("injured") and isinstance(p.get("condition"), (int, float))
                      and 0 <= p["condition"] < training_mod.CONDITION_MIN]
    else:
        b["injuries"] = b["expiring"] = b["tired"] = sq if not _ok(sq) else {"error": "no-date"}
    if _ok(fo):
        fl = form_mod.flags(form_mod.summary(fo))
        b["concerns"], b["low_form"] = fl["concerns"], fl["low_form"]
    else:
        b["concerns"] = b["low_form"] = fo or {"error": "missing"}
    b["vacancies_open"] = sum(j["open"] for j in vacancies_mod.open_jobs(cl)) if _ok(cl) else (cl or {"error": "missing"})
    if _ok(lo):
        lo = loans_mod.normalize(lo)
        b["loans_flagged"] = loans_mod.flags(lo["out"], date.fromisoformat(lo["today"]))
        b["intake_days"] = (lo.get("intake") or {}).get("days")
    else:
        b["loans_flagged"] = b["intake_days"] = lo or {"error": "missing"}
    return b


def _names(rows: list, n: int = 4) -> str:
    more = f" +{len(rows) - n}" if len(rows) > n else ""
    return ", ".join(r["name"] for r in rows[:n]) + more


def text(b: dict) -> str:
    """At most MAX_LINES lines, most urgent first."""
    lines = [f"briefing {b.get('today') or '?'}"]

    def section(label, val, fmt):
        if isinstance(val, dict) and "error" in val:
            lines.append(f"{label}: unavailable ({val['error']})")
        elif val:
            lines.append(f"{label}: {fmt(val)}")

    nf = b.get("next_fixture")
    if nf is None:
        lines.append("next match: no fixture scheduled")
    else:
        label = "fixtures" if isinstance(nf, dict) and "error" in nf else "next match"
        section(label, nf, lambda f: f"{f['opponent']['name']} {f['date']} ({fixtures_mod.venue(f)}"
                                          f"{', in ' + str(f['days_until']) + ' d' if f.get('days_until') is not None else ''})")
    section("injured", b.get("injuries"), lambda rs: "; ".join(
        f"{r['name']} back {r['return_date'] or '?'}" + (
            "" if r["matches_missed"] is None else f", misses {'≥' if r['beyond_view'] else ''}{r['matches_missed']}")
        for r in rs[:3]) + (f" +{len(rs) - 3}" if len(rs) > 3 else ""))
    section("tired", b.get("tired"), _names)
    section("contracts ending ≤180 d", b.get("expiring"), _names)
    section("concerns", b.get("concerns"), _names)
    section("low form", b.get("low_form"), _names)
    section("staff vacancies", b.get("vacancies_open"), str)
    section("loans to check", b.get("loans_flagged"), _names)
    iv = b.get("intake_days")
    if isinstance(iv, int) and iv <= 30:
        lines.append(f"youth intake in {iv} d")
    return "\n".join(lines[:MAX_LINES])
