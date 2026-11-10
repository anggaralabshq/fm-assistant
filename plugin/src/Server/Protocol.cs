// Protocol v1 shapes and the op registry. See docs/protocol.md.
using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;

namespace FmAssistant;

/// Expected failure, raised only on the WebSocket thread and sent as {"code", "detail"}.
internal sealed class OpException : Exception
{
    public string Code { get; }
    public OpException(string code, string detail) : base(detail) { Code = code; }
}

/// Main-thread result: main-thread code returns errors instead of throwing (managed exceptions on the
/// IL2CPP-entered thread are the startup-crash suspect, spike/FINDINGS.md "Startup crash").
internal readonly struct R<T>
{
    public readonly T Value;
    public readonly string Code, Detail;
    private R(T v, string code, string detail) { Value = v; Code = code; Detail = detail; }
    public static R<T> Ok(T v) => new R<T>(v, null, null);
    public static R<T> Err(string code, string detail) => new R<T>(default, code, detail);
    public static implicit operator R<T>(T v) => Ok(v);
    public T Unwrap() => Code == null ? Value : throw new OpException(Code, Detail);
}

internal delegate Task<JsonNode> OpHandler(JsonObject args, CancellationToken ct);

internal static class OpRegistry
{
    /// name -> (handler, timeout). Every handler is async; main-thread work hops through Reader.Main.
    public static readonly Dictionary<string, (OpHandler Handler, int TimeoutSeconds)> Ops = new()
    {
        ["hello"] = (Meta.Hello, 10),
        ["diag"] = (Meta.Diag, 5),
        ["panels"] = (Meta.Panels, 10),
        ["ui_dump"] = (Meta.UiDump, 10),
        ["prop_check"] = (Meta.PropCheck, 10),
        ["tree"] = (Meta.Tree, 10),
        ["read"] = (Meta.Read, 60),
        ["load_recent_save"] = (GameOps.LoadRecentSave, 10),
    };

}
