# Phase 1a — Read + Recommend (foundation, F11, F6, F10) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Owner asks Claude Code "cari pelatih/scout yang bagus sesuai budget", "pemain mana yang layak dibeli", "jadwal latihan minggu ini gimana" and gets a data-backed recommendation with reasons and alternatives, read live from the running FM27.

**Architecture:** Production rebuild of the Phase 0 spike. A BepInEx plugin (`plugin/`) serves read-only ops over an authenticated localhost WebSocket. A Python library `fm_assistant` (`fm/`) holds the client, normalization, budget filters and deterministic scores; the `fm` CLI is a thin click wrapper over it. A Claude Code skill (`skills/fm-manager/`) tells Claude how to weigh the data and how to answer. No in-game actions in this plan (spec §9: actions are Phase 2) — navigation between screens is the only UI driving.

**Tech Stack:** C# net6.0 + BepInEx 6 IL2CPP (sptndc FM27 arm64 loader), Il2CppInterop; Python ≥ 3.10, uv, click, websockets ≥ 12, pytest.

**Not in this plan:** F1–F5, F7–F9 (next plan), any in-game action/plan/apply/backup (Phase 2), MCP server, installer/uninstaller, save-parser fork (Phase 3 / when Phase 2 backups need it).

**Spec:** `docs/superpowers/specs/2026-11-07-fm-assistant-manager-design.md`. Phase 0 evidence and every discovered name: `spike/FINDINGS.md`. Spike code in `spike/` is the reference implementation to port (it is throwaway — port deliberately, don't copy blindly; Task 2 lists the fixes).

## Global Constraints

- macOS arm64, Steam FM27 only; SIP stays enabled; the original `fm.app` is never modified (`codesign --verify --deep --strict` valid before/after each live task).
- Never save, press Continue, or play/simulate a match. Plugin exposes no such op.
- No database value edits. This plan adds no state-changing op except screen navigation.
- Hidden attributes only as far as FM shows them to the manager; the agent never sees values the UI would not show.
- WebSocket on `127.0.0.1` only; requests with an `Origin` header rejected; every request carries the session token.
- Code, CLI, README in English; the skill instructs Claude to answer the owner in Indonesian.
- No SI/SEGA/FM branding, no game files or game-database excerpts in the repo (fixtures use invented names).
- Attribution: fm-dof-mcp (MIT) for ported plugin patterns, cli-anything-fm27 (Apache-2.0) for the save parser → `NOTICE`.
- Plugin install never overwrites the loaded DLL in place (copy to `.new`, rename) — Phase 0 crash.
- The agent may restart the game itself (owner's standing instruction) but never kills a career it did not load in the same game process (marker file, fail closed; `spike/client/game.py` + `test_game.py`). In-game date is not an unsaved-progress check.

## Review Focus

1. **Steam update to an untested build** → every command still answers; `fm doctor` and each JSON result carry `build_supported: false` and the CLI prints `warning: game build <X> is not tested with this plugin (tested: <list>)` on stderr. Never a crash or a Python traceback. (Task 3 test `test_unsupported_build_warns`.)
2. **Game closed / plugin not loaded / no career / wrong screen** → non-zero exit with one plain sentence (`FM27 is not running with the assistant plugin. Start it from Steam.` / `No career loaded.` / `Open <screen> first.`), and `{"ok": false, "error": {"code", "detail"}}` under `--json`. (Task 1 tests + Task 3 `test_cli_errors_are_one_line`.)
3. **Player the club has not scouted** → attributes come back exactly as the UI shows them (range like `"8-12"`, or `null` when hidden), never the true value. (Task 8 live check `check_knowledge_parity`.)
4. **Non-ASCII names and localized labels** (Indonesian UI, `França`, `広瀬 圭`) → byte-exact round trip; plugin logic never matches English or Indonesian text. (Task 1 `test_non_ascii_round_trip`, Task 7/8 live checks compare to screen.)
5. **Very large search results** (thousands of staff/players) → op returns `count`, `returned`, `truncated: true` within the timeout, capped by `max` (default 200, hard cap 1000) and read in batches of 20. (Task 7 `test_truncation_flag` on the core side + live run with `max=1000`.)

---

## File Structure

```
plugin/
  FmAssistant.csproj            # from spike csproj; AssemblyName FmAssistant
  build.sh                      # build + safe install (copy .new → rename)
  src/Plugin.cs                 # BepInEx entry, Harmony hooks (RepaintPanels tick, BindingSubsystem.Initialise)
  src/Server/WsServer.cs        # HttpListener WS, Origin reject, size cap, token check, per-op timeout
  src/Server/Protocol.cs        # request/response shapes, OpException, op registry
  src/Server/Session.cs         # token generation + ~/.fm-assistant/session.json (0600)
  src/Game/MainThreadQueue.cs
  src/Game/Reader.cs            # fabricate→bind→poll→collect, Decode, Native Create
  src/Game/Ui.cs                # panels, walk, bind paths, click
  src/Game/ListRead.cs          # table backing rows + column ids
  src/Game/Nav.cs               # open screen by panel id
  src/Ops/Meta.cs               # hello, panels, ui_dump, prop_check, read (discovery ops)
  src/Ops/Club.cs  src/Ops/Squad.cs  src/Ops/Staff.cs  src/Ops/Players.cs  src/Ops/Training.cs
fm/
  pyproject.toml                # package fm_assistant, script `fm = fm_assistant.cli:main`
  src/fm_assistant/client.py    # FmClient (token, protocol v1), errors
  src/fm_assistant/game.py      # launch/restart/load-recent (from spike game.py)
  src/fm_assistant/doctor.py
  src/fm_assistant/budget.py    src/fm_assistant/positions.py
  src/fm_assistant/squad.py     src/fm_assistant/staff.py   src/fm_assistant/players.py
  src/fm_assistant/training.py
  src/fm_assistant/data/staff_roles.json   # role → attribute weights (owner-overridable)
  src/fm_assistant/cli.py
  tests/  (test_client.py, test_cli.py, test_budget.py, test_positions.py, test_staff.py, test_players.py, test_training.py)
  tests/fixtures/*.json         # invented names, real shapes
  live/check_*.py               # live checks against the running game (not run by pytest)
skills/fm-manager/SKILL.md
skills/fm-manager/commands/fm-staff-search.md  fm-scout.md  fm-training.md
docs/protocol.md
NOTICE  LICENSE  README.md
```

---

### Task 1: Python package + protocol v1 client

**Files:**
- Create: `fm/pyproject.toml`, `fm/src/fm_assistant/__init__.py`, `fm/src/fm_assistant/client.py`, `fm/tests/test_client.py`, `docs/protocol.md`, `LICENSE` (MIT, owner as author), `NOTICE`

**Interfaces:**
- Produces (protocol v1, written down in `docs/protocol.md`):
  - request `{"v": 1, "id": str, "op": str, "args": object, "token": str}`
  - response `{"v": 1, "id": str, "ok": true, "result": any}` | `{"v": 1, "id": str, "ok": false, "error": {"code": str, "detail": str}}`
  - session file `~/.fm-assistant/session.json` = `{"port": int, "token": str, "pid": int, "plugin_version": str, "game_build": str}`, mode 0600, written by the plugin at startup.
  - error codes used across tasks: `unauthorized`, `bad-request`, `unknown-op`, `bindings-not-captured`, `no-career-loaded`, `wrong-screen`, `ui-element-missing`, `main-thread-timeout`, `binding-api-changed`, `internal`.
- Produces (Python): `FmClient(session_path: Path | None = None, timeout: float = 30.0)`; `FmClient.call(op: str, **args) -> Any`; exceptions `FmUnavailable(Exception)` (no session file, connection refused, timeout, dead pid) and `FmError(Exception)` with `.op`, `.code`, `.detail`.

- [ ] **Step 1: Write failing tests** in `fm/tests/test_client.py` using a threaded `websockets.sync.server` fake on port 0 plus a temp session file (port from the fake, token `"t0k"`):
  - `test_call_returns_result` — fake answers `{"v":1,"id":<id>,"ok":true,"result":{"x":1}}` → `{"x": 1}`.
  - `test_request_carries_token_and_version` — fake records the request; assert `req["token"] == "t0k"` and `req["v"] == 1`.
  - `test_error_raises_fmerror` — `{"ok":false,"error":{"code":"wrong-screen","detail":"expected X"}}` → `FmError` with `code == "wrong-screen"`, `detail == "expected X"`.
  - `test_unavailable_without_session_file`, `test_unavailable_when_nothing_listening`, `test_unavailable_when_server_never_answers` (timeout 0.5).
  - `test_non_ascii_round_trip` — `"Rúben Gonçalves"` and `"広瀬 圭"` echo back identical.
- [ ] **Step 2: Run** `cd fm && uv run pytest tests/test_client.py -q` → FAIL (module not found).
- [ ] **Step 3: Implement** `client.py`: read session file each `call` (plugin restarts change the token); one connection per call (`websockets.sync.client.connect`, no `Origin` header); wait for the matching `id`. Port from `spike/client/fmspike.py`.
- [ ] **Step 4: Run** the same command → 7 passed.
- [ ] **Step 5: Commit** `feat(fm): protocol v1 client with session token`.

### Task 2: Plugin port with protocol v1, token, and spike fixes

**Files:**
- Create: everything under `plugin/` listed in File Structure except `src/Game/Nav.cs`, `src/Ops/Club.cs`, `Squad.cs`, `Staff.cs`, `Players.cs`, `Training.cs` (later tasks).
- Create: `fm/live/check_protocol.py`

**Interfaces:**
- Consumes: Task 1 protocol.
- Produces: op `hello` → `{"plugin": "fm-assistant", "plugin_version": "0.1.0", "protocol": 1, "game_build": str, "build_supported": bool, "tested_builds": [str], "bindings_captured": bool, "career_loaded": bool, "human_club_uid": int|null}`. Discovery ops `panels`, `ui_dump`, `prop_check`, `read` with the spike's argument shapes (see `spike/plugin/src/*.cs`), now registered in `Protocol.cs` as `name → (handler, isAsync, timeoutSeconds)`.
- Produces (C#, for later ops): `Reader.ReadMany(List<Func<TypedValue>>, string[] props, int waitMs) -> Task<List<Plant>>`, `Reader.Collect(Plant) -> JsonObject`, `Reader.Close(Plant)`, `Reader.Main<T>(Func<T>) -> Task<T>`, `Reader.PersonRef/ClubRef/TeamRef(int)`, `ListRead.Widgets(string panelId)`, `ListRead.Rows(StreamedListView, int cap)`, `Ui.OpenPanels()`, `Ui.Walk`, `Ui.BindPath`, `Ui.Visible`, `Ui.OwnText`, `Ui.Click`.

- [ ] **Step 1: Write `fm/live/check_protocol.py`** (runs against the live game): `hello` has every key above and `protocol == 1`; `ui_click` → `unknown-op`; 20 back-to-back `read` calls leave no `__fm.` nodes under the binding root (`tree` of the root before == after); a raw websocket request without `token` → `error.code == "unauthorized"`; a handshake with header `Origin: http://evil.example` is refused (HTTP 403); a 300 KB message closes the connection; unknown op → `unknown-op`.
- [ ] **Step 2: Port the plugin** into the new layout and apply these decided changes:
  - `Session.cs`: 32 random bytes (`RandomNumberGenerator`) hex-encoded token; write `session.json` atomically (temp + rename) and `chmod 0600` via libc P/Invoke (`[DllImport("libc")] int chmod(string, uint)`); compare tokens with `CryptographicOperations.FixedTimeEquals`.
  - `Reader.cs`: keep every `ValueChangedCallback` delegate and its `Prop` referenced from the `Plant` until `Close` (GC safety); `Close` runs in a `finally` on every op path, including timeouts; numeric-string coercion from the spike stays.
  - Every main-thread job wraps its body in try/catch and converts to `OpException`/`internal` before leaving the job; no exception may propagate out of the Harmony `RepaintPanels` prefix (Phase 0 startup-crash suspect, `spike/FINDINGS.md` → "Startup crash").
  - `tested_builds` = `["27.0.0.2493426"]` plus the release build after Task 3.
  - Main-thread jobs carry a deadline; `Drain` skips expired jobs; async ops take a `CancellationToken` cancelled at the op timeout.
  - `Plant` keeps its parent key; `Close` clears the parent node and unbinds/closes children; every op wraps read→collect in `try/finally { Close }`; `Unbind` failures are logged, not swallowed.
  - Main-thread code returns error results instead of throwing; `OpException` is raised only on the WebSocket thread.
  - No generic click ops (`ui_click`, `ui_click_text`) — only `ui_dump`, `panels`, `prop_check`, `read` for discovery; navigation arrives as `nav_open` (Task 4).
  - `Native` resolves `Bindings.Create` overloads by parameter types; pooled pointer events are disposed; the bind owner object is created on the main thread at bindings capture.
  - Oversized messages close the socket with status 1009; non-string `id` → `bad-request`; max 4 concurrent connections.
  - Full list and reasons: `spike/FINDINGS.md` → "Phase 1 design rules from the final review".
- [ ] **Step 3: Build** `bash plugin/build.sh` → `Build succeeded`, installed as `BepInEx/plugins/FmAssistant/FmAssistant.dll`; remove `plugins/FmSpike/` (the two plugins would fight for port 7788).
- [ ] **Step 4: Live run** `uv run --project fm python fm/live/check_protocol.py` (restart the game first with Task 3's helper or `spike/client/game.py restart --load`) → `OK`.
- [ ] **Step 5: Commit** `feat(plugin): protocol v1 server with session token`.

### Task 3: Game control, version gate, `fm doctor`, release re-test

Precondition: Steam has installed the FM27 full-release build (released 2026-11-10). Do not start before.

**Files:**
- Create: `fm/src/fm_assistant/game.py`, `fm/src/fm_assistant/doctor.py`, `fm/src/fm_assistant/cli.py`, `fm/tests/test_cli.py`
- Modify: `plugin/src/Ops/Meta.cs` (`tested_builds`), `spike/FINDINGS.md` ("Re-test after release")

**Interfaces:**
- Consumes: `FmClient`, op `hello`.
- Produces: `game.status() -> dict` (hello or `{"running": false}`), `game.launch()`, `game.load_recent()`, `game.restart(load: bool, allow_career: bool)` (port of `spike/client/game.py` incl. saved-state clearing, retry, re-click); `doctor.run() -> list[dict]` with items `{"check": str, "ok": bool, "detail": str}`.
- Produces CLI: `fm [--json] game status|launch|load-recent|restart [--load] [--allow-career]`, `fm [--json] doctor`. Common error handling in `cli.py`: `FmUnavailable` → exit 2, `FmError` → exit 3, message on stderr, JSON error object on stdout with `--json`. Unsupported build → stderr warning (Review Focus 1).

- [ ] **Step 1: Write failing tests** in `fm/tests/test_cli.py` (click `CliRunner`, `FmClient.call` monkeypatched):
  - `test_doctor_all_ok` — hello ok + one read per feature ok → exit 0, every line starts with `ok`.
  - `test_unsupported_build_warns` — `build_supported: false, game_build: "27.0.9"` → stderr contains `not tested with this plugin`, exit 0.
  - `test_cli_errors_are_one_line` — `FmUnavailable` → exit 2, stderr exactly `FM27 is not running with the assistant plugin. Start it from Steam.\n`; `FmError("squad","no-career-loaded","...")` → exit 3, stderr `No career loaded.\n`.
  - `test_json_error_shape` — with `--json`, stdout parses to `{"ok": false, "error": {"code": "no-career-loaded", ...}}`.
  - `test_restart_refuses_loaded_career` — hello `career_loaded: true`, no `--allow-career` → exit 3, no `kill` called (monkeypatch `subprocess.run`).
- [ ] **Step 2: Run** `cd fm && uv run pytest tests/test_cli.py -q` → FAIL.
- [ ] **Step 3: Implement** `game.py`, `doctor.py`, `cli.py`. Doctor checks, in order: shadow app present, loader log shows `Chainloader startup complete`, session file present, `hello`, build supported, career loaded, then one read per feature as later tasks add them (registry list in `doctor.py`).
- [ ] **Step 4: Run** tests → pass.
- [ ] **Step 5: Release re-test (live).** Original-app signature check; `fm game restart --load --allow-career` (after checking date == save date); `fm doctor`; re-run `spike/client/check_squad.py`, `check_staff.py`, `check_training.py` against the spike plugin *or* note they are superseded by the Task 6, 7, 9 live checks; add the release build to `tested_builds`; record per-build results in `spike/FINDINGS.md` → "Re-test after release" (Phase 0 Task 6 Step 3).
- [ ] **Step 6: Commit** `feat(fm): game control, doctor, version gate; release re-test`.

### Task 4: Navigate by panel id

**Files:**
- Create: `plugin/src/Game/Nav.cs`, `fm/live/check_nav.py`

**Interfaces:**
- Produces: op `nav_open {"panel": str}` → `{"panel": str, "open": true}`; `wrong-screen` if the panel did not open within 5 s. Panel ids used by later tasks: `StaffSearchReport`, `TrainingScreen`, `SquadScreen`, and the player-search panel id found in Task 8.
- Produces (Python): `FmClient.call("nav_open", panel=...)` used by CLI read commands before reading.

- [ ] **Step 1: Discover the route.** Try `PanelManager.Open(PanelID, …)` with the `PanelID` ScriptableObject found by name (scan loaded `PanelID` assets: `Resources.FindObjectsOfTypeAll<PanelID>()`). If it opens `StaffSearchReport` with its data bound, use it. Otherwise fall back to clicking the main navigation tab by its index in `OverviewTitleBar` (order recorded in `spike/FINDINGS.md`) followed by the sub-tab element found by binding path — never by text. Record the chosen route in `docs/protocol.md`.
- [ ] **Step 2: Implement `nav_open`** with the chosen route.
- [ ] **Step 3: Live check** `fm/live/check_nav.py`: from Portal, `nav_open` each of `StaffSearchReport`, `TrainingScreen`, `SquadScreen` → `panels` contains it; game language untouched (works in Indonesian UI with no text matching).
- [ ] **Step 4: Commit** `feat(plugin): navigate by panel id`.

### Task 5: Club and budget

**Files:**
- Create: `plugin/src/Ops/Club.cs`, `fm/src/fm_assistant/budget.py`, `fm/tests/test_budget.py`, `fm/tests/fixtures/club.json`, `fm/live/check_club.py`
- Modify: `fm/src/fm_assistant/cli.py`, `fm/src/fm_assistant/doctor.py`

**Interfaces:**
- Produces: op `club` → `{"uid": int, "name": str, "balance": Money, "transfer_budget": Money, "wage_budget": Money, "wage_committed": Money, "staff_slots": {"coaching": {"used": int, "max": int}, "recruitment": {...}, "medical": {...}}}` where `Money = {"display": str, "value": number}` (`value` = the game's sort value, base currency; `display` = owner's currency text).
- Produces (Python): `budget.wage_headroom(club: dict) -> float` (`wage_budget.value - wage_committed.value`, never negative → 0), `budget.fmt(m: Money) -> str` (returns `display`).
- Produces CLI: `fm [--json] club budget`.

- [ ] **Step 1: Discover names.** `prop_check` + `read ref=path path=Human.Club` for `TransferBudget` (known), wage-budget candidates (`CurrentWageBudgetValueWithText`, `CommittedWageSpending`, `CurrentWageSpending`, `CurrentWageTotalValue`) and balance; staff slots from binding paths seen in Staff Search (`Team.StaffCoachingSubGroup.Count/MaxValue`, `…Recruitment…`, `…Medical…`). Confirm `value` units: `TransferBudget` raw vs. the UI's displayed budget. Record in `docs/protocol.md`.
- [ ] **Step 2: Write failing tests** `test_budget.py`: `test_wage_headroom` (budget 1000, committed 800 → 200), `test_wage_headroom_never_negative` (800/1000 → 0), `test_fmt_uses_display`.
- [ ] **Step 3: Implement** op `club`, `budget.py`, CLI `fm club budget` (table: balance, transfer budget, wage budget, committed, headroom, staff slots), doctor read.
- [ ] **Step 4: Run** `cd fm && uv run pytest -q` → pass; live `fm/live/check_club.py`: `display` strings equal the Finance screen texts (`ui_dump` of the club finances panel).
- [ ] **Step 5: Commit** `feat: club budget read`.

### Task 6: Squad v1

**Files:**
- Create: `plugin/src/Ops/Squad.cs`, `fm/src/fm_assistant/positions.py`, `fm/src/fm_assistant/squad.py`, `fm/tests/test_positions.py`, `fm/tests/fixtures/squad.json`, `fm/live/check_squad.py`
- Modify: `cli.py`, `doctor.py`

**Interfaces:**
- Produces: op `squad {"team": "first"|"reserve"|"youth"}` (club props `MainTeam`, `HighestLevelYouthTeam`, `YouthTeam`) → `{"club": {...}, "team": {"uid", "name"}, "count": int, "players": [Player]}`, `Player = {"uid", "name", "age", "position_mask": int, "attributes": {name: int|str|null}, "condition": number|null, "fatigue": number|null, "injured": bool|null, "contract": {"wage": Money, "end_date": "YYYY-MM-DD", "length_days": int}}`. Attributes: visible player attributes only (technical, mental, physical, goalkeeping — `Attribute*` names in `spike/FINDINGS.md`); hidden ones (Consistency, Dirtiness, ImportantMatches, InjuryProneness, Versatility, Adaptability, Ambition, Controversy, Loyalty, Pressure, Professionalism, Sportsmanship, Temperament) are never requested.
- Produces (Python): `positions.decode(mask: int) -> str` (bit table from fm-dof-mcp `PositionDecode.cs`, MIT; e.g. `1 → "GK"`, `16 → "D (C)"`, `16|8|4 → "D (RLC)"`, `16384 → "ST (C)"`, `0x100010 → "D (LC)"`); `squad.normalize(raw: dict) -> dict` adds `position`.
- Produces CLI: `fm [--json] squad list [--team first|reserve|youth]`.

- [ ] **Step 1: Discover** `Condition`, `Fatigue` scale and an injury flag (`prop_check` candidates `IsInjured`, `Injury`, `CurrentInjury`) on one fit and one injured player; record.
- [ ] **Step 2: Write failing tests** `test_positions.py` with the five examples above plus `test_unknown_bits_ignored` (`2 → ""`).
- [ ] **Step 3: Implement** op, `positions.py`, `squad.py`, CLI.
- [ ] **Step 4: Run** pytest → pass; live `check_squad.py` (port of the spike check: names vs newest save summary, ≥ 10 integer attributes per outfield player, dates parse, non-ASCII exact).
- [ ] **Step 5: Commit** `feat: squad read v1`.

### Task 7: Staff search (F11)

**Files:**
- Create: `plugin/src/Ops/Staff.cs`, `fm/src/fm_assistant/staff.py`, `fm/src/fm_assistant/data/staff_roles.json`, `fm/tests/test_staff.py`, `fm/tests/fixtures/staff_search.json`, `fm/live/check_staff.py`
- Modify: `cli.py`, `doctor.py`

**Interfaces:**
- Produces: op `staff_search {"max": int}` (opens `StaffSearchReport` via `nav_open` if not open; reads backing rows; batches of 20) → `{"count": int, "returned": int, "truncated": bool, "rows": [Staff]}`, `Staff = {"uid", "name", "age", "club_uid": int|null, "preferred_job": str, "attributes": {name: int}, "wage_demand": Money|null}`.
- Produces (Python): `staff.load_roles(path: Path | None = None) -> dict[str, dict[str, float]]` (packaged `staff_roles.json`, overridden key-by-key by `~/.fm-assistant/staff_roles.json`); `staff.score(s: dict, role: str, roles: dict) -> float` = weighted mean of the role's attributes on the 1–20 scale, rounded to 0.1, missing attribute counts as 0 weight; `staff.rank(rows: list, role: str, max_wage: float | None, roles: dict) -> list[dict]` — score desc, rows over `max_wage` dropped only when `wage_demand` is known, each row gets `"score"` and `"over_budget": bool|null`.
- `staff_roles.json` initial keys and weights (owner-editable): `coach_attacking` {Attacking 3, Technical 2, Tactical 1, Determination 1, Motivating 1}, `coach_defending` {Defending 3, Tactical 2, Technical 1, Determination 1, Motivating 1}, `coach_fitness` {CoachingFitness 3, SportsScience 1, Determination 1, Motivating 1}, `scout` {JudgingPlayerAbility 3, JudgingPlayerPotential 3, Adaptability 1}, `recruitment_analyst` {JudgingPlayerAbility 2, JudgingPlayerPotential 2, AnalysingData 2}, `performance_analyst` {AnalysingData 3, TacticalKnowledge 2}, `physio` {Physiotherapy 3, SportsScience 1}, `sports_scientist` {SportsScience 3, Physiotherapy 1}, `set_piece_coach` {SetPieces 3, Tactical 1}, `director_of_football` {JudgingStaffAbility 2, JudgingPlayerAbility 2, Negotiating 2, PeopleManagement 1}.
- Produces CLI: `fm [--json] staff search --role <key> [--max-wage N] [--max 200] [--top 10]`, `fm [--json] staff slots` (from `club.staff_slots`).

- [ ] **Step 1: Discover** the remaining staff attribute names (goalkeeping coaching, mental coaching, working with youngsters, discipline, man management, tactical knowledge already known) from a staff profile panel's `bind` paths (`ui_dump` with an attribute panel open), and the wage-demand source (a staff person prop such as an expected-wage / contract-demand record, or a column of the search table). If no wage source exists headlessly, `wage_demand` stays `null` and the skill says so; record the outcome. Add found attributes to `staff_roles.json` (goalkeeping coach role when found).
- [ ] **Step 2: Write failing tests** `test_staff.py`: `test_score_weighted_mean` (coach_attacking on fixture → exact expected value), `test_rank_orders_by_score`, `test_rank_drops_only_known_over_budget` (unknown wage kept with `over_budget: null`), `test_role_override_merges` (user file changes one weight only), `test_unknown_role_lists_valid_keys` (raises `ValueError` whose message lists the keys), `test_truncation_flag` (count 5000, max 200 → `truncated` shown in CLI output as `200 of 5000 shown`).
- [ ] **Step 3: Implement** op, `staff.py`, data file, CLI.
- [ ] **Step 4: Run** pytest → pass; live `check_staff.py` (port of spike check: on-screen names ⊆ returned; `max=1000` finishes under the op timeout).
- [ ] **Step 5: Commit** `feat: staff search with role scoring (F11)`.

### Task 8: Player search and scouting knowledge (F6)

**Files:**
- Create: `plugin/src/Ops/Players.cs`, `fm/src/fm_assistant/players.py`, `fm/tests/test_players.py`, `fm/tests/fixtures/player_search.json`, `fm/live/check_players.py`
- Modify: `cli.py`, `doctor.py`, `plugin/src/Game/Nav.cs` (player-search panel id)

**Interfaces:**
- Produces: op `player_search {"max": int}` → `{"count", "returned", "truncated", "rows": [Prospect]}`, `Prospect = {"uid", "name", "age", "position_mask", "club_uid": int|null, "value": Money|null, "asking_price": Money|null, "wage": Money|null, "contract_end": str|null, "attributes": {name: int|str|null}, "scout_rating": str|null}` — attribute values exactly as the UI shows them to the manager.
- Produces (Python): `players.affordable(rows: list, transfer_budget: float, wage_headroom: float) -> list[dict]` (keeps rows whose known `asking_price`/`value` ≤ budget and known `wage` ≤ headroom; unknowns kept and flagged `"budget_unknown": true`); `players.normalize(raw)` adds `position`.
- Produces CLI: `fm [--json] players search [--max 200] [--affordable]`.

- [ ] **Step 1: Discover** the player-search screen (Recruitment → player search / scouting panel id), its table column ids, and how the UI expresses knowledge: compare, for one fully known player and one barely scouted player, the headless `Attribute*` read with the values shown on screen. If headless reads return true values for unknown players, read the knowledge-masked values instead (the binding the UI cells use, found via `ui_dump` `bind` paths, or a knowledge prop) — the op must return what the UI shows.
- [ ] **Step 2: Write failing tests** `test_players.py`: `test_affordable_filters_known_prices`, `test_affordable_keeps_unknown_flagged`, `test_range_values_pass_through` (`"8-12"` stays a string).
- [ ] **Step 3: Implement** op, `players.py`, CLI, nav id.
- [ ] **Step 4: Run** pytest → pass; live `check_players.py` incl. `check_knowledge_parity` (for 5 on-screen rows, every visible attribute cell equals the op's value) and on-screen names ⊆ returned.
- [ ] **Step 5: Commit** `feat: player search respecting scouting knowledge (F6)`.

### Task 9: Training calendar and load (F10)

**Files:**
- Create: `plugin/src/Ops/Training.cs`, `fm/src/fm_assistant/training.py`, `fm/tests/test_training.py`, `fm/tests/fixtures/training.json`, `fm/live/check_training.py`
- Modify: `cli.py`, `doctor.py`

**Interfaces:**
- Produces: op `training` (opens `TrainingScreen` via `nav_open`) → `{"today": "YYYY-MM-DD", "days": [{"index": int, "day_of_month": int, "schedule": str, "sessions": [str, str, str], "match": str|null}]}`; `today` from `game.CurrentGameDate` (decoded GameDate); `match` = opponent short name when a slot holds a match. Port grouping from `spike/plugin/src/Training.cs` (anchors by binding path).
- Produces (Python): `training.assign_dates(day_numbers: list[int], today: date) -> list[date]` — the unique run of consecutive dates containing `today` whose day-of-month sequence equals `day_numbers`; raises `ValueError` if none or more than one; `training.week_load(days: list, squad: list) -> dict` = per ISO week: match count, sessions by category counts, players with `condition` below 85 % or `fatigue` above the threshold recorded in Task 6.
- Produces CLI: `fm [--json] training show [--weeks 2]`, `fm [--json] training load`.

- [ ] **Step 1: Write failing tests** `test_training.py`: `test_assign_dates_month_view` (`[27,28,29,30,31,1,2,…]` with today 2026-08-03 → first date 2026-07-27), `test_assign_dates_ambiguous_raises`, `test_assign_dates_today_missing_raises`, `test_week_load_counts_matches`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** op, `training.py`, CLI.
- [ ] **Step 4: Run** pytest → pass; live `check_training.py`: 42 days × 3 slots equal the screen; dates assigned; no state changed (`training` before == after).
- [ ] **Step 5: Commit** `feat: training calendar and squad load (F10)`.

### Task 10: Claude Code skill and slash commands

**Files:**
- Create: `skills/fm-manager/SKILL.md`, `skills/fm-manager/commands/fm-staff-search.md`, `fm-scout.md`, `fm-training.md`, `skills/fm-manager/settings.example.json`

**Interfaces:**
- Consumes: CLI commands from Tasks 3–9 (always with `--json`).
- Produces: a skill that, per request type, (1) runs `fm --json doctor`-lite (`game status`) first, (2) gathers only the commands it needs, (3) answers in Indonesian with: a ranked table (max 5 rows), the reason per pick tied to concrete numbers, one or two alternatives, budget line, and — since this plan has no actions — "Langkah manual di game:" steps using screen names; never claims to have changed anything. `settings.example.json` allows `Bash(fm --json *)` read commands and denies `Bash(websocat*)`, `Bash(nc *)` (spec §8 deny rule).

- [ ] **Step 1: Write the skill** using superpowers:writing-skills (pressure-test scenarios: no career loaded; unsupported build; wage demand unknown; owner asks to "langsung rekrut saja" → explains it's Phase 2 and gives manual steps).
- [ ] **Step 2: Live dry run** in Claude Code: `/fm-staff-search scout max 5jt/minggu`, `/fm-scout`, `/fm-training` → answers follow the format, cite numbers that match `fm --json` output.
- [ ] **Step 3: Commit** `feat(skill): fm-manager skill with staff, scout, training commands`.

### Task 11: End-to-end smoke and README

**Files:**
- Create: `scripts/smoke.sh`, `README.md`
- Modify: `docs/protocol.md` (final op list)

- [ ] **Step 1: Write `scripts/smoke.sh`**: `fm --json doctor`, then each read command with `--json` piped to `python -m json.tool >/dev/null`; exits non-zero on the first failure and prints which.
- [ ] **Step 2: Run** against the live game → `smoke: all ok` (one line per command, none failing).
- [ ] **Step 3: README** (English): what it does, the read-only status of this release, install steps (loader + plugin + `uv tool install ./fm`), the "back up / actions come in Phase 2" note, unsupported-build behaviour, credits (fm-dof-mcp, cli-anything-fm27, sptndc loader). Product-page polish is Phase 3.
- [ ] **Step 4: Commit** `docs: smoke test and README`.
