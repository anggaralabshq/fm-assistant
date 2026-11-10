import json
import subprocess

import pytest

pytest.importorskip("mcp")
from fm_assistant import mcp_server as m  # noqa: E402


def fake_run(monkeypatch, stdout="", code=0):
    seen = []

    def run(argv, **kw):
        seen.append(argv)
        return subprocess.CompletedProcess(argv, code, stdout=stdout, stderr="")

    monkeypatch.setattr(m.subprocess, "run", run)
    return seen


def tool(name):
    return next(t for t in m.TOOLS if t.name == name)


def test_argv_plain():
    assert tool("club_budget").argv_for({}) == ["club", "budget"]


def test_argv_flags_and_defaults_omitted():
    t = tool("squad_watch")
    assert t.argv_for({}) == ["squad", "watch"]
    assert t.argv_for({"within": 14, "team": "youth"}) == ["squad", "watch", "--within", "14", "--team", "youth"]


def test_argv_required_option():
    assert tool("staff_search").argv_for({"role": "scout", "top": 5}) == ["staff", "search", "--role", "scout", "--top", "5"]


def test_argv_bool_flag():
    assert tool("players_search").argv_for({"affordable": True}) == ["players", "search", "--affordable"]
    assert tool("players_search").argv_for({"affordable": False}) == ["players", "search"]


def test_table_has_expected_tools_and_nothing_acting():
    names = {t.name for t in m.TOOLS}
    assert names == {"doctor", "game_status", "club_budget", "squad_list", "staff_search", "staff_slots",
                     "players_search", "training_show", "training_load", "staff_vacancies", "squad_watch",
                     "squad_depth", "players_targets", "briefing", "fixtures", "squad_contracts", "squad_form",
                     "squad_loans"}
    argvs = [set(t.argv) for t in m.TOOLS]
    assert not any(a & {"launch", "restart", "load-recent", "call"} for a in argvs)


def test_run_invokes_json_cli_and_returns_parsed(monkeypatch):
    seen = fake_run(monkeypatch, json.dumps({"ok": True, "build_supported": True, "result": {"x": 1}}))
    out = m.run_tool(tool("club_budget"), {})
    assert out == {"ok": True, "build_supported": True, "result": {"x": 1}}
    assert seen[0][-3:] == ["--json", "club", "budget"]


def test_error_envelope_passthrough_on_nonzero(monkeypatch):
    err = {"ok": False, "error": {"code": "no-career-loaded", "detail": "x"}}
    fake_run(monkeypatch, json.dumps(err), code=3)
    assert m.run_tool(tool("squad_list"), {}) == err


def test_unparseable_output_becomes_error(monkeypatch):
    fake_run(monkeypatch, "Traceback boom", code=1)
    out = m.run_tool(tool("squad_list"), {})
    assert out["ok"] is False and out["error"]["code"] == "bad-output"


def test_timeout_becomes_error(monkeypatch):
    def run(argv, **kw):
        raise subprocess.TimeoutExpired(argv, 1)

    monkeypatch.setattr(m.subprocess, "run", run)
    assert m.run_tool(tool("doctor"), {})["error"]["code"] == "timeout"


def test_server_registers_every_tool():
    import asyncio
    tools = asyncio.run(m.build_server().list_tools())
    tools = getattr(tools, "tools", tools)
    assert {t.name for t in tools} == {t.name for t in m.TOOLS}
    team = next(t for t in tools if t.name == "squad_watch")
    schema = getattr(team, "input_schema", None) or getattr(team, "inputSchema", None)
    assert "youth" in json.dumps(schema)
