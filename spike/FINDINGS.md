# Phase 0 spike — findings

Game build: `27.0.0.2493426` (Steam, early access), macOS 26.1 (25B78), arm64, SIP enabled.

## Baseline (Task 1 Step 1, 2026-11-07)

```
codesign --verify --deep --strict --verbose=2 ".../Football Manager 27/fm.app"
fm.app: valid on disk
fm.app: satisfies its Designated Requirement
```

## Toolchain (Task 1 Step 2)

- .NET SDK `8.0.427` at `~/.dotnet` (dotnet-install.sh, channel 8.0)
- Rosetta 2: already installed

## Loader review (Task 1 Step 4)

Package: `FM27-BepInEx-macOS-arm64.zip` (sptndc base + FM27 patches by "hasan"), 237 files,
sha256 `c9789aba5fcb5391cd8904bee5bb6b57b9485b1aeb5a20e434c3af38db70eb43`, dated 2026-10-30.
Extracted to `~/fm-spike-vendor/sptndc/FM27-BepInEx/`.

| Part | Verdict |
|---|---|
| `run_fm27_bepinex.sh` | Read fully. No sudo/csrutil/network. Original `fm.app` only read (`cp -cR` APFS clone into `FM27-BepInEx/shadow/`); ad-hoc re-sign + thinning only on the clone. Clears quarantine only in its own folder. Launch via `/usr/bin/arch -arm64 -e DYLD_INSERT_LIBRARIES=…` for the game process only. OK. |
| `source/fm27_doorstop.c` | Read fully. dyld-interposes `dlsym`, swaps `il2cpp_init`, starts CoreCLR, calls `Doorstop.Entrypoint.Start`. No file/network beyond its log. OK. **Rebuilt from source locally** (clang, ad-hoc) → sha256 `4d9a599a…8424`; prebuilt kept as `fm27_doorstop.prebuilt.dylib`, not used. |
| `source/FM27HookFix/FM27HookFix.cs` | Read relevant parts. Harmony finalizer on Il2CppInterop hook lookup; only writes `BepInEx/config/fm27_hookfix.cfg`. Prebuilt DLL used (not rebuilt). |
| `dotnet/` | Official Microsoft .NET runtime 6.0.7 (dylibs signed TeamIdentifier `UBF8T346G9` = Microsoft). OK. |
| `libdobby.dylib`, `libcapstone.dylib` | Ad-hoc signed community builds, no source in package (capstone has build script). **Unverified.** |
| `BepInEx/core/*.dll` (modified BepInEx 6, Il2CppInterop) | sptndc's modified builds, upstream forks show no published diff. **Unverified.** |
| First launch | Per README, BepInEx downloads Unity base libraries once (standard BepInEx IL2CPP behavior). |

Residual risk: unverified community binaries run inside the FM27 process with the user's permissions.

## Criterion 1 — loader running: **PASS** (2026-11-07, build 27.0.0.2493426)

- Steam launch option: `".../Football Manager 27/FM27-BepInEx/run_fm27_bepinex.sh" %command%`
- `fm27_doorstop.log`: `il2cpp_init intercepted` → `CoreCLR started` → `Doorstop.Entrypoint.Start() returned` (~42 s first launch).
- `LogOutput.log`: `Chainloader startup complete`. FM27 Hook Fix resolved `GenericMethod::GetMethod` → `GameAssembly+0x7063D8`; warning `Class::Init signatures have been exhausted, using a substitute!` (non-fatal).
- `BepInEx/interop/`: 182 DLLs incl. SI.Bindable, SI.Bindable.Reference.Core, SI.Core, SI.UI, FM.UI, FM.GamePlugin, UnityEngine.UIElementsModule.
- Original `fm.app` signature after run: `codesign --verify --deep --strict` → valid (unchanged).

## Task 2 — plugin + ping (2026-11-07, build 27.0.0.2493426)

- Plugin loads (`[FmSpike] 0.0.1 loaded, ws://127.0.0.1:7788/`), tick via Harmony prefix on `UIElementsRuntimeUtility.RepaintPanels` works, `BindingSubsystem.Initialise` postfix captures bindings.
- Main menu ping: `{'plugin': 'fm-spike', 'version': '0.0.1', 'game_build': '27.0.0.2493426', 'bindings_captured': True, 'career_loaded': False}`.
- Game launch without the owner: `open steam://rungameid/4530370` (Steam running) works; plugin up ~10 s, bindings ~25 s.
- Security: WsServer rejects handshakes with an `Origin` header (blocks browser pages). Phase 1 adds a per-session token.

## Property-name discovery (Task 3 Step 1, main menu)

- Candidate list: 1083 PascalCase literals harvested from fm-dof-mcp (FM26) SquadReport/QueryPlayers/EntityVocabulary/MyClub.
- **989 / 1083 resolve in FM27** via `PropertyIdentifierSet.Instance.GetID`. Includes every `Attribute*` (Acceleration…WorkRate, incl. hidden ones like Consistency/Professionalism — must respect CanView* gates), `Wage`, `FullContract`, `ContractLength`, `ContractDaysElapsed`, `Condition`, `Fatigue`, `TransferBudget`, `CommittedWageSpending`, `TrainingCalendar`, `CustomTrainingSchedule`, `TrainingSessions`, `StaffScoutList`, `StaffAllListFiltered`, `CanViewStaffSearch`.
- Unresolved (94): see scratch list; mostly FM26-only debug/UI names.
- Binding root children include `Human`, `game`, `data`, `continue`, `SetupGame`, `IGE`, `fmpedia`.
- Career loaded (owner loaded Java United): ping → `career_loaded: True`; `Human` subtree = `Club` (ClubReference), `Team` (TeamReference), `HumanOptedInToTransferDeadlineDay`. **Task 2 PASS.**
- FM27 UI API change vs FM26: `PanelManager.RootVisualElement` gone; use `PanelManager.GetAllOpenPanels(List<SI.Bindable.Panel>)` (Panel : VisualElement). Op `panels` returns PanelID names, e.g. portal = `GameWorldBackground, OverviewTitleBar, PortalScreen, Watermark, GameVersion`; splash = `PhotosensitivityWarning_SplashScreen`.
- **Owner's game language is Indonesian** → actions must target PanelIDs / element names, never English button text.
- Closing the game: AppleScript quit is refused ("User canceled"), SIGTERM ignored; only SIGKILL works → acceptable only at main menu with no career. After a SIGKILL the next launch hung at "Chainloader initialized" until the owner relaunched. Phase 1 needs a safe "back to main menu / quit" path or leaves closing to the owner.

## Task 3 — read squad (2026-11-07, build 27.0.0.2493426)

- Op `squad` (club → `MainTeam` → `Team.Players` → per-player props → `FullContract` chained → `Wage/EndDate/ContractLength`): **28 players in 4.1 s**, batches of 20, one shared poll loop.
- `check_squad.py`: **OK: 28 players, 28/28 matched save summary** (newest save, read-only via cli-anything-fm27 `save_info`). Non-ASCII names exact (`França`).
- Save `squad_snapshot` uses short names (`K. Hirose`) and mixes in youth players (`S. Ramadhani` is in Java United U21) → checker matches initial+surname and looks in youth teams.
- FM27 port notes vs fm-dof-mcp (FM26): `Bindings.Bind` now takes an owner object `(ref Key, Object owner, ValueChangedCallback)`; native `Bindings.Create` overloads still resolved by param count; attribute values land as digit strings inside a `PropertyValue` record → decoder coerces numeric strings.
- Wage: `{"display": "Rp27Jt p/mgg", "sort": 1128}`. `sort` is not rupiah (likely the base currency); use `display` for the owner, `sort` only for ranking.
- Generic op `read {ref: person|club|team|path, uid|path, props[]}` added for discovery without restarts. `Human.Club` → `TransferBudget: 239000`, `PlayersOutOnLoan` works.

## Autonomous game control (2026-11-07)

- Owner's macOS permission: **Screen Recording** (screencapture works now; Accessibility not granted).
- After a SIGKILL, macOS shows a hidden "reopen windows?" modal (`NSPersistentUIRestorer promptToIgnorePersistentStateWithCrashHistory`) that blocks the next launch before `il2cpp_init` — the cause of the earlier "hang". Fix: delete `~/Library/Saved Application State/com.SportsInteractive.FootballManager27.savedState` and `defaults write com.SportsInteractive.FootballManager27 ApplePersistenceIgnoreState -bool YES`.
- `spike/client/game.py restart --load`: kill → clear state → `open steam://rungameid/4530370` → wait for plugin → click `LoadMostRecentSave` (MainMenu, language-neutral element name) → career loaded. Full cycle ~1.5 min, no owner input. Refuses to kill a loaded career unless `--allow-career` (caller checks in-game date == save date first; agent never saves).
- New UI ops: `ui_dump {panel, depth, max}` (element tree: name/type/text/bounds), `ui_click {name, panel, index}`.
