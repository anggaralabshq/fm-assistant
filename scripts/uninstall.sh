#!/bin/bash
# Removes what install.sh added: the plugin, the fm CLI, the skill and its slash commands.
# Keeps ~/.fm-assistant/backups (your save backups) always; --purge removes the rest of ~/.fm-assistant
# (plans, audit log, snapshots, settings). The BepInEx loader and the Steam launch option belong to the loader:
# remove those yourself if you no longer want them.
set -euo pipefail
GAME="${FM27_GAME:-$HOME/Library/Application Support/Steam/steamapps/common/Football Manager 27}"
CLAUDE_DIR="${CLAUDE_DIR:-$HOME/.claude}"
UV="${UV:-uv}"
PROC="${FM_GAME_PROC:-FM27-BepInEx/shadow/fm.app/Contents/MacOS}"
PURGE=0
for a in "$@"; do case "$a" in --purge) PURGE=1 ;; *) echo "usage: uninstall.sh [--purge]" >&2; exit 2 ;; esac; done
die() { echo "uninstall: $*" >&2; exit 1; }

pgrep -f "$PROC" >/dev/null && die "quit FM27 first (the plugin is loaded in the running game)"
rm -rf "$GAME/FM27-BepInEx/BepInEx/plugins/FmAssistant"
"$UV" tool uninstall fm-assistant >/dev/null 2>&1 || true
if [ -d "$CLAUDE_DIR/skills/fm-manager" ]; then
  for f in "$CLAUDE_DIR/skills/fm-manager/commands/"*.md; do [ -e "$f" ] && rm -f "$CLAUDE_DIR/commands/$(basename "$f")"; done
  rm -rf "$CLAUDE_DIR/skills/fm-manager"
fi
DATA="$HOME/.fm-assistant"
if [ "$PURGE" = 1 ] && [ -d "$DATA" ]; then
  find "$DATA" -mindepth 1 -maxdepth 1 ! -name backups -exec rm -rf {} +
fi
echo "Removed plugin, fm CLI and skill."
[ -d "$DATA/backups" ] && echo "Kept save backups: $DATA/backups"
echo "Loader and Steam launch option untouched: clear the launch option in Steam and delete FM27-BepInEx if unwanted."
