import json

import pytest

from fm_assistant import apply, audit, backup, plans
from fm_assistant.client import FmClient, FmError, FmUnavailable
from test_cli import HELLO, run


@pytest.fixture
def save():
    (backup.GAMES_DIR / "career.fm").write_bytes(b"save-bytes")


def mkplan(*acts):
    return plans.create([{"kind": k, "args": a} for k, a in acts], "because", "sum")


class Fake:
    """Answers per call (list) or one answer for all; records the token file seen during each call."""

    def __init__(self, answers):
        self.answers, self.calls, self.token_seen = answers, [], []

    def call(self, op, **args):
        self.calls.append((op, args))
        tok = args["apply_token"]
        f = apply.APPLY_DIR / tok
        self.token_seen.append((tok, json.loads(f.read_text()), f.stat().st_mode & 0o777))
        a = self.answers[len(self.calls) - 1] if isinstance(self.answers, list) else self.answers
        if isinstance(a, Exception):
            raise a
        return a


OK = {"verified": True, "answer": "done"}


def test_apply_aborts_without_backup():
    p = mkplan(("shortlist.add", {"uid": 1}))
    c = Fake(OK)
    r = apply.run(p["id"], c, HELLO)
    assert r["status"] == "proposed" and r["error"]["code"] == "backup-failed" and c.calls == []
    assert plans.load(p["id"])["status"] == "proposed"
    assert audit.tail(5)[-1]["result"] == "backup-failed"


def test_apply_refused_on_untested_build(save):
    p = mkplan(("shortlist.add", {"uid": 1}))
    c = Fake(OK)
    r = apply.run(p["id"], c, {**HELLO, "build_supported": False, "game_build": "27.9"})
    assert r["status"] == "refused" and "actions are disabled on untested build 27.9" in r["error"]["detail"]
    assert c.calls == [] and plans.load(p["id"])["status"] == "refused"
    assert not backup.BACKUP_DIR.exists()     # nothing backed up either
    assert audit.tail(1)[0]["result"] == "refused"


def test_apply_token_one_use(save):
    p = mkplan(("shortlist.add", {"uid": 1}), ("shortlist.remove", {"uid": 2}))
    c = Fake(OK)
    r = apply.run(p["id"], c, HELLO)
    assert r["status"] == "applied"
    (t1, body1, mode1), (t2, body2, _) = c.token_seen
    assert t1 != t2 and body1 == {"plan_id": p["id"], "index": 0, "kind": "shortlist.add"}
    assert body2["index"] == 1 and mode1 == 0o600
    assert (apply.APPLY_DIR.stat().st_mode & 0o777) == 0o700
    assert list(apply.APPLY_DIR.iterdir()) == []
    assert c.calls[0] == ("act_shortlist_add", {"uid": 1, "months": 0, "apply_token": t1})
    assert plans.load(p["id"])["status"] == "applied"
    with pytest.raises(ValueError):
        apply.run(p["id"], c, HELLO)


def test_partial_plan(save):
    p = mkplan(("shortlist.add", {"uid": 1}), ("shortlist.remove", {"uid": 2}), ("shortlist.add", {"uid": 3}))
    c = Fake([OK, FmError("act_shortlist_remove", "precondition", "not on list"), OK])
    r = apply.run(p["id"], c, HELLO)
    assert r["status"] == "partial" and len(c.calls) == 2
    assert [a["status"] for a in r["actions"]] == ["ok", "failed", "skipped"]
    assert r["actions"][1]["error"] == {"code": "precondition", "detail": "not on list"}
    log = audit.tail(10)
    assert [e["status"] for e in log] == ["ok", "failed", "skipped"]
    assert log[0]["backup_sha256"] == r["backup"]["sha256"] and log[0]["plan_id"] == p["id"]
    assert list(apply.APPLY_DIR.iterdir()) == []
    assert plans.load(p["id"])["status"] == "partial"


def test_first_action_failing_is_failed_and_unavailable_stops(save):
    p = mkplan(("shortlist.add", {"uid": 1}), ("shortlist.add", {"uid": 2}))
    r = apply.run(p["id"], Fake(FmUnavailable("gone")), HELLO)
    assert r["status"] == "failed" and r["actions"][0]["error"]["code"] == "unavailable"
    assert r["actions"][1]["status"] == "skipped"


def test_apply_requires_verified_true(save):
    p = mkplan(("shortlist.add", {"uid": 1}), ("shortlist.add", {"uid": 2}))
    c = Fake({"answer": "sent", "verified": False})
    r = apply.run(p["id"], c, HELLO)
    assert r["status"] == "failed" and len(c.calls) == 1
    assert r["actions"][0]["error"]["code"] == "not-verified"
    assert audit.tail(2)[0]["result"] == {"answer": "sent", "verified": False}


def patch_client(monkeypatch, c):
    monkeypatch.setattr(FmClient, "call", lambda self, op, **a: HELLO if op == "hello" else c.call(op, **a))


def test_cli_plan_create_and_apply_text(monkeypatch, save):
    r = run("plan", "create", "shortlist.add", "--arg", "uid=42", "--arg", "months=3", "--reason", "good winger")
    assert r.exit_code == 0, r.output
    pid = r.stdout.split()[0]
    assert plans.load(pid)["actions"][0]["args"] == {"uid": 42, "months": 3}
    shown = run("plan", "show", pid).stdout
    assert "good winger" in shown and "42" in shown
    assert pid in run("plan", "list", "--status", "proposed").stdout
    patch_client(monkeypatch, Fake({"verified": True, "answer": "added"}))
    r = run("apply", pid)
    assert r.exit_code == 0, r.output + r.stderr
    lines = r.stdout.strip().splitlines()
    assert lines[0].startswith("ok ") and lines[0].endswith(": added")
    assert lines[1].startswith("backup: ") and "(sha256 " in lines[1]
    assert run("apply", pid).exit_code != 0       # already applied


def test_cli_plan_create_file_and_bad_input(tmp_path):
    f = tmp_path / "a.json"
    f.write_text(json.dumps([{"kind": "training.set_focus", "args": {"uid": 3, "type_row": -1}}]))
    r = run("--json", "plan", "create", "--file", str(f), "--reason", "r")
    assert json.loads(r.stdout)["result"]["actions"][0]["kind"] == "training.set_focus"
    r = run("plan", "create", "staff.fire", "--arg", "uid=1", "--reason", "r")
    assert r.exit_code == 3 and "unknown kind" in r.stderr


def test_cli_apply_failure_exits_3(monkeypatch, save):
    p = mkplan(("shortlist.add", {"uid": 1}))
    patch_client(monkeypatch, Fake(FmError("act_shortlist_add", "forbidden", "bad token")))
    r = run("apply", p["id"])
    assert r.exit_code == 3 and r.stdout.startswith("FAIL ") and "forbidden" in r.stdout


def test_log_tail():
    for i in range(5):
        audit.write({"n": i})
    assert [e["n"] for e in audit.tail(2)] == [3, 4]
    assert "time" in audit.tail(1)[0]
    r = run("log", "--n", "3")
    assert r.exit_code == 0 and r.stdout.count("\n") == 3
    assert [e["n"] for e in json.loads(run("--json", "log", "--n", "2").stdout)["result"]] == [3, 4]
