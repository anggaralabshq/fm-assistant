"""Staff scoring: role -> attribute weights (owner-overridable), weighted mean on the game's 1-20 scale."""
import json
from importlib import resources
from pathlib import Path

USER_ROLES = Path.home() / ".fm-assistant" / "staff_roles.json"


def load_roles(user_path: Path | None = USER_ROLES) -> dict[str, dict[str, float]]:
    """Packaged weights, overridden key-by-key (role, then attribute) by the owner's file when present."""
    roles = json.loads(resources.files("fm_assistant").joinpath("data/staff_roles.json").read_text())
    if user_path and Path(user_path).exists():
        for role, weights in json.loads(Path(user_path).read_text()).items():
            roles[role] = {**roles.get(role, {}), **weights}
    return roles


def _weights(role: str, roles: dict) -> dict:
    if role not in roles:
        raise ValueError(f"unknown role {role!r}; valid: {', '.join(sorted(roles))}")
    return roles[role]


def score(s: dict, role: str, roles: dict) -> float:
    """Weighted mean of the role's attributes the row has (missing ones carry no weight), rounded to 0.1."""
    weights = _weights(role, roles)
    attrs = s.get("attributes") or {}
    have = {a: w for a, w in weights.items() if isinstance(attrs.get(a), (int, float))}
    total = sum(have.values())
    return round(sum(attrs[a] * w for a, w in have.items()) / total, 1) if total else 0.0


def rank(rows: list, role: str, max_wage: float | None, roles: dict) -> list[dict]:
    """Score desc. Rows over max_wage are dropped only when their wage demand is known."""
    _weights(role, roles)
    out = []
    for r in rows:
        wage = (r.get("wage_demand") or {}).get("value")
        over = None if max_wage is None or wage is None else wage > max_wage
        if over:
            continue
        out.append({**r, "score": score(r, role, roles), "over_budget": over})
    return sorted(out, key=lambda r: -r["score"])
