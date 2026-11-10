"""Installation and live-game health checks, in dependency order. Stops at the first failing prerequisite."""
from pathlib import Path

from .client import SESSION_PATH, FmClient, FmError, FmUnavailable

GAME_DIR = Path.home() / "Library/Application Support/Steam/steamapps/common/Football Manager 27"
SHADOW_APP = GAME_DIR / "FM27-BepInEx/shadow/fm.app"
LOADER_LOG = GAME_DIR / "FM27-BepInEx/BepInEx/LogOutput.log"
SESSION = SESSION_PATH

# (check name, op, args): one read per feature, appended as features land.
FEATURES: list[tuple[str, str, dict]] = [
    ("club read", "club", {}),
    ("squad read", "squad", {"team": "first"}),
    ("staff search read", "staff_search", {"max": 20}),
    ("player search read", "player_search", {"max": 20}),
    ("training read", "training", {}),
]


def run() -> list[dict]:
    out = []

    def add(check, ok, detail=""):
        out.append({"check": check, "ok": ok, "detail": detail})
        return ok

    if not add("shadow app present", SHADOW_APP.is_dir(), str(SHADOW_APP)):
        return out
    log = LOADER_LOG.read_text(errors="replace") if LOADER_LOG.exists() else ""
    if not add("loader started", "Chainloader startup complete" in log, str(LOADER_LOG)):
        return out
    if not add("session file present", SESSION.exists(), str(SESSION)):
        return out
    c = FmClient(timeout=15)
    try:
        h = c.call("hello")
    except (FmUnavailable, FmError) as e:
        add("plugin answers", False, str(e))
        return out
    add("plugin answers", True, f"plugin {h['plugin_version']}, protocol {h['protocol']}")
    add("game build supported", h["build_supported"],
        f"{h['game_build']} (tested: {', '.join(h['tested_builds'])})")
    if not add("career loaded", h["career_loaded"], f"club uid {h['human_club_uid']}"):
        return out
    slow = FmClient(timeout=95)   # feature reads may navigate the UI first
    for name, op, args in FEATURES:
        try:
            slow.call(op, **args)
            add(name, True)
        except FmError as e:
            add(name, False, f"{e.code}: {e.detail}")
    return out
