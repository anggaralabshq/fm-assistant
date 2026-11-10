import json

from fm_assistant import briefing

from helpers import fixture
from test_cli import HELLO, fake_calls, run


def parts(**over):
    p = {"squad": fixture("squad.json"), "training": fixture("training.json"), "fixtures": fixture("fixtures.json"),
         "form": fixture("form.json"), "club": fixture("club_jobs.json"), "loans": fixture("loans.json")}
    return {**p, **over}


def test_briefing_without_fixture():
    b = briefing.build(parts(fixtures={**fixture("fixtures.json"), "next": None, "upcoming": []}))
    assert b["next_fixture"] is None
    assert "no fixture scheduled" in briefing.text(b)


def test_briefing_part_error_does_not_stop_others():
    b = briefing.build(parts(fixtures={"error": "timeout"}, training={"error": "wrong-screen"}))
    assert b["next_fixture"] == {"error": "timeout"}
    assert b["injuries"] and b["injuries"][0]["return_date"] == "2026-08-05"
    assert b["injuries"][0]["matches_missed"] is None  # no calendar, no match count
    assert b["vacancies_open"] == 5
    assert "fixtures: unavailable (timeout)" in briefing.text(b)


def test_briefing_tired_excludes_injured():
    sq = fixture("squad.json")
    sq["players"][2]["condition"] = -1  # the game reports injured players at -1
    b = briefing.build(parts(squad=sq))
    assert sq["players"][2]["name"] not in {p["name"] for p in b["tired"]}


def test_briefing_text_max_12_lines():
    sq = fixture("squad.json")
    many = [{**sq["players"][0], "uid": 100 + i, "name": f"Pemain {i}", "condition": 50} for i in range(30)]
    b = briefing.build(parts(squad={**sq, "players": sq["players"] + many}))
    assert len(briefing.text(b).splitlines()) <= 12


def test_briefing_cli_calls_no_staff_search(monkeypatch):
    p = parts()
    calls = fake_calls(monkeypatch, {"hello": HELLO, **p})
    r = run("--json", "briefing")
    assert r.exit_code == 0, r.output + r.stderr
    assert "staff_search" not in [c[0] for c in calls] and "player_search" not in [c[0] for c in calls]
    assert json.loads(r.stdout)["result"]["today"] == "2026-08-03"


def test_briefing_survives_bad_data_in_one_part():
    fx = {**fixture("fixtures.json"), "next": {"date": None, "opponent": None, "home": None, "competition": None}}
    b = briefing.build(parts(fixtures=fx))
    assert b["injuries"] and b["vacancies_open"] == 5
    t = briefing.text(b)
    assert "injured:" in t
