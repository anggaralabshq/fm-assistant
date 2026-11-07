// HttpListener WebSocket server, localhost only. Shape adapted from redznn/fm-dof-mcp VoiceServer (MIT).
using System;
using System.IO;
using System.Net;
using System.Net.WebSockets;
using System.Text;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;

namespace FmSpike;

internal sealed class WsServer
{
    private const int MaxMessageBytes = 256 * 1024;
    private static readonly TimeSpan JobTimeout = TimeSpan.FromSeconds(20);
    private readonly int _port;
    private HttpListener _listener;

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
            catch (Exception e) { Plugin.L.LogWarning($"[FmSpike] accept: {e.Message}"); await Task.Delay(500); continue; }
            _ = Handle(ctx);
        }
    }

    private static async Task Handle(HttpListenerContext ctx)
    {
        if (!ctx.Request.IsWebSocketRequest) { ctx.Response.StatusCode = 426; ctx.Response.Close(); return; }
        // Browsers always send Origin; our CLI/MCP clients never do. Blocks cross-site WebSocket hijacking from web pages.
        if (!string.IsNullOrEmpty(ctx.Request.Headers["Origin"])) { ctx.Response.StatusCode = 403; ctx.Response.Close(); return; }
        WebSocket ws;
        try { ws = (await ctx.AcceptWebSocketAsync(null)).WebSocket; }
        catch { ctx.Response.StatusCode = 400; ctx.Response.Close(); return; }

        var buf = new byte[16 * 1024];
        var msg = new MemoryStream();
        while (ws.State == WebSocketState.Open)
        {
            WebSocketReceiveResult r;
            try { r = await ws.ReceiveAsync(new ArraySegment<byte>(buf), CancellationToken.None); }
            catch { return; }
            if (r.MessageType == WebSocketMessageType.Close)
            {
                try { await ws.CloseAsync(WebSocketCloseStatus.NormalClosure, null, CancellationToken.None); } catch { }
                return;
            }
            msg.Write(buf, 0, r.Count);
            if (msg.Length > MaxMessageBytes) return;
            if (!r.EndOfMessage) continue;
            var text = Encoding.UTF8.GetString(msg.ToArray());
            msg.SetLength(0);
            var reply = await Respond(text);
            var bytes = Encoding.UTF8.GetBytes(reply.ToJsonString());
            try { await ws.SendAsync(new ArraySegment<byte>(bytes), WebSocketMessageType.Text, true, CancellationToken.None); }
            catch { return; }
        }
    }

    private static async Task<JsonObject> Respond(string text)
    {
        string id = null, op = null;
        try
        {
            var req = JsonNode.Parse(text) as JsonObject ?? throw new OpException("bad-request", "not an object");
            id = (string)req["id"];
            op = (string)req["op"] ?? throw new OpException("bad-request", "missing op");
            var args = req["args"] as JsonObject ?? new JsonObject();
            var job = Plugin.Queue.Run(() => Ops.Dispatch(op, args));
            if (await Task.WhenAny(job, Task.Delay(JobTimeout)) != job)
                throw new OpException("main-thread-timeout", $"{op} did not run within {JobTimeout.TotalSeconds}s");
            return new JsonObject { ["id"] = id, ["ok"] = true, ["result"] = await job };
        }
        catch (Exception e)
        {
            var inner = e is AggregateException ae ? ae.InnerException : e;
            var err = inner is OpException oe ? $"{oe.Code}: {oe.Message}" : $"internal: {inner.GetType().Name}: {inner.Message}";
            if (!(inner is OpException)) Plugin.L.LogError($"[FmSpike] {op}: {inner}");
            return new JsonObject { ["id"] = id, ["ok"] = false, ["error"] = err };
        }
    }
}

/// Expected failures, sent to the client as "code: message".
internal sealed class OpException : Exception
{
    public string Code { get; }
    public OpException(string code, string message) : base(message) { Code = code; }
}
