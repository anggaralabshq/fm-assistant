"""Scouted star ranges (F6, F7). The game masks by knowledge: unscouted = -1/-1 = unknown, never 0 stars."""


def to_stars(v) -> float | None:
    """Game value (0-20 scale) to stars, as the first-team star widget shows it: (v - 10) / 2.

    ponytail: TODO(controller) below 10 returns None until the youth mapping (FMStarRatingSettings.YouthConfig) is
    verified live against the youth SquadScreen; then replace this single function and record it in docs/protocol.md.
    """
    if isinstance(v, bool) or not isinstance(v, int) or not 10 <= v <= 20:
        return None
    return (v - 10) / 2


def _range(r) -> list[float] | None:
    """{min, max} -> [lo, hi] in stars; None for null, -1/-1, out-of-range values or unmapped values."""
    if not isinstance(r, dict):
        return None
    lo, hi = to_stars(r.get("min")), to_stars(r.get("max"))
    return None if lo is None or hi is None else [lo, hi]


def of(raw: dict | None) -> dict:
    raw = raw or {}
    return {"current": _range(raw.get("current")), "potential": _range(raw.get("potential"))}


def _n(x: float) -> str:
    return f"{x:g}"


def fmt(rng: list[float] | None) -> str:
    """[3.5, 4.0] -> '3.5–4'; [4.0, 4.0] -> '4'; None -> '?'."""
    if not rng:
        return "?"
    return _n(rng[0]) if rng[0] == rng[1] else f"{_n(rng[0])}–{_n(rng[1])}"


def with_stars(rows: list[dict]) -> list[dict]:
    return [{**r, "stars": of(r.get("stars_raw"))} for r in rows]
