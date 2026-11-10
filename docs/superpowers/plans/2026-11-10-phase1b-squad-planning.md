# Phase 1b: Vacancies, Contract & Injury Watch, Squad Depth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Three read-only recommendations built on Phase 1a reads: staff vacancies with candidates per vacancy (F11), contract expiry and injury return vs fixtures (F2/F5), and thin positions with affordable scouting targets (F6).

**Architecture:** Almost all logic is pure Python in `fm/src/fm_assistant/` over the existing ops (`club`, `squad`, `staff_search`, `player_search`, `training`), unit-tested on invented fixtures. One small ops change: `squad` also returns `today`. New CLI commands follow the Phase 1a pattern (`need_hello`, `emit`, text table + `--json` envelope); the `fm-manager` skill gains one row per command.

**Tech Stack:** Python 3.12+ (click, websockets, pytest, uv); C# ops assembly (hot reload via `bash plugin/build.sh`).

**Spec:** `docs/superpowers/specs/2026-11-07-fm-assistant-manager-design.md` (§6 F2, F5, F6, F11; §3 non-goals). Phase 1a reference: `docs/protocol.md` (field names of every op), plan `docs/superpowers/plans/2026-11-07-phase1a-read-recommend.md`.

## Global Constraints

- Everything in Phase 1a's Global Constraints still holds (read-only, never save/Continue/match, no DB edits, 127.0.0.1 + token, English code/CLI/README, Indonesian answers via the skill, invented fixture names, no game data in the repo).
- No tactics: depth counts positions the players can play; it never names a formation or a lineup. Minimum per position is owner-editable (`~/.fm-assistant/depth.json`), default 2 for every position.
- Recommendations carry checkable numbers (spec §4 anti-goal "percaya saja").
- Branch `phase1b` off `phase1a`.

## Review Focus

1. A vacancy whose job has no role mapping (loan manager, doctor without a fitting role) → listed with `roles: []` and no candidates, never a crash. (Task 1 `test_unmapped_job_listed_without_candidates`.)
2. Staff search truncated (5000 rows, 1000 read) → every vacancy carries `truncated: true` and the text output says `ranked among 1000 of 5000`. (Task 1 `test_vacancies_carry_truncation`.)
3. An injured player whose `return_days` is null, or whose return falls after the last day of the training view → listed with `return_date: null` / `beyond_view: true`, never a crash or a wrong "0 matches missed". (Task 2 `test_injury_unknown_return`, `test_injury_beyond_view`.)
4. A contract without `end_date` (amateur, youth, loanee) → left out of `expiring`, no crash. (Task 2 `test_expiring_skips_missing_end_date`.)
5. A player with `position_mask` 0 or unknown bits → counted in no position and listed under `unknown_position`. (Task 3 `test_depth_unknown_mask`.)

---

### Task 1: Staff vacancies with candidates (F11)

**Files:**
- Create: `fm/src/fm_assistant/vacancies.py`, `fm/src/fm_assistant/data/job_roles.json`, `fm/tests/test_vacancies.py`, `fm/tests/fixtures/club_jobs.json`, `fm/live/check_vacancies.py`
- Modify: `fm/src/fm_assistant/cli.py`, `fm/tests/fixtures/staff_search.json` (add `preferred_job_type` to rows), `fm/tests/test_cli.py`

**Interfaces:**
- Consumes: op `club` → `staff_slots[group] = {used, max, summary, board_feedback, jobs: [{job, job_type, used, max}]}`; op `staff_search` rows with `preferred_job_type`; `staff.load_roles()`, `staff.rank()`.
- Produces: `vacancies.load_job_roles(user_path: Path | None = ~/.fm-assistant/job_roles.json) -> dict[int, list[str]]` (packaged map merged key-by-key with the owner's file); `vacancies.open_jobs(club: dict) -> list[dict]` → `[{group, job, job_type, open: max - used, summary, board_feedback}]` for jobs with `used < max`, in group order coaching, recruitment, medical; `vacancies.fill(jobs: list, staff: dict, roles: dict, job_roles: dict, top: int = 3) -> list[dict]` adds `roles: [str]` and `candidates: [Staff + score + role]` per job. For each mapped role, `staff.rank(..., max_wage=None)` runs on rows whose `preferred_job_type == job_type` first. If that gives fewer than `top`, it fills from the rest. Candidates are deduplicated by uid, keeping the best score. Every job also gets `truncated`, `returned` and `count` copied from the search.
- Produces CLI: `fm [--json] staff vacancies [--top 3]` → `{"jobs": [...], "count", "returned", "truncated"}`; text prints one block per job ("Pemandu Bakat: 2 open — <summary>") with a candidate table and, when truncated, `ranked among R of C`.
- `job_roles.json` (job_type → role keys; values observed on build 27.0.0.2493426): `14`, `44` → `scout`; `58` → `recruitment_analyst`; `60`, `62` → `performance_analyst`; `12`, `50` → `physio`; `40`, `48` → `sports_scientist`; `22` → `set_piece_coach`; `10`, `88` → `director_of_football`; `64` → `coach_youth`; `104` → `coach_attacking`, `coach_defending`, `coach_fitness`, `coach_goalkeeping`. Unmapped: `16` (manager), `38`, `46` (doctors), `86` (loan manager).

- [ ] **Step 1: Write the failing tests.** In `test_vacancies.py`, on fixture `club_jobs.json` (invented: recruitment jobs `{14: 0/2, 44: 0/1, 10: 1/1}`, medical `{12: 0/1, 46: 0/1}`, coaching `{104: 7/3}`):
  - `test_open_jobs_only_below_max` → job_types `[14, 44, 12, 46]`, opens `[2, 1, 1, 1]`.
  - `test_open_count_matches_summary_digits` → sums per group are recruitment 3 and medical 2.
  - `test_fill_prefers_matching_job_type`: for job 14, a scout-type row with score 9 ranks above a non-scout row with score 11 when there are enough scout-type rows.
  - `test_fill_tops_up_from_other_rows`.
  - `test_unmapped_job_listed_without_candidates` (job 46 → `roles == []`, `candidates == []`).
  - `test_vacancies_carry_truncation`.
  - `test_job_roles_override_merges`.
  - In `test_cli.py`: `test_staff_vacancies_text_says_ranked_among` (count 5000, returned 1000 → text contains `ranked among 1000 of 5000`).
- [ ] **Step 2: Run** `cd fm && uv run pytest -q tests/test_vacancies.py` → FAIL (ImportError).
- [ ] **Step 3: Implement** `vacancies.py`, the data file and the CLI command (`club` then `staff_search` with `max=1000`, through one `FmClient`).
- [ ] **Step 4: Run** `uv run pytest -q` → all pass.
- [ ] **Step 5: Live check `fm/live/check_vacancies.py`:**
  - For every group whose game `summary` contains a digit run, that number equals the sum of `open` in the group.
  - Every candidate's uid is in the staff search result.
  - Run with the game up: expected `OK`.
- [ ] **Step 6: Commit** `feat: staff vacancies with candidates per vacancy (F11)`.

### Task 2: Contract and injury watch (F2/F5)

**Files:**
- Create: `fm/src/fm_assistant/watch.py`, `fm/tests/test_watch.py`, `fm/live/check_watch.py`
- Modify: `plugin/src/Ops/Squad.cs` (add `today`), `docs/protocol.md` (squad result), `fm/tests/fixtures/squad.json` (add `"today": "2026-08-03"` and an `injury`), `fm/src/fm_assistant/cli.py`, `fm/tests/test_cli.py`

**Interfaces:**
- Consumes: op `squad` → players with `contract.end_date`, `injured`, `injury: {description, return_days}`; op `training` → `training.with_dates(cal)` days with `date` and `match`.
- Produces (op): `squad` result gains `"today": "YYYY-MM-DD"` (from `game.CurrentGameDate`, read the same way `Training.Read` does).
- Produces (Python):
  - `watch.expiring(players: list, today: date, within_days: int = 180) -> list[dict]` → `[{uid, name, age, end_date, days_left, wage}]` sorted by `days_left`, skipping players without a parseable `end_date`.
  - `watch.injuries(players: list, today: date, days: list) -> list[dict]` → `[{uid, name, description, return_days, return_date: str|null, matches_missed: int|null, beyond_view: bool}]`. `matches_missed` counts days in `days` with a `match` and today ≤ date < return_date. `beyond_view` is true when `return_date` is after the last day in `days`. An unknown `return_days` gives `return_date: null`, `matches_missed: null`, `beyond_view: false`.
- Produces CLI: `fm [--json] squad watch [--within 180] [--team first]` → `{"today", "expiring": [...], "injured": [...]}`. Text: two tables; `beyond_view` rows print `≥N` for matches missed.

- [ ] **Step 1: Write the failing tests** in `test_watch.py`:
  - `test_expiring_sorted_and_windowed`: today 2026-08-03; ends 2026-12-31, 2027-06-30, 2028-06-30 with a 180-day window → only 2026-12-31, `days_left == 150`.
  - `test_expiring_skips_missing_end_date`.
  - `test_injury_counts_matches_before_return`: training fixture via `training.with_dates` (days 2026-07-27..2026-08-04, matches 07-28, 07-31, 08-04), today 2026-08-03, `return_days` 2 → `return_date == "2026-08-05"`, `matches_missed == 1`, `beyond_view is False`.
  - `test_injury_unknown_return`: `return_days` null → `return_date is None`, `matches_missed is None`.
  - `test_injury_beyond_view`: `return_days` 5 → `return_date == "2026-08-08"`, `beyond_view is True`, `matches_missed == 1` (a lower bound).
  - In `test_cli.py`: `test_squad_watch_json_shape`.
- [ ] **Step 2: Run** → FAIL (ImportError).
- [ ] **Step 3: Implement.** Add `today` to `Squad.cs` (one more `ReadOne` on `Tree.Find("game")`, `Reader.Require` on it). Then `watch.py` and the CLI command, which calls `squad`, then `training`; `today` comes from `squad`.
- [ ] **Step 4: Run** `uv run pytest -q` → pass; `bash plugin/build.sh` → "Reloaded ops".
- [ ] **Step 5: Live check `fm/live/check_watch.py`:** `squad.today == training.today`; every injured player in `squad` appears in `injured`; every `expiring` date parses and is within the window. Expected `OK`.
- [ ] **Step 6: Commit** `feat: contract and injury watch (F2/F5)`.

### Task 3: Squad depth and scouting targets (F6)

**Files:**
- Create: `fm/src/fm_assistant/depth.py`, `fm/tests/test_depth.py`
- Modify: `fm/src/fm_assistant/positions.py` (add `covers`), `fm/tests/test_positions.py`, `fm/src/fm_assistant/cli.py`, `fm/tests/test_cli.py`

**Interfaces:**
- Consumes: `squad` players (`position_mask`, `injured`); `players.affordable()` rows from `player_search` (`position_mask`, `budget_unknown`, `age`).
- Produces:
  - `positions.SLOTS = ["GK", "D (R)", "D (L)", "D (C)", "WB (R)", "WB (L)", "DM", "M (R)", "M (L)", "M (C)", "AM (R)", "AM (L)", "AM (C)", "ST (C)"]`.
  - `positions.covers(mask: int, slot: str) -> bool`: the slot's own bit, or for a side slot the group's centre bit plus the matching side modifier (`0x100000` left, `0x200000` right). `ST (C)` also counts ST side bits `32768`/`65536`. Unknown slot → `ValueError`.
- Produces: `depth.load_minimums(user_path=~/.fm-assistant/depth.json) -> dict[str, int]` (default 2 per slot, owner override merged). `depth.depth(players: list, minimums: dict) -> dict` → `{"slots": [{slot, count, fit, names, thin: fit < min, min}], "unknown_position": [names]}`, where a player counts in every slot he covers and `fit` excludes `injured`. `depth.targets(slots: list, prospects: list, top: int = 5) -> dict[str, list]` gives, per thin slot, prospects covering it: budget-known before budget-unknown, then younger first.
- Produces CLI: `fm [--json] squad depth [--team first]` and `fm [--json] players targets [--top 5] [--max 1000]` (squad first team → thin slots → `player_search` + `affordable` with club budget → targets). Text: depth table (`slot  fit/min  names`), then one candidate table per thin slot.

- [ ] **Step 1: Write the failing tests.**
  - In `test_positions.py`, copied from the fm-dof-mcp tests: `covers(16|8, "D (C)")` True; `covers(2048|4096|16384, "ST (C)")` True; `covers(16384, "D (C)")` False; `covers(16|0x100000, "D (L)")` True; `covers(1, "GK")` True; `covers(1, "nope")` raises.
  - In `test_depth.py`, on the `squad.json` fixture:
    - `test_depth_counts_every_covered_slot`: the "D (LC)" player counts in D (C) and D (L).
    - `test_fit_excludes_injured`: the injured GK → GK fit 0, thin.
    - `test_depth_unknown_mask`: mask 0 → `unknown_position`.
    - `test_minimums_override`.
    - `test_targets_order_budget_known_then_young`.
  - In `test_cli.py`: `test_players_targets_only_for_thin_slots`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** `covers`, `depth.py` and the two CLI commands.
- [ ] **Step 4: Run** `uv run pytest -q` → pass. Live: `uv run fm squad depth` and `uv run fm players targets` exit 0. Every listed name is in `squad list`, and every target covers its slot (`positions.covers`).
- [ ] **Step 5: Commit** `feat: squad depth and scouting targets (F6)`.

### Task 4: Skill, smoke, README

**Files:**
- Modify: `skills/fm-manager/SKILL.md`, `skills/fm-manager/commands/` (add `fm-vacancies.md`, `fm-watch.md`, `fm-depth.md`), `skills/fm-manager/settings.example.json`, `scripts/smoke.sh`, `README.md`

**Interfaces:**
- Consumes: CLI commands from Tasks 1–3.
- Produces:
  - Skill table rows:
    - "Lowongan staf" → `staff vacancies`.
    - "Kontrak / cedera" → `squad watch`.
    - "Kedalaman skuad / target scouting" → `squad depth`, `players targets`.
  - Field notes:
    - `open` is relative to the board's target.
    - `beyond_view` means "at least".
    - Depth minimums are the owner's, not a formation.
  - Manual steps:
    - KLUB → Staf → Lowongan, then Cari Staf;
    - SKUAD → Kontrak;
    - REKRUTMEN → Database Pemain.

- [ ] **Step 1: Baseline.** One subagent (no skill) answers 3 scenarios on canned real `--json` outputs:
  - "ada lowongan staf apa?"
  - "kontrak siapa yang mau habis?"
  - "posisi mana yang kurang?" with a truncated search and an injured GK.
  Record the misreads.
- [ ] **Step 2: Update the skill** for the recorded misreads only, then re-run the same scenarios with the skill. Expected: numbers quoted from JSON, `ranked among` stated, no lineup or formation advice, "Langkah manual di game:" present, no action claimed.
- [ ] **Step 3:** Add the 4 commands to `scripts/smoke.sh` and to the README command table. Run `bash scripts/smoke.sh` → `smoke: all ok`.
- [ ] **Step 4: Commit** `feat(skill): vacancies, watch and depth in fm-manager`.
