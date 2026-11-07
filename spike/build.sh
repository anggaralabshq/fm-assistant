#!/bin/bash
# Build the spike plugin against the generated FM27 interop and install it.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
FM27_BEP="${FM27_BEP:-$HOME/Library/Application Support/Steam/steamapps/common/Football Manager 27/FM27-BepInEx/BepInEx}"
export DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_GENERATE_ASPNET_CERTIFICATE=false DOTNET_NOLOGO=1
DOTNET="${DOTNET:-$HOME/.dotnet/dotnet}"
"$DOTNET" build "$HERE/plugin/FmSpike.csproj" -c Release -nologo -v q \
  -p:CoreDir="$FM27_BEP/core" -p:InteropDir="$FM27_BEP/interop"
mkdir -p "$FM27_BEP/plugins/FmSpike"
cp "$HERE/plugin/bin/Release/net6.0/FmSpike.dll" "$FM27_BEP/plugins/FmSpike/"
echo "Installed: $FM27_BEP/plugins/FmSpike/FmSpike.dll"
