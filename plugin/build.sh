#!/bin/bash
# Build host + ops and install them into the loader's plugins dir.
#  - host (FmAssistant.dll): installed only when it changed; a running game needs a restart to pick it up.
#  - ops (FmAssistant.Ops.ops): always installed; a running game picks it up via op dev_reload (no restart).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
FM27_BEP="${FM27_BEP:-$HOME/Library/Application Support/Steam/steamapps/common/Football Manager 27/FM27-BepInEx/BepInEx}"
export DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_GENERATE_ASPNET_CERTIFICATE=false DOTNET_NOLOGO=1
DOTNET="${DOTNET:-$HOME/.dotnet/dotnet}"
PROPS=(-c Release -nologo -v q -p:CoreDir="$FM27_BEP/core" -p:InteropDir="$FM27_BEP/interop")
"$DOTNET" build "$HERE/FmAssistant.csproj" "${PROPS[@]}"
"$DOTNET" build "$HERE/ops/FmAssistant.Ops.csproj" "${PROPS[@]}"
DEST="$FM27_BEP/plugins/FmAssistant"
mkdir -p "$DEST"
# Never overwrite in place: a running game has the host DLL mmapped and crashes on the next JIT. Rename = new inode.
HOST="$HERE/bin/Release/net6.0/FmAssistant.dll"
if ! cmp -s "$HOST" "$DEST/FmAssistant.dll"; then
  cp "$HOST" "$DEST/FmAssistant.dll.new" && mv -f "$DEST/FmAssistant.dll.new" "$DEST/FmAssistant.dll"
  echo "Installed host: $DEST/FmAssistant.dll (restart the game to load it)"
fi
cp "$HERE/ops/bin/Release/net6.0/FmAssistant.Ops.dll" "$DEST/FmAssistant.Ops.ops.new"
mv -f "$DEST/FmAssistant.Ops.ops.new" "$DEST/FmAssistant.Ops.ops"
echo "Installed ops: $DEST/FmAssistant.Ops.ops"
# Hot-swap ops into a running game (no restart). Silent no-op when the game is not running.
if (cd "$HERE/../fm" && uv run --quiet fm call dev_reload >/dev/null 2>&1); then echo "Reloaded ops in the running game"; fi
