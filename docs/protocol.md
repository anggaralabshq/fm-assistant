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
| `diag` | – | `{ticks, last_tick_ms_ago, queued, bindings_captured}`; answered without the main thread (is the game's frame tick reaching the plugin?) | WS |
| `panels` | – | `[{panel_id, instance, w, h}]`, top-most last | main |
| `ui_dump` | `panel?`, `depth=12`, `max=400` | visible element tree `{name, type, text, bind, x, y, w, h, children}` | main |
| `prop_check` | `names[]` | `{name: property id}`; 0 = unknown in this build | main |
| `tree` | `path=""`, `depth=2`, `max=400` | binding tree `{name, type, value, children}` | main |
| `read` | `ref: person\|club\|team\|path`, `uid` or `path`, `props[]`, `wait_ms=4000`, `chain: {prop: [subprops]}` | decoded props; unresolved ones under `_missing` | main + polling |
| `load_recent_save` | – | `{clicked: true}`; clicks MainMenu's `LoadMostRecentSave` tile; refuses when a career is loaded | main |

There is no generic click op. Discovery ops are read-only.
