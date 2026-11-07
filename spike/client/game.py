"""Spike helper: restart FM27 (to reload the plugin DLL) and optionally load the most recent save.

    uv run python game.py restart [--load] [--allow-career]

Never saves. Fails closed: kills the game only when no career is loaded, or when --allow-career is given
AND this helper itself loaded the career in the same game process (marker file). A career the owner loaded
may hold unsaved progress that no date check can see, so it is never killed. Plugin unreachable while the
game runs -> refuse.
"""
import argparse
import subprocess
import sys
import time
import json
from pathlib import Path

from fmspike import FmClient, FmError, FmUnavailable

BUNDLE_ID = "com.SportsInteractive.FootballManager27"
PROC = "shadow/fm.app/Contents/MacOS"
MARKER = Path.home() / ".fm-assistant/agent-loaded.json"  # {"pid": "<game pid>"} written by load_recent


def pids() -> list[str]:
    return subprocess.run(["pgrep", "-f", PROC], capture_output=True, text=True).stdout.split()


def ping(timeout: float = 10):
    try:
        return FmClient(timeout=timeout).call("ping")
    except (FmUnavailable, FmError):
        return None


def agent_loaded(running: list[str]) -> bool:
    try:
        return json.loads(MARKER.read_text()).get("pid") in running
    except (OSError, ValueError):
        return False


def kill_refusal(allow_career: bool):
    """Reason not to kill, or None when killing is safe."""
    running = pids()
    if not running:
        return None
    p = ping()
    if p is None:
        return "game is running but the plugin does not answer: refusing to kill (close the game yourself)"
    if p.get("career_loaded") and not (allow_career and agent_loaded(running)):
        return "career loaded that this helper did not load: refusing to kill (owner may have unsaved progress)"
    return None


def clear_state() -> None:
    # A killed app triggers macOS's "reopen windows?" modal on next launch, which blocks before the loader.
    subprocess.run(["rm", "-rf", str(Path.home() / f"Library/Saved Application State/{BUNDLE_ID}.savedState")])
    subprocess.run(["defaults", "write", BUNDLE_ID, "ApplePersistenceIgnoreState", "-bool", "YES"])


def kill(allow_career: bool) -> None:
    reason = kill_refusal(allow_career)
    if reason:
        sys.exit(reason)
    for pid in pids():
        subprocess.run(["kill", "-9", pid])
    time.sleep(2)
    MARKER.unlink(missing_ok=True)
    clear_state()


def launch(timeout: float = 180, attempts: int = 3) -> dict:
    # ponytail: retry covers an intermittent startup crash (CoreCLR stack walk in libunwind, ~1 in 5 launches);
    # root cause is a Phase 1 item, see FINDINGS.md.
    for attempt in range(1, attempts + 1):
        time.sleep(10)  # let Steam notice the old process is gone
        subprocess.run(["open", "steam://rungameid/4530370"])
        end, seen = time.time() + timeout, False
        while time.time() < end:
            time.sleep(5)
            p = ping()
            if p and p.get("bindings_captured"):
                return p
            alive = bool(pids())
            seen |= alive
            if seen and not alive:
                print(f"launch {attempt}: game exited during startup, retrying")
                clear_state()  # process already exited; nothing to kill
                break
    sys.exit("plugin did not come up")


def load_recent(timeout: float = 180) -> dict:
    """Click the main menu's most-recent-save tile until the career is loaded (the tile ignores early clicks)."""
    c = FmClient(timeout=20)
    end, last_click = time.time() + timeout, 0.0
    while time.time() < end:
        panels = [p["panel_id"] for p in c.call("panels")]
        p = c.call("ping")
        if p["career_loaded"] and "PortalScreen" in panels:
            MARKER.parent.mkdir(exist_ok=True)
            MARKER.write_text(json.dumps({"pid": pids()[0] if pids() else None}))
            return p
        if "MainMenu" in panels and "LoadGameLoadingScreen" not in panels and time.time() - last_click > 15:
            try:
                c.call("ui_click", name="LoadMostRecentSave", panel="MainMenu")
                last_click = time.time()
            except FmError:
                pass  # tile not visible yet
        time.sleep(3)
    sys.exit("career did not load")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["restart"])
    ap.add_argument("--load", action="store_true")
    ap.add_argument("--allow-career", action="store_true")
    a = ap.parse_args()
    kill(a.allow_career)
    print("up:", launch())
    if a.load:
        print("loaded:", load_recent())


if __name__ == "__main__":
    main()
