// HttpListener WebSocket server, localhost only. Shape adapted from redznn/fm-dof-mcp VoiceServer (MIT).
using System;
using System.IO;
using System.Net;
using System.Net.WebSockets;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;

namespace FmAssistant;

internal sealed class WsServer
{
    public const int MaxMessageBytes = 256 * 1024;
    private const int MaxConnections = 4;
    private readonly int _port;
    private HttpListener _listener;
    private static int _open;

    public WsServer(int port) { _port = port; }

    public void Start()
    {
        _listener = new HttpListener();
        _listener.Prefixes.Add($"http://127.0.0.1:{_port}/");
        _listener.Start();
        Task.Run(AcceptLoop);
    }

    private async Task AcceptLoop()
    {
        while (true)
        {
            HttpListenerContext ctx;
            try { ctx = await _listener.GetContextAsync(); }
            catch (Exception e) { Plugin.L.LogWarning($"accept: {e.Message}"); await Task.Delay(500); continue; }
            _ = Task.Run(() => Handle(ctx));
        }
    }

    private static async Task Handle(HttpListenerContext ctx)
    {
        if (!ctx.Request.IsWebSocketRequest) { ctx.Response.StatusCode = 426; ctx.Response.Close(); return; }
        // Browsers always send Origin; local clients never do. Blocks cross-site WebSocket hijacking from web pages.
        if (!string.IsNullOrEmpty(ctx.Request.Headers["Origin"])) { ctx.Response.StatusCode = 403; ctx.Response.Close(); return; }
        if (Interlocked.Increment(ref _open) > MaxConnections)
        {
            Interlocked.Decrement(ref _open);
            ctx.Response.StatusCode = 503; ctx.Response.Close(); return;
        }
        try { await Serve(ctx); }
        catch (Exception e) { Plugin.L.LogWarning($"connection: {e.Message}"); }
        finally { Interlocked.Decrement(ref _open); }
    }

    private static async Task Serve(HttpListenerContext ctx)
    {
        WebSocket ws;
        try { ws = (await ctx.AcceptWebSocketAsync(null)).WebSocket; }
        catch { ctx.Response.StatusCode = 400; ctx.Response.Close(); return; }

        var buf = new byte[16 * 1024];
        var msg = new MemoryStream();
        while (ws.State == WebSocketState.Open)
        {
            var r = await ws.ReceiveAsync(new ArraySegment<byte>(buf), CancellationToken.None);
            if (r.MessageType == WebSocketMessageType.Close)
            {
                await ws.CloseAsync(WebSocketCloseStatus.NormalClosure, null, CancellationToken.None);
                return;
            }
            msg.Write(buf, 0, r.Count);
            if (msg.Length > MaxMessageBytes)
            {
                Plugin.L.LogWarning($"closing connection: message over {MaxMessageBytes} bytes");
                // CloseOutputAsync sends the close frame without waiting for the peer's echo (CloseAsync could hang
                // while the peer is still streaming the oversized message).
                await ws.CloseOutputAsync(WebSocketCloseStatus.MessageTooBig, "message too big", CancellationToken.None);
                ws.Abort();
                ctx.Response.Abort();  // HttpListener keeps the TCP connection open otherwise; the peer waits for EOF
                return;
            }
            if (!r.EndOfMessage) continue;
            var text = Encoding.UTF8.GetString(msg.ToArray());
            msg.SetLength(0);
            var reply = await Respond(text);
            await ws.SendAsync(new ArraySegment<byte>(Encoding.UTF8.GetBytes(reply.ToJsonString())),
                WebSocketMessageType.Text, true, CancellationToken.None);
        }
    }

    private static JsonObject Error(JsonNode id, string code, string detail) => new()
    {
        ["v"] = 1, ["id"] = id?.DeepCloneSafe(), ["ok"] = false,
        ["error"] = new JsonObject { ["code"] = code, ["detail"] = detail },
    };

    internal static async Task<JsonObject> Respond(string text)
    {
        JsonObject req;
        try { req = JsonNode.Parse(text) as JsonObject; }
        catch (JsonException) { req = null; }
        if (req == null) return Error(null, "bad-request", "request is not a JSON object");
        var idNode = req["id"];
        if (idNode is not JsonValue iv || !iv.TryGetValue<string>(out var id)) return Error(idNode, "bad-request", "id must be a string");
        if (!Session.Check(req["token"] is JsonValue tv && tv.TryGetValue<string>(out var t) ? t : null))
            return Error(id, "unauthorized", "missing or wrong session token");
        if (req["op"] is not JsonValue ov || !ov.TryGetValue<string>(out var op)) return Error(id, "bad-request", "op must be a string");
        var args = req["args"] ?? new JsonObject();
        if (args is not JsonObject argsObj) return Error(id, "bad-request", "args must be an object");
        if (!OpRegistry.Ops.TryGetValue(op, out var entry)) return Error(id, "unknown-op", op);

        using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(entry.TimeoutSeconds));
        try
        {
            // Re-parse args so the handler owns a detached node.
            var job = entry.Handler(JsonNode.Parse(argsObj.ToJsonString()) as JsonObject, cts.Token);
            var done = await Task.WhenAny(job, Task.Delay(TimeSpan.FromSeconds(entry.TimeoutSeconds + 1)));
            if (done != job) return Error(id, "main-thread-timeout", $"{op} did not finish within {entry.TimeoutSeconds}s");
            return new JsonObject { ["v"] = 1, ["id"] = id, ["ok"] = true, ["result"] = await job };
        }
        catch (Exception e)
        {
            var inner = e is AggregateException ae ? ae.InnerException : e;
            switch (inner)
            {
                case OpException oe: return Error(id, oe.Code, oe.Message);
                case OperationCanceledException: return Error(id, "main-thread-timeout", $"{op} did not finish within {entry.TimeoutSeconds}s");
                default:
                    Plugin.L.LogError($"{op}: {inner}");
                    return Error(id, "internal", $"{inner.GetType().Name}: {inner.Message}");
            }
        }
    }
}

internal static class JsonExt
{
    /// JsonNode has no DeepClone on net6; round-trip through text.
    public static JsonNode DeepCloneSafe(this JsonNode n) => n == null ? null : JsonNode.Parse(n.ToJsonString());
}
