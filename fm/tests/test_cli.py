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
