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
| `nav_open` | `panel` (dev only while `~/.fm-assistant/dev-nav` exists: `guid`, or `subtab` = GUID of a visible secondary tab) | `{panel, open: true}`; allowlist: `TrainingScreen`, `SquadScreen`, `ClubScreen`, `ClubAllStaffTool`, `StaffSearchReport`, `PlayerSearchReport`; `wrong-screen` if it did not open | main + waits |
| `load_recent_save` | – | `{clicked: true}`; clicks MainMenu's `LoadMostRecentSave` tile; refuses when a career is loaded | main |

| `club` | – | `{uid, name, balance, financial_status, transfer_budget, wage_budget, wage_committed, wage_remaining, staff_slots, wage_structure}`; see below | main + polling |
| `squad` | `team=first\|reserve\|youth` | `{club, team: {uid, name, kind}, today, count, players: [Player]}` (`today` = `game.CurrentGameDate`, as in `training`); see below | main + polling |
| `staff_search` | `max=200` (1–1000) | `{count, returned, truncated, rows: [Staff]}`; opens `StaffSearchReport` itself | main + polling |
| `player_search` | `max=200` (1–1000) | `{count, returned, truncated, rows: [Prospect]}`; opens `PlayerSearchReport` itself | main + polling |
| `training` | – | `{today, days: [Day]}`; opens `TrainingScreen` itself; see below | main + polling |

There is no generic click op. Discovery ops are read-only. `prop_check`, `tree` and `read` can reach values the
manager cannot see (hidden attributes), so they answer only in dev mode (file `~/.fm-assistant/dev-nav` exists);
otherwise `bad-request`. UI-driving ops (`nav_open`, `staff_search`, `player_search`, `training`) run one at a
time, and navigate only while the title bar's tab menu (`OverviewTitleBar > MenuBar`) is showing (`wrong-screen`
otherwise: match, press conference, full-screen dialog, main menu). Reads raise `binding-api-changed` when a
required property does not resolve. Read bindings are owned by a scope on the main thread and released on every
path (cancel, throw), by a cleanup job queued after any pending plant job.

Client timeouts: the CLI waits each op's server timeout + 5 s. No answer by then → error code `timeout`; the
plugin's connection limit (HTTP 503) → `busy`. Neither is reported as "game not running".

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
`WagesData.PlayerTypeWageData` (required) → `wage_structure: [{status, count, average, highest, lowest, advised_max, total, over}]`,
one row per squad status in the game's order: `status` = `Name` (localized), `count` = `Quantity`, `average`/`highest`/
`lowest`/`advised_max` = `AverageBasicWage`/`HighestBasicWage`/`LowestBasicWage`/`AdvisedMaxBasicWage` (display strings
only, the game gives no number), `total` = `{display: TotalBasicWage, value: TotalBasicWageValue}` (base currency),
`over` = `IsOverWages`. 17 rows on build 27.0.0.2493426, rows with `count` 0 included (their strings are a placeholder
minimum, `total.value` 0). Two rows can share a `status` display (emergency backup, outfield and goalkeeper), and the
last row is the overall total (all statuses; `count` = whole squad), not a status.
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
`FullContract` → `Wage` (`{display, sort}` → Money), `EndDate`, `ContractLength` (total contract length in days, start → end; NOT days left — use `EndDate`),
`StartDate`, `AgreedPlayingTime` (squad status `{display, sort}` → `squad_status: {display, code}`; `display` localized,
logic uses `code`), `MinimumFeeReleaseClauseValue` (`{display, sort}` → Money; `sort` 0 / display `"-"` = none →
`release_clause: null`), `HasRenewalOffer` (→ `renewal_offer` bool|null).
`Player = {uid, name, age, position_mask, attributes, condition, fatigue, injured, injury: {description,
return_days}|null, contract: {wage, end_date, length_days, start_date, squad_status, release_clause, renewal_offer}}`.

`AgreedPlayingTime.sort` codes seen live (build 27.0.0.2493426; English meaning inferred from the localized label and the
FM status list, not read from the game): 2 on loan (currently loaned out), 5 emergency backup, 7 youngster,
10 breakthrough prospect, 11 backup (goalkeeper), 13 rotation / fringe player, 19 first-team backup (impact sub),
21 first-choice goalkeeper, 22 regular starter, 23 important player, 24 star player. Other codes (squad player, future
prospect, cup goalkeeper, not needed, trial) exist but were not held by any player in this save.

### staff_search

Rows = every backing row of `StaffSearchReport > nonplayertable` (person refs, the table's current filter), read in
batches of 20 (166 rows ≈ 5 s). Props: `Name`, `Age`, `Club` (null = free agent), `PreferredJob` (`JobString`,
`JobType`), `FullContract.Wage` (→ `current_wage`, null when 0/"T/A"), and staff attributes without prefix:
`Attacking, Defending, Tactical, Technical, SetPieces, CoachingFitness, GoalkeepingCoaching, WorkingWithYoungster,
TacticalKnowledge, JudgingPlayerAbility, JudgingPlayerPotential, JudgingStaffAbility, PeopleManagement, Motivating,
Adaptability, Determination, Authority, Physiotherapy, SportsScience, Negotiating, AnalysingData`.
`Authority` is assumed to be the profile's level of discipline. Not found: mental coaching (tried ~30 names).
Wage demand: no person property found (`WageDemand`, `ExpectedWage`, `ContractDemand`, … unknown), so
`wage_demand` is always null; the demand only appears in the contract-offer flow (Phase 2).
`Staff = {uid, name, age, club_uid, preferred_job, preferred_job_type, attributes, current_wage, wage_demand}`.

### player_search

Rows = every backing row of `PlayerSearchReport > playertable` (the screen's current filter; 689 rows ≈ 19 s).
Person props: `Name`, `Age`, `Position`, `Club`, `ScoutRecommendation` (→ `scout_rating`), the 47 visible
`Attribute*` names of `squad`, `FullContract` → `Wage` (display may be a range, `sort` = low end), `EndDate`,
and `TransferValueRange` (`TransferValueRangeString` → `value.display`, `TransferValueRangeMaxValue` → `value.value`,
`AskingPrice` (> 0 → `asking_price`), `ScoutingKnowledgeLevel` → `value_knowledge {level, max, text}`).
Knowledge: headless attribute reads already apply the game's masking — `"-"` (unknown), `"6-10"` (range), int
(known) — so the op returns what the manager may know. `value_knowledge` is the knowledge of the transfer value,
not the table's knowledge column (whose source is not identified; it read "none" for players whose value
knowledge was "known").
`Prospect = {uid, name, age, position_mask, club_uid, value, asking_price, wage, contract_end, value_knowledge,
scout_rating, attributes}`.

### training

Month view of `TrainingScreen` (35 or 42 days, Monday first). Each day = one `EventsList` widget (backing rows:
`EventType` 1000 = session with `SessionName` (localized), `SessionType` (int, language-neutral), `DayIndex`
(weekday 0–6), `SessionIndex`; 1001 = match with `TeamOpponent` → team `AbbreviatedName`), paired in screen order
with the day headers (binding `day.DayOfTheMonth`, e.g. `31 Agu`, `1 Sep`, `2`) and week schedule names
(`week.TrainingScheduleName`, one per row of 7). `today` = `game.CurrentGameDate`.
`Day = {index, day_label, day_of_month, weekday, schedule, sessions[3], session_types[3], match}`; a match slot is
`null` in `sessions`/`session_types`. The view is the month the screen shows (normally today's month), so days
after its last week are not included.

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
   - `PlayerSearchReport`: `RecruitmentButton` (opens `RecruitmentScreen`) → GUID `bfe5117deac3c454f8970018733ac664`
     ("player database").
   Primary tabs in `MenuBar`: `PortalButton`, `SquadButton`, `ClubTacticsButton`, `RecruitmentButton`,
   `TrainingButton`, `ClubButton`.
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

## Discovery notes (phase 1c)

Details: `docs/discovery/2026-11-10-phase1c.md`.
- Property names can be harvested from `il2cpp_data/Metadata/global-metadata.dat` (concatenated, sorted
  literals) and validated in bulk with `prop_check`.
- Two classes of props: headless (land on `read`'s planted root) and context-bound (exist in `prop_check`,
  never land headless: `Team.Tactic`, `Human*` inbox lists, `NumberUnreadMessages`, per-player `Morale` /
  `Happiness*`, star ratings, `Estimated*Demands`, `IsWillingToEnterNegotiations`, `HasTeamReport`).
  Context-bound values can be read via `read {ref: "path"}` on a panel's own node while that panel is open.
- Panel nodes at the tree root are `<PanelId or PanelID GUID><hex counter>`; the counter changes each time
  the panel opens, so find nodes by walking, never by fixed path.
- Headless finds: news item fields on `NewsItemReference`; `SeasonStatsList`, `LastFiveClubMatchesForm`;
  `FullContract.AgreedPlayingTime` (squad status), `FullContract.MinimumFeeReleaseClauseValue`,
  `FullContract.ContractClauses`; `Club.WagesData.PlayerTypeWageData`; `Club.PlayersOutOnLoan`,
  `Club.IntakeDate`; person `LoanClub`, `OnLoanFrom`, `LoanContract`, `Loan*` stats; team `NextFixture`
  (`FixtureDate`, `HomeTeam`, `AwayTeam`, `Competition`), `Next5FixturesData`, `RemainingLeagueFixtures`,
  `Team.HappinessIssuesPlayers`, `Team.ClubAtmosphereFeedback`.
- Primary tab `ClubTacticsButton` opens `TacticalPlannerTool`; its `Tactic` node holds
  `TacticalPositionsCombined` (11 slots: player, IP/OOP position and role bitmasks).
