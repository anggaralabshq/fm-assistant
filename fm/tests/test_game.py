import json

from fm_assistant import game


def setup(monkeypatch, tmp_path, running, hello, marker_pid=None):
    monkeypatch.setattr(game, "pids", lambda: running)
    monkeypatch.setattr(game, "hello", lambda timeout=10: hello)
    monkeypatch.setattr(game, "MARKER", tmp_path / "m.json")
    if marker_pid:
        (tmp_path / "m.json").write_text(json.dumps({"pid": marker_pid}))


def test_no_game_is_safe(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path, [], None)
    assert game.kill_refusal(False) is None


def test_unreachable_plugin_refuses(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path, ["42"], None)
    assert "does not answer" in game.kill_refusal(True)


def test_owner_loaded_career_refuses_even_with_flag(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path, ["42"], {"career_loaded": True})
    assert "did not load" in game.kill_refusal(True)


def test_marker_from_old_process_refuses(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path, ["42"], {"career_loaded": True}, marker_pid="7")
    assert game.kill_refusal(True) is not None


def test_agent_loaded_career_with_flag_is_allowed(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path, ["42"], {"career_loaded": True}, marker_pid="42")
    assert game.kill_refusal(True) is None
    assert game.kill_refusal(False) is not None


def test_main_menu_is_safe(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path, ["42"], {"career_loaded": False})
    assert game.kill_refusal(False) is None
