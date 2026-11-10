import json

from fm_assistant import briefing, fixtures, inbox

from helpers import fixture
from test_briefing import parts
from test_cli import HELLO, fake_calls, run


def test_inbox_since_after_all():
    # the op returns no items when `since` is after every item: the unread count is kept, nothing crashes
    res = {"today": "2026-09-14", "unread": 3, "items": []}
    t = inbox.text(res, since="2026-09-20")
    assert "3 unread" in t and "no messages since 2026-09-20" in t
    assert inbox.recent(res) == []
    b = briefing.build(parts(inbox=res))
    assert b["inbox"] == {"unread": 3, "recent": []}


def test_inbox_text_newest_first_with_unread_mark():
    lines = inbox.text(fixture("inbox.json")).splitlines()
    assert "2 unread" in lines[0]
    rows = lines[1:]
    assert [r.split()[0] for r in rows] == ["2026-09-14", "2026-09-14", "2026-09-13", "2026-09-12"]
    assert rows[0].startswith("2026-09-14 09:30 *") and "!" in rows[0]   # unread mark, important mark
    assert "*" not in rows[1].split("Laporan")[0] and "Laporan scout mingguan" in rows[1]
    assert "Tawaran untuk" in rows[0]


def test_briefing_includes_inbox_recent():
    b = briefing.build(parts(inbox=fixture("inbox.json")))
    assert b["inbox"]["unread"] == 2
    assert [r["title"] for r in b["inbox"]["recent"]][0] == "Tawaran untuk Rúben Gonçalves"
    assert set(b["inbox"]["recent"][0]) == {"date", "title"}
    t = briefing.text(b)
    assert "inbox: 2 unread" in t and "Tawaran untuk" in t
    many = {**fixture("inbox.json"), "items": fixture("inbox.json")["items"] * 3}
    assert len(briefing.build(parts(inbox=many))["inbox"]["recent"]) == 5
    assert len(t.splitlines()) <= 12


def test_briefing_inbox_error_does_not_stop_others():
    b = briefing.build(parts(inbox={"error": "timeout"}))
    assert b["inbox"] == {"error": "timeout"} and b["vacancies_open"] == 5
    assert "inbox: unavailable (timeout)" in briefing.text(b)


def test_inbox_json_shape(monkeypatch):
    calls = fake_calls(monkeypatch, {"hello": HELLO, "inbox": fixture("inbox.json")})
    r = run("--json", "inbox", "--since", "2026-09-13", "--unread", "--max", "20")
    assert r.exit_code == 0, r.output + r.stderr
    assert ("inbox", {"since": "2026-09-13", "tab": "unread", "max": 20}) in calls
    res = json.loads(r.stdout)["result"]
    assert set(res) == {"today", "unread", "items"}
    assert set(res["items"][0]) == {"id", "date", "time", "read", "important", "category", "title", "body"}


def test_inbox_cli_defaults_and_text(monkeypatch):
    calls = fake_calls(monkeypatch, {"hello": HELLO, "inbox": fixture("inbox.json")})
    r = run("inbox")
    assert r.exit_code == 0 and "Tawaran untuk" in r.stdout
    assert ("inbox", {"since": None, "tab": "all", "max": 20}) in calls


def test_briefing_cli_asks_inbox_since_yesterday(monkeypatch):
    calls = fake_calls(monkeypatch, {"hello": HELLO, **parts(inbox=fixture("inbox.json"))})
    r = run("--json", "briefing")
    assert r.exit_code == 0, r.output + r.stderr
    assert ("inbox", {"since": "2026-08-02", "tab": "all", "max": 20}) in calls
    assert json.loads(r.stdout)["result"]["inbox"]["unread"] == 2


def test_fixtures_report_flag_in_text():
    res = {**fixture("fixtures.json"), "report": True}
    assert "scouting report" in fixtures.text(res).lower()
    assert "scouting report" not in fixtures.text({**res, "report": None}).lower()
