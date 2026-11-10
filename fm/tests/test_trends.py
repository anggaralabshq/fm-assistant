import json

from fm_assistant import trends

from helpers import fixture
from test_briefing import parts
from test_cli import HELLO, fake_calls, run


def P(name="A", condition=95, morale=10, rating=7.0, apps=5, injured=False):
    return {"name": name, "condition": condition, "morale": morale, "rating": rating, "apps": apps, "injured": injured}


def S(date="2026-09-01", club_uid=900001, players=None, balance=1000, budget=500, wage=100):
    return {"club_uid": club_uid, "date": date, "balance": balance, "transfer_budget": budget, "wage_remaining": wage,
            "players": players if players is not None else {"1": P()}}


def test_save_same_date_overwrites(tmp_path):
    p1 = trends.save(S(balance=1), tmp_path)
    p2 = trends.save(S(balance=2), tmp_path)
    assert p1 == p2 == tmp_path / "900001" / "2026-09-01.json"
    assert json.loads(p1.read_text())["balance"] == 2
    assert len(list((tmp_path / "900001").iterdir())) == 1


def test_load_previous_picks_latest_not_after(tmp_path):
    for d in ("2026-08-01", "2026-08-20", "2026-09-10"):
        trends.save(S(date=d), tmp_path)
    assert trends.load_previous(900001, "2026-09-05", tmp_path)["date"] == "2026-08-20"
    assert trends.load_previous(900001, "2026-09-10", tmp_path)["date"] == "2026-08-20"   # earlier day beats same day
    assert trends.load_previous(900001, "2026-07-01", tmp_path) is None


def test_trends_other_club_ignored(tmp_path, monkeypatch):
    trends.save(S(club_uid=555), tmp_path)
    assert trends.load_previous(900001, "2026-12-01", tmp_path) is None
    # a stray file in this club's folder that belongs to another club is ignored too
    (tmp_path / "900001").mkdir()
    (tmp_path / "900001" / "2026-08-01.json").write_text(json.dumps(S(club_uid=555, date="2026-08-01")))
    (tmp_path / "900001" / "2026-08-02.json").write_text("not json")
    assert trends.load_previous(900001, "2026-12-01", tmp_path) is None
    monkeypatch.setattr(trends, "SNAP_DIR", tmp_path)
    fake_calls(monkeypatch, {"hello": HELLO, "club": fixture("club.json"), "squad": fixture("squad.json"),
                             "form": fixture("form.json")})
    res = json.loads(run("--json", "trends").stdout)["result"]
    assert res["previous"] is None and res["diff"] is None


def test_trends_without_previous(tmp_path, monkeypatch):
    monkeypatch.setattr(trends, "SNAP_DIR", tmp_path)
    fake_calls(monkeypatch, {"hello": HELLO, "club": fixture("club.json"), "squad": fixture("squad.json"),
                             "form": fixture("form.json")})
    r = run("trends")
    assert r.exit_code == 0, r.output + r.stderr
    assert "no earlier snapshot for this club" in r.stdout
    assert (tmp_path / "900001" / "2026-08-03.json").exists()      # today's snapshot was saved
    r2 = run("--json", "trends")                                    # second run: same day -> diff with days 0
    res = json.loads(r2.stdout)["result"]
    assert res["diff"]["days"] == 0 and res["previous"] == "2026-08-03"
    assert "since 2026-08-03 (0 days)" in run("trends").stdout


def test_diff_rating_needs_two_more_apps():
    old = S(players={"1": P("A", rating=7.0, apps=5), "2": P("B", rating=6.0, apps=5), "3": P("C", rating=7.0, apps=5),
                     "4": P("D", rating=7.0, apps=5), "5": P("E", rating=None, apps=0)})
    new = S(date="2026-09-08", players={
        "1": P("A", rating=7.5, apps=7),    # +0.5 over 2 apps: up
        "2": P("B", rating=5.5, apps=6),    # -0.5 but only 1 more app: ignored
        "3": P("C", rating=6.6, apps=7),    # -0.4 over 2 apps: down
        "4": P("D", rating=7.2, apps=9),    # +0.2 < 0.3: ignored
        "5": P("E", rating=7.0, apps=3)})   # no earlier rating: ignored
    d = trends.diff(old, new)
    assert d["days"] == 7
    assert [r["name"] for r in d["rating_up"]] == ["A"] and d["rating_up"][0]["change"] == 0.5
    assert [r["name"] for r in d["rating_down"]] == ["C"] and d["rating_down"][0]["change"] == -0.4


def test_diff_money_morale_injuries():
    old = S(balance=1000, budget=500, wage=100, players={
        "1": P("A", morale=12), "2": P("B", injured=True), "3": P("C", morale=None), "4": P("D")})
    new = S(date="2026-09-03", balance=900, budget=700, wage=None, players={
        "1": P("A", morale=9), "2": P("B", injured=False), "3": P("C", morale=5), "4": P("D", injured=True),
        "9": P("Baru", injured=True)})
    d = trends.diff(old, new)
    assert (d["days"], d["balance_change"], d["budget_change"]) == (2, -100, 200)
    assert [r["name"] for r in d["morale_down"]] == ["A"]    # unknown earlier morale is not a drop
    assert [r["name"] for r in d["new_injuries"]] == ["D"]   # a new arrival is not a "new injury"
    assert [r["name"] for r in d["recovered"]] == ["B"]


def test_snapshot_from_reads():
    snap = trends.snapshot(fixture("club.json"), fixture("squad.json"), fixture("form.json"))
    assert (snap["club_uid"], snap["date"], snap["balance"], snap["transfer_budget"]) == (900001, "2026-08-03", 1200000, 239000)
    assert snap["wage_remaining"] == 3000
    assert set(snap["players"]) == {"1", "2", "3"}
    assert snap["players"]["1"] == {"name": "Rúben Gonçalves", "condition": 96, "morale": 12, "rating": 6.8, "apps": 6,
                                    "injured": False}
    assert snap["players"]["3"]["injured"] is True


def test_snapshot_cli_saves_and_reports_path(tmp_path, monkeypatch):
    monkeypatch.setattr(trends, "SNAP_DIR", tmp_path)
    fake_calls(monkeypatch, {"hello": HELLO, "club": fixture("club.json"), "squad": fixture("squad.json"),
                             "form": fixture("form.json")})
    res = json.loads(run("--json", "snapshot").stdout)["result"]
    assert res["path"] == str(tmp_path / "900001" / "2026-08-03.json") and res["players"] == 3


def test_briefing_writes_snapshot_unless_opted_out(tmp_path, monkeypatch):
    monkeypatch.setattr(trends, "SNAP_DIR", tmp_path)
    fake_calls(monkeypatch, {"hello": HELLO, **parts(inbox=fixture("inbox.json"))})
    assert run("briefing", "--no-snapshot").exit_code == 0
    assert not list(tmp_path.iterdir())
    r = run("briefing")
    assert r.exit_code == 0, r.output + r.stderr
    assert (tmp_path / "900001" / "2026-08-03.json").exists()


def test_snap_dir_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("FM_ASSISTANT_SNAP_DIR", str(tmp_path / "x"))
    assert trends.default_dir() == tmp_path / "x"
    monkeypatch.delenv("FM_ASSISTANT_SNAP_DIR")
    assert trends.default_dir().parts[-2:] == (".fm-assistant", "snapshots")


def test_previous_prefers_earlier_day_over_todays_briefing_snapshot(tmp_path):
    trends.save(S(date="2026-08-25", balance=1), tmp_path)
    trends.save(S(date="2026-09-01", balance=2), tmp_path)   # briefing earlier today saved this
    assert trends.load_previous(900001, "2026-09-01", tmp_path)["date"] == "2026-08-25"
    assert trends.load_previous(900001, "2026-08-25", tmp_path)["date"] == "2026-08-25"   # nothing earlier: same day


def test_trends_refuses_when_snapshots_are_dated_after_today(tmp_path, monkeypatch):
    # another career at the same club, or an older save reloaded: comparing would mix two timelines
    trends.save(S(date="2026-12-01"), tmp_path)
    trends.save(S(date="2026-07-01"), tmp_path)
    monkeypatch.setattr(trends, "SNAP_DIR", tmp_path)
    fake_calls(monkeypatch, {"hello": HELLO, "club": fixture("club.json"), "squad": fixture("squad.json"),
                             "form": fixture("form.json")})
    res = json.loads(run("--json", "trends").stdout)["result"]
    assert res["diff"] is None and res["previous"] is None and res["later_snapshot"] == "2026-12-01"
    assert "dated after today" in run("trends").stdout
