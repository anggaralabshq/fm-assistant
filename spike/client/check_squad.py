"""Live check for op `squad`: cross-check against the newest save's summary (read-only).

Usage: CLI_ANYTHING_FM27=<path to cli-anything-fm27/agent-harness> uv run python check_squad.py
"""
import datetime as dt
import os
import sys
from pathlib import Path

from fmspike import FmClient

GAMES = Path.home() / "Library/Application Support/Sports Interactive/Football Manager 27/games"


def newest_save() -> Path:
    saves = [p for p in GAMES.glob("*.fm") if "backup" not in p.name]
    return max(saves, key=lambda p: p.stat().st_mtime)


def same_person(save_name: str, full: str) -> bool:
    """Save summary shortens to "B. Santoso"; plugin has "Budi Santoso". Single names ("Rendra") match exactly."""
    if save_name == full:
        return True
    initial, dot, surname = save_name.partition(". ")
    return bool(dot) and full.split()[-1:] == [surname] and full.startswith(initial)


def youth_names(club_uid: int) -> list:
    c = FmClient(timeout=95)
    club = c.call("read", ref="club", uid=club_uid, props=["HighestLevelYouthTeam", "YouthTeam"])
    out = []
    for team in club.values():
        if isinstance(team, dict) and "uid" in team:
            for p in c.call("read", ref="team", uid=team["uid"], props=["Players"]).get("Players", []):
                out.append(c.call("read", ref="person", uid=p["uid"], props=["Name"]).get("Name", ""))
    return out


def attrs(player: dict) -> list:
    return [v for k, v in player.items() if k.startswith("Attribute") and isinstance(v, (int, float))]


def main() -> int:
    sys.path.insert(0, os.environ["CLI_ANYTHING_FM27"])
    from cli_anything.fm27.core.saves import save_info

    squad = FmClient(timeout=95).call("squad")
    players = squad["players"]
    names = {p.get("Name") for p in players}
    errors = []
    for p in players:
        if len([a for a in attrs(p) if 1 <= a <= 20]) < 3:
            errors.append(f"{p.get('Name')}: <3 attributes in 1-20: {p}")
        end = (p.get("contract") or {}).get("EndDate")
        try:
            dt.date.fromisoformat(str(end))
        except ValueError:
            errors.append(f"{p.get('Name')}: EndDate not a date: {end!r}")

    save = newest_save()
    expected = [s["name"] for s in save_info(save)["summary"]["squad_snapshot"]]
    matched = [n for n in expected if any(same_person(n, m or "") for m in names)]
    if len(matched) < len(expected):  # save snapshot mixes in youth players; look there via op `read`
        youth = youth_names(squad["club"]["uid"])
        matched += [n for n in expected if n not in matched and any(same_person(n, m) for m in youth)]
    for n in expected:
        if n not in matched:
            errors.append(f"save name missing from plugin: {n!r}")

    print(f"club={squad['club']} team={squad['team']} save={save.name}")
    for p in players[:5]:
        print("  sample:", p)
    if errors:
        print("FAIL:\n  " + "\n  ".join(errors[:30]))
        return 1
    print(f"OK: {len(players)} players, {len(matched)}/{len(expected)} matched save summary")
    return 0


if __name__ == "__main__":
    sys.exit(main())
