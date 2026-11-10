// hello + discovery ops (panels, ui_dump, prop_check, tree, read). Arguments are validated on the WS thread.
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using SI.Bindable;
using SI.Core;

namespace FmAssistant;

internal static class Meta
{
    public static readonly string[] TestedBuilds = { "27.0.0.2493426" };

    internal static string Str(JsonObject a, string key, bool required = false)
    {
        var n = a[key];
        if (n == null) return required ? throw new OpException("bad-request", $"{key} required") : null;
        return n is JsonValue v && v.TryGetValue<string>(out var s) ? s : throw new OpException("bad-request", $"{key} must be a string");
    }

    internal static int Int(JsonObject a, string key, int dflt, int min = int.MinValue, int max = int.MaxValue)
    {
        var n = a[key];
        if (n == null) return dflt;
        if (n is not JsonValue v || !v.TryGetValue<int>(out var i)) throw new OpException("bad-request", $"{key} must be an integer");
        return Math.Clamp(i, min, max);
    }

    internal static string[] Strs(JsonObject a, string key)
    {
        if (a[key] is not JsonArray arr) throw new OpException("bad-request", $"{key}[] required");
        return arr.Select(n => n is JsonValue v && v.TryGetValue<string>(out var s) ? s : throw new OpException("bad-request", $"{key}[] must hold strings")).ToArray();
    }

    public static async Task<JsonNode> Hello(JsonObject a, CancellationToken ct)
    {
        var (captured, club) = await Reader.Main(() => (Plugin.Bindings != null, FmAssistant.Tree.HumanClubUid()), ct, needBindings: false);
        var tested = new JsonArray();
        foreach (var b in TestedBuilds) tested.Add(b);
        return new JsonObject
        {
            ["plugin"] = "fm-assistant", ["plugin_version"] = Plugin.Version, ["protocol"] = 1,
            ["game_build"] = Plugin.GameBuild, ["build_supported"] = TestedBuilds.Contains(Plugin.GameBuild),
            ["tested_builds"] = tested, ["bindings_captured"] = captured, ["career_loaded"] = club != null,
            ["human_club_uid"] = club,
        };
    }

    public static Task<JsonNode> Panels(JsonObject a, CancellationToken ct) =>
        Reader.Main<JsonNode>(Ui.Panels, ct, needBindings: false);

    /// {"panel": id?, "depth": 12, "max": 400}
    public static Task<JsonNode> UiDump(JsonObject a, CancellationToken ct)
    {
        var panel = Str(a, "panel");
        var depth = Int(a, "depth", 12, 0, 40);
        var max = Int(a, "max", 400, 1, 5000);
        return Reader.MainR(() => Ui.Dump(panel, depth, max), ct, needBindings: false);
    }

    /// {"panel": id, "index": 0, "start": 0, "max": 200} -> {panel, widgets: [{name, type, item_count, columns}], rows: [...]}.
    /// Read-only discovery of list/table backing data (all rows, not only the rendered ones).
    public static Task<JsonNode> ListRows(JsonObject a, CancellationToken ct)
    {
        var panel = Str(a, "panel", required: true);
        var index = Int(a, "index", 0, 0);
        var start = Int(a, "start", 0, 0);
        var max = Int(a, "max", 200, 1, 1000);
        return Reader.MainR<JsonNode>(() =>
        {
            var ws = ListRead.Widgets(panel);
            if (ws.Count == 0) return R<JsonNode>.Err("wrong-screen", $"expected {panel} with a list, open: {Ui.OpenIds()}");
            var meta = new JsonArray();
            foreach (var w in ws)
            {
                string type = "?"; try { type = w.GetIl2CppType().Name; } catch { }
                meta.Add(new JsonObject { ["name"] = w.name, ["type"] = type, ["item_count"] = ListRead.Count(w), ["columns"] = ListRead.Columns(w) });
            }
            return new JsonObject { ["panel"] = panel, ["widgets"] = meta, ["rows"] = ListRead.Rows(ws[Math.Min(index, ws.Count - 1)], max, start) };
        }, ct);
    }

    /// {"names": [...]} -> {"<name>": id or 0}. 0 = unknown property name in this build.
    public static Task<JsonNode> PropCheck(JsonObject a, CancellationToken ct)
    {
        var names = Strs(a, "names");
        return Reader.Main<JsonNode>(() =>
        {
            var o = new JsonObject();
            foreach (var s in names) o[s] = (long)Reader.Id(s);
            return o;
        }, ct);
    }

    /// {"path": "Human", "depth": 2, "max": 400} -> nested {name, type, value, children[]}.
    public static Task<JsonNode> Tree(JsonObject a, CancellationToken ct)
    {
        var path = Str(a, "path") ?? "";
        var depth = Int(a, "depth", 2, 0, 10);
        var max = Int(a, "max", 400, 1, 20000);
        return Reader.MainR<JsonNode>(() =>
        {
            var start = path.Length == 0 ? Plugin.Bindings.RootNode : FmAssistant.Tree.Find(path);
            if (start == null) return R<JsonNode>.Err("bad-request", $"binding path not found: {path}");
            var budget = max;
            return TreeNode(start, depth, ref budget);
        }, ct);
    }

    private static JsonObject TreeNode(IReadOnlyNode n, int depth, ref int budget)
    {
        budget--;
        var o = new JsonObject { ["name"] = FmAssistant.Tree.Name(n) };
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
                kids.Add(TreeNode(c, depth - 1, ref budget));
            }
            o["children"] = kids;
        }
        return o;
    }

    /// {"ref": "person|club|team|path", "uid": 123 | "path": "Human.Club", "props": [...], "wait_ms": 4000,
    ///  "chain": {"FullContract": ["Wage", ...]}} -> decoded props.
    public static async Task<JsonNode> Read(JsonObject a, CancellationToken ct)
    {
        var kind = Str(a, "ref", required: true);
        var props = Strs(a, "props");
        var uid = Int(a, "uid", 0);
        var path = Str(a, "path") ?? "";
        var wait = Int(a, "wait_ms", 4000, 100, 30000);
        Func<TypedValue> parent = kind switch
        {
            "person" => () => Reader.PersonRef(uid),
            "club" => () => Reader.ClubRef(uid),
            "team" => () => Reader.TeamRef(uid),
            "path" => () => FmAssistant.Tree.Find(path)?.Value,
            _ => throw new OpException("bad-request", "ref must be person|club|team|path"),
        };
        var chain = new List<(string Prop, string[] Sub)>();
        if (a["chain"] is JsonObject ch)
            foreach (var kv in ch) chain.Add((kv.Key, Strs(ch, kv.Key)));

        await using var scope = new ReadScope(ct);
        var plant = await scope.ReadOne(parent, props, wait);
        var json = (await scope.Collect(new List<Plant> { plant }))[0];
        foreach (var (prop, sub) in chain)
        {
            var v = plant[prop]?.Value;
            var cp = await scope.ReadOne(() => v, sub, wait);
            json[prop] = (await scope.Collect(new List<Plant> { cp }))[0];
        }
        return json;
    }
}
