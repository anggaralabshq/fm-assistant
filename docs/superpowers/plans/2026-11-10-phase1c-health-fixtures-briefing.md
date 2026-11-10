# Phase 1c: Contracts, Form, Fixtures, Loans, Briefing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The rest of Phase 1's read features that the game exposes headless:
- contract advisor data (F5);
- season and recent form plus squad concerns (F2);
- next fixtures and the assistant's threat note (F8);
- loans out and the youth intake (F7);
- a session briefing that combines everything (F1-lite).

**Architecture:**
- The ops (hot reload, `bash plugin/build.sh`, no game restart) read only the props that `docs/discovery/2026-11-10-phase1c.md` marks as landing headless. Python normalizes and composes; the CLI follows the Phase 1a/1b pattern.
- Out of scope, for Phase 1d: the inbox list, the active tactic / role fit (F3), morale, star ratings and wage demands. They are context-bound and need a screen-context read or a profile route.

**Tech Stack:** Python 3.12+ (click, pytest, uv); C# ops assembly (hot reload).

**Spec:** `docs/superpowers/specs/2026-11-07-fm-assistant-manager-design.md` (§6 F1, F2, F5, F7, F8; §3 non-goals). Data sources: `docs/discovery/2026-11-10-phase1c.md`. Field conventions: `docs/protocol.md`.

## Global Constraints

- Phase 1a/1b Global Constraints hold: read-only, never save/Continue/match, invented fixture names, no game data in the repo, unexpected shapes surface as the CLI's `internal` error.
- Ops request only props listed as landing headless in the discovery doc. A missing prop costs `wait_ms`.
- Localized strings (`…String`, `display`) are for display only; logic uses ints/`sort` codes/dates.
- Hidden values (`*PotentialAbility*`, `Debug*`) are never requested (spec §6).
- No tactics advice: `opponent_formation` is reported as the game shows it, nothing is recommended from it.
- Branch `phase1c` off `phase1b`. Owner's standing approval: execute without check-ins; report at phase end.

## Review Focus

1. Early season: every season counter is 0 and `LastFiveMatchesListHasValidFixtures` is false. Form must then read "no matches yet" (`rating: null`), never a 0.0 rating ranked as bad form. (Task 2 `test_form_no_matches_is_null_not_zero`.)
2. No next fixture (end of season, or cup-only gaps): `next: null`, an empty `upcoming`, and a briefing line "no fixture scheduled". No crash. (Task 3 `test_fixtures_none_scheduled`; Task 5 `test_briefing_without_fixture`.)
3. `NextMatchLocation` value other than 1, or own team not in `HomeTeam`/`AwayTeam`: `home: null`, not a guess. (Task 3 `test_home_unknown_location`.)
4. A release clause `sort` 0 / `display "-"` is `release_clause: null`, never `Rp0`. (Task 1 `test_release_clause_none`.)
5. Club with no players out on loan: `out: []` and the text says "none", with no per-player reads issued. (Task 4 `test_no_loans`.)

---

### Task 1: Contract details and wage structure (F5)

**Files:**
- Modify: `plugin/src/Ops/Squad.cs` (more `FullContract` props), `plugin/src/Ops/Club.cs` (`WagesData`), `docs/protocol.md`, `fm/tests/fixtures/squad.json`, `fm/tests/fixtures/club.json`, `fm/src/fm_assistant/cli.py`
- Create: `fm/src/fm_assistant/contracts.py`, `fm/tests/test_contracts.py`, `fm/live/check_contracts.py`

**Interfaces:**
- Produces (op `squad`): each `contract` gains:
  - `start_date`;
  - `squad_status: {display, code}`, from `AgreedPlayingTime` `{display, sort}`;
  - `release_clause: Money|null`, from `MinimumFeeReleaseClauseValue`; null when `sort` is 0;
  - `renewal_offer: bool|null`, from `HasRenewalOffer`.
- Produces (op `club`): `wage_structure: [{status, count, average, highest, lowest, advised_max, total: Money, over: bool|null}]`, from `WagesData.PlayerTypeWageData`.
  - `total` is `{display: TotalBasicWage, value: TotalBasicWageValue}`.
  - The other money fields stay display strings, because the game gives no value for them.
- Produces (Python): `contracts.table(players: list, structure: list, today: date) -> list[dict]` returns `[{uid, name, age, squad_status, end_date, days_left, wage, release_clause, renewal_offer, advised_max}]`.
  - Sorted by `end_date`; a missing end date sorts last.
  - `advised_max` is the structure row whose `status` equals `squad_status.display`, or null.
- Produces CLI: `fm [--json] squad contracts [--team first]` → `{today, players: [...], wage_structure}`. The text prints two tables.

- [ ] **Step 1: Write the failing tests** in `test_contracts.py`:
  - `test_table_sorted_by_end_date_missing_last`;
  - `test_release_clause_none` (sort 0 → null);
  - `test_advised_max_matched_by_status_display`;
  - `test_days_left_from_today`.
  - CLI test `test_squad_contracts_json_shape` (with `fake_calls` from `test_cli`).
- [ ] **Step 2: Run** `cd fm && uv run pytest -q tests/test_contracts.py`. Expected: FAIL (ImportError).
- [ ] **Step 3: Implement.**
  - Ops: request only `AgreedPlayingTime`, `MinimumFeeReleaseClauseValue`, `StartDate`, `HasRenewalOffer` (in addition to the existing ones), and `WagesData` on the club. Use `Reader.Require` on `WagesData`.
  - Then `contracts.py` and the CLI.
  - Record the `AgreedPlayingTime.sort` codes seen live in `docs/protocol.md` (codes, not names).
- [ ] **Step 4: Run** `uv run pytest -q` → pass. Then `bash plugin/build.sh` → "Reloaded ops". Then `uv run python fm/live/check_contracts.py`. Expected `OK`:
  - every squad player has `squad_status.code` as an int;
  - `wage_structure` has ≥ 1 row;
  - each `total.value` is a number;
  - `squad` still reads in under 30 s.
- [ ] **Step 5: Commit** `feat: contract details and wage structure (F5)`.

### Task 2: Season and recent form, squad concerns (F2)

**Files:**
- Create: `plugin/src/Ops/Form.cs`, `fm/src/fm_assistant/form.py`, `fm/tests/test_form.py`, `fm/tests/fixtures/form.json`, `fm/live/check_form.py`
- Modify: `plugin/src/OpsEntry.cs` (register `form`, timeout 90), `fm/src/fm_assistant/client.py` (`OP_TIMEOUTS["form"] = 90`), `docs/protocol.md`, `fm/src/fm_assistant/cli.py`

**Interfaces:**
- Produces (op `form`, `team=first|reserve|youth`): `{today, team, players: [Form], concerns: [uid], atmosphere: {level: int, text}}`.
  - Each `Form` is `{uid, name, season: [{competition, apps, starts, subs, rating}], last5: {rating, valid, minutes: [int|null]}}`.
  - `season` comes from `SeasonStatsList`. `competition` is the comp's `Name` or null.
  - `last5` comes from `LastFiveClubMatchesForm`. Minutes per match come from `MinuteSubOn`/`MinuteSubOff`: 0/0 means 90, and an unknown value is null.
  - `concerns` comes from `Team.HappinessIssuesPlayers`; `atmosphere` from `Team.ClubAtmosphereFeedback`.
  - Players are read in batches of 10, like `squad`.
- Produces (Python):
  - `form.summary(form: dict) -> list[dict]` returns `[{uid, name, apps, rating: float|null, last5_rating: float|null, last5_minutes: int|null, concern: bool}]`.
    - `apps` sums over competitions.
    - `rating` is the apps-weighted mean, or null when `apps == 0`.
    - `last5_rating` is null when `valid` is false.
  - `form.flags(rows, min_apps=3) -> dict` returns `{low_form: [...], unused: [...], concerns: [...]}`.
    - `low_form`: `last5_rating` < 6.5 with apps ≥ `min_apps`.
    - `unused`: apps == 0 while the team has played (some player apps > 0).
- Produces CLI: `fm [--json] squad form [--team first]` gives a table plus the flag lines.

- [ ] **Step 1: Write the failing tests:**
  - `test_form_no_matches_is_null_not_zero`;
  - `test_rating_apps_weighted_over_competitions`;
  - `test_last5_minutes_full_match_is_90`;
  - `test_unused_only_when_team_has_played`;
  - `test_low_form_needs_min_apps`;
  - CLI `test_squad_form_text_flags`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** the op (only props that land headless; see discovery F2), then `form.py` and the CLI.
- [ ] **Step 4: Run** `uv run pytest -q` → pass. Then build/reload, then `fm/live/check_form.py`. Expected `OK`:
  - player uids == `squad` uids;
  - every `rating` is null or 1–10;
  - concerns ⊆ squad uids;
  - op time < 60 s.
- [ ] **Step 5: Commit** `feat: season and recent form, squad concerns (F2)`.

### Task 3: Fixtures and next opponent (F8)

**Files:**
- Create: `plugin/src/Ops/Fixtures.cs`, `fm/src/fm_assistant/fixtures.py`, `fm/tests/test_fixtures.py`, `fm/tests/fixtures/fixtures.json`, `fm/live/check_fixtures.py`
- Modify: `plugin/src/OpsEntry.cs` (register `fixtures`, timeout 60), `client.py` `OP_TIMEOUTS`, `docs/protocol.md`, `cli.py`

**Interfaces:**
- Produces (op `fixtures`, `n=5`, max 10): `{today, team_uid, next: Fixture|null, upcoming: [Fixture], threat: str|null, opponent_formation: str|null}`.
  - Each `Fixture` is `{date, opponent: {uid, name}, home: bool|null, competition: str|null}`.
  - `next` comes from `Human.Team.NextFixture`, chained with `FixtureDate`, `HomeTeam`, `AwayTeam`, `Competition`.
  - `upcoming` comes from `Next5FixturesData`. Each record's `Fixture` value is planted directly; list records carry no uid, so the op plants on the record value itself, not through `chain`.
  - `home` is decided by comparing `HomeTeam`/`AwayTeam` uids with the own team. If neither matches, `home` is null.
  - `threat` comes from `NextOppositionThreatLevelAssessment`.
  - `opponent_formation` is the next opponent's `MostUsedFormation`.
- Produces (Python):
  - `fixtures.days_until(fx, today) -> int`.
  - `fixtures.text(res) -> str`.
- Produces CLI: `fm [--json] fixtures [--n 5]`.

- [ ] **Step 1: Write the failing tests:**
  - `test_fixtures_none_scheduled`;
  - `test_home_unknown_location`;
  - `test_days_until`;
  - CLI `test_fixtures_json_shape`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** pytest → pass. Then build/reload, then `fm/live/check_fixtures.py`. Expected `OK`:
  - `upcoming` dates ascending and ≥ today;
  - `upcoming[0] == next`;
  - every match day in `training show` (current month) that has a match also appears in `upcoming`, or lies after its last date.
- [ ] **Step 5: Commit** `feat: fixtures and next opponent (F8)`.

### Task 4: Loans out and youth intake (F7)

**Files:**
- Create: `plugin/src/Ops/Loans.cs`, `fm/src/fm_assistant/loans.py`, `fm/tests/test_loans.py`, `fm/tests/fixtures/loans.json`, `fm/live/check_loans.py`
- Modify: `OpsEntry.cs` (register `loans`, timeout 60), `client.py`, `docs/protocol.md`, `cli.py`

**Interfaces:**
- Produces (op `loans`): `{today, out: [Loan], intake: {date, days}}`.
  - Each `Loan` is `{uid, name, age, club: {uid, name}, start_date, end_date, apps, rating, happiness, agreed_time, actual_time}`.
  - The list comes from `Club.PlayersOutOnLoan`.
  - The per-player props are `LoanClub`, `LoanContract`→`StartDate`, `EndDate`, `LoanAppearances`, `LoanAverageRating`, `LoanHappiness`, and `LoanReport`'s `AgreedPlayingTime`/`ActualPlayingTime` (strings, display only).
  - `intake` comes from `IntakeDate` and `DaysUntilYouthIntake`.
  - No per-player reads are issued when the list is empty.
- Produces (Python): `loans.flags(out, today) -> list[dict]` returns the loanees with `apps == 0` whose loan started ≥ 21 days before `today`. When `start_date` is null, they are never flagged.
- Produces CLI: `fm [--json] squad loans`.

- [ ] **Step 1: Write the failing tests:**
  - `test_no_loans`;
  - `test_loan_rating_null_when_no_apps`;
  - `test_flag_unused_loanee_after_21_days`;
  - `test_intake_days`;
  - CLI `test_squad_loans_text_none`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** pytest → pass. Then build/reload, then `fm/live/check_loans.py`. Expected `OK`:
  - `len(out) == PlayersOutOnLoanCount`;
  - none of the `out` uids are in the first-team squad;
  - `intake.date` ≥ today.
- [ ] **Step 5: Commit** `feat: loans out and youth intake (F7)`.

### Task 5: Session briefing (F1-lite) + skill, smoke, README, MCP

**Files:**
- Create: `fm/src/fm_assistant/briefing.py`, `fm/tests/test_briefing.py`, `skills/fm-manager/commands/fm-briefing.md`
- Modify: `cli.py`, `skills/fm-manager/SKILL.md`, `skills/fm-manager/settings.example.json`, `scripts/smoke.sh`, `README.md`; on branch `phase3-mcp` (rebased onto `phase1c`), `fm/src/fm_assistant/mcp_server.py` `TOOLS`.

**Interfaces:**
- Consumes: Tasks 1–4 functions, plus 1b's `watch`, `vacancies` and `training.week_load`.
- Produces: `briefing.build(parts: dict) -> dict` returns `{today, next_fixture, injuries, expiring, tired, concerns, low_form, vacancies_open, loans_flagged, intake_days}`. Each part is optional: a part that failed is `{"error": code}` and does not stop the others.
- Produces CLI: `fm [--json] briefing`.
  - It calls, in order: `squad` (with `today`), `training`, `fixtures`, `form`, `club`, `loans`.
  - It never calls `staff_search`. `vacancies_open` is the count from `club` only, because staff search is slow.
  - The text is at most 12 lines, most urgent first: next match, injuries, tired, expiring, concerns.

- [ ] **Step 1: Write the failing tests:**
  - `test_briefing_without_fixture`;
  - `test_briefing_part_error_does_not_stop_others`;
  - `test_briefing_text_max_12_lines`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** the briefing and the CLI.
- [ ] **Step 4: Skill.**
  - Baseline: one subagent answers "briefing dong", "siapa yang performanya turun?", "lawan berikutnya siapa?" and "kontrak siapa yang harus diprioritaskan?" on canned real `--json` outputs, with the current skill. Record the misreads.
  - Update `SKILL.md` for those misreads only. Add rows: briefing, form, fixtures, contracts, loans.
  - Re-test the same scenarios. Expected: numbers quoted from the JSON, no tactic advice from `opponent_formation`, `null` ratings said as "belum main", manual steps present.
- [ ] **Step 5: Smoke, README, MCP.**
  - Add the 5 commands to `scripts/smoke.sh` and the README table. Run `bash scripts/smoke.sh` → `smoke: all ok`.
  - Rebase `phase3-mcp` onto `phase1c`, add 5 `TOOLS` entries, run `uv run pytest -q`, and do a stdio `tools/list` smoke.
- [ ] **Step 6: Commit** `feat: session briefing; skill, smoke, README for phase 1c` (on `phase1c`) and `feat(mcp): phase 1c tools` (on `phase3-mcp`).
