"""Squad normalization."""
from .positions import decode
from .stars import with_stars


def normalize(raw: dict) -> dict:
    """Adds "position" (decoded label) and "stars" (from stars_raw) to every player."""
    return {**raw, "players": with_stars([{**p, "position": decode(p.get("position_mask") or 0)} for p in raw["players"]])}
