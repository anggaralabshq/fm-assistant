// Binding tree helpers. Path walk + Human.Club discovery adapted from redznn/fm-dof-mcp TreeWalker/MyClub (MIT).
using System;
using SI.Bindable;

namespace FmAssistant;

internal static class Tree
{
    /// Walk a dotted path ("Human.Club") from the binding root. Main thread only.
    public static IReadOnlyNode Find(string path)
    {
        var b = Plugin.Bindings;
        if (b == null) return null;
        var segs = path.Trim('.').Split('.');
        IReadOnlyNode cur = b.RootNode;
        foreach (var s in segs)
        {
            if (cur == null || cur.FirstChild == null) return null;
            IReadOnlyNode next = null;
            foreach (var c in cur.Children)
                if (Name(c) == s) { next = c; break; }
            cur = next;
        }
        return cur;
    }

    public static string Name(IReadOnlyNode n)
    {
        try { return n.Name.ToString(); } catch { return ""; }
    }

    /// uid of the human manager's club, or null when no career is loaded.
    public static int? HumanClubUid()
    {
        try
        {
            var tv = Find("Human.Club")?.Value;
            var r = tv?.Get()?.TryCast<FM.UI.DatabaseRecordReference>();
            return r?.m_index;
        }
        catch { return null; }
    }
}
