import hashlib
import os

import pytest

from fm_assistant import backup


def test_backup_copies_newest_and_hashes(tmp_path):
    games, root = tmp_path / "g", tmp_path / "b"
    games.mkdir()
    (games / "old.fm").write_bytes(b"old")
    (games / "new.fm").write_bytes(b"newer")
    os.utime(games / "old.fm", (1, 1))
    r = backup.make(games, root)
    assert r["sha256"] == hashlib.sha256(b"newer").hexdigest()
    assert r["source"].endswith("new.fm")
    copy = next(root.glob("*/new.fm"))
    assert copy.read_bytes() == b"newer" and str(copy.parent) == r["path"]
    assert (copy.parent / "SHA256SUMS").read_text() == f"{r['sha256']}  new.fm\n"
    assert not list(root.glob("*/old.fm"))


def test_backup_fails_without_save(tmp_path):
    (tmp_path / "g").mkdir()
    with pytest.raises(backup.BackupError):
        backup.make(tmp_path / "g", tmp_path / "b")
    with pytest.raises(backup.BackupError):
        backup.make(tmp_path / "missing", tmp_path / "b")
