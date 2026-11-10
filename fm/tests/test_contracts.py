import json
from datetime import date

from fm_assistant import contracts

from helpers import fixture
from test_cli import HELLO, fake_calls, run

TODAY = date(2026, 8, 3)
STRUCT = fixture("club.json")["wage_structure"]


def pl(uid, end="2027-06-30", status=("Key Player", 23), release=None, **kw):
    return {"uid": uid, "name": f"P{uid}", "age": 25,
            "contract": {"wage": {"display": "w", "value": 1}, "end_date": end,
                         "squad_status": {"display": status[0], "code": status[1]} if status else None,
                         "release_clause": release, "renewal_offer": None, **kw}}


def test_table_sorted_by_end_date_missing_last():
    rows = contracts.table([pl(1, "2028-06-30"), pl(2, None), pl(3, "2026-12-31")], STRUCT, TODAY)
    assert [r["uid"] for r in rows] == [3, 1, 2]
    assert rows[2]["end_date"] is None and rows[2]["days_left"] is None


def test_release_clause_none():
    # op sends null when sort is 0; a stray "-"/0 Money must not become a price either
    zero = {"display": "-", "value": 0}
    rows = contracts.table([pl(1, release=None), pl(2, release=zero),
                            pl(3, release={"display": "Rp5Mi", "value": 5e9})], STRUCT, TODAY)
    by = {r["uid"]: r for r in rows}
    assert by[1]["release_clause"] is None and by[2]["release_clause"] is None
    assert by[3]["release_clause"] == {"display": "Rp5Mi", "value": 5e9}


def test_advised_max_matched_by_status_display():
    rows = contracts.table([pl(1, status=("Key Player", 23)), pl(2, status=("Rotation", 21)),
                            pl(3, status=("Nonexistent", 1)), pl(4, status=None)], STRUCT, TODAY)
    by = {r["uid"]: r for r in rows}
    assert by[1]["advised_max"] == "Rp35Jt p/mgg"
    assert by[2]["advised_max"] == "Rp15Jt p/mgg"
    assert by[3]["advised_max"] is None and by[4]["advised_max"] is None
    assert by[4]["squad_status"] is None


def test_days_left_from_today():
    rows = contracts.table([pl(1, "2026-12-31"), pl(2, "2026-08-01")], STRUCT, TODAY)
    assert [(r["uid"], r["days_left"]) for r in rows] == [(2, -2), (1, 150)]


def test_squad_contracts_json_shape(monkeypatch):
    calls = fake_calls(monkeypatch, {"hello": HELLO, "squad": fixture("squad.json"), "club": fixture("club.json")})
    r = run("--json", "squad", "contracts")
    assert r.exit_code == 0, r.output + r.stderr
    res = json.loads(r.stdout)["result"]
    assert res["today"] == "2026-08-03"
    assert [p["uid"] for p in res["players"]] == [3, 2, 1]
    assert set(res["players"][0]) == {"uid", "name", "age", "squad_status", "end_date", "days_left", "wage",
                                      "release_clause", "renewal_offer", "advised_max"}
    assert res["players"][2]["release_clause"]["value"] == 5000000000
    assert len(res["wage_structure"]) == 3
    assert ("squad", {"team": "first"}) in calls


def test_squad_contracts_text(monkeypatch):
    fake_calls(monkeypatch, {"hello": HELLO, "squad": fixture("squad.json"), "club": fixture("club.json")})
    r = run("squad", "contracts")
    assert r.exit_code == 0
    assert "Key Player" in r.stdout and "Rp35Jt p/mgg" in r.stdout


def test_advised_max_null_when_status_text_is_ambiguous():
    # the game lists two rows with the same status text (e.g. emergency backup outfield / goalkeeper)
    structure = [{"status": "Cadangan Darurat", "advised_max": "Rp1Jt"}, {"status": "Cadangan Darurat", "advised_max": "Rp2Jt"}]
    p = {"uid": 1, "name": "Budi Santoso", "contract": {"end_date": "2027-06-30", "squad_status": {"display": "Cadangan Darurat", "code": 24}}}
    assert contracts.table([p], structure, date(2026, 8, 3))[0]["advised_max"] is None


def test_squad_contracts_text_labels_advice_by_status_not_player(monkeypatch):
    fake_calls(monkeypatch, {"hello": HELLO, "squad": fixture("squad.json"), "club": fixture("club.json")})
    r = run("squad", "contracts")
    assert "advice for status" in r.stdout.splitlines()[0]
