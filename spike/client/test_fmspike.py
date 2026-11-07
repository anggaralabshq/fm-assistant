import json
import threading
import time

import pytest
from websockets.sync.server import serve

from fmspike import FmClient, FmError, FmUnavailable


class FakeServer:
    """Answers every request with reply(req) -> dict (id copied in)."""

    def __init__(self, reply):
        self._reply = reply
        self._server = serve(self._handle, "127.0.0.1", 0)
        port = self._server.socket.getsockname()[1]
        self.url = f"ws://127.0.0.1:{port}"
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def _handle(self, ws):
        for raw in ws:
            req = json.loads(raw)
            ws.send(json.dumps({"id": req["id"], **self._reply(req)}, ensure_ascii=False))

    def close(self):
        self._server.shutdown()


@pytest.fixture
def server_factory():
    servers = []

    def make(reply):
        s = FakeServer(reply)
        servers.append(s)
        return s

    yield make
    for s in servers:
        s.close()


def test_call_returns_result(server_factory):
    s = server_factory(lambda req: {"ok": True, "result": {"pong": 1}})
    assert FmClient(s.url).call("ping") == {"pong": 1}


def test_call_sends_op_and_args(server_factory):
    seen = {}

    def reply(req):
        seen.update(req)
        return {"ok": True, "result": None}

    s = server_factory(reply)
    FmClient(s.url).call("squad", limit=3)
    assert seen["op"] == "squad" and seen["args"] == {"limit": 3}


def test_error_raises_fmerror(server_factory):
    s = server_factory(lambda req: {"ok": False, "error": "unknown-op: nope"})
    with pytest.raises(FmError) as e:
        FmClient(s.url).call("nope")
    assert e.value.code == "unknown-op" and e.value.op == "nope" and e.value.detail == "nope"


def test_unavailable_when_nothing_listening():
    t0 = time.monotonic()
    with pytest.raises(FmUnavailable):
        FmClient("ws://127.0.0.1:7799", timeout=1.0).call("ping")
    assert time.monotonic() - t0 < 3.0


def test_unavailable_when_server_never_answers(server_factory):
    silent = serve(lambda ws: time.sleep(5), "127.0.0.1", 0)
    threading.Thread(target=silent.serve_forever, daemon=True).start()
    url = f"ws://127.0.0.1:{silent.socket.getsockname()[1]}"
    t0 = time.monotonic()
    with pytest.raises(FmUnavailable):
        FmClient(url, timeout=1.0).call("ping")
    assert time.monotonic() - t0 < 3.0
    silent.shutdown()


def test_non_ascii_round_trip(server_factory):
    names = ["Rúben Gonçalves", "広瀬 圭"]
    s = server_factory(lambda req: {"ok": True, "result": names})
    assert FmClient(s.url).call("names") == names
