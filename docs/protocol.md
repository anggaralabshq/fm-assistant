# FM Assistant plugin protocol v1

JSON text frames over a WebSocket at `ws://127.0.0.1:<port>/`. One request per connection is fine; the
client opens a connection per call.

## Session file

The plugin writes `~/.fm-assistant/session.json` (mode 0600, atomic temp + rename) when it starts:

```json
{"port": 7788, "token": "<64 hex chars>", "pid": 12345, "plugin_version": "0.1.0", "game_build": "27.0.0.2493426"}
```

A new token is generated on every game start. Clients re-read the file on every call. A session file whose
`pid` is not running is stale (the game exited).

## Request / response

```json
{"v": 1, "id": "<string>", "op": "<name>", "args": {}, "token": "<token>"}
{"v": 1, "id": "<same id>", "ok": true, "result": <any>}
{"v": 1, "id": "<same id>", "ok": false, "error": {"code": "<code>", "detail": "<text>"}}
```

Rules enforced by the plugin:
- Listens on `127.0.0.1` only. A handshake carrying an `Origin` header gets HTTP 403 (blocks browser pages).
- Every request must carry the session token, else `unauthorized`.
- Messages over 256 KB close the socket with status 1009. At most 4 concurrent connections.
- A missing or non-string `id`, or non-object `args` → `bad-request`.

## Error codes

| code | meaning |
|---|---|
| `unauthorized` | token missing or wrong |
| `bad-request` | malformed request or arguments |
| `unknown-op` | op not registered |
| `bindings-not-captured` | game still starting |
| `no-career-loaded` | op needs a loaded career |
| `wrong-screen` | op needs a screen that is not open (or did not open) |
| `ui-element-missing` | an expected UI element was not found |
| `main-thread-timeout` | the game's main thread did not run the job before its deadline |
| `binding-api-changed` | a game API the plugin relies on is missing (likely a game update) |
| `internal` | anything else; detail has the exception message |

## Ops

| op | args | result | thread |
|---|---|---|---|
| `hello` | – | `{plugin, plugin_version, protocol, game_build, build_supported, tested_builds[], bindings_captured, career_loaded, human_club_uid}` | main |
| `diag` | – | `{ticks, last_tick_ms_ago, queued, sources: {tick source: count}, bindings_captured, ops: {sha, loaded_at, loads, error}}`; answered without the main thread | WS |
| `dev_reload` | – | `{loaded, ops, message}`; re-reads the ops assembly from the plugin folder (no game restart) | WS |
| `panels` | – | `[{panel_id, instance, w, h}]`, top-most last | main |
| `ui_dump` | `panel?`, `depth=12`, `max=400` | visible element tree `{name, type, text, bind, x, y, w, h, children}` | main |
| `prop_check` | `names[]` | `{name: property id}`; 0 = unknown in this build | main |
| `tree` | `path=""`, `depth=2`, `max=400` | binding tree `{name, type, value, children}` | main |
| `read` | `ref: person\|club\|team\|path`, `uid` or `path`, `props[]`, `wait_ms=4000`, `chain: {prop: [subprops]}` | decoded props; unresolved ones under `_missing` | main + polling |
| `list_rows` | `panel`, `index=0`, `start=0`, `max=200` | `{panel, widgets: [{name, type, item_count, columns}], rows}`; backing data of list/table widgets (all rows, decoded) | main |
| `nav_open` | `panel` (dev only while `~/.fm-assistant/dev-nav` exists: `guid`, or `subtab` = GUID of a visible secondary tab) | `{panel, open: true}`; allowlist: `TrainingScreen`, `SquadScreen`, `ClubScreen`, `ClubAllStaffTool`, `StaffSearchReport`; `wrong-screen` if it did not open | main + waits |
| `load_recent_save` | – | `{clicked: true}`; clicks MainMenu's `LoadMostRecentSave` tile; refuses when a career is loaded | main |

| `club` | – | `{uid, name, balance, financial_status, transfer_budget, wage_budget, wage_committed, wage_remaining, staff_slots}`; see below | main + polling |
| `squad` | `team=first\|reserve\|youth` | `{club, team: {uid, name, kind}, count, players: [Player]}`; see below | main + polling |

There is no generic click op. Discovery ops are read-only.

### Money

`Money = {"display": str, "value": number}`. `value` is the game's base-currency number (what the props hold);
`display` is the game's own formatter `SI.Bindable.BindableTranslationUtils.FormatCashValue(value)` in the owner's
chosen currency (e.g. `Rp5,71M`). Screens may round the last digit differently (`Rp364Jt` vs a tile's `Rp365Jt`).

### club

Human club (`Human.Club` uid) props: `TransferBudget`, `WageBudget` (per week), `CommittedWageSpending`,
`RemainingWageBudget` (= budget − committed), `OverallBalance` (ClubScreen "overall balance"),
`FinancialStatus` (`{display, sort}`), `MainTeam`. Staff slots from the main team's `StaffCoachingSubGroup`,
`StaffRecruitmentSubGroup`, `StaffMedicalSubGroup`: `Count` → `used`, `MaxValue` → `max` (the board's target;
`used > max` happens), `ShortString` → `summary`, `StaffSubGroupCountFeedbackString` → `board_feedback`,
`StaffSubGroupJobsData[]` → `jobs: [{job, job_type, used, max}]`.
Known gap: the ClubScreen "transfer/wage budget" tile showed Rp5,75M while `TransferBudget` formats to Rp5,71M
(build 27.0.0.2493426); the tile's source is a VisualFunction not identified yet. Finance (`Keuangan`) is a
secondary-tab dropdown (`SecondaryTabDropdownButton`, no SIButton), not reachable by `ClickSubtab` yet.

### squad

Teams: club props `MainTeam` (first), `HighestLevelYouthTeam` (reserve, e.g. U21), `YouthTeam` (e.g. U18; may be
empty). `Team.Players` → person refs, read in batches of 10. Player props: `Name`, `Age`, `Position` (position bit
mask, multi-position; decoded by `fm_assistant.positions`), `Condition` (percent, 0–100), `Fatigue` (signed; fresh
players read about −360…−270 on build 27.0.0.2493426, higher = more tired; no threshold used yet), `IsInjured`
(`"True"`/`"False"`), `CurrentInjury` (`InjuryDescription`, `InjuryReturnDays`), visible `Attribute*` (47 names, see
`Squad.Attributes`; off the ball is `AttributeMovement`; hidden personality attributes are never requested),
`FullContract` → `Wage` (`{display, sort}` → Money), `EndDate`, `ContractLength` (days left).
`Player = {uid, name, age, position_mask, attributes, condition, fatigue, injured, injury: {description,
return_days}|null, contract: {wage, end_date, length_days}}`.

## Navigation routes (nav_open)

Never by visible text (the owner's UI is Indonesian):

1. PanelID asset already loaded (`Resources.FindObjectsOfTypeAll<PanelID>()` by name) → `PanelManager.Open(PanelID)`.
   Works for `TrainingScreen`, `SquadScreen`, `ClubScreen` (data-bound).
2. Screens that need the game's navigation context: click the primary tab container by element name inside
   `OverviewTitleBar > MenuBar` (`ClubButton`; a club-badge SIButton outside MenuBar has the same name), then the
   secondary tab whose backing row has `RowData.Value` == the screen's PanelID GUID (rendered item matched by
   order and checked against the row's own `SubtabText`), then optionally a tile by element name.
   - `ClubAllStaffTool`: `ClubButton` → GUID `9ba550b513bf5144da547e7d87df80da`.
   - `StaffSearchReport`: as above, then tile `StaffSearch`.
   Opening these by GUID directly (`PanelManager.Open(AssetReferenceT<PanelID>)`) shows an empty panel (no context).
   Looking up Addressables keys from the resource locators crashed the game (SIGSEGV) — do not.

## Plugin layout and hot reload

- Host `FmAssistant.dll` (BepInEx plugin): server, session, tick hooks, main-thread queue, ops loader. Changing it
  needs a game restart.
- Ops `FmAssistant.Ops.ops` (the `FmAssistant.Ops` assembly, not named `.dll` so BepInEx ignores it): every op except
  `diag`/`dev_reload`. Loaded from bytes into its own AssemblyLoadContext; `plugin/build.sh` installs it and calls
  `dev_reload`, so op changes apply in seconds without a restart.
- Main-thread code never formats an exception's stack trace (`e.ToString()`): CoreCLR's stack walk through IL2CPP
  frames crashes in libunwind (Phase 0 "startup crash" signature).
- Tick sources: `UIElementsRuntimeUtility.RepaintPanels`, `PanelManager.Tick`, `Bindings.Update` prefixes, main
  thread only (one launch got no RepaintPanels prefix calls at all).
