# Phase 0 — Feasibility Spike Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove on the owner's Mac that a BepInEx plugin inside FM27 can (1) load, (2) serve squad data over a localhost WebSocket, (3) read Staff Search results, and (4) change one training session and verify it — or record exactly where it fails.

**Architecture:** A throwaway C# BepInEx 6 IL2CPP plugin (`spike/plugin`) runs inside FM27 via sptndc's FM27 macOS loader, hosts a JSON-over-WebSocket server on `127.0.0.1:7788`, and runs every game call on the main thread through a queue. A small Python client (`spike/client`) calls it and checks results against the save parser. Reads use SI's binding framework; the action drives FM's own UI elements by name (the approach `redznn/fm-dof-mcp` proved for FM26).

**Tech Stack:** C# (net6.0) + BepInEx 6 IL2CPP (sptndc FM27 build) + Il2CppInterop + HarmonyX; .NET 8 SDK arm64; Python ≥ 3.10 via `uv`, `websockets` ≥ 12 (sync API), `pytest`.

**Spec:** `docs/superpowers/specs/2026-11-07-fm-assistant-manager-design.md` (§5 Constraints, §7 Architecture, §9 Fase 0).

**References (read before coding, MIT — keep attribution if code is copied):**
- `github.com/redznn/fm-dof-mcp` → `bridge/FMBridge/src/`: `BridgePlugin.cs` (tick via Harmony prefix on `UIElementsRuntimeUtility.RepaintPanels`), `Voice/MainThreadQueue.cs`, `Voice/VoiceServer.cs` (HttpListener WebSocket), `World/NativeBindings.cs` (span-marshalling workaround), `World/ReadEntity.cs` + `World/SquadReport.cs` (binding reads), `World/Navigator*.cs` (UI clicks by element name/text), `FMBridge.csproj` (reference list).
- `github.com/oeknudsen/fm27-player-export-macos` → `build_plugin.sh` (FM27 loader paths `FM27-BepInEx/BepInEx/{core,interop}`), `README.md` (install + Rosetta).
- `github.com/DadMych/fm26-player-export-macos` → `run_bepinex_arm64.sh` (shadow-app technique, fallback loader).

## Global Constraints

- macOS arm64, SIP stays **enabled**; never run anything that asks to disable it.
- The Steam bundle `.../steamapps/common/Football Manager 27/fm.app` is **never modified**: `codesign --verify --deep --strict` on it must pass before and after the spike.
- Server binds `127.0.0.1` only, port `7788`.
- Plugin never saves the game, presses Continue, or starts/plays a match.
- Before any action test: copy the active save (`games/Nael Anggara - Java United.fm`) to `~/fm-spike-backups/<timestamp>/` and record its SHA-256.
- Third-party binaries (loader zip) are inspected before first run: list contents, `codesign -dv` each dylib, read every shell script.
- Everything under `spike/` is throwaway: no polish, minimal tests. Production code in Phase 1 is a new tree.
- Record the game build (`CFBundleShortVersionString`, currently `27.0.0.2493426`) in every finding.

## Review Focus

1. **FM27 not running / plugin not loaded** → client fails within the timeout with `FmUnavailable`, never hangs. (Task 2 test)
2. **No career loaded (main menu, loading screen)** → plugin answers `ok:false, error:"no-career-loaded"` instead of throwing or returning empty lists. (Task 3 manual check)
3. **Non-ASCII names** (e.g. `Rúben Gonçalves`, Japanese names in squad) → preserved byte-for-byte through C# → JSON → Python. (Task 2 test + Task 3 check)
4. **Action target screen not open / UI element not found** → `ok:false` with the missing element named, and a re-read shows nothing changed. (Task 5 manual check)
5. **Steam update replaces the game build mid-spike** (full release 10 Nov) → loader/plugin either still load or fail visibly in `LogOutput.log`; findings note which build each result came from. (Task 6)

---

### Task 1: Toolchain + loader running in FM27 (criterion 1)

**Files:**
- Create: `spike/FINDINGS.md`
- Create: `spike/README.md` (one paragraph: throwaway, how to build/run)

**Interfaces:**
- Produces: loader dirs `$FM27_BEP/core` and `$FM27_BEP/interop` where `FM27_BEP="$HOME/Library/Application Support/Steam/steamapps/common/Football Manager 27/FM27-BepInEx/BepInEx"`; interop must contain `SI.Bindable.dll`, `SI.Bindable.Reference.Core.dll`, `SI.Core.dll`, `FM.UI.dll`, `FM.GamePlugin.dll`, `UnityEngine.UIElementsModule.dll`.

- [ ] **Step 1: Baseline signature check of the original app**

Run: `codesign --verify --deep --strict --verbose=2 "$HOME/Library/Application Support/Steam/steamapps/common/Football Manager 27/fm.app"`
Expected: `valid on disk` and `satisfies its Designated Requirement`. Paste output into `FINDINGS.md` under "Baseline".

- [ ] **Step 2: Install .NET 8 SDK (arm64, user-local) and Rosetta**

Run: `curl -sSL https://dot.net/v1/dotnet-install.sh | bash -s -- --channel 8.0 --install-dir "$HOME/.dotnet"` then `softwareupdate --install-rosetta --agree-to-license`
Expected: `"$HOME/.dotnet/dotnet" --version` prints `8.0.x`.

- [ ] **Step 3: Owner downloads sptndc's FM27 BepInEx**

The owner downloads the zip from `https://sortitoutsi.net/content/78080/fm27-bepinex-6-il2cpp-for-macos-apple-silicon-latest-macos-no-game-files-modified` (the site blocks automated fetches) into `~/Downloads`. Unzip into a fresh empty dir `~/fm-spike-vendor/sptndc/`.

- [ ] **Step 4: Inspect the loader before running it**

Run: `find ~/fm-spike-vendor/sptndc -type f | head -200`, `codesign -dv` on every `*.dylib`, and read every `*.sh` / `*.py` fully.
Expected: written summary in `FINDINGS.md` → "Loader review": what each script does, whether it touches the original `fm.app`, whether it calls `sudo`, `csrutil`, or network. **Stop and report to the owner** if any script modifies the original bundle, needs sudo, or downloads code.

- [ ] **Step 5: Install loader per its README and set the Steam launch option**

Follow the loader's own README (it installs into `Football Manager 27/FM27-BepInEx/` and uses a launch option of the form `"<script>" %command%` with the real macOS username `labs`).

- [ ] **Step 6: Launch FM27 from Steam to the main menu, then quit**

Expected: `"$FM27_BEP/LogOutput.log"` exists and contains the Chainloader start line; `ls "$FM27_BEP/interop"` lists every DLL named in Interfaces. Record loader version + log excerpt in `FINDINGS.md`.

- [ ] **Step 7: Re-run Step 1**

Expected: identical `valid on disk` result. If not → stop, report, restore via Steam "Verify integrity of game files".

- [ ] **Step 8: Commit**

```bash
git add spike/FINDINGS.md spike/README.md
git commit -m "spike: FM27 BepInEx loader running on macOS arm64"
```

Fallback if Steps 5–6 fail: adapt `DadMych/fm26-player-export-macos/run_bepinex_arm64.sh` for FM27 paths, same inspection rules; record the failure and the fallback attempt in `FINDINGS.md`.

---

### Task 2: Plugin skeleton + WebSocket `ping` + Python client

**Files:**
- Create: `spike/plugin/FmSpike.csproj` (net6.0; references as `fm-dof-mcp/bridge/FMBridge/FMBridge.csproj`, HintPaths via `$(CoreDir)` / `$(InteropDir)`)
- Create: `spike/plugin/src/Plugin.cs`, `spike/plugin/src/MainThreadQueue.cs`, `spike/plugin/src/WsServer.cs`, `spike/plugin/src/Ops.cs`
- Create: `spike/build.sh` (dotnet build with `-p:CoreDir=$FM27_BEP/core -p:InteropDir=$FM27_BEP/interop`, copies DLL to `$FM27_BEP/plugins/FmSpike/`)
- Create: `spike/client/pyproject.toml`, `spike/client/fmspike.py`
- Test: `spike/client/test_fmspike.py`

**Interfaces:**
- Wire protocol (one JSON text frame each way):
  request `{"id": "<str>", "op": "<str>", "args": {...}}`
  response `{"id": "<same>", "ok": true, "result": <any>}` or `{"id": "<same>", "ok": false, "error": "<kebab-case-code>: <detail>"}`
- C#: `internal static class Ops { public static JsonObject Dispatch(string op, JsonObject args); }` — runs on main thread (enqueued by `WsServer`, drained in the RepaintPanels prefix tick). Unknown op → `ok:false, error:"unknown-op: <op>"`.
- C# op `ping` → `{"plugin": "fm-spike", "version": "0.0.1", "game_build": Application.version, "career_loaded": <bool>}`.
- Python: `class FmUnavailable(Exception)`, `class FmError(Exception)` with attrs `op: str`, `code: str`, `detail: str`; `class FmClient: def __init__(self, url: str = "ws://127.0.0.1:7788", timeout: float = 5.0); def call(self, op: str, **args) -> object` using `websockets.sync.client.connect`.

- [ ] **Step 1: Write failing client tests**

```python
# spike/client/test_fmspike.py — fake server via websockets.sync.server.serve in a thread
def test_call_returns_result(fake_server):          # server echoes {"ok":true,"result":{"pong":1}}
    assert FmClient(fake_server.url).call("ping") == {"pong": 1}

def test_error_raises_fmerror(fake_server_error):    # server answers ok:false, error "unknown-op: nope"
    with pytest.raises(FmError) as e:
        FmClient(fake_server_error.url).call("nope")
    assert e.value.code == "unknown-op" and e.value.op == "nope"

def test_unavailable_when_nothing_listening():
    t0 = time.monotonic()
    with pytest.raises(FmUnavailable):
        FmClient("ws://127.0.0.1:7799", timeout=1.0).call("ping")
    assert time.monotonic() - t0 < 3.0

def test_non_ascii_round_trip(fake_server_names):    # server returns ["Rúben Gonçalves", "山田 太郎"]
    assert FmClient(fake_server_names.url).call("names") == ["Rúben Gonçalves", "山田 太郎"]
```

- [ ] **Step 2: Run tests, expect failure**

Run: `cd spike/client && uv run --with websockets --with pytest pytest -v`
Expected: FAIL, `ModuleNotFoundError: fmspike` / names undefined.

- [ ] **Step 3: Implement `fmspike.py`**

`call` sends one request with a `uuid4().hex` id, waits for the matching id, maps connect errors and timeouts to `FmUnavailable`, splits `error` on the first `": "` into `code` / `detail`.

- [ ] **Step 4: Run tests, expect pass**

Run: same as Step 2. Expected: 4 passed.

- [ ] **Step 5: Implement plugin skeleton (`Plugin.cs`, `MainThreadQueue.cs`, `WsServer.cs`, `Ops.cs` with `ping` only)**

Tick: Harmony prefix on `UnityEngine.UIElements.UIElementsRuntimeUtility.RepaintPanels` (as fm-dof-mcp `BridgePlugin.cs`). `WsServer`: `HttpListener` on `http://127.0.0.1:7788/`, accepts WebSocket upgrades on a background thread, enqueues `Ops.Dispatch` onto `MainThreadQueue`, awaits a `TaskCompletionSource`, replies. UTF-8 text frames. `career_loaded`: true when the `Human.Club` binding resolves (fm-dof-mcp `MyClub.DiscoverHumanClubUid` pattern), else false.

- [ ] **Step 6: Build and install**

Run: `bash spike/build.sh`. Expected: `Build succeeded`, DLL present in `$FM27_BEP/plugins/FmSpike/`.

- [ ] **Step 7: Live check in game**

Launch FM27 via Steam, wait for main menu. Run: `cd spike/client && uv run --with websockets python -c "from fmspike import FmClient; print(FmClient().call('ping'))"`
Expected: `{'plugin': 'fm-spike', 'version': '0.0.1', 'game_build': '27.0.0…', 'career_loaded': False}`; after loading the Java United save, `career_loaded: True`. `LogOutput.log` shows the plugin load line and no exceptions.

- [ ] **Step 8: Commit**

```bash
git add spike/plugin spike/build.sh spike/client
git commit -m "spike: in-game WebSocket ping + python client"
```

---

### Task 3: Read squad (criterion 2)

**Files:**
- Create: `spike/plugin/src/ReadSquad.cs`, `spike/plugin/src/DumpProps.cs`
- Modify: `spike/plugin/src/Ops.cs` (register `dump_props`, `squad`)
- Create: `spike/client/check_squad.py`

**Interfaces:**
- Consumes: Task 2 `Ops.Dispatch`, `FmClient.call`.
- Produces: op `dump_props` `{"filter": "<substring>"}` → `["<property identifier name>", …]` from `PropertyIdentifierSet` (discovery aid for every later read).
- Produces: op `squad` → `[{"uid": int, "name": str, "position": str, "attributes": {"<name>": int, …}, "contract_expires": "YYYY-MM-DD", "wage": number}]`, minimum 3 attribute entries per player. When `career_loaded` is false → `ok:false, error:"no-career-loaded: …"`.
- Save parser for cross-check: `cli_anything.fm27.core.saves.save_info(Path) -> dict` from `mattboostkit/cli-anything-fm27` (`summary.squad` = list of `{"name", "shirt_number"}`).

- [ ] **Step 1: Discover property names**

With the career loaded, call `dump_props` with filters `Contract`, `Wage`, `Finishing`, `Passing`, `Pace`, `Position`. Record the exact FM27 names that exist in `FINDINGS.md` → "Property names (build …)". Reading approach: port `fm-dof-mcp` `ReadEntity`/`SquadReport` (fabricate → bind → poll → collect), keeping its `NativeBindings` span workaround; batch ≤ 20 people per bind cycle.

- [ ] **Step 2: Implement `squad` using the names from Step 1**

- [ ] **Step 3: Write `check_squad.py`**

Calls `squad`, loads `save_info()` for the newest save, and asserts: every save-summary squad name appears in the plugin's names; each player has ≥ 3 integer attributes in 1–20; each `contract_expires` parses as a date; output is UTF-8 and non-ASCII names match the save's spelling exactly.

- [ ] **Step 4: Run check live**

Run: `cd spike/client && uv run --with websockets python check_squad.py`
Expected: `OK: <n> players, <n> matched save summary`. Also call `squad` from the main menu and confirm `FmError` with `code == "no-career-loaded"`.

- [ ] **Step 5: Commit**

```bash
git add spike/plugin/src spike/client/check_squad.py spike/FINDINGS.md
git commit -m "spike: read squad over websocket, cross-checked with save"
```

---

### Task 4: Read Staff Search results (criterion 3)

**Files:**
- Create: `spike/plugin/src/ReadVisibleList.cs`
- Modify: `spike/plugin/src/Ops.cs` (register `staff_search_visible`)

**Interfaces:**
- Produces: op `staff_search_visible` → `{"screen": str, "rows": [{"name": str, "role": str, "wage_demand": str|null, "cells": {"<column header>": "<text>"}}]}`. Precondition: the owner has the Staff Search screen open. Wrong screen → `ok:false, error:"wrong-screen: expected staff search, got <screen>"`.

- [ ] **Step 1: Implement by porting `fm-dof-mcp` `Navigator.ListRead.cs`** (reads the visible scrolled table's bound rows; headers become `cells` keys). Record the screen identifier for Staff Search in `FINDINGS.md`.

- [ ] **Step 2: Live check**

Open Staff Search in game (filter: Scout). Run: `uv run --with websockets python -c "from fmspike import FmClient; import json; print(json.dumps(FmClient().call('staff_search_visible'), ensure_ascii=False, indent=1)[:3000])"`
Expected: ≥ 1 page of rows whose names match what is on screen, and a wage/demand column when that column is visible in the view. Then open the Squad screen and expect `FmError` code `wrong-screen`.

- [ ] **Step 3: Commit**

```bash
git add spike/plugin/src spike/FINDINGS.md
git commit -m "spike: read staff search results"
```

---

### Task 5: Change one training session and verify (criterion 4)

**Files:**
- Create: `spike/plugin/src/Training.cs`
- Modify: `spike/plugin/src/Ops.cs` (register `training_get`, `training_set_session`)
- Create: `spike/client/check_training.py`

**Interfaces:**
- Produces: op `training_get` → `{"week_start": "YYYY-MM-DD", "sessions": [{"day": 0-6, "slot": "morning"|"afternoon"|"extra", "name": str}]}`.
- Produces: op `training_set_session` `{"day": int, "slot": str, "name": str}` → `{"before": str, "after": str}`. Element not found → `ok:false, error:"ui-element-missing: <element/text>"`, nothing changed.
- Approach: first try reading via `TrainingCalendarBinding` / `CustomTrainingScheduleBinding` (names seen in FM27 metadata); perform the change by driving the Training calendar UI by element name/text (fm-dof-mcp `Navigator.ClickByText` / `UiClick` pattern). Writing binding values directly is out of scope for the spike.

- [ ] **Step 1: Back up the save** (Global Constraints rule) and record the SHA-256 in `FINDINGS.md`.

- [ ] **Step 2: Implement `training_get`; live check** with the Training → Schedule screen open. Expected: 21 sessions for the current week matching the screen.

- [ ] **Step 3: Implement `training_set_session`.**

- [ ] **Step 4: Write `check_training.py`**

Reads `training_get`, picks one non-match session that is not already `"Recovery"`, sets it to `"Recovery"`, reads again, asserts exactly that one session changed, then sets it back to the original value and asserts the week equals the first read.

- [ ] **Step 5: Run live**

Run: `uv run --with websockets python check_training.py`
Expected: `OK: changed <day>/<slot> <orig> -> Recovery -> <orig>`. Then close the training screen and run again: expect `FmError` code `ui-element-missing` or `wrong-screen` and `training_get` unchanged.

- [ ] **Step 6: Commit**

```bash
git add spike/plugin/src spike/client/check_training.py spike/FINDINGS.md
git commit -m "spike: set one training session via in-game UI and verify"
```

---

### Task 6: Verdict + post-release re-test

**Files:**
- Modify: `spike/FINDINGS.md`
- Modify: `docs/superpowers/specs/2026-11-07-fm-assistant-manager-design.md` (only if a criterion failed or a decision changed)

- [ ] **Step 1: Write verdict table** in `FINDINGS.md`: criterion 1–4 → pass/fail, game build, loader version, evidence (command + output excerpt), surprises, property/screen names discovered, estimated difficulty per Phase 1 feature (F11, F6, F10 first).

- [ ] **Step 2: Apply spec fallbacks if needed** (spec §9: criterion 1 fails → evaluate other loader; criterion 4 fails → actions become "recommend + UI steps") and note the change in the spec.

- [ ] **Step 3: After FM27 full release (≥ 2026-11-10) and the Steam update**, re-run: Task 1 Step 6, Task 2 Step 7, `check_squad.py`, Task 4 Step 2, `check_training.py`. Record per-build results in `FINDINGS.md` → "Re-test after release".

- [ ] **Step 4: Re-run the original-app signature check** (Task 1 Step 1). Expected: valid.

- [ ] **Step 5: Commit**

```bash
git add spike/FINDINGS.md docs/superpowers/specs
git commit -m "spike: phase 0 verdict"
```
