# FM Assistant

An assistant manager for Football Manager 27 on macOS (Apple Silicon, Steam). It reads your career from the
running game and recommends staff to hire, players to scout, how your budget stands and how heavy your
training load is. You decide; you click.

**Status: read-only.** This release never changes anything in the game: no hiring, no bids, no training
changes, no saving. Actions (each after your approval, with a save backup first) are planned for Phase 2.

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

Back up your save folder before trying anything new; this release only reads, but the loader is third-party.

## Commands

| Command | What you get |
|---|---|
| `fm doctor` | loader, plugin, game build, career, one read per feature |
| `fm club budget` | balance, transfer budget, wage budget / committed / headroom, staff slots |
| `fm squad list [--team first\|reserve\|youth]` | players, positions, condition, injuries |
| `fm squad watch [--within 180]` | contracts ending soon; injured players' return date and matches missed |
| `fm squad depth` | fit players per position against your minimums (`~/.fm-assistant/depth.json`, default 2); no formations |
| `fm staff search --role scout [--top 10]` | Staff Search rows ranked for a role (`staff_roles.json`, overridable in `~/.fm-assistant/`) |
| `fm staff slots` | staff slots per department, with the board's view |
| `fm staff vacancies [--top 3]` | open staff jobs, each with the best Staff Search candidates for it |
| `fm players search [--affordable]` | Player Database rows within your budget, as your scouts know them |
| `fm players targets [--top 5]` | affordable Player Database rows for each thin position |
| `fm training show [--weeks 2]` / `fm training load` | the training calendar; sessions and matches per week, tired players |

Add `--json` before the command for machine output. `scripts/smoke.sh` runs all of them against the live game.

## Unsupported game builds

The plugin is tested against specific game builds (`fm doctor` lists them). On another build every command
still runs but warns on stderr, and the skill says the numbers may be wrong. Game updates can rename the
properties the plugin reads; reads then fail with a clear error instead of guessing.

## Known gaps

- Staff wage demands are not readable outside the contract-offer screen; only current wages are shown.
- Player search returns the Player Database's current filter.
- The training view covers the month the Training screen shows.

See `docs/protocol.md` for the plugin protocol and everything discovered about the game's data.

## Credits

fm-dof-mcp (MIT): binding read patterns and the position bit table. cli-anything-fm27 (Apache-2.0): save
parsing used in development checks. sptndc's FM27 BepInEx loader. See `NOTICE`. Not affiliated with the
makers of Football Manager.
