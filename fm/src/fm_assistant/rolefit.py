"""Active tactic vs squad (F3): position fit and condition facts per slot. Reports only; never proposes anything."""
from .positions import covers
from .training import CONDITION_MIN


def check(tactic: dict, squad: dict) -> list[dict]:
    """One row per tactic slot. A slot may be empty (player None) or hold a player gone from the squad list:
    those rows keep what is known and leave natural/injured/condition None."""
    by_uid = {p["uid"]: p for p in squad.get("players") or []}
    rows = []
    for s in tactic.get("slots") or []:
        who = s.get("player")
        p = by_uid.get(who["uid"]) if who else None
        natural = None
        if p is not None:
            try:
                natural = covers(p.get("position_mask") or 0, s.get("position_label"))
            except ValueError:
                natural = None   # label not a known slot: unknown, not False
        rows.append({"index": s["index"], "position_label": s.get("position_label"), "role": s.get("role"),
                     "player": who, "natural": natural,
                     "injured": None if p is None else p.get("injured"),
                     "condition": None if p is None else p.get("condition"),
                     "best_oop_role": None if p is None else p.get("best_oop_role")})
    return rows


def flags(rows: list[dict]) -> dict:
    """Facts about the XI: players out of position, injured or tired. Slots without a known player are skipped."""
    return {"out_of_position": [r for r in rows if r["natural"] is False],
            "injured_or_tired": [r for r in rows if r["injured"] or (
                isinstance(r["condition"], (int, float)) and 0 <= r["condition"] < CONDITION_MIN)]}


def text(tactic: dict, rows: list[dict], table) -> str:
    """Slot table plus two fact lines. `table` is the CLI's table formatter."""
    yn = {True: "yes", False: "no", None: "?"}

    def cell(r):
        return [r["index"], r["position_label"] or "?", r["role"] or "?", (r["player"] or {}).get("name") or "(empty)",
                yn[r["natural"]], "?" if r["condition"] is None else ("injured" if r["injured"] else f"{r['condition']}%")]

    fl = flags(rows)
    who = lambda rs: ", ".join(f"{r['player']['name']} ({r['position_label']})" for r in rs) or "none"
    return (f"Tactic: {tactic.get('name') or '?'}, mentality {tactic.get('mentality') or '?'}\n"
            + table([cell(r) for r in rows], ["slot", "position", "role", "player", "natural", "condition"])
            + f"\nout of position: {who(fl['out_of_position'])}"
            + f"\ninjured/tired in XI: {who(fl['injured_or_tired'])}")
