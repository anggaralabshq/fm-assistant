import json
from datetime import date

from fm_assistant import fixtures

from helpers import fixture
from test_cli import HELLO, fake_calls, run

NONE = {"today": "2026-09-14", "team_uid": 900101, "next": None, "upcoming": [], "threat": None,
        "opponent_formation": None}


def fx(d="2026-09-16", home=True, comp="Liga"):
    return {"date": d, "opponent": {"uid": 5, "name": "Lawan"}, "home": home, "competition": comp}


def test_fixtures_none_scheduled():
    text = fixtures.text(NONE)
    assert "no fixture scheduled" in text
    assert "None" not in text


def test_home_unknown_location():
    res = {**fixture("fixtures.json"), "next": fx(home=None)}
    text = fixtures.text(res)
    assert "venue unknown" in text
    assert "(H)" not in text.splitlines()[0] and "(A)" not in text.splitlines()[0]
    assert "Lembah Barat" in text  # unknown-venue upcoming row still prints


def test_days_until():
    assert fixtures.days_until(fx("2026-09-16"), date(2026, 9, 14)) == 2
    assert fixtures.days_until(fx("2026-09-14"), date(2026, 9, 14)) == 0
    assert fixtures.days_until(fx("2026-09-10"), date(2026, 9, 14)) == -4


def test_text_reports_threat_and_formation_without_advice():
    text = fixtures.text(fixture("fixtures.json"))
    assert "Bukit Selatan" in text and "in 2 days" in text
    assert "Bukit Selatan adalah lawan" in text
    assert "4-3-3" in text


def test_fixtures_json_shape(monkeypatch):
    calls = fake_calls(monkeypatch, {"hello": HELLO, "fixtures": fixture("fixtures.json")})
    r = run("--json", "fixtures", "--n", "3")
    assert r.exit_code == 0, r.output + r.stderr
    assert ("fixtures", {"n": 3}) in calls
    res = json.loads(r.stdout)["result"]
    assert set(res) == {"today", "team_uid", "next", "upcoming", "threat", "opponent_formation"}
    assert res["next"]["days_until"] == 2
    assert [f["days_until"] for f in res["upcoming"]] == [2, 9, 16]


def test_fixtures_cli_none_scheduled(monkeypatch):
    fake_calls(monkeypatch, {"hello": HELLO, "fixtures": NONE})
    r = run("fixtures")
    assert r.exit_code == 0
    assert "no fixture scheduled" in r.stdout
    assert json.loads(run("--json", "fixtures").stdout)["result"]["next"] is None


def test_days_until_unknown_date_is_none():
    from datetime import date
    assert fixtures.days_until({"date": None}, date(2026, 8, 3)) is None
