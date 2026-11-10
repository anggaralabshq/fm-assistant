"""Local snapshots and season trends (F9). Snapshots live outside the repo: <root>/<club_uid>/<game date>.json."""
import json
import os
from datetime import date
from pathlib import Path

from . import form as form_mod

RATING_MIN_CHANGE = 0.3
RATING_MIN_APPS = 2


def default_dir() -> Path:
    env = os.environ.get("FM_ASSISTANT_SNAP_DIR")
    return Path(env) if env else Path.home() / ".fm-assistant" / "snapshots"


SNAP_DIR = default_dir()


def _val(m):
    return m.get("value") if isinstance(m, dict) else None


def snapshot(club: dict, squad: dict, form: dict) -> dict:
    """Compact state of the club and every first-team player on the game date. Unknown values stay null."""
    rows = {r["uid"]: r for r in form_mod.summary(form)}
    players = {}
    for p in squad["players"]:
        f = rows.get(p["uid"]) or {}
        players[str(p["uid"])] = {"name": p["name"], "condition": p.get("condition"), "morale": f.get("morale"),
                                  "rating": f.get("rating"), "apps": f.get("apps"), "injured": bool(p.get("injured"))}
    return {"club_uid": club.get("uid") or (squad.get("club") or {}).get("uid"), "date": squad["today"],
            "balance": _val(club.get("balance")), "transfer_budget": _val(club.get("transfer_budget")),
            "wage_remaining": _val(club.get("wage_remaining")), "players": players}


def save(snap: dict, root: Path | None = None) -> Path:
    path = Path(root or SNAP_DIR) / str(snap["club_uid"]) / f"{snap['date']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snap, ensure_ascii=False, indent=1))
    return path


def _snaps(club_uid, root: Path | None = None):
    """This club's readable snapshots, newest first. Unreadable files and other clubs' files are skipped."""
    folder = Path(root or SNAP_DIR) / str(club_uid)
    for f in sorted(folder.glob("*.json"), reverse=True) if folder.is_dir() else []:
        try:
            snap = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        if isinstance(snap, dict) and snap.get("club_uid") == club_uid:
            yield snap


def load_previous(club_uid, before_date: str, root: Path | None = None) -> dict | None:
    """Latest snapshot of this club dated strictly before `before_date`; only when none exists, a same-day one
    (so a briefing earlier today never hides last week's snapshot, and a re-run still diffs with days 0)."""
    same_day = None
    for snap in _snaps(club_uid, root):
        if snap.get("date", "") < before_date:
            return snap
        if snap.get("date") == before_date and same_day is None:
            same_day = snap
    return same_day


def later_snapshot(club_uid, today: str, root: Path | None = None) -> str | None:
    """Date of a snapshot newer than today: another career at this club or an older save reloaded.
    ponytail: no career id in the plugin yet, so time going backwards is the signal; add the human uid when exposed."""
    newest = next(_snaps(club_uid, root), None)
    return newest["date"] if newest and newest.get("date", "") > today else None


def _change(a, b):
    return None if a is None or b is None else b - a


def diff(old: dict, new: dict) -> dict:
    both = [(uid, old["players"][uid], new["players"][uid]) for uid in new["players"] if uid in old["players"]]
    up, down, morale_down, hurt, healed = [], [], [], [], []
    for uid, o, n in both:
        row = {"uid": int(uid), "name": n["name"]}
        if (o.get("rating") is not None and n.get("rating") is not None
                and (n.get("apps") or 0) - (o.get("apps") or 0) >= RATING_MIN_APPS):
            ch = round(n["rating"] - o["rating"], 2)
            if ch >= RATING_MIN_CHANGE:
                up.append({**row, "old": o["rating"], "new": n["rating"], "change": ch})
            elif ch <= -RATING_MIN_CHANGE:
                down.append({**row, "old": o["rating"], "new": n["rating"], "change": ch})
        if o.get("morale") is not None and n.get("morale") is not None and n["morale"] < o["morale"]:
            morale_down.append({**row, "old": o["morale"], "new": n["morale"]})
        if n.get("injured") and not o.get("injured"):
            hurt.append(row)
        if o.get("injured") and not n.get("injured"):
            healed.append(row)
    return {"days": (date.fromisoformat(new["date"]) - date.fromisoformat(old["date"])).days,
            "balance_change": _change(old.get("balance"), new.get("balance")),
            "budget_change": _change(old.get("transfer_budget"), new.get("transfer_budget")),
            "rating_up": up, "rating_down": down, "morale_down": morale_down,
            "new_injuries": hurt, "recovered": healed}


def text(snap: dict, prev: dict | None, d: dict | None, later: str | None = None) -> str:
    if later:
        return (f"not compared: this club has a snapshot dated after today ({later}), so it is from another career or"
                f" a reloaded older save. Move {Path(SNAP_DIR) / str(snap['club_uid'])} aside to start fresh.")
    if prev is None or d is None:
        return "no earlier snapshot for this club (saved today's; run again after the game date moves on)"

    def names(rows, key=None):
        return ", ".join(f"{r['name']}" + (f" {r[key]:+g}" if key else "") for r in rows) or "none"

    def money(v):
        return "?" if v is None else f"{v:+,}"

    return "\n".join([
        f"Trends since {prev['date']} ({d['days']} days)",
        f"balance {money(d['balance_change'])}, transfer budget {money(d['budget_change'])}",
        f"rating up: {names(d['rating_up'], 'change')}",
        f"rating down: {names(d['rating_down'], 'change')}",
        f"morale down: {names(d['morale_down'])}",
        f"new injuries: {names(d['new_injuries'])}",
        f"recovered: {names(d['recovered'])}"])
