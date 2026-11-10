// Read the data behind a list/table widget (all rows, not only the rendered ones). Main thread only.
// Widget discovery and SourceData/ListElement.Items route adapted from redznn/fm-dof-mcp Navigator.ListRead (MIT).
using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using SI.Bindable;
using UnityEngine.UIElements;

namespace FmAssistant;

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
            if (Ui.PanelId(p) == panelId) Collect(p, acc, 0);
        return acc;
    }

    public static int Count(StreamedListView sl)
    {
        var items = Items(sl);
        return items == null ? 0 : items.Cast<Il2CppSystem.Collections.ICollection>().Count;
    }

    private static Il2CppSystem.Collections.IList Items(StreamedListView sl)
    {
        Il2CppSystem.Collections.IList items = null;
        try { items = sl.SourceData; } catch { }
        if (items == null) try { items = sl.ListElement?.Items; } catch { }
        return items;
    }

    /// Backing rows [start, start+cap) of one widget, decoded (Person rows -> {"$ref":"Person","uid":n}). Indexer only.
    public static JsonArray Rows(StreamedListView sl, int cap, int start = 0)
    {
        var items = Items(sl);
        var rows = new JsonArray();
        if (items == null) return rows;
        var n = Math.Min(items.Cast<Il2CppSystem.Collections.ICollection>().Count, start + cap);
        for (int i = start; i < n; i++)
        {
            try { rows.Add(Reader.Decode(items[i]?.TryCast<SI.Core.TypedValue>())); }
            catch (Exception e) { rows.Add("error: " + e.Message); }
        }
        return rows;
    }

    public static JsonArray Columns(StreamedListView sl)
    {
        var cols = new JsonArray();
        try
        {
            var ids = sl.TryCast<StreamedTable>()?.m_columnIDs;
            if (ids != null) for (int i = 0; i < ids.Count; i++) cols.Add(ids[i]);
        }
        catch { }
        return cols;
    }
}
