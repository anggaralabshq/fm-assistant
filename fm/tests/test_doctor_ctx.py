from fm_assistant import doctor

from test_cli import HELLO, fake_calls, install, run  # noqa: F401  (install is a fixture)


def test_doctor_reports_context_mismatch(monkeypatch, install):
    monkeypatch.setattr(doctor, "FEATURES", [("binding contexts", "ctx_check", {})])
    bad = {"checked": 30, "mismatches": [{"prop": "Morale", "expected": ["team", "human"], "game": ["team"]}]}
    fake_calls(monkeypatch, {"hello": HELLO, "ctx_check": bad})
    r = run("doctor")
    assert r.exit_code == 1
    line = next(l for l in r.stdout.splitlines() if "binding contexts" in l)
    assert line.startswith("FAIL") and "Morale" in line


def test_doctor_context_ok(monkeypatch, install):
    monkeypatch.setattr(doctor, "FEATURES", [("binding contexts", "ctx_check", {})])
    fake_calls(monkeypatch, {"hello": HELLO, "ctx_check": {"checked": 30, "mismatches": []}})
    r = run("doctor")
    assert r.exit_code == 0 and "ok   binding contexts" in r.stdout


def test_doctor_lists_context_check():
    assert ("binding contexts", "ctx_check", {}) in doctor.FEATURES
