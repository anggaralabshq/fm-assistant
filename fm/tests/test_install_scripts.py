"""scripts/install.sh and scripts/uninstall.sh against fake folders (never the real game, Steam or ~/.claude)."""
import os
import platform
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]


def sh(script, tmp, *args, **env):
    e = {"PATH": os.environ["PATH"], "HOME": str(tmp / "home"), "FM27_GAME": str(tmp / "game"),
         "CLAUDE_DIR": str(tmp / "claude"), "UV": "true", "FM_GAME_PROC": "no-such-process-xyz", **env}
    return subprocess.run(["bash", str(ROOT / "scripts" / script), *args], env=e, capture_output=True, text=True)


@pytest.mark.skipif(platform.machine() != "arm64" or platform.system() != "Darwin", reason="install.sh checks Apple Silicon first")
def test_install_fails_closed_without_game_or_loader(tmp_path):
    r = sh("install.sh", tmp_path)
    assert r.returncode == 1 and "FM27 not found" in r.stderr
    (tmp_path / "game" / "fm.app").mkdir(parents=True)
    r = sh("install.sh", tmp_path)
    assert r.returncode == 1 and "loader missing" in r.stderr
    assert not (tmp_path / "claude").exists()          # nothing installed on a failed preflight


def test_uninstall_removes_only_ours_and_keeps_backups(tmp_path):
    plug = tmp_path / "game/FM27-BepInEx/BepInEx/plugins"
    (plug / "FmAssistant").mkdir(parents=True)
    (plug / "Other").mkdir()
    cmds = tmp_path / "claude/commands"
    (tmp_path / "claude/skills/fm-manager/commands").mkdir(parents=True)
    (tmp_path / "claude/skills/fm-manager/commands/fm-inbox.md").write_text("x")
    cmds.mkdir()
    (cmds / "fm-inbox.md").write_text("x")
    (cmds / "mine.md").write_text("x")
    data = tmp_path / "home/.fm-assistant"
    (data / "backups/20261110-1").mkdir(parents=True)
    (data / "plans").mkdir()

    assert sh("uninstall.sh", tmp_path, FM_GAME_PROC=".").returncode == 1      # "." matches any process: game running, refuses
    assert (plug / "FmAssistant").exists()

    r = sh("uninstall.sh", tmp_path, "--purge")
    assert r.returncode == 0, r.stderr
    assert not (plug / "FmAssistant").exists() and (plug / "Other").exists()
    assert not (tmp_path / "claude/skills/fm-manager").exists()
    assert sorted(p.name for p in cmds.iterdir()) == ["mine.md"]
    assert sorted(p.name for p in data.iterdir()) == ["backups"]
    assert "backups" in r.stdout


def test_empty_home_refused(tmp_path):
    for s in ("install.sh", "uninstall.sh"):
        r = sh(s, tmp_path, HOME="", FM27_GAME="", CLAUDE_DIR="")
        assert r.returncode != 0 and "HOME" in r.stderr, (s, r.stderr)
