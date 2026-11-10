// Entry point the host calls after loading this assembly: the op table.
using System.Collections.Generic;

namespace FmAssistant;

internal static class OpsEntry
{
    internal static Dictionary<string, (OpHandler Handler, int TimeoutSeconds)> Ops() => new()
    {
        ["hello"] = (Meta.Hello, 10),
        ["panels"] = (Meta.Panels, 10),   // reload smoke: comment only
        ["ui_dump"] = (Meta.UiDump, 10),
        ["prop_check"] = (Meta.PropCheck, 10),
        ["tree"] = (Meta.Tree, 10),
        ["read"] = (Meta.Read, 60),
        ["list_rows"] = (Meta.ListRows, 15),
        ["load_recent_save"] = (GameOps.LoadRecentSave, 10),
        ["nav_open"] = (Nav.Open, 30),
        ["club"] = (Club.Read, 30),
        ["squad"] = (Squad.Read, 90),
        ["staff_search"] = (Staff.Search, 90),
    };
}
