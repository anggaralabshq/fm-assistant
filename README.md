# FM Assistant

An assistant manager for Football Manager 27 on macOS (Apple Silicon, Steam). It reads your career from the
running game and recommends staff to hire, players to scout, how your budget stands and how heavy your
training load is. You decide.

**Status:** reads everything below; a few actions (staff offers, shortlist, training sessions, contract renewals)
run only after you approve a plan, with a save backup first. It never saves, bids, sells or changes tactics.

## How it works

```
Claude Code skill (fm-manager)  ->  fm CLI (Python)  ->  WebSocket 127.0.0.1 + session token  ->  plugin inside FM27
```

The plugin runs inside the game through a BepInEx loader and reads the same data the game's own screens
bind to, so what you get is what your manager could see: unscouted players show `-` or ranges like `6-10`,
not their true values. Screens are opened by internal panel id, never by on-screen text, so any game
language works.

## Install

1. Install the sptndc FM27 BepInEx loader (macOS arm64) and set the Steam launch options it documents.
   The original game app is not modified.
2. Build and install the plugin: `bash plugin/build.sh` (needs the .NET 6 SDK; the loader's generated
   interop assemblies must exist, i.e. start the game once through the loader).
3. Install the CLI: `uv tool install ./fm`.
4. Start FM27 from Steam, load your career, then run `fm doctor`.
5. Optional, for Claude Code: copy `skills/fm-manager` into `~/.claude/skills/`, the files in its `commands/`
   into `~/.claude/commands/`, and merge `settings.example.json` into your settings.

Back up your save folder before trying anything new; the loader is third-party.

## Commands

| Command | What you get |
|---|---|
| `fm doctor` | loader, plugin, game build, career, one read per feature |
| `fm briefing` | one-screen session summary: next match, injuries, tired, contracts, concerns, form, vacancies, loans |
| `fm fixtures [--n 5]` | upcoming matches (home/away, competition) and the assistant's note on the next opponent |
| `fm club budget` | balance, transfer budget, wage budget / committed / headroom, staff slots |
| `fm squad list [--team first\|reserve\|youth]` | players, positions, condition, injuries |
| `fm squad watch [--within 180]` | contracts ending soon; injured players' return date and matches missed |
| `fm squad depth` | fit players per position against your minimums (`~/.fm-assistant/depth.json`, default 2); no formations |
| `fm squad contracts` | squad status, contract end, release clause, against the game's wage structure |
| `fm squad form` | season appearances and rating, last five matches, unhappy players, club atmosphere |
| `fm squad loans` | players out on loan with their games and rating; youth intake date |
| `fm staff search --role scout [--top 10]` | Staff Search rows ranked for a role (`staff_roles.json`, overridable in `~/.fm-assistant/`) |
| `fm staff slots` | staff slots per department, with the board's view |
| `fm staff vacancies [--top 3]` | open staff jobs, each with the best Staff Search candidates for it |
| `fm players search [--affordable]` | Player Database rows within your budget, as your scouts know them |
| `fm players targets [--top 5]` | affordable Player Database rows for each thin position |
| `fm training show [--weeks 2]` / `fm training load` | the training calendar; sessions and matches per week, tired players |
| `fm inbox [--unread] [--since DATE]` | inbox messages, newest first; `*` unread, `!` important |
| `fm tactic` | the active tactic's slots, roles and players; who is out of position, injured or tired (facts only) |
| `fm squad rotation [--days 7]` | before congested fixtures: XI players injured or tired, with fitter options per slot |
| `fm snapshot` / `fm trends` | save today's club and squad state; compare with the latest earlier snapshot (`~/.fm-assistant/snapshots/`) |

Add `--json` before the command for machine output. `scripts/smoke.sh` runs all of them against the live game.

## Actions (after approval)

The assistant can do a few things in the game, only through a plan you approve:

| Kind | What it does |
|---|---|
| `staff.approach` / `staff.offer` | open contract talks with a staff member; send one offer at a wage up to the board's maximum |
| `shortlist.add` / `shortlist.remove` | add a player to, or take one off, the shortlist |
| `scout.request_report` | ask one of your scouts for a report on a player |
| `training.set_sessions` / `training.set_focus` | change sessions in the training calendar; set a player's individual focus |
| `contract.open_renewal` / `contract.offer_renewal` | open renewal talks with your own player; send the terms you approved, once |

```bash
fm plan create shortlist.add --arg uid=123456 --reason "winger cover"   # writes a plan, nothing happens yet
fm plan show <id>
fm apply <id>          # backs up the newest save, performs each action, reads the result back
fm log --n 5           # audit log (~/.fm-assistant/log.jsonl)
```

- Only the kinds above exist; the plugin also checks a one-use token that only `fm apply` writes. It never accepts
  bids, sells, releases, terminates contracts or changes tactics, and it never answers a counter-offer by itself.
- Before acting, `fm apply` copies the newest save to `~/.fm-assistant/backups/<time>/` with a SHA-256. The game
  holds the changes in memory until you save. **Rollback = load a save from before the change**; once you have
  saved, the backup copy is the only way back (copy it over the save in the game's `games/` folder with the game
  closed).
- Actions refuse to run on an untested game build.
- `settings.example.json` lets the skill write plans and read the log on its own, and asks you before every
  `fm apply`.

## MCP server

Read tools plus `propose` (writes a plan), `plan_show`, `log` and `apply`. `apply` changes the game: the client
must ask you before each call. There are no tools that launch, restart, load or call anything else in the game.

`fm-mcp` runs over stdio; each tool runs `fm --json ...`, and errors come back as `{"ok": false, "error": {...}}`.

```bash
cd fm && uv sync --extra mcp
claude mcp add fm-assistant -- uv run --directory /path/to/fm-cli/fm --extra mcp fm-mcp
```

Claude Desktop (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{"mcpServers": {"fm-assistant": {"command": "uv",
  "args": ["run", "--directory", "/path/to/fm-cli/fm", "--extra", "mcp", "fm-mcp"]}}}
```

New CLI commands become tools by adding one `Tool(...)` line to `TOOLS` in `fm/src/fm_assistant/mcp_server.py`.

## Unsupported game builds

The plugin is tested against specific game builds (`fm doctor` lists them). On another build every command
still runs but warns on stderr, and the skill says the numbers may be wrong. Game updates can rename the
properties the plugin reads; reads then fail with a clear error instead of guessing.

## Known gaps

- Staff wage demands are not readable outside the contract-offer screen; only current wages are shown.
- Player search returns the Player Database's current filter.
- The training view covers the month the Training screen shows.
- Scout report requests and individual training focus exist in the plugin but the skill leaves them manual: no read
  shows your scouts' ids or the focus option names yet.

See `docs/protocol.md` for the plugin protocol and everything discovered about the game's data.

## Credits

fm-dof-mcp (MIT): binding read patterns and the position bit table. cli-anything-fm27 (Apache-2.0): save
parsing used in development checks. sptndc's FM27 BepInEx loader. See `NOTICE`. Not affiliated with the
makers of Football Manager.
