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
- Security: WsServer rejects handshakes with an `Origin` header (blocks browser pages). Phase 1 adds a session token for every request; Phase 2 adds the per-plan token minted by `fm apply` (spec §8).

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
- `spike/client/game.py restart --load`: kill → clear state → `open steam://rungameid/4530370` → wait for plugin → click `LoadMostRecentSave` (MainMenu, language-neutral element name) → career loaded. Full cycle ~1.5 min, no owner input. **Kill guard (fixed after final review):** fails closed — kills only when no career is loaded, or with `--allow-career` when this helper itself loaded the career in the same game process (marker `~/.fm-assistant/agent-loaded.json`). An owner-loaded career is never killed; "in-game date == save date" is NOT a valid unsaved-progress check (a training change leaves the date unchanged). Plugin unreachable while the game runs → refuse. Tests: `test_game.py`.
- New UI ops: `ui_dump {panel, depth, max}` (element tree: name/type/text/bounds), `ui_click {name, panel, index}`.

## Task 4 — Staff Search (2026-11-07, build 27.0.0.2493426)

- Screen: panel id **`StaffSearchReport`**; table `StreamedTable 'nonplayertable'`, columns `default-selection-column, status, non-player, clubjob, preferredjob, club, club-division, rating`. Reached via KLUB → Staf → "Database Staf / Seluruh dunia" tile (spike navigates by Indonesian text; Phase 1 must use ids).
- `StreamedListView.SourceData` / `ListElement.Items` are public in FM27 (no reflection) → **all 173 rows**, not just the 17 rendered.
- `check_staff.py`: **OK: 173/173 staff rows, 17 on-screen names all present**; Squad screen → `wrong-screen: expected StaffSearchReport, got …SquadScreen…`.
- **Staff attribute property names have no `Attribute` prefix** (player ones do): `Attacking, Defending, Tactical, Technical, SetPieces, CoachingFitness, TacticalKnowledge, JudgingPlayerAbility, JudgingPlayerPotential, JudgingStaffAbility, PeopleManagement, Motivating, Adaptability, Determination, Physiotherapy, SportsScience, Negotiating, AnalysingData` (1–20). Not found yet: goalkeeping coaching, mental coaching, working with youngsters, discipline.
- `PreferredJob` → record with `JobString` (e.g. "Analis Performa", localized). Wage demand is not in the search view → `wage_demand: null`; Phase 1 reads it from the contract offer screen.
- Discovery aids: `ui_dump` now reports each SIText's binding path (`bind`), `list_rows` reports table column ids, `read` takes `chain: {prop: [subprops]}`.
- **Crash found + fixed:** overwriting `FmSpike.dll` in place while the game runs crashes it on the next JIT (SIGSEGV in `SignatureNative::GetSignature`; the file is mmapped). `build.sh` now copies to `.new` and renames.
- Main menu `squad` → `no-career-loaded: load a career first` (Task 3 Step 4 check).

## Task 5 — change one training session (2026-11-07, build 27.0.0.2493426)

- Save backup before any action: `~/fm-spike-backups/20261107-133259/Nael Anggara - Java United.fm`, sha256 `5e9ed5d108586ca04e71b5fb93ec88603882afd33b28630ea8c63c93f30ba042`. After the run the save still has the same sha256 (game never saved) and original `fm.app` signature is valid.
- Screen: panel **`TrainingScreen`** (LATIHAN tab) shows a 6-week month view, 3 slots per day (S1–S3). Popup on clicking a slot: **`TrainingSessionSelectCard`** (week editor + category radios + session option radios + buttons named `confirm` / `cancel`).
- Language-neutral anchors (binding paths): `day.DayOfTheMonth`, `week.TrainingScheduleName`, `Event.SessionName`, `Event.TeamOpponent.AbbreviatedName` (match in a slot), option radios `item.DisplayValue`. Session *names* are localized text — Phase 1 should map them via a session-id binding, not the display string.
- `training_get` → 42 days × 3 slots matching the screen; matches show as `vs <opp>`.
- `check_training.py`: **OK: changed 17/0 Kondisi Fisik -> Istirahat -> Kondisi Fisik; calendar restored; wrong-screen off screen.**
- Interface deviation from plan: FM27 has S1/S2/S3 per day (not morning/afternoon/extra) and the screen is a month view, so ops address `{index: day index in the view, slot: 0-2}`.
- "Perjalanan" (travel) slots exist around away matches; check avoids them (may not be restorable from the option list).

## Startup crash (open, Phase 1)

- ~1 in 5 launches: SIGSEGV ~7–9 s after start in `libunwind setInfoBasedOnIPRegister ← PAL_VirtualUnwind ← DebugStackTrace::GetStackFramesInternal` (CoreCLR capturing a managed exception's stack trace through frames libunwind can't parse). Same signature with plugin 0.0.1-old and new → not caused by new ops. Reports: `~/Library/Logs/DiagnosticReports/Football Manager 27-2026-11-07-130758.ips`, `-133543.ips`.
- Spike mitigation: `game.py launch` retries (process exits during startup → clear state → relaunch). Phase 1: find the thrown exception (first-chance handler log), avoid managed exceptions on IL2CPP-entered threads.
- `load_recent` now re-clicks `LoadMostRecentSave` every 15 s (early clicks during the menu intro are ignored).

## Verdict (2026-11-07, pre-release build 27.0.0.2493426, loader sptndc FM27-BepInEx arm64 2026-10-30 + locally rebuilt doorstop)

| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1 | BepInEx loader runs on macOS arm64, SIP on, original app untouched | **PASS** | `Chainloader startup complete`; `codesign --verify --deep --strict fm.app` valid before and after all tasks |
| 2 | Read squad (≥3 attributes, contract, wage) | **PASS** | `check_squad.py` → `OK: 28 players, 28/28 matched save summary`, 4.1 s |
| 3 | Read staff search (≥1 page + requested wage) | **PASS (partial)** | `check_staff.py` → `OK: 173/173 staff rows, 17 on-screen names all present`; wrong screen → `wrong-screen`. **Requested wage not found** in the search view (`wage_demand: null`); its source is unproven → Phase 1a Task 7 discovery |
| 4 | Change one training session and verify | **PASS** | `check_training.py` → `OK: changed 17/0 Kondisi Fisik -> Istirahat -> Kondisi Fisik; restored; unknown option cancelled; wrong-screen off screen, calendar unchanged` |

**Go for Phase 1.** No spec fallback needed (spec §9).

Plan deviations (all deliberate, spike-only): training addressed `{day index, slot 0-2}` (FM27 month view, S1–S3); `squad` returns raw prop names with nested `contract` instead of the plan's flat shape; `prop_check {names}` replaced `dump_props {filter}`; `staff_search_visible` has no `cells` by column header (headless person reads instead); staff check used the worldwide database, not a Scout filter; navigation by Indonesian tab text.

Surprises:
- Fully unattended loop works: restart game, load career, navigate, read, act (`game.py`) — the owner never touched the laptop for Tasks 3–5.
- Reading is headless and screen-independent (fabricate → bind → poll), so most recommendation features need no UI navigation at all.
- Actions go through the real UI by element name / binding path → language-neutral except option *labels*.
- Two crash classes: (a) overwriting the loaded DLL — fixed; (b) intermittent startup crash in CoreCLR stack walking — open, retried.
- Killed app → hidden macOS "reopen windows?" modal blocks the next launch — fixed by `ApplePersistenceIgnoreState`.

Discovered names: see Task 3–5 sections (panels `StaffSearchReport`, `TrainingScreen`, `TrainingSessionSelectCard`, `MainMenu` tile `LoadMostRecentSave`; staff attributes without `Attribute` prefix; club `TransferBudget`, `MainTeam`, `HighestLevelYouthTeam`, `YouthTeam`, `PlayersOutOnLoan`).

Phase 1 difficulty (first three features):
| Feature | Read | Action | Estimate |
|---|---|---|---|
| F11 Staff search | rows + 18 attributes + role done; **wage demand source unknown** | `staff.offer`: open contract offer from staff row, read wage demand there, confirm — UI path still to map | medium once wage source is found; unestimated before |
| F6 Transfer/scouting ranker | budget (`TransferBudget`) done; player search = same list-read route as staff search | shortlist/scout request/bid via UI — per-action mapping | medium–high (bids + negotiation counters) |
| F10 Training | calendar read + single-slot change done | weekly apply = 21 single-slot changes or the schedule template picker; individual training not explored | low–medium |

Phase 1 design rules from the final review:
- Main-thread jobs carry a deadline and are skipped in `Drain` once expired; multi-step ops take a cancellation token; a client timeout on an action means "outcome unknown → re-read state", never "unavailable".
- Every read releases what it planted: keep the parent key in `Plant`, close parent + children in `finally` (spike leaks `__fmspike.N` parent nodes and, on error paths, child bindings).
- No exceptions as control flow on the main thread: return error results there, throw only on the WebSocket thread (startup-crash suspect path).
- No generic click ops on the socket (spike `ui_click`/`ui_click_text` can click Continue/Save). Phase 1 navigation = `nav_open` by panel id; Phase 2 actions = closed registry only.
- Native `Bindings.Create` resolved by parameter types, not only count; pooled pointer events disposed; the bind owner object created from main-thread code.
- A loaded career is never killed unless this tool loaded it in the same process; otherwise the owner closes it (or a safe quit-to-menu path, to be found).
- Startup crash: isolate with a launch where the plugin is not installed ("same with old/new plugin" only rules out the new ops).

Open items for Phase 1: per-session WebSocket token; startup crash root cause; safe quit-to-menu path; map localized session/option labels to ids; staff wage demand source; goalkeeping/mental/youngsters/discipline staff attribute names.

## Re-test after release

Owner decided on 2026-11-10 to build Phase 1a on the pre-release build instead of waiting (Steam still
showed `releasestate: prerelease`, local Steam build 26340721 from 2026-11-07).

| Build | Date | Result |
|---|---|---|
| 27.0.0.2493426 (pre-release, baseline for Phase 1a) | 2026-11-10 | `codesign --verify --deep --strict fm.app` valid; `fm game restart --load` OK (no owner input); `fm doctor` all ok; `fm/live/check_protocol.py` OK. Spike checks `check_squad/staff/training.py` need the spike plugin (removed: it fights for port 7788) — superseded by the Phase 1a Task 6, 7 and 9 live checks. |
| release build | pending | run `fm doctor`, `scripts/smoke.sh` and every `fm/live/check_*.py`; add the build to `Meta.TestedBuilds` when they pass |

Phase 1a observation: one owner-launched session had the plugin loaded and bindings captured but no main-thread
tick at all (every main-thread op timed out, no errors logged); the next launch ticked normally. Op `diag` now
reports the tick count without needing the main thread.
