#!/bin/bash
# Build the FM Assistant plugin against the generated FM27 interop and install it into the loader's plugins dir.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
FM27_BEP="${FM27_BEP:-$HOME/Library/Application Support/Steam/steamapps/common/Football Manager 27/FM27-BepInEx/BepInEx}"
export DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_GENERATE_ASPNET_CERTIFICATE=false DOTNET_NOLOGO=1
DOTNET="${DOTNET:-$HOME/.dotnet/dotnet}"
"$DOTNET" build "$HERE/FmAssistant.csproj" -c Release -nologo -v q \
  -p:CoreDir="$FM27_BEP/core" -p:InteropDir="$FM27_BEP/interop"
DEST="$FM27_BEP/plugins/FmAssistant"
mkdir -p "$DEST"
# Never overwrite in place: a running game has the DLL mmapped and crashes on the next JIT. Rename = new inode.
cp "$HERE/bin/Release/net6.0/FmAssistant.dll" "$DEST/FmAssistant.dll.new"
mv -f "$DEST/FmAssistant.dll.new" "$DEST/FmAssistant.dll"
echo "Installed: $DEST/FmAssistant.dll"
