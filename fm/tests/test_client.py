import json
import os
import socket

import pytest

from fm_assistant.client import FmClient, FmError, FmUnavailable


def test_call_returns_result(fake):
    f = fake(lambda req: {"ok": True, "result": {"x": 1}})
    assert FmClient(f.session).call("hello") == {"x": 1}


def test_request_carries_token_and_version(fake):
    f = fake(lambda req: {"ok": True, "result": None})
    FmClient(f.session).call("panels", a=1)
    req = f.requests[0]
    assert req["token"] == "t0k"
    assert req["v"] == 1
    assert req["op"] == "panels"
    assert req["args"] == {"a": 1}


def test_error_raises_fmerror(fake):
    f = fake(lambda req: {"ok": False, "error": {"code": "wrong-screen", "detail": "expected X"}})
    with pytest.raises(FmError) as e:
        FmClient(f.session).call("staff_search")
    assert (e.value.op, e.value.code, e.value.detail) == ("staff_search", "wrong-screen", "expected X")


def test_unavailable_without_session_file(tmp_path):
    with pytest.raises(FmUnavailable):
        FmClient(tmp_path / "missing.json").call("hello")


def test_unavailable_when_nothing_listening(tmp_path):
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    p = tmp_path / "session.json"
    p.write_text(json.dumps({"port": port, "token": "t0k", "pid": os.getpid()}))
    with pytest.raises(FmUnavailable):
        FmClient(p).call("hello")


def test_unavailable_when_pid_dead(fake):
    f = fake(lambda req: {"ok": True, "result": 1})
    data = json.loads(f.session.read_text())
    data["pid"] = 999999
    f.session.write_text(json.dumps(data))
    with pytest.raises(FmUnavailable):
        FmClient(f.session).call("hello")


def test_unavailable_when_server_never_answers(fake):
    f = fake(lambda req: None)
    with pytest.raises(FmUnavailable):
        FmClient(f.session, timeout=0.5).call("hello")


def test_non_ascii_round_trip(fake):
    f = fake(lambda req: {"ok": True, "result": req["args"]["names"]})
    names = ["Rúben Gonçalves", "広瀬 圭"]
    assert FmClient(f.session).call("echo", names=names) == names
