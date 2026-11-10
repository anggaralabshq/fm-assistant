"""Squad depth per position slot and scouting targets for thin slots (F6). Counts positions only: no formation, no lineup."""
import json
from pathlib import Path

from . import stars
from .positions import SLOTS, covers

USER_DEPTH = Path.home() / ".fm-assistant" / "depth.json"
DEFAULT_MIN = 2


def load_minimums(user_path: Path | None = USER_DEPTH) -> dict[str, int]:
    """Default 2 per slot; the owner's file overrides slot by slot."""
    mins = {s: DEFAULT_MIN for s in SLOTS}
    if user_path and Path(user_path).exists():
        mins.update(json.loads(Path(user_path).read_text()))
    return mins


def depth(players: list, minimums: dict) -> dict:
    """A player counts in every slot he covers; `fit` excludes injured. Players covering no slot go to unknown_position."""
    slots = []
    for slot in SLOTS:
        cover = [p for p in players if covers(p.get("position_mask") or 0, slot)]
        fit = sum(1 for p in cover if not p.get("injured"))
        m = minimums.get(slot, DEFAULT_MIN)
        slots.append({"slot": slot, "count": len(cover), "fit": fit, "names": [p["name"] for p in cover],
                      "thin": fit < m, "min": m})
    unknown = [p["name"] for p in players if not any(covers(p.get("position_mask") or 0, s) for s in SLOTS)]
    return {"slots": slots, "unknown_position": unknown}


def targets(slots: list, prospects: list, top: int = 5) -> dict[str, list]:
    """Per slot, prospects covering it, best first: budget-known, then scouted potential (max, in stars), then
    current (max), then younger. Unknown stars (unscouted, -1) sort after every known value, never as 0 stars."""
    def key(p):
        st = stars.of(p.get("stars_raw"))
        pot, cur = (st["potential"] or [None, None])[1], (st["current"] or [None, None])[1]
        age = p.get("age")
        return (bool(p.get("budget_unknown")), pot is None, -(pot or 0), cur is None, -(cur or 0), age is None, age or 0)

    return {s["slot"]: sorted((p for p in prospects if covers(p.get("position_mask") or 0, s["slot"])), key=key)[:top]
            for s in slots}
