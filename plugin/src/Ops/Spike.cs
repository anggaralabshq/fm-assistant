// Phase 1d spike: context-bound property discovery (dev mode only). Read-only.
using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using SI.Bindable;
using SI.Bindable.Reference.Core;
using SI.Core;

namespace FmAssistant;

internal static class Spike
{
    private static Func<TypedValue> Parent(JsonObject a)
    {
        var kind = Meta.Str(a, "ref", required: true);
        var uid = Meta.Int(a, "uid", 0);
        var path = Meta.Str(a, "path") ?? "";
        return kind switch
        {
            "person" => () => Reader.PersonRef(uid),
            "club" => () => Reader.ClubRef(uid),
            "team" => () => Reader.TeamRef(uid),
            "path" => () => FmAssistant.Tree.Find(path)?.Value,
            _ => throw new OpException("bad-request", "ref must be person|club|team|path"),
        };
    }

    /// {"ref", "uid"|"path", "props": [...]} -> {prop: {handler, contexts: [...]}}: what each property's data handler
    /// says it needs (Bindings.GetHandler's outRequiredContext).
    public static Task<JsonNode> CtxProbe(JsonObject a, CancellationToken ct)
    {
        var parent = Parent(a);
        var props = Meta.Strs(a, "props");
        return Reader.MainR<JsonNode>(() =>
        {
            var tv = parent();
            if (tv == null) return R<JsonNode>.Err("bad-request", "no parent value");
            var o = new JsonObject();
            string st = "?"; try { st = tv.DataType?.Name; } catch { }
            o["_source_type"] = st;
            foreach (var name in props)
            {
                var r = new JsonObject();
                try
                {
                    var id = PropertyIdentifierSet.Instance.GetID(Il2CppSystem.MemoryExtensions.AsSpan(name));
                    if (id.ID == 0) { r["error"] = "unknown-property"; o[name] = r; continue; }
                    var list = new Il2CppSystem.Collections.Generic.List<string>();
                    var h = Plugin.Bindings.GetHandler(tv, new Bindings.Property(name, id), list);
                    string ht = null; try { ht = h == null ? null : ((Il2CppSystem.Object)h.Cast<Il2CppSystem.Object>()).GetIl2CppType().FullName; } catch { }
                    r["handler"] = ht;
                    var ctx = new JsonArray();
                    for (var i = 0; i < list.Count; i++) ctx.Add(list[i]);
                    r["contexts"] = ctx;
                }
                catch (Exception e) { r["error"] = $"{e.GetType().Name}: {e.Message}"; }
                o[name] = r;
            }
            return o;
        }, ct);
    }

    /// Main thread. Which of `names` have a data handler on `tv`, with their required contexts ({name: [ctx]}).
    public static JsonObject Handlers(TypedValue tv, string[] names)
    {
        var o = new JsonObject();
        if (tv == null) return o;
        foreach (var name in names)
        {
            try
            {
                var id = PropertyIdentifierSet.Instance.GetID(Il2CppSystem.MemoryExtensions.AsSpan(name));
                if (id.ID == 0) continue;
                var list = new Il2CppSystem.Collections.Generic.List<string>();
                if (Plugin.Bindings.GetHandler(tv, new Bindings.Property(name, id), list) == null) continue;
                var ctx = new JsonArray();
                for (var i = 0; i < list.Count; i++) ctx.Add(list[i]);
                o[name] = ctx;
            }
            catch { }
        }
        return o;
    }

    /// {"max": 4096} -> registered binding context ids -> names.
    public static Task<JsonNode> CtxNames(JsonObject a, CancellationToken ct)
    {
        var max = Meta.Int(a, "max", 4096, 1, 1 << 20);
        return Reader.MainR<JsonNode>(() =>
        {
            var o = new JsonObject();
            var set = ContextIdentifierSet.Instance;
            for (uint i = 0; i < max; i++)
            {
                try
                {
                    if (!set.HasID(i)) continue;
                    var info = set.GetInfo(i);
                    o[i.ToString()] = info?.Name;
                }
                catch { }
            }
            return o;
        }, ct);
    }

    /// {"panel": id, "max": 500} -> every visible text of an open panel at any depth: [{text, bind, name, x, y}]
    /// (ui_dump stops at depth 40; the tactics pitch is deeper). Dev, read-only.
    public static Task<JsonNode> UiTexts(JsonObject a, CancellationToken ct)
    {
        var panel = Meta.Str(a, "panel", required: true);
        var max = Meta.Int(a, "max", 500, 1, 5000);
        return Reader.MainR<JsonNode>(() =>
        {
            var arr = new JsonArray();
            foreach (var p in Ui.OpenPanels())
            {
                if (Ui.PanelId(p) != panel) continue;
                Ui.Walk(p, 0, n =>
                {
                    if (arr.Count >= max || !Ui.Visible(n)) return;
                    var t = Ui.OwnText(n);
                    if (t == null) return;
                    var r = Ui.Row(n, t);
                    r["bind"] = Ui.BindPath(n);
                    arr.Add(r);
                });
            }
            return arr;
        }, ct);
    }

    /// {"panel": id, "max": 20} -> star widgets of an open panel: bindings, unmapped (bound) and mapped (drawn) values.
    public static Task<JsonNode> StarsDump(JsonObject a, CancellationToken ct)
    {
        var panel = Meta.Str(a, "panel", required: true);
        var max = Meta.Int(a, "max", 20, 1, 500);
        return Reader.MainR<JsonNode>(() =>
        {
            var arr = new JsonArray();
            foreach (var p in Ui.OpenPanels())
            {
                if (Ui.PanelId(p) != panel) continue;
                Ui.Walk(p, 0, n =>
                {
                    if (arr.Count >= max) return;
                    var w = n.TryCast<FM.UI.FMStarRatingTemp>();
                    if (w == null) return;
                    var o = new JsonObject();
                    try { o["min_bind"] = w.MinBinding.Path; } catch { }
                    try { o["max_bind"] = w.MaxBinding.Path; } catch { }
                    try { o["unmapped"] = $"{w.m_unmappedMinValue}-{w.m_unmappedMaxValue}"; } catch { }
                    try { o["mapped"] = $"{w.m_minValue}-{w.m_maxValue}"; } catch { }
                    try { var r = w.worldBound; o["y"] = (int)r.center.y; o["x"] = (int)r.center.x; } catch { }
                    arr.Add(o);
                });
            }
            return arr;
        }, ct);
    }

    /// Main thread. Fields of an il2cpp object (il2cpp reflection), values as text, nested objects one level deep.
    /// ScriptableObject settings only: run over a VisualElement (FMStarRatingTemp) it crashed the game (native).
    private static JsonObject Fields(Il2CppSystem.Object o, int depth)
    {
        var r = new JsonObject();
        if (o == null) return r;
        Il2CppSystem.Type t = null;
        try { t = o.GetIl2CppType(); r["$type"] = t.FullName; } catch { return r; }
        var flags = Il2CppSystem.Reflection.BindingFlags.Instance | Il2CppSystem.Reflection.BindingFlags.Public | Il2CppSystem.Reflection.BindingFlags.NonPublic;
        foreach (var f in t.GetFields(flags))
        {
            try
            {
                var v = f.GetValue(o);
                string ft = f.FieldType.FullName ?? "";
                if (v == null) r[f.Name] = null;
                else if (depth > 0 && !f.FieldType.IsPrimitive && !f.FieldType.IsEnum && ft != "System.String") r[f.Name] = Fields(v, depth - 1);
                else r[f.Name] = v.ToString();
            }
            catch (Exception e) { r[f.Name] = $"<{e.GetType().Name}>"; }
        }
        return r;
    }

    /// {} -> every loaded FMStarRatingSettings asset: its youth / non-youth configuration fields (dev, read-only).
    public static Task<JsonNode> StarsSettings(JsonObject a, CancellationToken ct) => Reader.MainR<JsonNode>(() =>
    {
        var arr = new JsonArray();
        foreach (var o in UnityEngine.Resources.FindObjectsOfTypeAll(Il2CppInterop.Runtime.Il2CppType.Of<FM.UI.FMStarRatingSettings>()))
            arr.Add(Fields(o.Cast<Il2CppSystem.Object>(), 2));
        return arr;
    }, ct);

    private static FM.UI.EmbeddedDataHandler.PersonReferenceClickedHandler PersonClick()
    {
        foreach (var o in UnityEngine.Resources.FindObjectsOfTypeAll(Il2CppInterop.Runtime.Il2CppType.Of<FM.UI.EmbeddedDataHandler>()))
        {
            var h = o.TryCast<FM.UI.EmbeddedDataHandler>()?.m_personReferenceClickedHandler;
            if (h != null) return h;
        }
        return null;
    }

    private static string Guid(UnityEngine.AddressableAssets.AssetReference r)
    {
        try { return r?.AssetGUID; } catch { return null; }
    }

    /// {} -> the game's person-link click handler config: profile PanelID GUIDs and parameter names.
    public static Task<JsonNode> ProfileInfo(JsonObject a, CancellationToken ct) => Reader.MainR<JsonNode>(() =>
    {
        var h = PersonClick();
        if (h == null) return R<JsonNode>.Err("ui-element-missing", "EmbeddedDataHandler not loaded");
        return new JsonObject
        {
            ["player_panel"] = Guid(h.m_playerPanelRef), ["player_param"] = h.m_playerParamName,
            ["team_param"] = h.m_teamParamName, ["comp_param"] = h.m_compParamName,
            ["nonplayer_panel"] = Guid(h.m_nonPlayerPanelRef), ["nonplayer_param"] = h.m_nonPlayerParamName,
            ["npr_team_param"] = h.m_nprTeamParamName, ["agent_panel"] = Guid(h.m_agentPanelRef),
            ["retired_panel"] = Guid(h.m_retiredPanelRef), ["human_panel"] = Guid(h.m_humanPanelRef),
            ["team_context_name"] = h.m_teamContextName, ["international_context"] = h.m_internationalContext,
            ["player_in_match_panel"] = Guid(h.m_playerInMatchPanelRef),
        };
    }, ct);

    /// {"uid": person, "kind": "player"|"nonplayer"} -> opens that person's profile the way a person link does
    /// (PanelManager.Open(profile PanelID, paramName, person)). A view only: no offer/negotiation is opened.
    public static async Task<JsonNode> ProfileOpen(JsonObject a, CancellationToken ct)
    {
        var uid = Meta.Int(a, "uid", 0, 1);
        var kind = Meta.Str(a, "kind") ?? "player";
        if (kind != "player" && kind != "nonplayer") throw new OpException("bad-request", "kind must be player|nonplayer");
        await Reader.MainR(Nav.OnGameScreens, ct);
        var t0 = Environment.TickCount64;
        var before = await Reader.Main(Ui.OpenIds, ct);
        await Reader.MainR<bool>(() =>
        {
            var h = PersonClick();
            if (h == null) return R<bool>.Err("ui-element-missing", "EmbeddedDataHandler not loaded");
            var guid = Guid(kind == "player" ? h.m_playerPanelRef : h.m_nonPlayerPanelRef);
            var param = kind == "player" ? h.m_playerParamName : h.m_nonPlayerParamName;
            if (string.IsNullOrEmpty(guid) || string.IsNullOrEmpty(param)) return R<bool>.Err("binding-api-changed", "profile panel ref missing");
            ManualSingleton<PanelManager>.Instance.Open(new UnityEngine.AddressableAssets.AssetReferenceT<PanelID>(guid), param,
                Reader.PersonRef(uid), null, null, RebindMethod.None);
            return true;
        }, ct);
        string after = before;
        var end = Environment.TickCount64 + 8000;
        while (Environment.TickCount64 < end)
        {
            await Task.Delay(250, ct);
            after = await Reader.Main(Ui.OpenIds, ct);
            if (after != before) { await Task.Delay(750, ct); after = await Reader.Main(Ui.OpenIds, ct); break; }
        }
        return new JsonObject { ["before"] = before, ["after"] = after, ["ms"] = Environment.TickCount64 - t0 };
    }

    /// {"guid": PanelID GUID, "param": "team", "team_uid": n} -> opens a team-scoped screen (e.g. a youth squad's
    /// SquadScreen) the way a navigation entry with an object does: PanelManager.Open(PanelID, param, TeamReference).
    /// A view only. Dev mode, UI lock, normal game screens only.
    public static async Task<JsonNode> TeamPanelOpen(JsonObject a, CancellationToken ct)
    {
        var guid = Meta.Str(a, "guid", required: true);
        var param = Meta.Str(a, "param") ?? "team";
        var uid = Meta.Int(a, "team_uid", 0, 1);
        if (guid.Length != 32) throw new OpException("bad-request", "guid must be 32 hex chars");
        await Reader.MainR(Nav.OnGameScreens, ct);
        var before = await Reader.Main(Ui.OpenIds, ct);
        await Reader.MainR<bool>(() =>
        {
            ManualSingleton<PanelManager>.Instance.Open(new UnityEngine.AddressableAssets.AssetReferenceT<PanelID>(guid), param,
                Reader.TeamRef(uid), null, null, RebindMethod.None);
            return true;
        }, ct);
        string after = before;
        var end = Environment.TickCount64 + 8000;
        while (Environment.TickCount64 < end)
        {
            await Task.Delay(250, ct);
            after = await Reader.Main(Ui.OpenIds, ct);
            if (after != before) { await Task.Delay(1500, ct); after = await Reader.Main(Ui.OpenIds, ct); break; }
        }
        return new JsonObject { ["before"] = before, ["after"] = after };
    }

    /// {"path": "" (root), "names": [...], "max_nodes": 200000} -> nodes (by value type, first path seen) where any
    /// of the names has a data handler. Walks the binding tree; GetHandler only (no channel is opened).
    public static Task<JsonNode> TreeProbe(JsonObject a, CancellationToken ct)
    {
        var path = Meta.Str(a, "path") ?? "";
        var names = Meta.Strs(a, "names");
        var maxNodes = Meta.Int(a, "max_nodes", 200000, 1, 2000000);
        return Reader.MainR<JsonNode>(() =>
        {
            var start = path.Length == 0 ? Plugin.Bindings.RootNode : FmAssistant.Tree.Find(path);
            if (start == null) return R<JsonNode>.Err("bad-request", "path not found");
            var seenTypes = new HashSet<string>();
            var hits = new JsonObject();
            var budget = maxNodes;
            var stack = new Stack<(IReadOnlyNode N, string P, int D)>();
            stack.Push((start, FmAssistant.Tree.Name(start), 0));
            while (stack.Count > 0 && budget-- > 0)
            {
                var (n, p, d) = stack.Pop();
                try
                {
                    var v = n.Value;
                    if (v != null)
                    {
                        string t = null; try { t = v.DataType?.FullName; } catch { }
                        if (t != null && seenTypes.Add(t))
                        {
                            var h = Handlers(v, names);
                            if (h.Count > 0) hits[t] = new JsonObject { ["path"] = p, ["handled"] = h };
                        }
                    }
                }
                catch { }
                if (d >= 40 || n.FirstChild == null) continue;
                foreach (var c in n.Children) stack.Push((c, p + "." + FmAssistant.Tree.Name(c), d + 1));
            }
            hits["_types_seen"] = seenTypes.Count;
            return hits;
        }, ct);
    }
}
