# spike/ — Phase 0 feasibility spike (throwaway)

Throwaway code proving FM27 can be read and driven from a BepInEx plugin on macOS arm64.
Not production code; Phase 1 starts a fresh tree. Results live in `FINDINGS.md`.

- `plugin/` — C# BepInEx 6 IL2CPP plugin, WebSocket JSON server on `127.0.0.1:7788`. Build: `bash spike/build.sh`.
- `client/` — Python client + live check scripts. Tests: `cd spike/client && uv run pytest`.

Loader: sptndc FM27 BepInEx (see FINDINGS.md "Loader review"), launched via Steam launch option.
