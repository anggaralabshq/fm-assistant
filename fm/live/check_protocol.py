"""Live check (Task 2): protocol v1 server rules against the running game with a loaded career.

Usage: uv run --project fm python fm/live/check_protocol.py
"""
import json
import sys

from websockets.exceptions import ConnectionClosed, InvalidStatus
from websockets.sync.client import connect

from fm_assistant.client import FmClient, FmError

HELLO_KEYS = {"plugin", "plugin_version", "protocol", "game_build", "build_supported", "tested_builds",
              "bindings_captured", "career_loaded", "human_club_uid"}

c = FmClient()
errors = []


def expect_code(code, op, **args):
    try:
        c.call(op, **args)
        errors.append(f"{op}: expected {code}, got ok")
    except FmError as e:
        if e.code != code:
            errors.append(f"{op}: expected {code}, got {e.code}: {e.detail}")


def raw(payload: dict | str, **kw):
    s = c.session()
    with connect(f"ws://127.0.0.1:{s['port']}", max_size=None, **kw) as ws:
        ws.send(payload if isinstance(payload, str) else json.dumps(payload))
        return json.loads(ws.recv(timeout=10))


def root_fm_nodes() -> list[str]:
    return sorted(n["name"] for n in c.call("tree", depth=1, max=5000).get("children", [])
                  if isinstance(n, dict) and n["name"].startswith("__fm"))


hello = c.call("hello")
if missing := HELLO_KEYS - hello.keys():
    errors.append(f"hello missing {missing}")
if hello.get("protocol") != 1:
    errors.append(f"hello protocol {hello.get('protocol')}")
if not hello.get("career_loaded"):
    sys.exit("load a career first (fm game restart --load)")

expect_code("unknown-op", "ui_click", name="x")
expect_code("unknown-op", "no_such_op")

before = root_fm_nodes()
club = {"ref": "path", "path": "Human.Club", "props": ["Name", "TransferBudget"]}
for _ in range(20):
    r = c.call("read", **club)
    if "_missing" in r:
        errors.append(f"read missing {r['_missing']}")
        break
after = root_fm_nodes()
if before != after:
    errors.append(f"binding nodes leaked: before {before[:5]} after {after[:5]} ({len(after)})")

r = raw({"v": 1, "id": "x", "op": "hello", "args": {}})
if r.get("error", {}).get("code") != "unauthorized":
    errors.append(f"no token: {r}")
r = raw({"v": 1, "id": 7, "op": "hello", "args": {}, "token": c.session()["token"]})
if r.get("error", {}).get("code") != "bad-request":
    errors.append(f"non-string id: {r}")

try:
    raw({"v": 1, "id": "o", "op": "hello"}, additional_headers={"Origin": "http://evil.example"})
    errors.append("Origin header accepted")
except InvalidStatus as e:
    if e.response.status_code != 403:
        errors.append(f"Origin: status {e.response.status_code}")

try:
    raw("x" * 300_000)
    errors.append("300 KB message answered")
except ConnectionClosed as e:
    if e.rcvd is None or e.rcvd.code != 1009:
        errors.append(f"300 KB message: close {e.rcvd}")

if errors:
    print("FAIL:\n  " + "\n  ".join(errors))
    sys.exit(1)
print(f"OK: hello {hello['game_build']} supported={hello['build_supported']}; 20 reads, no leaked nodes; "
      "unauthorized/bad-request/unknown-op/Origin 403/1009 enforced")
