import json
import os
import threading

import pytest
from websockets.sync.server import serve


class FakePlugin:
    """Threaded websocket server; `handler(request) -> response dict | None` (None = never answer)."""

    def __init__(self, tmp_path, handler):
        self.requests = []
        self.handler = handler
        self.server = serve(self._on_conn, "127.0.0.1", 0)
        self.port = self.server.socket.getsockname()[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.session = tmp_path / "session.json"
        self.session.write_text(json.dumps({"port": self.port, "token": "t0k", "pid": os.getpid(),
                                            "plugin_version": "0.1.0", "game_build": "27.0.0.2493426"}))

    def _on_conn(self, ws):
        for raw in ws:
            req = json.loads(raw)
            self.requests.append(req)
            resp = self.handler(req)
            if resp is not None:
                ws.send(json.dumps({"v": 1, "id": req["id"], **resp}, ensure_ascii=False))


@pytest.fixture
def fake(tmp_path):
    made = []

    def make(handler):
        f = FakePlugin(tmp_path, handler)
        made.append(f)
        return f

    yield make
    for f in made:
        f.server.shutdown()
