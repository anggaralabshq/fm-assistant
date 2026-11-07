// Discovery aids for Phase 0: which property names exist, what the binding tree holds.
using System;
using System.Text.Json.Nodes;
using SI.Bindable;
using SI.Bindable.Reference.Core;
using SI.Core;

namespace FmSpike;

internal static class Discover
{
    /// {"names":[...]} -> {"<name>": <id or 0>}. 0 = unknown property name in this build.
    public static JsonNode PropCheck(JsonObject args)
    {
        var names = args["names"] as JsonArray ?? throw new OpException("bad-request", "names[] required");
        var o = new JsonObject();
        foreach (var n in names)
        {
            var s = (string)n;
            try { o[s] = (long)PropertyIdentifierSet.Instance.GetID(Il2CppSystem.MemoryExtensions.AsSpan(s)).ID; }
            catch (Exception e) { o[s] = "error: " + e.Message; }
        }
        return o;
    }

    /// {"path":"Human", "depth":2, "max":400} -> nested {name, type, value, children[]}.
    public static JsonNode TreeDump(JsonObject args)
    {
        if (Plugin.Bindings == null) throw new OpException("bindings-not-captured", "BindingSubsystem not initialised yet");
        var path = (string)args["path"] ?? "";
        var depth = (int?)args["depth"] ?? 2;
        var budget = (int?)args["max"] ?? 400;
        var start = path.Length == 0 ? Plugin.Bindings.RootNode : Tree.Find(path);
        if (start == null) throw new OpException("path-not-found", path);
        return Node(start, depth, ref budget);
    }

    private static JsonObject Node(IReadOnlyNode n, int depth, ref int budget)
    {
        budget--;
        var o = new JsonObject { ["name"] = Tree.Name(n) };
        try
        {
            var v = n.Value;
            if (v != null)
            {
                try { o["type"] = v.DataType?.Name; } catch { }
                try { var s = v.AsString(); o["value"] = s != null && s.Length > 200 ? s.Substring(0, 200) : s; } catch { }
            }
        }
        catch { }
        if (depth > 0 && n.FirstChild != null)
        {
            var kids = new JsonArray();
            foreach (var c in n.Children)
            {
                if (budget <= 0) { kids.Add("…truncated"); break; }
                kids.Add(Node(c, depth - 1, ref budget));
            }
            o["children"] = kids;
        }
        return o;
    }
}
