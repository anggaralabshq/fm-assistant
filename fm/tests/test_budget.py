from fm_assistant import budget

from helpers import fixture


def money(v):
    return {"display": f"Rp{v}", "value": v}


def test_wage_headroom():
    assert budget.wage_headroom({"wage_budget": money(1000), "wage_committed": money(800)}) == 200


def test_wage_headroom_never_negative():
    assert budget.wage_headroom({"wage_budget": money(800), "wage_committed": money(1000)}) == 0


def test_fmt_uses_display():
    assert budget.fmt(fixture("club.json")["transfer_budget"]) == "Rp239Jt"
    assert budget.fmt(None) == "?"
