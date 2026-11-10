"""Player search helpers. Attribute values stay exactly as the UI shows them (ranges like "8-12", or null)."""
from .positions import decode
from .stars import with_stars


def normalize(raw: dict) -> dict:
    return {**raw, "rows": with_stars([{**r, "position": decode(r.get("position_mask") or 0)} for r in raw["rows"]])}


def affordable(rows: list, transfer_budget: float, wage_headroom: float) -> list[dict]:
    """Keeps rows whose known price (asking price, else value) and known wage fit; unknowns kept, flagged."""
    out = []
    for r in rows:
        price = (r.get("asking_price") or r.get("value") or {}).get("value")
        wage = (r.get("wage") or {}).get("value")
        if price is not None and price > transfer_budget:
            continue
        if wage is not None and wage > wage_headroom:
            continue
        out.append({**r, "budget_unknown": price is None or wage is None})
    return out
