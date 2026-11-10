"""Club money helpers. Money = {"display": owner's currency text, "value": game sort value in base currency}."""


def wage_headroom(club: dict) -> float:
    """Weekly wage budget left: wage_budget - wage_committed, never negative."""
    return max(0.0, club["wage_budget"]["value"] - club["wage_committed"]["value"])


def fmt(m: dict | None) -> str:
    return m["display"] if m else "?"
