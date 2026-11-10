"""Copy the newest save before an apply: <BACKUP_DIR>/<YYYYmmdd-HHMMSS>/<save>.fm + SHA256SUMS."""
import hashlib
import os
import shutil
from datetime import datetime
from pathlib import Path

BACKUP_DIR = Path(os.environ.get("FM_ASSISTANT_BACKUP_DIR") or Path.home() / ".fm-assistant" / "backups")
GAMES_DIR = Path(os.environ.get("FM_ASSISTANT_GAMES_DIR")
                 or Path.home() / "Library/Application Support/Sports Interactive/Football Manager 27/games")


class BackupError(Exception):
    pass


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def make(games_dir=None, root=None) -> dict:
    games = Path(games_dir or GAMES_DIR)
    saves = [f for f in games.glob("*.fm") if f.is_file()] if games.is_dir() else []
    if not saves:
        raise BackupError(f"no .fm save found in {games}")
    src = max(saves, key=lambda f: f.stat().st_mtime)
    dest = Path(root or BACKUP_DIR) / f"{datetime.now():%Y%m%d-%H%M%S}"
    try:
        dest.mkdir(parents=True)
        want = _sha(src)
        shutil.copy2(src, dest / src.name)
        if _sha(dest / src.name) != want:
            raise BackupError("copy does not match the source hash")
        (dest / "SHA256SUMS").write_text(f"{want}  {src.name}\n")
    except OSError as e:
        raise BackupError(f"backup failed: {e}") from e
    return {"path": str(dest), "sha256": want, "source": str(src)}
