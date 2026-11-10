from fm_assistant import players

from helpers import fixture


def rows():
    return fixture("player_search.json")["rows"]


def test_affordable_filters_known_prices():
    out = players.affordable(rows(), transfer_budget=300000, wage_headroom=5000)
    assert [r["uid"] for r in out] == [21, 23]   # 22 costs 900000 and earns 8000


def test_affordable_uses_asking_price_before_value():
    out = players.affordable(rows(), transfer_budget=160000, wage_headroom=5000)
    assert 21 not in [r["uid"] for r in out]     # value 150000 fits, asking price 200000 does not


def test_affordable_keeps_unknown_flagged():
    out = {r["uid"]: r for r in players.affordable(rows(), transfer_budget=300000, wage_headroom=5000)}
    assert out[23]["budget_unknown"] is True
    assert out[21]["budget_unknown"] is False


def test_range_values_pass_through():
    out = players.normalize(fixture("player_search.json"))
    first = out["rows"][0]
    assert first["attributes"]["AttributePassing"] == "8-12"
    assert first["position"] == "AM (C)"
