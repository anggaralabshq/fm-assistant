// UI Toolkit find/click by visible text. Pointer-event synthesis adapted from redznn/fm-dof-mcp Navigator (MIT).
using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using SI.Bindable;
using SI.Core;
using UnityEngine.UIElements;
using Panel = SI.Bindable.Panel;

namespace FmSpike;

internal static class Ui
{
    private static readonly Regex Tags = new Regex(@"</?[a-zA-Z][^<>]{0,150}>", RegexOptions.Compiled);

    /// Every open panel (FM27: PanelManager has no single RootVisualElement; Panel : VisualElement).
    public static List<Panel> OpenPanels()
    {
        PanelManager pm = null;
        try { pm = ManualSingleton<PanelManager>.Instance; } catch { }
        if (pm == null) throw new OpException("no-ui-root", "PanelManager not available");
        var il = new Il2CppSystem.Collections.Generic.List<Panel>();
        pm.GetAllOpenPanels(il);
        var list = new List<Panel>();
        for (int i = 0; i < il.Count; i++) list.Add(il[i]);
        return list;
    }

    /// [] -> open panels, top-most last: {panel_id, instance, w, h}.
    public static JsonNode Panels(JsonObject args)
    {
        var a = new JsonArray();
        foreach (var p in OpenPanels())
        {
            string id = null; try { id = p.PanelID?.name; } catch { }
            string inst = null; try { inst = p.InstanceName; } catch { }
            var r = p.worldBound;
            a.Add(new JsonObject { ["panel_id"] = id, ["instance"] = inst, ["w"] = (int)r.width, ["h"] = (int)r.height });
        }
        return a;
    }

    internal static string OwnText(VisualElement n)
    {
        try
        {
            var raw = n.TryCast<TextElement>()?.text;
            if (string.IsNullOrWhiteSpace(raw)) return null;
            var s = Tags.Replace(raw, "").Trim().Replace("\n", " / ");
            return s.Length == 0 ? null : (s.Length > 200 ? s.Substring(0, 200) : s);
        }
        catch { return null; }
    }

    internal static bool Visible(VisualElement n)
    {
        try { var r = n.worldBound; return r.width > 0 && r.height > 0 && n.resolvedStyle.display != DisplayStyle.None; }
        catch { return false; }
    }

    internal static void Walk(VisualElement n, int depth, Action<VisualElement> f)
    {
        if (n == null || depth > 80) return;
        f(n);
        for (int i = 0; i < n.childCount; i++) Walk(n[i], depth + 1, f);
    }

    private static JsonObject Row(VisualElement n, string text)
    {
        var r = n.worldBound;
        return new JsonObject { ["name"] = n.name, ["text"] = text, ["x"] = (int)r.center.x, ["y"] = (int)r.center.y, ["w"] = (int)r.width, ["h"] = (int)r.height };
    }

    /// {"text":"contin", "max":60} -> visible text elements whose text contains needle (case-insensitive).
    public static JsonNode Find(JsonObject args)
    {
        var needle = ((string)args["text"] ?? "").ToLowerInvariant();
        var max = (int?)args["max"] ?? 60;
        var rows = new JsonArray();
        foreach (var p in OpenPanels()) Walk(p, 0, n =>
        {
            if (rows.Count >= max) return;
            var t = OwnText(n);
            if (t != null && t.ToLowerInvariant().Contains(needle) && Visible(n)) rows.Add(Row(n, t));
        });
        return rows;
    }

    /// {"text":"Continue", "exact":true} -> click the first visible text element matching; reports what was hit.
    public static JsonNode ClickText(JsonObject args)
    {
        var needle = (string)args["text"] ?? throw new OpException("bad-request", "text required");
        var exact = (bool?)args["exact"] ?? true;
        VisualElement hit = null; string hitText = null;
        var seen = new List<string>();
        foreach (var p in OpenPanels()) Walk(p, 0, n =>
        {
            if (hit != null) return;
            var t = OwnText(n);
            if (t == null || !Visible(n)) return;
            if (seen.Count < 40) seen.Add(t);
            var m = exact ? string.Equals(t, needle, StringComparison.OrdinalIgnoreCase) : t.IndexOf(needle, StringComparison.OrdinalIgnoreCase) >= 0;
            if (m) { hit = n; hitText = t; }
        });
        if (hit == null) throw new OpException("ui-element-missing", $"no visible text '{needle}'; seen: {string.Join(" | ", seen)}");
        Click(hit);
        return Row(hit, hitText);
    }

    internal static void Click(VisualElement hit)
    {
        var pos = hit.worldBound.center;
        var down = PointerDownEvent.GetPooled();
        down.position = pos; down.localPosition = pos; down.button = 0; down.pressedButtons = 1; down.clickCount = 1;
        hit.SendEvent(down);
        var up = PointerUpEvent.GetPooled();
        up.position = pos; up.localPosition = pos; up.button = 0; up.pressedButtons = 0; up.clickCount = 1;
        hit.SendEvent(up);
    }

    /// Binding path behind an SIText (e.g. a property name), null when not a direct binding. Discovery aid.
    internal static string BindPath(VisualElement n)
    {
        try
        {
            var t = n.TryCast<SIText>();
            if (t == null) return null;
            var m = t.m_textBinding;
            var path = m.Direct.Path.Path;
            return string.IsNullOrEmpty(path) ? $"<{m.Kind}>" : path;
        }
        catch { return null; }
    }

    private static string TypeName(VisualElement n)
    {
        try { return n.GetIl2CppType().Name; } catch { return "?"; }
    }

    /// {"panel":"PortalScreen", "depth":12, "max":400} -> visible element tree {name,type,text,x,y,w,h,children}. Language-neutral discovery.
    public static JsonNode Dump(JsonObject args)
    {
        var id = (string)args["panel"];
        var depth = (int?)args["depth"] ?? 12;
        var budget = (int?)args["max"] ?? 400;
        var roots = new JsonArray();
        foreach (var p in OpenPanels())
        {
            string pid = null; try { pid = p.PanelID?.name; } catch { }
            if (id != null && pid != id) continue;
            roots.Add(DumpNode(p, depth, ref budget));
        }
        if (roots.Count == 0) throw new OpException("wrong-screen", $"panel '{id}' not open");
        return roots;
    }

    private static JsonObject DumpNode(VisualElement n, int depth, ref int budget)
    {
        budget--;
        var o = Row(n, OwnText(n));
        o["type"] = TypeName(n);
        var bind = BindPath(n);
        if (bind != null) o["bind"] = bind;
        if (depth > 0 && n.childCount > 0)
        {
            var kids = new JsonArray();
            for (int i = 0; i < n.childCount; i++)
            {
                var c = n[i];
                if (!Visible(c)) continue;
                if (budget <= 0) { kids.Add("…truncated"); break; }
                kids.Add(DumpNode(c, depth - 1, ref budget));
            }
            if (kids.Count > 0) o["children"] = kids;
        }
        return o;
    }

    /// {"name":"ContinueButton", "panel":"PortalScreen"?, "index":0} -> click the visible element with that name (language-neutral).
    public static JsonNode ClickName(JsonObject args)
    {
        var name = (string)args["name"] ?? throw new OpException("bad-request", "name required");
        var id = (string)args["panel"];
        var index = (int?)args["index"] ?? 0;
        var hits = new List<VisualElement>();
        foreach (var p in OpenPanels())
        {
            string pid = null; try { pid = p.PanelID?.name; } catch { }
            if (id != null && pid != id) continue;
            Walk(p, 0, n => { if (n.name == name && Visible(n)) hits.Add(n); });
        }
        if (hits.Count <= index) throw new OpException("ui-element-missing", $"'{name}' visible matches: {hits.Count}");
        Click(hits[index]);
        return Row(hits[index], OwnText(hits[index]));
    }
}
