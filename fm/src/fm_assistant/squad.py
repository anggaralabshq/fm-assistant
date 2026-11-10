"""Squad normalization."""
from .positions import decode


def normalize(raw: dict) -> dict:
    """Adds "position" (decoded label) to every player."""
    return {**raw, "players": [{**p, "position": decode(p.get("position_mask") or 0)} for p in raw["players"]]}
