// Entry point the host calls after loading this assembly: the op table.
using System.Collections.Generic;

namespace FmAssistant;

internal static class OpsEntry
{
    /// Raw property reads can reach values the manager cannot see (hidden attributes): discovery only, while
    /// ~/.fm-assistant/dev-nav exists.
    private static OpHandler DevOnly(OpHandler h) => (a, ct) => Nav.DevGuids ? h(a, ct)
        : throw new OpException("bad-request", "discovery op: dev mode only (~/.fm-assistant/dev-nav)");

    /// UI-driving ops run one at a time (Nav.UiLock).
    private static OpHandler Exclusive(OpHandler h) => async (a, ct) =>
    {
        await Nav.UiLock.WaitAsync(ct);
        try { return await h(a, ct); }
        finally { Nav.UiLock.Release(); }
    };

    internal static Dictionary<string, (OpHandler Handler, int TimeoutSeconds)> Ops() => new()
    {
        ["hello"] = (Meta.Hello, 10),
        ["panels"] = (Meta.Panels, 10),   // reload smoke: comment only
        ["ui_dump"] = (Meta.UiDump, 10),
        ["prop_check"] = (DevOnly(Meta.PropCheck), 10),
        ["tree"] = (DevOnly(Meta.Tree), 10),
        ["read"] = (DevOnly(Meta.Read), 60),
        ["list_rows"] = (Meta.ListRows, 15),
        ["load_recent_save"] = (GameOps.LoadRecentSave, 10),
        ["nav_open"] = (Exclusive(Nav.Open), 30),
        ["club"] = (Club.Read, 30),
        ["squad"] = (Squad.Read, 90),
        ["staff_search"] = (Exclusive(Staff.Search), 90),
        ["player_search"] = (Exclusive(Players.Search), 90),
        ["training"] = (Exclusive(Training.Read), 60),
    };
}
