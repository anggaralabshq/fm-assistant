import json

from fm_assistant import training, watch

from helpers import fixture
from test_cli import HELLO, fake_calls, run

TODAY = watch.date(2026, 8, 3)


def pl(uid, end=None, **kw):
    return {"uid": uid, "name": f"P{uid}", "age": 25, "contract": {"wage": {"display": "w", "value": 1}, "end_date": end}, **kw}


def days():
    return training.with_dates(fixture("training.json"))


def injured(return_days, uid=1):
    return pl(uid, injured=True, injury={"description": "Strain", "return_days": return_days})


def test_expiring_sorted_and_windowed():
    ps = [pl(1, "2028-06-30"), pl(2, "2027-06-30"), pl(3, "2026-12-31")]
    out = watch.expiring(ps, TODAY, 180)
    assert [e["uid"] for e in out] == [3]
    assert out[0]["days_left"] == 150
    assert out[0]["end_date"] == "2026-12-31"


def test_expiring_skips_missing_end_date():
    ps = [pl(1, None), {"uid": 2, "name": "x", "contract": None}, {"uid": 3, "name": "y"}, pl(4, "bogus"), pl(5, "2026-09-01")]
    assert [e["uid"] for e in watch.expiring(ps, TODAY)] == [5]


def test_injury_counts_matches_before_return():
    [r] = watch.injuries([injured(2)], TODAY, days())
    assert r["return_date"] == "2026-08-05"
    assert r["matches_missed"] == 1
    assert r["beyond_view"] is False


def test_injury_unknown_return():
    [r] = watch.injuries([injured(None)], TODAY, days())
    assert r["return_date"] is None and r["matches_missed"] is None and r["beyond_view"] is False


def test_injury_beyond_view():
    [r] = watch.injuries([injured(5)], TODAY, days())
    assert r["return_date"] == "2026-08-08"
    assert r["beyond_view"] is True
    assert r["matches_missed"] == 1


def test_injury_ignores_fit_players():
    assert watch.injuries([pl(1, injured=False, injury=None)], TODAY, days()) == []


def test_squad_watch_json_shape(monkeypatch):
    calls = fake_calls(monkeypatch, {"hello": HELLO, "squad": fixture("squad.json"), "training": fixture("training.json")})
    r = run("--json", "squad", "watch")
    assert r.exit_code == 0, r.output + r.stderr
    data = json.loads(r.stdout)
    res = data.get("result", data)
    assert res["today"] == "2026-08-03"
    assert {e["name"] for e in res["expiring"]} == {"Dimas Prakoso"}
    assert res["injured"][0]["return_date"] == "2026-08-05"
    assert res["injured"][0]["matches_missed"] == 1
    assert ("squad", {"team": "first"}) in calls


def test_squad_watch_non_first_team_has_no_match_counts(monkeypatch):
    fake_calls(monkeypatch, {"hello": HELLO, "squad": fixture("squad.json"), "training": fixture("training.json")})
    res = json.loads(run("--json", "squad", "watch", "--team", "reserve").stdout)["result"]
    assert res["injured"] and all(i["matches_missed"] is None and i["beyond_view"] is False for i in res["injured"])
    assert res["injured"][0]["return_date"] == "2026-08-05"
