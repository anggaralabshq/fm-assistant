"""Start, restart and load FM27 without the owner (port of spike/client/game.py).

Never saves. Kill guard fails closed: kills the game only when no career is loaded, or when allow_career is set
AND this module itself loaded the career in the same game process (marker file). A career the owner loaded may
hold unsaved progress that no date check can see, so it is never killed. Plugin unreachable while the game
runs -> refuse.
"""
import json
import subprocess
import time
from pathlib import Path

from .client import FmClient, FmError, FmUnavailable

APP_ID = "4530370"
BUNDLE_ID = "com.SportsInteractive.FootballManager27"
PROC = "shadow/fm.app/Contents/MacOS"
MARKER = Path.home() / ".fm-assistant/agent-loaded.json"  # {"pid": "<game pid>"} written by load_recent


class Refused(Exception):
    """A game-control step was refused to protect the owner's career."""


def pids() -> list[str]:
    return subprocess.run(["pgrep", "-f", PROC], capture_output=True, text=True).stdout.split()


def hello(timeout: float = 10):
    try:
        return FmClient(timeout=timeout).call("hello")
    except (FmUnavailable, FmError):
        return None


def status() -> dict:
    """hello, or {"running": false} when the game is not running. Plugin errors propagate."""
    if not pids():
        return {"running": False}
    return {"running": True, **FmClient(timeout=10).call("hello")}


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
    h = hello()
    if h is None:
        return "game is running but the plugin does not answer: refusing to kill (close the game yourself)"
    if h.get("career_loaded") and not (allow_career and agent_loaded(running)):
        return "career loaded that this tool did not load: refusing to kill (owner may have unsaved progress)"
    return None


def clear_state() -> None:
    # A killed app triggers macOS's "reopen windows?" modal on next launch, which blocks before the loader.
    subprocess.run(["rm", "-rf", str(Path.home() / f"Library/Saved Application State/{BUNDLE_ID}.savedState")])
    subprocess.run(["defaults", "write", BUNDLE_ID, "ApplePersistenceIgnoreState", "-bool", "YES"])


def kill(allow_career: bool) -> None:
    reason = kill_refusal(allow_career)
    if reason:
        raise Refused(reason)
    for pid in pids():
        subprocess.run(["kill", "-9", pid])
    time.sleep(2)
    MARKER.unlink(missing_ok=True)
    clear_state()


def launch(timeout: float = 180, attempts: int = 3) -> dict:
    """Start the game through Steam and wait for the plugin with bindings captured."""
    # ponytail: retry covers an intermittent startup crash (CoreCLR stack walk in libunwind, ~1 in 5 launches).
    h = hello()
    if h and h.get("bindings_captured"):
        return h
    for attempt in range(1, attempts + 1):
        if not pids():
            time.sleep(10)  # let Steam notice the old process is gone
            subprocess.run(["open", f"steam://rungameid/{APP_ID}"])
        end, seen = time.time() + timeout, False
        while time.time() < end:
            time.sleep(5)
            h = hello()
            if h and h.get("bindings_captured"):
                return h
            alive = bool(pids())
            seen |= alive
            if seen and not alive:
                clear_state()  # exited during startup; nothing to kill
                break
    raise FmUnavailable("plugin did not come up after launch")


def load_recent(timeout: float = 180) -> dict:
    """Load the main menu's most recent save; the tile ignores early clicks, so retry every 15 s."""
    c = FmClient(timeout=20)
    end, last_click = time.time() + timeout, 0.0
    while time.time() < end:
        h = c.call("hello")
        panels = [p["panel_id"] for p in c.call("panels")]
        if h["career_loaded"] and not last_click:
            return h  # already loaded by someone else: no marker, so it stays protected from kill
        if h["career_loaded"] and "PortalScreen" in panels:
            MARKER.parent.mkdir(exist_ok=True)
            MARKER.write_text(json.dumps({"pid": (pids() or [None])[0]}))
            return h
        if "MainMenu" in panels and "LoadGameLoadingScreen" not in panels and time.time() - last_click > 15:
            try:
                c.call("load_recent_save")
                last_click = time.time()
            except FmError:
                pass  # tile not visible yet
        time.sleep(3)
    raise FmUnavailable("career did not load in time")


def restart(load: bool, allow_career: bool) -> dict:
    kill(allow_career)
    h = launch()
    return load_recent() if load else h
