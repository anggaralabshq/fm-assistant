#!/bin/bash
# One-command install: the plugin into the FM27 BepInEx loader, the fm CLI (uv tool), and the Claude Code skill.
# Re-run after `git pull` to update. Never touches the original fm.app, Steam's settings or your saves.
#   --no-skill  skip copying the skill and slash commands into ~/.claude
#   --mcp       also install the MCP server (fm-mcp)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GAME="${FM27_GAME:-$HOME/Library/Application Support/Steam/steamapps/common/Football Manager 27}"
LOADER="$GAME/FM27-BepInEx"
CLAUDE_DIR="${CLAUDE_DIR:-$HOME/.claude}"
UV="${UV:-uv}"
SKILL=1 EXTRA=""
for a in "$@"; do
  case "$a" in --no-skill) SKILL=0 ;; --mcp) EXTRA="[mcp]" ;; *) echo "usage: install.sh [--no-skill] [--mcp]" >&2; exit 2 ;; esac
done
die() { echo "install: $*" >&2; exit 1; }
LAUNCH="\"$LOADER/run_fm27_bepinex.sh\" %command%"

[ "$(uname -sm)" = "Darwin arm64" ] || die "needs macOS on Apple Silicon"
[ -d "$GAME/fm.app" ] || die "FM27 not found at $GAME (set FM27_GAME to the folder that holds fm.app)"
[ -x "$LOADER/run_fm27_bepinex.sh" ] || die "BepInEx loader missing: put the FM27-BepInEx folder next to fm.app and follow its README, then run this again"
[ -d "$LOADER/BepInEx/interop" ] || die "start FM27 once through the loader (Steam launch option: $LAUNCH) so it generates its files, quit, then run this again"
command -v "$UV" >/dev/null || die "uv not found: https://docs.astral.sh/uv/"
DOTNET="${DOTNET:-$(command -v dotnet || echo "$HOME/.dotnet/dotnet")}"
[ -x "$DOTNET" ] || die ".NET 6 SDK not found: https://dotnet.microsoft.com/download (or set DOTNET)"

echo "1/3 plugin"
FM27_BEP="$LOADER/BepInEx" DOTNET="$DOTNET" bash "$ROOT/plugin/build.sh"
echo "2/3 fm CLI"
"$UV" tool install --force --quiet "$ROOT/fm$EXTRA"
if [ "$SKILL" = 1 ]; then
  echo "3/3 Claude Code skill"
  mkdir -p "$CLAUDE_DIR/skills" "$CLAUDE_DIR/commands"
  rm -rf "$CLAUDE_DIR/skills/fm-manager"
  cp -R "$ROOT/skills/fm-manager" "$CLAUDE_DIR/skills/fm-manager"
  cp "$ROOT/skills/fm-manager/commands/"*.md "$CLAUDE_DIR/commands/"
  echo "    merge $CLAUDE_DIR/skills/fm-manager/settings.example.json into $CLAUDE_DIR/settings.json"
  echo "    (it allows the read commands and asks before every fm apply)"
else
  echo "3/3 skill skipped"
fi
# ponytail: Steam's launch options are only checked, never written (Steam rewrites localconfig.vdf while it runs)
if grep -qs run_fm27_bepinex "$HOME/Library/Application Support/Steam/userdata/"*/config/localconfig.vdf; then
  echo "Steam launch option: set"
else
  echo "Steam launch option missing: Steam -> FM27 -> Properties -> Launch Options:"
  echo "    $LAUNCH"
fi
echo "Done. Start FM27 from Steam, load your career, then run: fm doctor"
