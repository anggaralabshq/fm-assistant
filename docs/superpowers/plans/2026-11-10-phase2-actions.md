# Phase 2: Actions after approval — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The owner approves a plan and `fm apply` performs it in the game. Before acting it backs up the save. After acting it verifies the result by reading it back and writes an audit log line. The actions are:
- staff offers (F11);
- shortlist and scout requests (F6);
- training sessions and individual focus (F10);
- player contract renewals (F5).

**Architecture:**
- Python owns plans (`~/.fm-assistant/plans/<id>.json`), the closed action registry, backup, audit log and the `fm plan` / `fm apply` / `fm log` commands.
- The plugin gets `act_*` ops. Each refuses to run without a one-use apply token, which `fm apply` writes to `~/.fm-assistant/apply/<token>` immediately before the call.
- Every `act_*` op performs the action through the game's own action dispatcher or fixed element names, then reads the state back headless.

**Tech Stack:** C# BepInEx IL2CPP hot-reloadable ops (`bash plugin/build.sh`); Python 3.10+ (click, pytest); `uv`.

**Spec:** `docs/superpowers/specs/2026-11-07-fm-assistant-manager-design.md` §8 (approval, closed registry, negotiation), §9 (Phase 2 order), §9b (untested build → read-only). Discovery: `docs/discovery/2026-11-10-phase2.md` (routes, ids, read-backs, risks).

## Global Constraints

- Never save, never press Continue, never play or simulate a match, never open press conferences. No act op touches MainMenu or the date.
- Back up before every apply: copy the newest `.fm` in the games dir to `~/.fm-assistant/backups/<YYYYmmdd-HHMMSS>/` and write `SHA256SUMS`.
  - If the backup fails, the apply is aborted and nothing is sent.
  - Games dir default: `~/Library/Application Support/Sports Interactive/Football Manager 27/games`. Override: `FM_ASSISTANT_GAMES_DIR`.
- Closed registry, two layers:
  - Python accepts only the action kinds listed in Task 1.
  - The plugin accepts only the allow-listed `ActionID`s below. It never takes an action id as an argument.
  - Allow-listed ids: `PersonApproachToSign` 1749837424, `PersonOfferContract` 2000111204, `PersonAddPlayersToShortlist` 1097488485, `PersonRemovePlayersFromShortlist` 1500280650, `PersonAssignScoutToPlayersClub` 1363818831.
- One approval sends one offer. The agent never sends a counter-offer on its own; each reply is reported and any response is a new plan.
- An untested game build (`build_supported` not True) refuses every apply with "actions are disabled on untested build X".
- No generic click op ships. The phase2-spike dev ops (`ui_click`, `ui_find`, `subtab_action`, `person_panel_open`, `ref_info`) are not merged. Production code uses fixed element names inside each act op.
- Main thread rules hold: no stack-trace formatting, no Addressables scans, no il2cpp reflection over UI element fields.
- Dialogs: an act op that opened a game confirmation dialog confirms or cancels it on every path, including errors.
- Money args are base-currency integers (`value`); display stays the game's `display` text.
- No SI/SEGA/FM branding or game data in the repo; fixtures use invented names.
- Owner approval 2026-11-10: the career save is experimental and live action tests need no per-type approval, but they still go through `fm apply`: backup + log. After live tests, reload the career (`fm game restart --load --allow-career`) so that nothing lingers in memory.

## Review Focus

1. Apply token missing, reused, or for another plan: the op refuses with `forbidden`, nothing is performed, and the audit log records the refusal. (Task 2 `ActGate` live check; Task 1 `test_apply_token_one_use`.)
2. Backup fails (no save found, disk error): the apply aborts before any op call, and the plan stays `proposed`. (Task 1 `test_apply_aborts_without_backup`.)
3. A multi-action plan where action 2 fails: action 1 stays logged as done, actions 2+ are logged `failed`/`skipped`, and the plan status is `partial`. Never "done". (Task 1 `test_partial_plan`.)
4. Staff wage above the board maximum, or a renewal promise that differs from the current status: the op refuses with `precondition` before sending anything, and any open dialog is closed. (Tasks 4, 6.)
5. Untested build: every apply is refused, and reads keep working. (Task 1 `test_apply_refused_on_untested_build`.)

---

### Task 1: Plans, registry, backup, audit, apply (Python)

**Files:**
- Create: `fm/src/fm_assistant/actions.py`, `plans.py`, `backup.py`, `audit.py`, `apply.py`; tests `fm/tests/test_actions.py`, `test_plans.py`, `test_backup.py`, `test_apply.py`
- Modify: `cli.py` (groups `plan`, commands `apply`, `log`), `client.py` (`OP_TIMEOUTS` for act ops: 60 each, `negotiation` 15)

**Interfaces:**
- Produces `actions.REGISTRY: dict[str, Kind]`, where `Kind(op: str, required: dict[str, type], optional: dict[str, type], describe: Callable[[dict], str])`. The kinds:

  | kind | op | required | optional |
  |---|---|---|---|
  | `staff.approach` | `act_staff_approach` | `uid` | |
  | `staff.offer` | `act_staff_offer` | `uid`, `wage` | |
  | `shortlist.add` | `act_shortlist_add` | `uid` | `months` ∈ {0, 1, 3, 6, 12} (default 0) |
  | `shortlist.remove` | `act_shortlist_remove` | `uid` | |
  | `scout.request_report` | `act_scout_request` | `uid`, `scout_uid` | `duration` ∈ {"week", "month", "full"} (default "week") |
  | `training.set_sessions` | `act_training_sessions` | `changes: list[{date, slot: 0-2, session_type: int}]` (1–21 items) | |
  | `training.set_focus` | `act_training_focus` | `uid`, `type_row: int` (−1 = none) | |
  | `contract.open_renewal` | `act_contract_open` | `uid` | |
  | `contract.offer_renewal` | `act_contract_offer` | `uid` | |

- `actions.validate(kind, args) -> dict` returns normalized args with defaults filled in. It raises `ValueError` naming the problem for: an unknown kind, a missing or extra key, a wrong type, or a value out of range.
- `plans.create(actions: list[{kind, args}], reason: str, summary: str, root=None) -> dict`:
  - validates every action;
  - id = `YYYYmmdd-HHMMSS-<4 hex>`;
  - writes `{id, created, status: "proposed", reason, summary, actions: [{kind, args, describe}]}`.
- `plans.load(id)` and `plans.update(plan)`. Status is one of `proposed`, `applied`, `partial`, `failed`, `refused`. An applied plan cannot be applied again: that raises `ValueError`.
- `backup.make(games_dir=None, root=None) -> {path, sha256, source}`:
  - takes the newest `*.fm` by mtime;
  - raises `BackupError` when there is none or the copy fails;
  - after copying, re-reads the copy and checks its hash.
- `audit.write(entry: dict, path=None)` appends one JSON line with a `time` field. `audit.tail(n) -> list[dict]`.
- `apply.run(plan_id, client, hello) -> dict`:
  1. Refuse when `hello["build_supported"] is not True`: plan → `refused`, audited.
  2. Back up the save. On failure: abort; the plan stays `proposed`; audit `{"result": "backup-failed"}`.
  3. For each action in order:
     - write the token file `~/.fm-assistant/apply/<secrets.token_hex(16)>`, containing `{plan_id, index, kind}`;
     - call the op with `{**args, "apply_token": token}`;
     - the result must carry `verified: true`;
     - audit `{plan_id, index, kind, args, result, backup_sha256}`.
  4. The first failure stops the run. Later actions are audited as `skipped`. Plan status is `partial` if at least one action succeeded, otherwise `failed`.
  5. Delete token files that are still present in a `finally` block.
- CLI:
  - `fm plan create <kind> --arg k=v ... --reason TEXT [--summary TEXT]`. Values are parsed as JSON when possible, else kept as strings. `changes` takes a JSON list.
  - `fm plan create --file actions.json --reason TEXT`
  - `fm plan show <id>`, `fm plan list [--status proposed]`
  - `fm apply <id>`
  - `fm log [--n 20]`
  - Text output for `apply` is one line per action: `ok|FAIL <describe>: <answer or error>`, then `backup: <path> (sha256 <first 12>)`.

- [ ] **Step 1: Write the failing tests** (fake client):
  - `test_validate_rejects_unknown_kind_and_extra_keys`
  - `test_validate_fills_defaults`
  - `test_plan_create_writes_file_and_describe`
  - `test_plan_cannot_apply_twice`
  - `test_backup_copies_newest_and_hashes`
  - `test_apply_aborts_without_backup`
  - `test_apply_refused_on_untested_build`
  - `test_apply_token_one_use`: the token file exists during the call and is gone after; two actions get two different tokens.
  - `test_partial_plan`
  - `test_apply_requires_verified_true`
  - `test_cli_plan_create_and_apply_text`
  - `test_log_tail`
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run them.** Expected: all pass, and the full suite is green.
- [ ] **Step 5: Commit** `feat: plans, closed action registry, backup, audit log and fm apply`.

### Task 2: Act gate, profile route, action dispatch, negotiation read (C#)

**Files:**
- Create: `plugin/src/Ops/Act.cs`
- Modify: `OpsEntry.cs`, `docs/protocol.md` (section "Actions")

**Interfaces:**
- `Act.Gate(args)`:
  - requires `apply_token` (hex, 32 characters);
  - the file `~/.fm-assistant/apply/<token>` must exist;
  - it deletes the file before acting;
  - missing or invalid → `OpException("forbidden", ...)`;
  - the build is not in `TestedBuilds` → `forbidden`.
- `Act.OpenProfile(uid, kind)`:
  - opens via `PanelManager.Open(profile PanelID, "player"|"person", PersonReference)`;
  - waits until `CurrentViewedPlayer` = uid;
  - otherwise `precondition`.
- `Act.Perform(actionId, Func<ActionEntry, bool> leafMatch)`:
  - walks the secondary-tab action tree (folders → leaves);
  - `actionId` must be in the allow-list, otherwise `bad-request`;
  - dispatches through `PluginContextActionsModule.HandleActionEvent(..., checkForConfirmation: true, ...)`;
  - if a `GenericModalDialog` appears, clicks its `buttons-button-primary-default`;
  - on any exception after the dialog appeared, closes it.
- Read op `negotiation {uid}` (no token, no UI): the headless `ContractEditSession` read, with contexts `human` and `BuyingClub` = Human.Club. Result:

  ```
  {open: bool,
   stage: "promises" | "contract" | null,
   wage: {value, display},
   job: text,
   board_max_wage: {value, display} | null,
   patience: {status, value},
   changed_by_other_party: bool,
   read_only: bool,
   key_info: [text]}
  ```

  `{open: false}` when there is no session.
- Every act op returns `{verified: bool, before, after, answer?}` and runs inside `Exclusive`.

- [ ] **Step 1:** Implement `Gate`, `OpenProfile`, `Perform` and `negotiation`, reusing the logic of the phase2-spike `Spike.cs` code (`git show phase2-spike:plugin/src/Ops/Spike.cs`). Do not copy the generic ops.
- [ ] **Step 2: Live.**
  - Call `fm call act_shortlist_add '{"uid": <id>}'` without a token. Expected: `forbidden`.
  - Call with a made-up token. Expected: `forbidden`.
  - `negotiation` on a player with no talks. Expected: `{open: false}`.
- [ ] **Step 3: Commit** `feat(plugin): act gate, profile route, allow-listed action dispatch, negotiation read`.

### Task 3: Shortlist and scout request (F6)

**Files:** `Act.cs` (ops `act_shortlist_add`, `act_shortlist_remove`, `act_scout_request`), `OpsEntry.cs`, `docs/protocol.md`

**Interfaces:**
- `act_shortlist_add {uid, months, apply_token}` → `{verified, before: {shortlisted, count}, after: {...}}`. Verified when `IsShortlisted` is True and the count went up by 1.
  - Already shortlisted → `verified: true, answer: "already"`, with no action.
- `act_shortlist_remove {uid, apply_token}`: the reverse, with confirmation.
- `act_scout_request {uid, scout_uid, duration, apply_token}`:
  - walks the folder whose staff member = `scout_uid`, then the leaf whose `ActionData` duration matches;
  - verified when `IsBeingScouted` is True;
  - `answer: "pending"`, because the report arrives after the date advances;
  - already being scouted → `answer: "already"`.

- [ ] **Step 1:** Implement.
- [ ] **Step 2: Live**, via `fm plan create` + `fm apply`:
  - shortlist add, then a remove plan; the count returns to n;
  - one scout request for a Player Database row;
  - `fm log` shows 3 entries with the backup hash.
- [ ] **Step 3: Commit** `feat(plugin): shortlist and scout request actions`.

### Task 4: Staff approach and offer (F11)

**Files:** `Act.cs` (ops `act_staff_approach`, `act_staff_offer`), `OpsEntry.cs`, `docs/protocol.md`

**Interfaces:**
- `act_staff_approach {uid, apply_token}`:
  - opens the profile and performs `PersonApproachToSign`;
  - the result is `negotiation` plus `demand: {job, wage, end_date}` (the prefilled offer);
  - verified when `negotiation.open` is True.
- `act_staff_offer {uid, wage, apply_token}`:
  - requires an open session for uid, otherwise `precondition` "approach first";
  - `wage > board_max_wage.value` → `precondition`, and nothing is sent;
  - steps the wage with the `-`/`+` SIButtons until the session `Wage` is the largest interval value ≤ `wage`;
  - the job stays as the game prefilled it;
  - sends the propose action (`Event 20`), after checking that the `ActionsForButtonsList` count matches the number of `StandardButton`s;
  - reads back. Result: `{verified, offered: {wage, job}, answer: "accepted"|"countered"|"rejected"|"pending", counter: {wage, job}|null, patience}`.

- [ ] **Step 1:** Implement.
- [ ] **Step 2: Live.**
  - Plan `staff.approach` for a Staff Search candidate on a job with an open slot. Expected: the demand is read.
  - Plan `staff.offer` with `wage` = min(demand, board max). The answer is recorded.
  - A plan with `wage` above the board max. Expected: `precondition`, nothing sent.
- [ ] **Step 3: Commit** `feat(plugin): staff approach and offer actions`.

### Task 5: Training sessions and individual focus (F10)

**Files:** `Act.cs` (ops `act_training_sessions`, `act_training_focus`), `OpsEntry.cs`, `docs/protocol.md`

**Interfaces:**
- `act_training_sessions {changes, apply_token}`:
  - uses the Phase 0 session-card route (`TrainingSessionSelectCard`: slot by `Event.SessionName`, option by session type, then `confirm`);
  - performs the changes in order;
  - reads back the `training` calendar;
  - result `{verified, changes: [{date, slot, before, after}]}`; verified when every slot equals its target.
  - No week templates: they do not restore exactly.
- `act_training_focus {uid, type_row, apply_token}`:
  - opens `TeamIndividualTrainingTool` (guid `41012275212b88b46957d71fc17c5876`, param `team`, first team);
  - selects the player's row by uid;
  - picks the option by its index in `PossibleIndividualTrainingTypes`; `type_row` not in that list → `precondition`;
  - reads back `AdditionalFocus` (`-1` = none). Result `{verified, before, after}`.

- [ ] **Step 1:** Implement.
- [ ] **Step 2: Live.**
  - A plan changing 2 slots, then a plan restoring them. `training show` must equal the start.
  - A focus plan `-1 → x`, then `x → -1`.
- [ ] **Step 3: Commit** `feat(plugin): training session and individual focus actions`.

### Task 6: Contract renewal (F5)

**Files:** `Act.cs` (ops `act_contract_open`, `act_contract_offer`), `OpsEntry.cs`, `docs/protocol.md`

**Interfaces:**
- `act_contract_open {uid, apply_token}`:
  - only for an own first-team player; otherwise `precondition`;
  - performs `PersonOfferContract`;
  - at the promises stage, reads the requested `AgreedPlayingTime`;
  - if it differs from the player's current squad status: `precondition` "promise differs: <requested>". The session is left open so the owner can decide manually, and the response says so.
  - if it is equal: finalizes the promises and moves to the contract stage.
  - result `{verified, promises: {playing_time}, demand: {wage, loyalty_bonus, agent_fee, end_date, bonuses: [text], clauses: [text]}}`.
- `act_contract_offer {uid, apply_token}`:
  - requires the contract stage for uid;
  - sends the prefilled terms as they stand ("finalize deal"); editing the wage or bonuses is a manual step;
  - reads back `read_only`/patience. Result `{verified, answer: "pending"|"accepted"|"rejected"}`.

- [ ] **Step 1:** Implement.
- [ ] **Step 2: Live.** A renewal plan for an own backup player: open, then offer. Expected: `pending`, `read_only` True.
- [ ] **Step 3: Commit** `feat(plugin): contract renewal actions`.

### Task 7: Skill, permissions, MCP, docs, smoke

**Files:** `skills/fm-manager/SKILL.md`, `skills/fm-manager/settings.example.json`, `skills/fm-manager/commands/fm-apply.md`, `fm/src/fm_assistant/mcp_server.py` (+ test), `README.md`, `scripts/smoke.sh`

- [ ] **Step 1: Skill baseline.** One subagent with canned outputs answers:
  - "tawarkan kontrak ke scout terbaik"
  - "masukkan pemain X ke shortlist"
  - "ubah latihan Selasa jadi istirahat"
  - "perpanjang kontrak Y"
  - "langsung aja tawar dia lagi" (after a counter)

  Record misreads.
- [ ] **Step 2: Update the skill.**
  - Approval box: action, target, numbers, reason, and "backup otomatis sebelum apply; aksi sesudah save terakhir hanya bisa dibatalkan dengan load save".
  - `fm plan create`, then show the plan, then wait for the owner's yes before `fm apply`.
  - Report the answer. A counter-offer means a new recommendation and a new approval.
  - Only actions in the registry; everything else stays manual steps.

  Re-test. Expected:
  - the agent never runs `fm apply` without an explicit yes in the conversation;
  - it never sends a counter on its own;
  - it quotes the verify result.
- [ ] **Step 3: Permissions.** `settings.example.json`:
  - allow `fm --json plan*` and `fm --json log*`;
  - **ask** `fm --json apply*` and `fm apply*`;
  - keep the deny rules for `fm call*`, `websocat`, `nc`.
- [ ] **Step 4: MCP.**
  - `propose` tool = `plan create --file` with an inline actions list.
  - `apply` tool = `apply <id>`; its doc says that the client must confirm.
  - `plan_show` and `log` tools.
  - Test: argv mapping.
- [ ] **Step 5: README and smoke.**
  - README: an actions section, the backup and rollback caveat, permission setup.
  - smoke: add `log --n 1` and `plan list`. Smoke never applies anything.
- [ ] **Step 6: End-to-end live.** Through the skill flow: shortlist add, then remove. Then reload the career.
- [ ] **Step 7: Commit** `feat(skill): approval flow for actions`.
