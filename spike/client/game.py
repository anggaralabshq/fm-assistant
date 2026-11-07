"""Spike helper: restart FM27 (to reload the plugin DLL) and optionally load the most recent save.

    uv run python game.py restart [--load] [--allow-career]

Never saves. Refuses to kill a running career unless --allow-career: the caller must first confirm
the in-game date equals the save's date (nothing unsaved), because a kill drops unsaved progress.
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

from fmspike import FmClient, FmError, FmUnavailable

BUNDLE_ID = "com.SportsInteractive.FootballManager27"
PROC = "shadow/fm.app/Contents/MacOS"


def pids() -> list[str]:
    return subprocess.run(["pgrep", "-f", PROC], capture_output=True, text=True).stdout.split()


def ping():
    try:
        return FmClient(timeout=3).call("ping")
    except (FmUnavailable, FmError):
        return None


def kill(allow_career: bool) -> None:
    p = ping()
    if p and p.get("career_loaded") and not allow_career:
        sys.exit("career loaded: refusing to kill (pass --allow-career after checking nothing is unsaved)")
    for pid in pids():
        subprocess.run(["kill", "-9", pid])
    time.sleep(2)
    # A killed app triggers macOS's "reopen windows?" modal on next launch, which blocks before the loader.
    subprocess.run(["rm", "-rf", str(Path.home() / f"Library/Saved Application State/{BUNDLE_ID}.savedState")])
    subprocess.run(["defaults", "write", BUNDLE_ID, "ApplePersistenceIgnoreState", "-bool", "YES"])


def launch(timeout: float = 180) -> dict:
    time.sleep(10)  # let Steam notice the old process is gone
    subprocess.run(["open", "steam://rungameid/4530370"])
    end = time.time() + timeout
    while time.time() < end:
        time.sleep(5)
        p = ping()
        if p and p.get("bindings_captured"):
            return p
    sys.exit("plugin did not come up")


def load_recent(timeout: float = 180) -> dict:
    c = FmClient(timeout=20)
    end = time.time() + timeout
    while time.time() < end:  # main menu appears a few seconds after bindings
        if any(p["panel_id"] == "MainMenu" for p in c.call("panels")):
            break
        time.sleep(3)
    c.call("ui_click", name="LoadMostRecentSave", panel="MainMenu")
    while time.time() < end:
        time.sleep(5)
        p = c.call("ping")
        if p["career_loaded"] and any(x["panel_id"] == "PortalScreen" for x in c.call("panels")):
            return p
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
