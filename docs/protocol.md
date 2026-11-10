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

Listed with their arguments as they are added (see the end of this file).
