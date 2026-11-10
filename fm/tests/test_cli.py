import json

import pytest
from click.testing import CliRunner

from fm_assistant import cli, doctor, game
from fm_assistant.client import FmClient, FmError, FmUnavailable

HELLO = {"plugin": "fm-assistant", "plugin_version": "0.1.0", "protocol": 1, "game_build": "27.0.0.2493426",
         "build_supported": True, "tested_builds": ["27.0.0.2493426"], "bindings_captured": True,
         "career_loaded": True, "human_club_uid": 7}


def fake_calls(monkeypatch, answers: dict):
    """answers: op -> result, or an exception instance to raise."""
    calls = []

    def call(self, op, **args):
        calls.append((op, args))
        a = answers[op]
        if isinstance(a, Exception):
            raise a
        return a

    monkeypatch.setattr(FmClient, "call", call)
    return calls


def run(*args):
    return CliRunner().invoke(cli.main, list(args))


@pytest.fixture
def install(monkeypatch, tmp_path):
    app = tmp_path / "shadow/fm.app"
    app.mkdir(parents=True)
    log = tmp_path / "LogOutput.log"
    log.write_text("[Message:   BepInEx] Chainloader startup complete\n")
    session = tmp_path / "session.json"
    session.write_text("{}")
    monkeypatch.setattr(doctor, "SHADOW_APP", app)
    monkeypatch.setattr(doctor, "LOADER_LOG", log)
    monkeypatch.setattr(doctor, "SESSION", session)
    monkeypatch.setattr(doctor, "FEATURES", [("squad read", "read", {"ref": "path", "path": "Human.Club", "props": ["Name"]})])


def test_doctor_all_ok(monkeypatch, install):
    fake_calls(monkeypatch, {"hello": HELLO, "read": {"Name": "X"}})
    r = run("doctor")
    assert r.exit_code == 0, r.output + r.stderr
    lines = r.stdout.strip().splitlines()
    assert len(lines) == 7
    assert all(line.startswith("ok") for line in lines)


def test_unsupported_build_warns(monkeypatch):
    monkeypatch.setattr(game, "pids", lambda: ["42"])
    fake_calls(monkeypatch, {"hello": {**HELLO, "build_supported": False, "game_build": "27.0.9"}})
    r = run("game", "status")
    assert r.exit_code == 0
    assert "warning: game build 27.0.9 is not tested with this plugin (tested: 27.0.0.2493426)" in r.stderr


def test_unsupported_build_flag_in_json(monkeypatch):
    monkeypatch.setattr(game, "pids", lambda: ["42"])
    fake_calls(monkeypatch, {"hello": {**HELLO, "build_supported": False, "game_build": "27.0.9"}})
    r = run("--json", "game", "status")
    assert json.loads(r.stdout)["build_supported"] is False


def test_cli_errors_are_one_line(monkeypatch):
    fake_calls(monkeypatch, {"hello": FmUnavailable("no session")})
    r = run("call", "hello")
    assert (r.exit_code, r.stderr) == (2, "FM27 is not running with the assistant plugin. Start it from Steam.\n")
    fake_calls(monkeypatch, {"read": FmError("read", "no-career-loaded", "load a career first")})
    r = run("call", "read")
    assert (r.exit_code, r.stderr) == (3, "No career loaded.\n")


def test_json_error_shape(monkeypatch):
    fake_calls(monkeypatch, {"read": FmError("read", "no-career-loaded", "x")})
    r = run("--json", "call", "read")
    body = json.loads(r.stdout)
    assert body["ok"] is False
    assert body["error"]["code"] == "no-career-loaded"


def test_restart_refuses_loaded_career(monkeypatch, tmp_path):
    ran = []
    monkeypatch.setattr(game.subprocess, "run", lambda *a, **k: ran.append(a))
    monkeypatch.setattr(game, "pids", lambda: ["42"])
    monkeypatch.setattr(game, "MARKER", tmp_path / "none.json")
    fake_calls(monkeypatch, {"hello": HELLO})
    r = run("game", "restart")
    assert r.exit_code == 3
    assert "refusing to kill" in r.stderr
    assert ran == []


def test_doctor_stops_when_plugin_missing(monkeypatch, install):
    fake_calls(monkeypatch, {"hello": FmUnavailable("refused")})
    r = run("doctor")
    assert r.exit_code == 1
    assert r.stdout.strip().splitlines()[-1].startswith("FAIL plugin answers")


def test_status_when_game_not_running(monkeypatch):
    monkeypatch.setattr(game, "pids", lambda: [])
    r = run("--json", "game", "status")
    assert (r.exit_code, json.loads(r.stdout)["result"]) == (0, {"running": False})


# --- feature commands (Tasks 5-9) ---
from helpers import fixture  # noqa: E402


def test_club_budget_shows_headroom_and_slots(monkeypatch):
    fake_calls(monkeypatch, {"hello": HELLO, "club": fixture("club.json")})
    r = run("club", "budget")
    assert r.exit_code == 0, r.output
    assert "Rp239Jt" in r.output and "wage headroom: Rp72Jt" in r.output
    assert "coaching 7/9" in r.output


def test_squad_list_decodes_positions(monkeypatch):
    calls = fake_calls(monkeypatch, {"hello": HELLO, "squad": fixture("squad.json")})
    r = run("--json", "squad", "list", "--team", "youth")
    assert ("squad", {"team": "youth"}) in calls
    assert [p["position"] for p in json.loads(r.output)["result"]["players"]] == ["ST (C)", "D (LC)", "GK"]


def test_staff_search_ranks_and_tops(monkeypatch):
    calls = fake_calls(monkeypatch, {"hello": HELLO, "staff_search": fixture("staff_search.json")})
    r = run("--json", "staff", "search", "--role", "coach_attacking", "--top", "2", "--max", "50")
    assert ("staff_search", {"max": 50}) in calls
    res = json.loads(r.output)["result"]
    assert [s["uid"] for s in res["rows"]] == [12, 11] and res["role"] == "coach_attacking"


def test_truncation_flag(monkeypatch):
    fake_calls(monkeypatch, {"hello": HELLO, "staff_search": {**fixture("staff_search.json"), "returned": 200}})
    r = run("staff", "search", "--role", "scout")
    assert r.exit_code == 0, r.output
    assert "200 of 5000 shown" in r.output


def test_staff_search_unknown_role_is_usage_error(monkeypatch):
    fake_calls(monkeypatch, {"hello": HELLO})
    r = run("staff", "search", "--role", "nope")
    assert r.exit_code == 2 and "coach_attacking" in r.output


def test_staff_slots(monkeypatch):
    fake_calls(monkeypatch, {"hello": HELLO, "club": fixture("club.json")})
    r = run("--json", "staff", "slots")
    assert json.loads(r.output)["result"]["medical"] == {"used": 1, "max": 3}


def test_players_search_affordable_uses_club_budget(monkeypatch):
    fake_calls(monkeypatch, {"hello": HELLO, "club": fixture("club.json"), "player_search": fixture("player_search.json")})
    r = run("--json", "players", "search", "--affordable")
    res = json.loads(r.output)["result"]
    assert all("budget_unknown" in p for p in res["rows"]) and all("position" in p for p in res["rows"])


def test_training_show_limits_weeks(monkeypatch):
    fake_calls(monkeypatch, {"hello": HELLO, "training": fixture("training.json")})
    r = run("--json", "training", "show", "--weeks", "1")
    days = json.loads(r.output)["result"]["days"]
    assert [d["date"] for d in days] == ["2026-08-03", "2026-08-04"]
    r = run("--json", "training", "show", "--weeks", "0")
    assert [d["date"] for d in json.loads(r.output)["result"]["days"]] == ["2026-08-03"]


def test_training_load(monkeypatch):
    fake_calls(monkeypatch, {"hello": HELLO, "training": fixture("training.json"), "squad": fixture("squad.json")})
    r = run("--json", "training", "load")
    res = json.loads(r.output)["result"]
    assert res["weeks"]["2026-W31"]["matches"] == 2 and len(res["tired"]) == 1


def test_doctor_features_listed():
    assert [op for _, op, _ in doctor.FEATURES] == ["club", "squad", "staff_search", "player_search", "training"]


def test_malformed_game_data_is_one_line_not_traceback(monkeypatch):
    club = fixture("club.json")
    club["wage_budget"] = None
    fake_calls(monkeypatch, {"hello": HELLO, "club": club})
    r = run("--json", "club", "budget")
    assert r.exit_code == 3
    assert "Traceback" not in r.output
    assert json.loads(r.output.splitlines()[0])["error"]["code"] == "internal"


def test_training_other_month_asks_for_current_month(monkeypatch):
    cal = fixture("training.json")
    cal["today"] = "2026-10-20"
    fake_calls(monkeypatch, {"hello": HELLO, "training": cal})
    r = run("training", "show")
    assert r.exit_code == 3 and "Traceback" not in r.output
    assert "current month" in r.output


def test_staff_search_reads_1000_rows_by_default(monkeypatch):
    calls = fake_calls(monkeypatch, {"hello": HELLO, "staff_search": fixture("staff_search.json")})
    run("staff", "search", "--role", "scout")
    assert ("staff_search", {"max": 1000}) in calls


def test_timeout_message_is_not_game_closed(monkeypatch):
    fake_calls(monkeypatch, {"hello": HELLO, "club": FmError("club", "timeout", "no answer in 35s")})
    r = run("club", "budget")
    assert r.exit_code == 3 and "not running" not in r.output and "did not answer" in r.output
