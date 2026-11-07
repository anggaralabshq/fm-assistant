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
    private static List<Panel> OpenPanels()
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

    private static string OwnText(VisualElement n)
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

    private static bool Visible(VisualElement n)
    {
        try { var r = n.worldBound; return r.width > 0 && r.height > 0 && n.resolvedStyle.display != DisplayStyle.None; }
        catch { return false; }
    }

    private static void Walk(VisualElement n, int depth, Action<VisualElement> f)
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
        var pos = hit.worldBound.center;
        var down = PointerDownEvent.GetPooled();
        down.position = pos; down.localPosition = pos; down.button = 0; down.pressedButtons = 1; down.clickCount = 1;
        hit.SendEvent(down);
        var up = PointerUpEvent.GetPooled();
        up.position = pos; up.localPosition = pos; up.button = 0; up.pressedButtons = 0; up.clickCount = 1;
        hit.SendEvent(up);
        return Row(hit, hitText);
    }
}
