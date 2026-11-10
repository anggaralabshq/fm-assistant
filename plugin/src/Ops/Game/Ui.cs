// UI Toolkit helpers: open panels, element walk, binding paths, synthetic click.
// Pointer-event synthesis adapted from redznn/fm-dof-mcp Navigator (MIT). Main thread only.
using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using SI.Bindable;
using SI.Core;
using UnityEngine.UIElements;
using Panel = SI.Bindable.Panel;

namespace FmAssistant;

internal static class Ui
{
    private static readonly Regex Tags = new Regex(@"</?[a-zA-Z][^<>]{0,150}>", RegexOptions.Compiled);

    /// Every open panel, top-most last; empty when the UI is not up yet.
    public static List<Panel> OpenPanels()
    {
        var list = new List<Panel>();
        PanelManager pm = null;
        try { pm = ManualSingleton<PanelManager>.Instance; } catch { }
        if (pm == null) return list;
        var il = new Il2CppSystem.Collections.Generic.List<Panel>();
        pm.GetAllOpenPanels(il);
        for (int i = 0; i < il.Count; i++) list.Add(il[i]);
        return list;
    }

    public static string PanelId(Panel p)
    {
        try { return p.PanelID?.name; } catch { return null; }
    }

    public static bool IsOpen(string panelId) => OpenPanels().Exists(p => PanelId(p) == panelId);

    public static string OpenIds() => string.Join(", ", OpenPanels().ConvertAll(PanelId));

    public static JsonArray Panels()
    {
        var a = new JsonArray();
        foreach (var p in OpenPanels())
        {
            string inst = null; try { inst = p.InstanceName; } catch { }
            var r = p.worldBound;
            a.Add(new JsonObject { ["panel_id"] = PanelId(p), ["instance"] = inst, ["w"] = (int)r.width, ["h"] = (int)r.height });
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

    internal static JsonObject Row(VisualElement n, string text)
    {
        var r = n.worldBound;
        return new JsonObject { ["name"] = n.name, ["text"] = text, ["x"] = (int)r.center.x, ["y"] = (int)r.center.y, ["w"] = (int)r.width, ["h"] = (int)r.height };
    }

    /// Synthetic left click at the element's centre. Pooled events are disposed after dispatch.
    internal static void Click(VisualElement hit)
    {
        var pos = hit.worldBound.center;
        var down = PointerDownEvent.GetPooled();
        try
        {
            down.position = pos; down.localPosition = pos; down.button = 0; down.pressedButtons = 1; down.clickCount = 1;
            hit.SendEvent(down);
        }
        finally { down.Dispose(); }
        var up = PointerUpEvent.GetPooled();
        try
        {
            up.position = pos; up.localPosition = pos; up.button = 0; up.pressedButtons = 0; up.clickCount = 1;
            hit.SendEvent(up);
        }
        finally { up.Dispose(); }
    }

    /// Binding path behind an SIText (e.g. a property name), null when not a direct binding.
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

    /// Visible element tree {name,type,text,bind,x,y,w,h,children} of one panel (or all). Discovery aid.
    public static R<JsonNode> Dump(string panelId, int depth, int budget)
    {
        var roots = new JsonArray();
        foreach (var p in OpenPanels())
        {
            if (panelId != null && PanelId(p) != panelId) continue;
            roots.Add(DumpNode(p, depth, ref budget));
        }
        if (roots.Count == 0) return R<JsonNode>.Err("wrong-screen", $"panel '{panelId}' not open; open: {OpenIds()}");
        return roots;
    }

    /// BindingRemapper: {from -> to path} (where a cell's "binding.X" variable comes from). Discovery aid.
    private static JsonObject Remaps(VisualElement n)
    {
        try
        {
            var r = n.TryCast<SI.Bindable.BindingRemapper>();
            if (r == null || r.Mappings == null) return null;
            var o = new JsonObject();
            foreach (var m in r.Mappings) o[m.from ?? "?"] = m.to.Path;
            return o;
        }
        catch (Exception e) { return new JsonObject { ["error"] = e.GetType().Name }; }
    }

    private static JsonObject DumpNode(VisualElement n, int depth, ref int budget)
    {
        budget--;
        var o = Row(n, OwnText(n));
        o["type"] = TypeName(n);
        var bind = BindPath(n);
        if (bind != null) o["bind"] = bind;
        var remap = Remaps(n);
        if (remap != null) o["remap"] = remap;
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
}
