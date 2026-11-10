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
| `forbidden` | action op without a valid apply token, or on an untested game build (see "Actions") |
| `precondition` | action op refused before anything was sent (wrong target, board limit, stage); detail says why |
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
| `read` | `ref: person\|club\|team\|path\|persons`, `uid` / `uids[]` or `path`, `props[]`, `wait_ms=4000`, `chain: {prop: [subprops]}`, `ctx: {name: {ref\|path\|int\|bool\|string, uid\|path\|value}}` (binding contexts, see phase 1d), `each: {listprop: [subprops]}`, `max_each=50`, `probe: [names]` | decoded props; unresolved ones under `_missing` | main + polling |
| `ctx_probe` / `tree_probe` | `ref`/`path` + `props[]` / `names[]` | data handler + required binding contexts per name (no channel opened); dev only | main |
| `team_panel_open` | `guid`, `param=team`, `team_uid` | opens a team-scoped screen with its team (`PanelManager.Open(PanelID, param, TeamReference)`; SquadScreen GUID `7957386accba7b44d81ac248d04efbac` + a youth team → `TeamSquadReport`); dev only, UI lock | main + waits |
| `ui_texts` | `panel`, `max=500` | every visible text of an open panel at any depth `[{name, text, x, y, w, h, bind}]` (`ui_dump` stops at depth 40); dev only | main |
| `stars_dump` / `stars_settings` | `panel`, `max` / – | star widgets of an open panel (bound vs drawn values) / the `FMStarRatingSettings` asset's youth and non-youth configurations; dev only | main |
| `profile_info` / `profile_open` | – / `uid`, `kind=player\|nonplayer` | person-link handler's profile PanelIDs; opens a profile the way a person link does (dev only, UI lock) | main + waits |
| `list_rows` | `panel`, `index=0`, `start=0`, `max=200` | `{panel, widgets: [{name, type, item_count, columns}], rows}`; backing data of list/table widgets (all rows, decoded) | main |
| `nav_open` | `panel` (dev only while `~/.fm-assistant/dev-nav` exists: `guid`, or `subtab` = GUID of a visible secondary tab) | `{panel, open: true}`; allowlist: `TrainingScreen`, `SquadScreen`, `ClubScreen`, `ClubAllStaffTool`, `StaffSearchReport`, `PlayerSearchReport`; `wrong-screen` if it did not open | main + waits |
| `load_recent_save` | – | `{clicked: true}`; clicks MainMenu's `LoadMostRecentSave` tile; refuses when a career is loaded | main |

| `club` | – | `{uid, name, balance, financial_status, transfer_budget, wage_budget, wage_committed, wage_remaining, staff_slots, wage_structure}`; see below | main + polling |
| `squad` | `team=first\|reserve\|youth` | `{club, team: {uid, name, kind}, today, count, players: [Player], warnings: [str]}` (`today` = `game.CurrentGameDate`, as in `training`); see below | main + polling |
| `staff_search` | `max=200` (1–1000) | `{count, returned, truncated, rows: [Staff]}`; opens `StaffSearchReport` itself | main + polling |
| `player_search` | `max=200` (1–1000) | `{count, returned, truncated, rows: [Prospect], warnings: [str]}`; opens `PlayerSearchReport` itself | main + polling |
| `training` | – | `{today, days: [Day]}`; opens `TrainingScreen` itself; see below | main + polling |
| `form` | `team=first\|reserve\|youth` | `{today, team: {uid, name, kind}, players: [Form], concerns: [uid], atmosphere: {level, text}\|null}`; see below | main + polling |
| `fixtures` | `n=5` (1–10) | `{today, team_uid, next: Fixture\|null, upcoming: [Fixture], threat, opponent_formation, report}`; see below | main + polling |
| `loans` | – | `{today, out: [Loan], intake: {date, days}, warnings: [str]}`; see below | main + polling |
| `inbox` | `since=null` (`YYYY-MM-DD`), `tab=all\|unread`, `max=50` (1–200) | `{today, unread, items: [Item]}`; headless, no screen; see below | main + polling |
| `tactic` | – | `{name, mentality, slots: [Slot]}` (11 slots); first team's active tactic, headless, read-only; see below | main + polling |
| `ctx_check` | – | `{checked: int, mismatches: [{prop, expected: [ctx], game: [ctx]}]}`; startup check of the binding-context table (`Contexts.cs`) against `Bindings.GetHandler`; no channel opened; see "Binding contexts" | main |

There is no generic click op. Discovery ops are read-only. `prop_check`, `tree` and `read` can reach values the
manager cannot see (hidden attributes), so they answer only in dev mode (file `~/.fm-assistant/dev-nav` exists);
otherwise `bad-request`. UI-driving ops (`nav_open`, `staff_search`, `player_search`, `training`) run one at a
time, and navigate only while the title bar's tab menu (`OverviewTitleBar > MenuBar`) is showing (`wrong-screen`
otherwise: match, press conference, full-screen dialog, main menu). Reads raise `binding-api-changed` when a
required property does not resolve. Read bindings are owned by a scope on the main thread and released on every
path (cancel, throw), by a cleanup job queued after any pending plant job.

Client timeouts: the CLI waits each op's server timeout + 5 s. No answer by then → error code `timeout`; the
plugin's connection limit (HTTP 503) → `busy`. Neither is reported as "game not running".

### Binding contexts

Some props are context-bound: their data handler (`Bindings.GetHandler`) names binding contexts that a panel
normally provides. `Contexts.cs` holds a fixed table (prop → contexts, from `docs/discovery/2026-11-10-phase1d.md`);
`ReadScope.ReadMany` plants the union of the contexts the requested props need as sibling nodes of the parent
(`Reader.PlantOne(..., ctx)`), so they land headless. Values: `team` and `TeamRequestingReport` = `Human.Team`
(always the viewer's team: star ranges and morale are masked by it), `human` = `Human` (a `PersonReference`),
`club` = `Human.Club`, `Boolean` = `false` (true reads the same), `StringType` = `""`, `PortalMessagesTab` = the
inbox tab (supplied by `inbox`).

| source | props | contexts |
|---|---|---|
| person | `Morale`, `MoraleString`, `CurrentAbilityStarRange`, `PotentialAbilityStarRange` | `team`, `human` |
| person | `CanViewHappinessInfo`, `HappinessPlayingTime`, `HappinessClub`, `HappinessManagement`, `HappinessTraining` | `human`, `team` |
| person | `TacticsRoleName` | `team` |
| team | `Tactic` | `Boolean` |
| team | `HasTeamReport` | `TeamRequestingReport` |
| human | `HumanPortalFilteredMessages` | `team`, `StringType`, `PortalMessagesTab` |
| human | `NumberUnreadMessages` | `team` |

`ctx_check` asks `GetHandler` for every row on `Human` (person/human rows) and `Human.Team` (team rows) and lists
each prop whose context set differs (order ignored): `game` is the game's list, or `(unknown-property)` /
`(no-handler)`. `mismatches: []` = the table matches this build. A mismatch means a context was renamed: the
affected props would read `_missing`.

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
`Player = {uid, name, age, position_mask, attributes, stars_raw, condition, fatigue, injured, injury: {description,
return_days}|null, contract: {wage, end_date, length_days, start_date, squad_status, release_clause, renewal_offer}}`.

`AgreedPlayingTime.sort` codes seen live (build 27.0.0.2493426; English meaning inferred from the localized label and the
FM status list, not read from the game): 2 on loan (currently loaned out), 5 emergency backup, 7 youngster,
10 breakthrough prospect, 11 backup (goalkeeper), 13 rotation / fringe player, 19 first-team backup (impact sub),
21 first-choice goalkeeper, 22 regular starter, 23 important player, 24 star player. Other codes (squad player, future
prospect, cup goalkeeper, not needed, trial) exist but were not held by any player in this save.

### Star ranges (stars_raw)

`squad`, `player_search` and `loans` read person props `CurrentAbilityStarRange` and `PotentialAbilityStarRange`
(context-bound, contexts `team` + `human` = the viewer: the game masks them by the manager's knowledge). Each is a
record `{MinValue, MaxValue, IsScoutsOpinion}` on a 0–20 scale, not raw ability.
`stars_raw = {current: {min, max}|null, potential: {min, max}|null}`.
- −1/−1 = not scouted → null (never 0 stars).
- A value outside 0..20 (other than −1/−1), or min > max, is dropped (null) and the result's `warnings` gets
  `"person <uid>: <prop> <min>-<max> outside -1..20, dropped"`. `warnings` is always present (`[]` normally).
- Own players: `current` is `n-n`; `potential` is a range for young players (e.g. 14-16, 18-20) even for own
  players. Partly scouted others read ranges (e.g. 13-14 / 15-20); unknown players −1/−1 (672 of 689 search rows).
- Display mapping (star widget `FMStarRatingTemp`, bindings `starrating.minvalue`/`maxvalue`): drawn half-stars =
  value − 10, i.e. **stars = (value − 10) / 2** (10 = 0, 20 = 5 stars). Verified live on the first-team SquadScreen
  (30 players, 42 widgets, values 13–18, ranges included) and on the U21 squad (`TeamSquadReport`, 5 youth players
  aged 17–21, values 12–17: 12→2, 13→3, 13-15→3-5, 14-16→4-6, 15-17→5-7 half-stars): the youth view uses the same
  mapping. `FMStarRatingSettings.YouthConfig` / `NonYouthConfig` differ only in USS style classes
  (`…-youth-true` / `…-youth-false`), not in numbers. **Values below 10 were not seen** in this save (35 own players,
  689 search rows, the U18 team is empty), so their display is unverified: keep them unmapped.
- Timing: `squad` 30 players ≈ 3.1 s; `player_search` 689 rows ≈ 19.9 s; `loans` ≈ 2.2 s.

### tactic

Headless, read-only (no screen, nothing changed). `Human.Team.Tactic` (context `Boolean` = false) →
`TeamTacticReference`; props `HasTactic`, `CurrentTacticSlot` (0-based; 0 seen), `TacticSlot1Name`…`TacticSlot3Name`
(localized "mentality formation style"; null for an empty slot), `MentalityString` (localized),
`TacticalPositionsCombined` (one record per slot: `TeamSelectionIndex` 0–10, `Player` person ref, `Position`,
`IPPosition`, `OOPPosition`, `IPRole`, `OOPRole`, …). Per slot player: person `Name`, `TacticsRoleName` (context
`team`; localized, the in-possession role as the screen's "IP role" column).
`Slot = {index, position_mask, position_label, role, player: {uid, name}|null}`, exactly 11, in `TeamSelectionIndex`
order (not the screen's top-to-bottom order). `name` = the current slot's `TacticSlot<n>Name`. A slot with no
player: `player: null`, `role: null`; an index missing from the list: all fields null. `HasTactic` false →
`{name: null, mentality: null, slots: []}`.
- `position_mask` = the slot's `Position` (= `IPPosition`; `OOPPosition` can differ, e.g. AM (R) in possession,
  M (R) out of it). It uses the **same bit scheme** as player `Position` (verified live: 11 slots of a 4-2-3-1 DM AM
  wide), but central slots may carry a side modifier for a half-space: `0x100000` (left) / `0x200000` (right).
  `positions.decode` renders those as `D (RC)` / `D (LC)` / `DM (R)` / `DM (L)`, while the tactics screen labels them
  `D (C)` / `DM`. So use `position_label`, not `decode(position_mask)`.
- `position_label`: the screen's slot label, from the mask with the modifiers removed:

  | bit | label | bit | label |
  |---|---|---|---|
  | 1 | GK | 512 | M (L) |
  | 4 | D (R) | 1024 | M (C) |
  | 8 | D (L) | 2048 | AM (R) |
  | 16 (+0x100000/0x200000) | D (C) | 4096 | AM (L) |
  | 32 | WB (R) | 8192 | AM (C) |
  | 64 | WB (L) | 16384, 32768, 65536 | ST (C) |
  | 128 (+0x100000/0x200000) | DM | | |
  | 256 | M (R) | | |

  Every label is one of `fm_assistant.positions.SLOTS`; a mask with none or several of these bits → null. Live check
  (tactics screen `TacticalPlannerTool`, column `StartingXI`): all 11 labels equal the screen's, including the four
  half-space slots (two `D (C)`, two `DM`). Timing ≈ 1.7 s round trip.

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
scout_rating, stars_raw, attributes}`.

### form

Team as in `squad` (`Team.Players`, read in batches of 10). Person props: `Name`, `SeasonStatsList` (one record per
competition: `Competition` comp ref or `NullReference`, `Appearances`, `StartingAppearances`, `SubAppearances`,
`AppearancesForRating`, `AverageRating`), `LastFiveClubMatchesForm` (`LastFiveMatchesRating`,
`LastFiveMatchesListHasValidFixtures`, `LastFiveMatchesList[]` with `MinuteSubOn`/`MinuteSubOff`/`MinuteSentOff`).
Competition names: the record's `Competition` value is planted directly (`Reader.ListField`) once per comp uid, prop
`Name`; a `NullReference` competition (friendlies) is `competition: null`. Team props: `HappinessIssuesPlayers` (person
refs → `concerns`), `ClubAtmosphereFeedback` (`CurrentDynamicSupportLevel` → `atmosphere.level`,
`CurrentDynamicSupportStringShort` (localized) → `atmosphere.text`).
`Form = {uid, name, season: [{competition, apps, starts, subs, rating}], last5: {rating, valid, minutes: [int|null]},
morale: {value, text}|null, happiness: {playing_time, club, management, training}|null}`, each area
`{severity, change, text}|null`.
- `season[].rating` = `AverageRating`, null when `AppearancesForRating` is 0 (never a 0.0 rating).
- `last5.valid` = `LastFiveMatchesListHasValidFixtures` and a non-empty list; `last5.rating` is null when not valid.
- `last5.minutes`, one per listed match (most recent first, as the game lists them): sub on/off 0/0 = 90; a sub-off
  minute ends the stint, else a sending-off minute, else 90; minus the sub-on minute. Unreadable or negative → null.
  Extra time is not counted. There is no season-minutes prop.
- Early season / friendlies only: competitive counters are 0 and `Competition` is null; ratings come from the
  friendlies' records (competition null).
- Morale and happiness (context-bound, contexts `team` + `human` = the viewer): person props `CanViewHappinessInfo`,
  `Morale` (int → `morale.value`), `MoraleString` (localized → `morale.text`), `HappinessPlayingTime`,
  `HappinessClub`, `HappinessManagement`, `HappinessTraining` (records `{Severity, Description, HappinessRecentChange,
  ProsList, ConsList, DetailedString?}` → `{severity, change, text}`; `text` = `Description` with tags removed,
  localized, embeds the player's name). Both `morale` and `happiness` are null unless `CanViewHappinessInfo` is
  `"True"` (other clubs' players read made-up negative `Morale` numbers). `morale` is null when `Morale` did not
  land (never 0); an area that did not land is null.
- Values seen live (build 27.0.0.2493426, first team 30 + reserve 5 players, one game date; youth team empty):
  - `Morale` 9–14: 9 "Cukup Oke", 10 "Oke", 11 "Lumayan Bagus", 12 "Cukup Bagus", 13 "Bagus", 14 "Sangat Bagus"
    (okay → very good; no low morale in this save).
  - `playing_time`, `club`, `management` share one small scale where **lower = happier**: −5 "senang sekali"
    (delighted), −4 "sangat senang" (very happy), −3 "senang" (happy), 0 "puas" (content). Positive values were not
    seen; by the direction of the scale the text turns negative above 0 (inferred, not observed).
  - `training` uses a different, wider scale where **higher = happier**: −32 and −26 "Khawatir" (worried, the only
    negative text seen), −20 … 25 "Puas" (content), 49 "Senang" (happy), 52 "Sangat Bahagia" (very happy); its text
    is a short label (no name). The text turns negative between −20 and −26. −111 with text `"-"` = no training
    data (two reserve players).
  - So no single "severity above X" threshold works for all four areas: per area, unhappy = `severity > 0` for
    playing_time/club/management, `severity < -20` for training (worried seen at −26 and −32, content at −20; fm uses −20 so the unknown −25…−21 band errs toward flagging), and −111 =
    unknown.
  - `change` (`HappinessRecentChange`): −1, 0, 1 seen.

### fixtures

First team (`Club.MainTeam`). Team props: `NextFixture` (`FixtureReference`), `NextMatchOpponent`, `NextMatchLocation`,
`Next5FixturesData` (5 × `{Fixture, Team}`), `NextOppositionThreatLevelAssessment` (localized sentence → `threat`;
null when empty or no next fixture), and for `n` > 5 `RemainingLeagueFixtures` (`{Fixture, Team}` records, league
only). A `FixtureReference` inside a list record has no uid, so the op plants on each record's `Fixture` value
directly (`Reader.ListField`) and reads `FixtureDate`, `HomeTeam`, `AwayTeam`, `Competition` (→ comp `Name`, planted on
the comp value once per comp uid). Opponent names: team `Name`; `opponent_formation` = the next opponent's
`MostUsedFormation` (localized, as the game shows it; never used for advice).
`Fixture = {date, opponent: {uid, name}, home, competition}`.
- `home`: own team uid == `HomeTeam` → true, == `AwayTeam` → false, neither → null (the opponent then comes from the
  record's `Team` / `NextMatchOpponent`). For `next` only: when `NextMatchLocation` disagrees with that comparison
  (1 = home is the only value seen) `home` is null (e.g. a neutral venue).
- `upcoming`: the next fixtures, date ascending, `date` ≥ `today`, deduplicated by (date, opponent), at most `n`;
  `upcoming[0]` equals `next` when both exist. Beyond the fifth fixture only league fixtures are known (cup ties after
  the fifth are missing).
- No next fixture: `next: null`, `threat: null`, `opponent_formation: null`, `report: null`.
- `report`: the next opponent's `HasTeamReport` (context `TeamRequestingReport` = `Human.Team`) → bool: true when
  the recruitment team has an opposition report on that team. Reading it does not request a report.

### inbox

Headless (no screen opened). `Human.HumanPortalFilteredMessages` with contexts `team`, `StringType` = `""`,
`PortalMessagesTab` = `0` (`tab=all`) or `3` (`tab=unread`) → `NewsItemReference` values, newest first (the
portal's window, about three weeks); `Human.NumberUnreadMessages` (context `team`) → `unread`. The first `max`
elements are planted directly (no context) for `NewsItemId`, `Date`, `NewsItemTimeSent`, `NewsItemHasBeenRead`,
`NewsItemIsImportant`, `MediaNewsCategory`, `NewsTitleString`, `NewsBodyString`.
`Item = {id, date, time, read, important, category, title, body}`.
- `id` is not monotonic (do not order by it); `category` = `MediaNewsCategory` (int, language-neutral; 0, 1, 2 seen).
- `title`/`body`: localized, markup tags removed; `body` is cut to 600 characters.
- `since`: items stop at the first one whose `date` is before `since` (the list is date-descending). A `since` after
  every item, or an empty tab, gives `items: []` with `unread` still set.
- Reading does not mark anything read. Timing: 75 items ≈ 1.6 s round trip.

### loans

Club props (`Human.Club`): `PlayersOutOnLoan` (person refs; required), `IntakeDate` → `intake.date`,
`DaysUntilYouthIntake` → `intake.days`. Per loanee (batches of 10; none read when the list is empty): `Name`, `Age`,
`LoanClub` (club ref → `club: {uid, name}`, name = club `Name`), `LoanContract` → `StartDate`, `EndDate`,
`LoanAppearances` → `apps`, `LoanAverageRating` → `rating` (null when `apps` is 0, never 0.0), `LoanHappiness` (int),
`LoanReport` → `AgreedPlayingTime` / `ActualPlayingTime` (localized strings, display only; `"-"` or empty → null).
`Loan = {uid, name, age, club: {uid, name}, start_date, end_date, apps, rating, happiness, agreed_time, actual_time,
stars_raw}`.
`LoanClub` is not a test for "out on loan" (it reads the own club for players at home); the list is the source.
Loanees also stay in their team's `Players` (seen in the reserve team, squad status code 2).

### training

Month view of `TrainingScreen` (35 or 42 days, Monday first). Each day = one `EventsList` widget (backing rows:
`EventType` 1000 = session with `SessionName` (localized), `SessionType` (int, language-neutral), `DayIndex`
(weekday 0–6), `SessionIndex`; 1001 = match with `TeamOpponent` → team `AbbreviatedName`), paired in screen order
with the day headers (binding `day.DayOfTheMonth`, e.g. `31 Agu`, `1 Sep`, `2`) and week schedule names
(`week.TrainingScheduleName`, one per row of 7). `today` = `game.CurrentGameDate`.
`Day = {index, day_label, day_of_month, weekday, schedule, sessions[3], session_types[3], match}`; a match slot is
`null` in `sessions`/`session_types`. The view is the month the screen shows (normally today's month), so days
after its last week are not included.

## Actions

Action ops change the career (in memory; nothing is saved). They are gated:

- Tested game build only (`hello.tested_builds`), else `forbidden` "actions are disabled on untested build X".
- `apply_token`: 32 lowercase hex chars naming a file `~/.fm-assistant/apply/<token>` written by `fm apply`
  (content `{"plan_id", "index", "kind"}`). The plugin consumes it before acting (rename to `.used`, read, delete),
  so a token works once. Missing, malformed, unknown or reused token → `forbidden`. A token whose `kind` belongs to
  another op → `forbidden` "apply token was written for <kind>, not <op>".
- Kinds → ops: `staff.approach` `act_staff_approach`, `staff.offer` `act_staff_offer`, `shortlist.add`
  `act_shortlist_add`, `shortlist.remove` `act_shortlist_remove`, `scout.request_report` `act_scout_request`,
  `training.set_sessions` `act_training_sessions`, `training.set_focus` `act_training_focus`,
  `contract.open_renewal` `act_contract_open`, `contract.offer_renewal` `act_contract_offer`.
- Every action op holds the UI lock and needs a loaded career.

Person actions run through the person's profile (opened like a person link; the op waits until the profile shows
the uid). The action is an allow-listed `ActionEntry` of the profile's secondary tabs, performed with
`PluginContextActionsModule.HandleActionEvent`; the entry's `ActionData` must name the target person, else
`ui-element-missing`. Allow-list (action ids): approach to sign `1749837424`, offer contract `2000111204`, shortlist
add `1097488485`, shortlist remove `1500280650`, assign scout `1363818831`. Entries that ask for confirmation get
the game's `GenericModalDialog` primary button; on any error after the dialog opened it is cancelled.
Negotiation buttons are the screen's speak-to buttons, clicked only when the button at the action's position shows
that action's own title (`ContractEditSession.SpeakTo.Actions`, events: 20 propose, 41 finalize, 140 negotiate
contract after promises).

| op | args | result | timing |
|---|---|---|---|
| `negotiation` | `uid` | Negotiation (below); read-only, not gated | ~1.3 s |
| `act_shortlist_add` | `uid`, `months=0` (0 = indefinite, 1, 3, 6, 12) | `{verified, before: {shortlisted, count}, after, performed, answer?}`; `answer: "already"` when nothing was needed | ~10 s |
| `act_shortlist_remove` | `uid` | same shape; confirms the game's dialog | ~13 s |
| `act_scout_request` | `uid`, `scout_uid`, `duration=week\|month\|full` | `{verified, answer: "pending"\|"already", before: {being_scouted}, after, performed}`; the scout must be one the action lists | ~10 s |
| `act_staff_approach` | `uid` (non-player) | `{verified, negotiation, demand: {job, wage, end_date}}`; the prefilled terms are the demand | ~10–13 s |
| `act_staff_offer` | `uid`, `wage` (base currency) | `{verified, offered: {wage, job, event}, answer, counter, patience, before, after}` | ~19 s |

Op details:

- `act_staff_offer` needs the person's negotiation on screen (`act_staff_approach` first) and not read-only. `wage`
  above the board maximum → `precondition` "wage X exceeds the board maximum Y; nothing sent". The job stays as
  prefilled; the wage is stepped with the screen's `-`/`+` to the largest step ≤ `wage`. One offer (propose, or
  finalize when the terms equal the demand). `answer`: `accepted` (now employed by the human club), `rejected`
  (patience 0, or the screen closed without read-only), `countered` (the reply rewrote the wage or the base terms;
  `counter` has the new terms), `pending` (read-only). A counter is never answered.

Negotiation = `{open, on_screen, stage, wage, job, end_date, board_max_wage, wage_over_board_max, patience: {status,
value}, changed_by_other_party, read_only, key_info: [text]}`, read headless from `Person.ContractEditSession`
(contexts `human`, `BuyingClub`). The game computes a session for anyone (the terms it would offer), so `open` =
the negotiation screen shows this person, or the session carries a reply (changed by the other party, patience
status set, read-only). `stage` = `promises`/`contract` from the screen when on screen; off screen an open session
is `contract`; null when not open. `job` = job group (`recruitment`/`coaching`/`medical`, null for players).
`board_max_wage` = the largest step of the wage step list (above it the game disables `+` and sets
`wage_over_board_max`). `end_date` = `YYYY-MM-DD`.

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

## Discovery notes (phase 2)

Details: `docs/discovery/2026-11-10-phase2.md`.
- Person actions (approach, offer contract, shortlist, scout) are `ActionEntry` rows in the profile's secondary tabs;
  perform with `FM.Game.PluginContextActionsModule.HandleActionEvent(id, Event, ActionReference, ActionData, true, null)`.
  Allow-list action ids: own-player profiles also carry release / termination.
- Negotiations: `Person.ContractEditSession` (contexts `human`, `BuyingClub`) reads headless; the prefilled terms are
  the demand. `Estimated*` have no handler anywhere. Popups/dropdowns live under the UI root's `FloatingElement`.

## Discovery notes (phase 1d)

- Never run il2cpp reflection `FieldInfo.GetValue` over a UI element's fields (tried on an `FMStarRatingTemp`
  widget): the game died (native crash). `stars_settings` reads only the `FMStarRatingSettings` ScriptableObject.

Details: `docs/discovery/2026-11-10-phase1d.md`.
- "Context-bound" props need named binding contexts (`Bindings.GetHandler`'s `outRequiredContext`, e.g. `team` +
  `human` for `Morale` and star ranges). `Reader.PlantOne(..., ctx)` plants them as sibling nodes of the parent;
  they then land headless in ~1.2 s.
- Inbox: `Human.HumanPortalFilteredMessages` with contexts `team`, `StringType`, `PortalMessagesTab` (0 all,
  1 new, 2 tasks, 3 unread), no screen needed.
- Profiles: `PanelManager.Open(profile PanelID, "player"|"person", PersonReference)`; `Estimated*` wage demands
  have no handler outside the negotiation flow.

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
