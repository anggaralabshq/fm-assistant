import copy
import json

from fm_assistant import form

from helpers import fixture
from test_cli import HELLO, fake_calls, run


def F(uid=1, season=(), last5=None):
    return {"uid": uid, "name": f"P{uid}", "season": list(season),
            "last5": last5 or {"rating": 0.0, "valid": False, "minutes": []}}


def S(apps, rating, comp="Liga"):
    return {"competition": comp, "apps": apps, "starts": apps, "subs": 0, "rating": rating}


def doc(*players, concerns=()):
    return {"today": "2026-09-14", "team": "first", "players": list(players), "concerns": list(concerns),
            "atmosphere": {"level": 3, "text": "x"}}


def test_form_no_matches_is_null_not_zero():
    # early season: every counter 0, last five invalid -> "no matches yet", never a 0.0 rating
    rows = form.summary(doc(F(1, [S(0, 0.0, None)]), F(2)))
    assert [(r["apps"], r["rating"], r["last5_rating"], r["last5_minutes"]) for r in rows] == [(0, None, None, None)] * 2
    assert form.flags(rows) == {"low_form": [], "unused": [], "concerns": []}


def test_rating_apps_weighted_over_competitions():
    rows = form.summary(doc(F(1, [S(4, 7.2), S(2, 6.0, "Piala")])))
    assert rows[0]["apps"] == 6
    assert rows[0]["rating"] == 6.8


def test_last5_minutes_full_match_is_90():
    rows = form.summary(doc(F(1, [S(5, 7.0)], {"rating": 7.0, "valid": True, "minutes": [90, 90, None, 63]})))
    assert rows[0]["last5_minutes"] == 243
    assert rows[0]["last5_rating"] == 7.0
    assert form.summary(doc(F(2, [S(1, 7.0)], {"rating": 7.0, "valid": True, "minutes": [None]})))[0]["last5_minutes"] is None


def test_unused_only_when_team_has_played():
    nobody = form.summary(doc(F(1), F(2)))
    assert form.flags(nobody)["unused"] == []
    played = form.summary(doc(F(1, [S(3, 7.0)]), F(2)))
    assert [r["uid"] for r in form.flags(played)["unused"]] == [2]


def test_low_form_needs_min_apps():
    bad = {"rating": 5.9, "valid": True, "minutes": [90]}
    rows = form.summary(doc(F(1, [S(2, 5.9)], bad), F(2, [S(3, 5.9)], bad), F(3, [S(5, 7.5)], {**bad, "rating": 7.5})))
    assert [r["uid"] for r in form.flags(rows)["low_form"]] == [2]
    assert [r["uid"] for r in form.flags(rows, min_apps=2)["low_form"]] == [1, 2]


def test_concern_flag():
    rows = form.summary(doc(F(1), F(2), concerns=[2]))
    assert [r["concern"] for r in rows] == [False, True]
    assert [r["uid"] for r in form.flags(rows)["concerns"]] == [2]


def test_squad_form_text_flags(monkeypatch):
    calls = fake_calls(monkeypatch, {"hello": HELLO, "form": fixture("form.json")})
    r = run("squad", "form")
    assert r.exit_code == 0, r.output + r.stderr
    assert ("form", {"team": "first"}) in calls
    assert "Anto Wijaya" in r.stdout and "6.8" in r.stdout
    assert "no matches yet" in r.stdout
    assert "Low form" in r.stdout and "Budi Santoso" in r.stdout
    assert "Unused" in r.stdout and "Cakra Nugraha" in r.stdout
    assert "Concerns" in r.stdout


def test_squad_form_json_shape(monkeypatch):
    fake_calls(monkeypatch, {"hello": HELLO, "form": fixture("form.json")})
    res = json.loads(run("--json", "squad", "form").stdout)["result"]
    assert set(res) == {"today", "team", "players", "flags", "atmosphere"}
    assert res["players"][3]["rating"] is None
    assert [r["uid"] for r in res["flags"]["low_form"]] == [2]
    assert copy.deepcopy(res["atmosphere"]) == {"level": 4, "text": "Penuh semangat"}
