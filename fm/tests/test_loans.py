import json
from datetime import date

from fm_assistant import loans

from helpers import fixture
from test_cli import HELLO, fake_calls, run

TODAY = date(2026, 9, 14)
NO_LOANS = {"today": "2026-09-14", "out": [], "intake": {"date": "2027-01-05", "days": 113}}


def loan(uid=1, start="2026-07-01", apps=0, rating=0.0):
    return {"uid": uid, "name": f"P{uid}", "age": 20, "club": {"uid": 9, "name": "C"}, "start_date": start,
            "end_date": None, "apps": apps, "rating": rating, "happiness": None, "agreed_time": "-", "actual_time": "-"}


def test_no_loans(monkeypatch):
    calls = fake_calls(monkeypatch, {"hello": HELLO, "loans": NO_LOANS})
    r = run("squad", "loans")
    assert r.exit_code == 0, r.output + r.stderr
    assert "none" in r.stdout.lower()
    assert [op for op, _ in calls] == ["hello", "loans"]  # one op call, no per-player reads
    res = json.loads(run("--json", "squad", "loans").stdout)["result"]
    assert res["out"] == [] and res["flagged"] == []


def test_loan_rating_null_when_no_apps():
    out = loans.normalize({"out": [loan(1, apps=0, rating=0.0), loan(2, apps=4, rating=6.8)]})["out"]
    assert out[0]["rating"] is None
    assert out[1]["rating"] == 6.8


def test_flag_unused_loanee_after_21_days():
    out = [loan(1, "2026-08-24"),   # exactly 21 days, no apps -> flagged
           loan(2, "2026-08-25"),   # 20 days -> not yet
           loan(3, "2026-07-01", apps=3, rating=6.5),  # played
           loan(4, None)]           # unknown start -> never flagged
    assert [l["uid"] for l in loans.flags(out, TODAY)] == [1]


def test_intake_days():
    text = loans.intake_line(NO_LOANS["intake"])
    assert "Youth intake: 2027-01-05" in text and "113 days" in text
    assert "Youth intake: unknown" in loans.intake_line({"date": None, "days": None})


def test_squad_loans_text_none(monkeypatch):
    fake_calls(monkeypatch, {"hello": HELLO, "loans": NO_LOANS})
    r = run("squad", "loans")
    assert r.stdout.splitlines()[0] == "Out on loan: none"


def test_squad_loans_json_and_text_with_loanees(monkeypatch):
    fake_calls(monkeypatch, {"hello": HELLO, "loans": fixture("loans.json")})
    res = json.loads(run("--json", "squad", "loans").stdout)["result"]
    assert [l["rating"] for l in res["out"]] == [None, 6.9, None, None]
    assert [l["uid"] for l in res["flagged"]] == [11]
    text = run("squad", "loans").stdout
    assert "Eko Saputra" in text and "Rawa Tengah" in text and "Flagged" in text
