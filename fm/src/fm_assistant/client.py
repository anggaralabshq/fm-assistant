"""Protocol v1 client for the FM Assistant plugin (JSON over an authenticated localhost WebSocket).

See docs/protocol.md. The plugin writes ~/.fm-assistant/session.json at startup; it is re-read on every
call because a game restart changes the port token.
"""
import json
import os
import uuid
from pathlib import Path
from typing import Any

from websockets.exceptions import InvalidStatus, WebSocketException
from websockets.sync.client import connect

SESSION_PATH = Path.home() / ".fm-assistant" / "session.json"

# Server-side op timeouts (plugin OpsEntry/OpRegistry). The client waits OP_TIMEOUT + 5 s so a slow read is
# reported by the plugin (or as "timeout"), never as "game not running".
OP_TIMEOUTS = {"hello": 10, "diag": 5, "dev_reload": 30, "panels": 10, "ui_dump": 10, "prop_check": 10, "tree": 10,
               "read": 60, "list_rows": 15, "load_recent_save": 10, "nav_open": 30, "club": 30, "squad": 90,
               "staff_search": 90, "player_search": 90, "training": 60}


class FmUnavailable(Exception):
    """Plugin not reachable: no session file, dead game process, connection refused."""


class FmError(Exception):
    """Plugin answered ok:false."""

    def __init__(self, op: str, code: str, detail: str = ""):
        self.op, self.code, self.detail = op, code, detail
        super().__init__(f"{op}: {code}: {detail}")


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class FmClient:
    def __init__(self, session_path: Path | None = None, timeout: float = 30.0):
        self.session_path = Path(session_path) if session_path else SESSION_PATH
        self.timeout = timeout

    def session(self) -> dict:
        try:
            s = json.loads(self.session_path.read_text())
        except (OSError, ValueError) as e:
            raise FmUnavailable(f"no session file at {self.session_path}") from e
        if not isinstance(s.get("pid"), int) or not _alive(s["pid"]):
            raise FmUnavailable(f"game process {s.get('pid')} from {self.session_path} is not running")
        return s

    def call(self, op: str, **args) -> Any:
        s = self.session()
        req_id = uuid.uuid4().hex
        req = {"v": 1, "id": req_id, "op": op, "args": args, "token": s["token"]}
        wait = max(self.timeout, OP_TIMEOUTS.get(op, 0) + 5)
        try:
            ws = connect(f"ws://127.0.0.1:{s['port']}", open_timeout=self.timeout, close_timeout=1, max_size=None)
        except InvalidStatus as e:
            if e.response.status_code == 503:
                raise FmError(op, "busy", "plugin connection limit reached") from e
            raise FmUnavailable(f"port {s['port']}: {e!r}") from e
        except (OSError, TimeoutError, WebSocketException) as e:
            raise FmUnavailable(f"port {s['port']}: {e!r}") from e
        try:
            with ws:
                ws.send(json.dumps(req, ensure_ascii=False))
                while True:
                    msg = json.loads(ws.recv(timeout=wait))
                    if isinstance(msg, dict) and msg.get("id") == req_id:
                        break
        except TimeoutError as e:
            raise FmError(op, "timeout", f"no answer in {wait:g}s") from e
        except (OSError, WebSocketException) as e:
            raise FmUnavailable(f"port {s['port']}: {e!r}") from e
        if msg.get("ok"):
            return msg.get("result")
        err = msg.get("error") or {}
        raise FmError(op, err.get("code", "internal"), err.get("detail", ""))
