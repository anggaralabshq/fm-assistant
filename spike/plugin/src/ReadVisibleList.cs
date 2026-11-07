// Read the data behind a list/table widget (all rows, not only the visible ones).
// Widget discovery and SourceData/ListElement.Items route adapted from redznn/fm-dof-mcp Navigator.ListRead (MIT).
using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using SI.Bindable;
using UnityEngine.UIElements;

namespace FmSpike;

internal static class ListRead
{
    private static void Collect(VisualElement n, List<StreamedListView> acc, int depth)
    {
        if (n == null || depth > 80) return;
        var sl = n.TryCast<StreamedListView>();
        if (sl != null) { acc.Add(sl); return; }
        for (int i = 0; i < n.childCount; i++) Collect(n[i], acc, depth + 1);
    }

    public static List<StreamedListView> Widgets(string panelId)
    {
        var acc = new List<StreamedListView>();
        foreach (var p in Ui.OpenPanels())
        {
            string pid = null; try { pid = p.PanelID?.name; } catch { }
            if (pid == panelId) Collect(p, acc, 0);
        }
        return acc;
    }

    /// Backing rows of one widget, decoded (Person rows -> {"$ref":"Person","uid":n}). Indexer only, never foreach.
    public static JsonArray Rows(StreamedListView sl, int cap)
    {
        Il2CppSystem.Collections.IList items = null;
        try { items = sl.SourceData; } catch { }
        if (items == null) try { items = sl.ListElement?.Items; } catch { }
        var rows = new JsonArray();
        if (items == null) return rows;
        var n = Math.Min(items.Cast<Il2CppSystem.Collections.ICollection>().Count, cap);
        for (int i = 0; i < n; i++)
        {
            try { rows.Add(Reader.Decode(items[i]?.TryCast<SI.Core.TypedValue>())); }
            catch (Exception e) { rows.Add("error: " + e.Message); }
        }
        return rows;
    }

    /// {"panel":"StaffSearchReport", "index":0, "max":500} -> {panel, widgets:[{name,item_count}], rows:[...]}
    public static JsonNode Op(JsonObject args)
    {
        var panel = (string)args["panel"] ?? throw new OpException("bad-request", "panel required");
        var ws = Widgets(panel);
        if (ws.Count == 0) throw new OpException("wrong-screen", $"no list widget in panel '{panel}'");
        var index = (int?)args["index"] ?? 0;
        var meta = new JsonArray();
        foreach (var w in ws)
        {
            var cols = new JsonArray();
            try
            {
                var ids = w.TryCast<StreamedTable>()?.m_columnIDs;
                if (ids != null) for (int i = 0; i < ids.Count; i++) cols.Add(ids[i]);
            }
            catch { }
            meta.Add(new JsonObject { ["name"] = w.name, ["item_count"] = w.ItemCount, ["columns"] = cols });
        }
        return new JsonObject { ["panel"] = panel, ["widgets"] = meta, ["rows"] = Rows(ws[Math.Min(index, ws.Count - 1)], (int?)args["max"] ?? 500) };
    }
}
