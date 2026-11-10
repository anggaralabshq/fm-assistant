"""Throwaway client for the FM27 spike plugin (JSON over WebSocket)."""
import json
import uuid

from websockets.exceptions import WebSocketException
from websockets.sync.client import connect

DEFAULT_URL = "ws://127.0.0.1:7788"


class FmUnavailable(Exception):
    """Plugin not reachable or did not answer in time."""


class FmError(Exception):
    """Plugin answered ok:false. error is '<code>: <detail>'."""

    def __init__(self, op: str, error: str):
        self.op = op
        self.code, _, self.detail = error.partition(": ")
        super().__init__(f"{op}: {error}")


class FmClient:
    def __init__(self, url: str = DEFAULT_URL, timeout: float = 5.0):
        self.url = url
        self.timeout = timeout

    def call(self, op: str, **args) -> object:
        req_id = uuid.uuid4().hex
        try:
            with connect(self.url, open_timeout=self.timeout, close_timeout=1) as ws:
                ws.send(json.dumps({"id": req_id, "op": op, "args": args}, ensure_ascii=False))
                while True:
                    msg = json.loads(ws.recv(timeout=self.timeout))
                    if msg.get("id") == req_id:
                        break
        except (OSError, TimeoutError, WebSocketException) as e:
            raise FmUnavailable(f"{self.url}: {e!r}") from e
        if not msg.get("ok"):
            raise FmError(op, msg.get("error") or "unknown-error: no message")
        return msg.get("result")
