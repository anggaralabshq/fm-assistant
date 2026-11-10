# Phase 1d: Context Reads — Inbox, Morale, Stars, Tactic Fit, Rotation, Trends Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish Phase 1's read features. The phase 1d spike found how the game resolves context-bound properties. Using that, add:
- the inbox (F1, full briefing);
- morale and happiness (F2);
- scouted star ranges, with quality-ordered targets (F6, F7);
- the active tactic with role and position fit (F3);
- rotation hints before congested fixtures (F4);
- season trends from local snapshots (F9).

**Architecture:**
- Ops plant the binding contexts each property's handler names (`Reader.PlantOne(..., ctx)` from `phase1d-spike`). Values are read headless, with no screen open.
- A startup check compares the expected context names with `Bindings.GetHandler`. Renamed contexts fail loudly as `binding-api-changed`.
- Python normalizes and composes, as in Phases 1a to 1c.
- F4 and F9 are pure Python over existing reads.
- The spike's profile-route ops stay dev-only, as a Phase 2 building block.

**Tech Stack:** Python 3.12+ (click, pytest, uv); C# ops assembly (hot reload, `bash plugin/build.sh`).

**Spec:** `docs/superpowers/specs/2026-11-07-fm-assistant-manager-design.md` (§6 F1–F4, F6, F7, F9; §3 non-goals: no tactics *changes*; §6 "atribut tersembunyi hanya sejauh yang FM tampilkan ke manager"). Data sources: `docs/discovery/2026-11-10-phase1d.md` and `docs/discovery/2026-11-10-phase1c.md`.

## Global Constraints

- The Phase 1a–1c Global Constraints hold.
- Star ratings come only from the `*StarRange` props, planted with the viewer's team (`Human.Team`) as context. Values must be ≤ 20 or −1. Any other value is dropped, and the op says so in `warnings`.
- Morale and happiness are returned only when `CanViewHappinessInfo == "True"`; otherwise null.
- F3 and F4 report fit and condition facts. They never propose a formation, role change or instruction, and nothing is written to the game.
- Snapshots (F9) live in `~/.fm-assistant/snapshots/<club_uid>/`, never in the repo.
- Branch `phase1d` off `phase1d-spike`. Owner's standing approval: execute, then report at phase end. Merge to `main` when the final review is clean.

## Review Focus

1. A player whose star range is −1/−1 (unscouted) must get `stars: null`. The order of targets must not treat it as 0 stars. (Task 4 `test_unscouted_stars_null_sorted_last`.)
2. If the tactic has an empty slot, or a slot whose player has left or is injured, list the slot with `player: null` or a flag. Never crash. (Task 5 `test_empty_slot_and_injured_player`.)
3. The inbox `since` date may be after every item, or a list may be empty. Return `items: []` with the `unread` count kept. (Task 2 `test_inbox_since_after_all`.)
4. The first `fm trends` with no earlier snapshot, or with a snapshot from another club or career, gives "no earlier snapshot for this club", not a diff. (Task 7 `test_trends_without_previous`, `test_trends_other_club_ignored`.)
5. If a player can be seen but has no morale (`CanViewHappinessInfo` True, `Morale` missing), return `morale: null`, never 0. (Task 3 `test_morale_missing_is_null`.)

---

### Task 1: Context reads in production + startup check

**Files:**
- Modify: `plugin/src/Ops/Game/Reader.cs`; `plugin/src/Ops/OpsEntry.cs`; `fm/src/fm_assistant/doctor.py`; `docs/protocol.md`
- Create: `plugin/src/Ops/Contexts.cs`; `fm/tests/test_doctor_ctx.py`

**Interfaces:**
- Produces (C#): `Contexts.For(string prop) -> string[]`, a fixed table copied from the discovery doc. Plus `Contexts.Values(ReadScope)`, which builds `team`, `human`, `club`, `TeamRequestingReport` and `Boolean`.
- Produces (op `ctx_check`, not dev-gated, read-only, timeout 30): `{checked: int, mismatches: [{prop, expected: [..], game: [..]}]}`. It calls `GetHandler` and opens no channel.
- Produces (Python): `doctor.FEATURES` gains a "binding contexts" check. It is ok when `mismatches == []`.

- [ ] **Step 1: Write the failing test** `test_doctor_reports_context_mismatch` (fake `ctx_check` with one mismatch → the check fails, and the detail names the prop).
- [ ] **Step 2: Run** `cd fm && uv run pytest -q tests/test_doctor_ctx.py`. Expected: FAIL.
- [ ] **Step 3: Implement** the C# table and op, then the doctor entry.
- [ ] **Step 4: Run pytest** (expect pass). Then run `bash plugin/build.sh` (expect "Reloaded ops"), then `uv run fm doctor`. Expected: "ok binding contexts".
- [ ] **Step 5: Commit** `feat: production context reads and startup context check`.

### Task 2: Inbox (F1 full) + opposition report flag

**Files:**
- Create: `plugin/src/Ops/Inbox.cs`; `fm/src/fm_assistant/inbox.py`; `fm/tests/test_inbox.py`; `fm/tests/fixtures/inbox.json`; `fm/live/check_inbox.py`
- Modify: `plugin/src/Ops/Fixtures.cs` (add `report`); `OpsEntry.cs` (register `inbox`, timeout 30); `client.py` `OP_TIMEOUTS`; `cli.py`; `briefing.py`; `docs/protocol.md`

**Interfaces:**
- Produces (op `inbox`): args `since: "YYYY-MM-DD"|null`, `tab: "all"|"unread"` (tab 0 or 3), `max: int = 50` (1–200). Result:
  - `{today, unread: int, items: [{id, date, time, read: bool, important: bool, category: int, title, body}]}`.
  - Items are newest first and stop at the first item older than `since`.
  - `body` is cut to 600 characters.
- Produces (op `fixtures`): adds `report: bool|null`, from the next opponent's `HasTeamReport`.
- Produces (Python):
  - `inbox.text(res) -> str`.
  - `briefing.build` takes an `inbox` part and adds `inbox: {unread, recent: [{date, title}] (max 5, since yesterday)}`.
  - The briefing CLI calls `inbox` with `since = today - 1`.
- Produces CLI: `fm [--json] inbox [--since D] [--unread] [--max 20]`.

- [ ] **Step 1: Write the failing tests:**
  - `test_inbox_since_after_all`
  - `test_inbox_text_newest_first_with_unread_mark`
  - `test_briefing_includes_inbox_recent`
  - CLI `test_inbox_json_shape`
- [ ] **Step 2: Run** the tests. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run pytest** (expect pass), then build/reload, then run `fm/live/check_inbox.py`. Expected `OK` when:
  - `unread` equals the number of unread items in tab 0;
  - dates are non-increasing;
  - `since` = today returns only today's items;
  - one run takes < 5 s.
- [ ] **Step 5: Commit** `feat: inbox and opposition report flag (F1, F8)`.

### Task 3: Morale and happiness (F2)

**Files:**
- Modify: `plugin/src/Ops/Form.cs`; `fm/src/fm_assistant/form.py`; `fm/tests/test_form.py`; `fm/tests/fixtures/form.json`; `cli.py` (`squad form` columns); `briefing.py`; `docs/protocol.md`; `fm/live/check_form.py`

**Interfaces:**
- Produces (op `form`): each player gains:
  - `morale: {value: int, text}|null`;
  - `happiness: {playing_time: {severity, change, text}, club: {...}, management: {...}, training: {...}}|null`.
  - Both are gated on `CanViewHappinessInfo`.
  - `text` is the localized `Description` with tags stripped.
- Produces (Python):
  - `form.summary` rows gain `morale_text`, `morale` (int|null) and `unhappy: [area]`.
  - An area is listed when its `severity` is above the threshold `UNHAPPY_SEVERITY`. Fix that constant from the live values: record the severities seen in `docs/protocol.md` and choose the value at which the game's own text turns negative.
  - `form.flags` gains `unhappy`.
- Briefing: `concerns` also lists the `unhappy` players.

- [ ] **Step 1: Write the failing tests:**
  - `test_morale_missing_is_null`
  - `test_unhappy_areas_over_threshold`
  - `test_morale_hidden_when_cannot_view` (op shape: null)
- [ ] **Step 2: Run** the tests. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run pytest**, build/reload, then `check_form.py`. Expected `OK` when:
  - every first-team player has `morale` set, or `CanViewHappinessInfo` is False;
  - `value` is within the range recorded live.
- [ ] **Step 5: Commit** `feat: morale and happiness in form (F2)`.

### Task 4: Scouted star ranges, quality-ordered targets (F6, F7)

**Files:**
- Modify:
  - `plugin/src/Ops/Squad.cs`, `Players.cs`, `Loans.cs`;
  - Python: `players.py`, `depth.py` (targets order), `squad.py`, `loans.py`, `cli.py` (star columns);
  - tests and fixtures for each module;
  - `docs/protocol.md`.
- Create: `fm/src/fm_assistant/stars.py`; `fm/tests/test_stars.py`; `fm/live/check_stars.py`

**Interfaces:**
- Produces (ops `squad`, `player_search`, `loans`): each person gains `stars_raw: {current: {min, max}|null, potential: {min, max}|null}`.
  - Values come from `CurrentAbilityStarRange` and `PotentialAbilityStarRange` (0–20).
  - −1/−1 becomes null.
  - A value outside −1..20 is dropped and added to the result's `warnings`.
- Produces (Python):
  - `stars.to_stars(v: int) -> float|None` returns `(v − 10) / 2` for 10–20, and None below 10 until the youth mapping is verified (see Step 4).
  - `stars.of(raw) -> {current: [min,max]|None, potential: [min,max]|None}` in stars.
  - `depth.targets` order becomes:
    1. budget-known first;
    2. then potential max in stars, descending, with unknown last;
    3. then current max, descending;
    4. then younger.
- Produces CLI: `squad list`, `players search`, `players targets` and `squad loans` gain `ability` and `potential` columns (e.g. `3.5–4`, `?`).

- [ ] **Step 1: Write the failing tests:**
  - `test_unscouted_stars_null_sorted_last`
  - `test_to_stars_scale`, with 18 → 4.0 and 10 → 0.0
  - `test_targets_quality_before_youth`
  - `test_star_value_out_of_range_dropped`
- [ ] **Step 2: Run** the tests. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Live (ops agent).** Open the youth team's SquadScreen and compare the star widget's mapped values with `stars_raw` for 5 youth players.
  - If the values below 10 follow a different linear mapping, record it in `docs/protocol.md`, and the Python side updates `to_stars`.
  - Run `check_stars.py`. Expected `OK` when:
    - all values are within −1..20;
    - first-team players have `min == max`;
    - unscouted search rows give null.
- [ ] **Step 5: Commit** `feat: scouted star ranges; targets ordered by scouted quality (F6, F7)`.

### Task 5: Active tactic and role fit (F3)

**Files:**
- Create: `plugin/src/Ops/Tactic.cs`; `fm/src/fm_assistant/rolefit.py`; `fm/tests/test_rolefit.py`; `fm/tests/fixtures/tactic.json`; `fm/live/check_tactic.py`
- Modify: `OpsEntry.cs` (register `tactic`, timeout 30); `client.py`; `cli.py`; `docs/protocol.md`

**Interfaces:**
- Produces (op `tactic`):
  - Result: `{name, mentality, slots: [{index, position_mask, position_label, role, player: {uid, name}|null}]}`, with exactly 11 slots in `TeamSelectionIndex` order.
  - Read headless from `Human.Team.Tactic` (context `Boolean`).
  - `role` is the player's `TacticsRoleName` (context `team`).
  - `position_mask` must use the same bit scheme as player `position_mask`. The ops agent verifies this live: for each slot, decode it with `positions.decode` and compare with the tactics screen label. If the schemes differ, the op maps the slot to the player scheme and records the table in `docs/protocol.md`.
- Produces (Python): `rolefit.check(tactic: dict, squad: dict) -> list[dict]`, one row per slot:
  - fields `{index, position_label, role, player, natural: bool|None, injured, condition, best_oop_role}`;
  - `natural` = `positions.covers(player_mask, slot_label)`, or None when unknown.
- Produces CLI: `fm [--json] tactic`. It prints the slot table plus the lines "out of position: …" and "injured/tired in XI: …". It gives no advice.

- [ ] **Step 1: Write the failing tests:**
  - `test_empty_slot_and_injured_player`
  - `test_natural_uses_covers`
  - CLI `test_tactic_text_has_no_advice_words` (no "should", "change", "ganti" in the output)
- [ ] **Step 2: Run** the tests. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run pytest**, build/reload, then `check_tactic.py`. Expected `OK` when:
  - there are 11 slots;
  - slot player uids are a subset of the squad uids;
  - each `position_label` equals the tactics screen label for that slot (read once with `ui_dump` in dev mode, then dev mode is removed).
- [ ] **Step 5: Commit** `feat: active tactic and role fit (F3)`.

### Task 6: Rotation hints (F4)

**Files:**
- Create: `fm/src/fm_assistant/rotation.py`; `fm/tests/test_rotation.py`
- Modify: `cli.py`

**Interfaces:**
- Consumes: `rolefit.check` rows, `squad`, `fixtures.upcoming` and `form.summary`.
- Produces: `rotation.hints(fit_rows, squad_players, upcoming, today, form_rows, window_days=7, condition_min=90) -> {matches_in_window: int, at_risk: [{slot, player, condition}], options: {slot_index: [{uid, name, condition, last5_rating, natural}]}}`.
  - `at_risk` lists XI players with `condition < condition_min`, or injured. It is filled only when `matches_in_window >= 2`.
  - `options` are non-XI, non-injured players who cover the slot. They are sorted by condition descending, then by `last5_rating` descending (null last), with at most 3 per slot.
- Produces CLI: `fm [--json] squad rotation [--days 7]`. When fewer than 2 matches fall in the window, the text says "no congested fixtures in the next N days".

- [ ] **Step 1: Write the failing tests:**
  - `test_no_hints_without_congestion`
  - `test_options_cover_slot_and_exclude_xi`
  - `test_injured_xi_player_at_risk`
- [ ] **Step 2: Run** the tests. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run pytest** (expect pass). Then run `uv run fm squad rotation` live (expect exit 0) and check that every option covers its slot.
- [ ] **Step 5: Commit** `feat: rotation hints before congested fixtures (F4)`.

### Task 7: Snapshots and trends (F9)

**Files:**
- Create: `fm/src/fm_assistant/trends.py`; `fm/tests/test_trends.py`
- Modify: `cli.py` (`snapshot`, `trends`; `briefing` writes a snapshot unless `--no-snapshot`); `briefing.py`

**Interfaces:**
- Produces:
  - `trends.SNAP_DIR = ~/.fm-assistant/snapshots`.
  - `trends.save(snap: dict, root=SNAP_DIR) -> Path` writes to `<root>/<club_uid>/<game_date>.json`, overwriting an existing file for the same date.
  - The snapshot is `{club_uid, date, balance, transfer_budget, wage_remaining, players: {uid: {name, condition, morale, rating, apps, injured}}}`.
  - `trends.load_previous(club_uid, before_date, root) -> dict|None`.
  - `trends.diff(old, new) -> {days, balance_change, budget_change, rating_up, rating_down, morale_down, new_injuries, recovered}`.
    - Rating changes count only players with ≥ 2 more apps and a change of at least 0.3.
- Produces CLI:
  - `fm [--json] snapshot` saves a snapshot from `club`, `squad` and `form`.
  - `fm [--json] trends` saves today's snapshot, then diffs it against the latest earlier one.

- [ ] **Step 1: Write the failing tests:**
  - `test_trends_without_previous`
  - `test_trends_other_club_ignored`
  - `test_diff_rating_needs_two_more_apps`
  - `test_save_same_date_overwrites`
- [ ] **Step 2: Run** the tests. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run pytest** (expect pass). Then run `uv run fm trends` live twice: the first run says "no earlier snapshot", the second shows `days 0`. Afterwards delete the test snapshot directory for that club.
- [ ] **Step 5: Commit** `feat: snapshots and season trends (F9)`.

### Task 8: Skill, smoke, README, MCP

**Files:** `skills/fm-manager/SKILL.md`, `commands/` (`fm-inbox.md`, `fm-tactic.md`), `settings.example.json`, `scripts/smoke.sh`, `README.md`, `fm/src/fm_assistant/mcp_server.py` `TOOLS`, `fm/tests/test_mcp_server.py`.

- [ ] **Step 1: Baseline.** Run one subagent on canned real outputs with the current skill, asking:
  - "ada pesan penting?"
  - "moral tim gimana?"
  - "pemain mana yang main di luar posisi?"
  - "perlu rotasi minggu ini?"
  - "trennya gimana sejak terakhir?"
  - "target bek kiri yang bagus siapa?"

  Record the misreads.
- [ ] **Step 2: Update the skill for those misreads only**, then re-test. Expected:
  - stars quoted as ranges (e.g. "3,5–4 bintang, perkiraan scout");
  - no tactic or formation advice;
  - rotation presented as options;
  - inbox titles quoted.
- [ ] **Step 3: Smoke, README and MCP.**
  - Add `inbox`, `tactic`, `squad rotation`, `snapshot` and `trends` to `smoke.sh`. Smoke must not leave a snapshot behind: run it with `FM_ASSISTANT_SNAP_DIR` pointing to a temp dir, and add that env override to `trends.SNAP_DIR`.
  - Update the README table.
  - Add `TOOLS` entries for `inbox`, `tactic`, `squad_rotation` and `trends`. Leave out `snapshot`, which writes a file.
  - Run `bash scripts/smoke.sh`. Expected `smoke: all ok`. Run the MCP stdio `tools/list` check.
- [ ] **Step 4: Commit** `feat(skill): inbox, morale, stars, tactic fit, rotation, trends`.
