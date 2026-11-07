using System.Text.Json.Nodes;

namespace FmSpike;

/// All ops run on the main thread. Unknown op -> "unknown-op: <op>".
internal static class Ops
{
    public static JsonNode Dispatch(string op, JsonObject args)
    {
        switch (op)
        {
            case "ping": return Ping();
            case "prop_check": return Discover.PropCheck(args);
            case "tree": return Discover.TreeDump(args);
            case "panels": return Ui.Panels(args);
            case "ui_find": return Ui.Find(args);
            case "ui_click_text": return Ui.ClickText(args);
            case "ui_dump": return Ui.Dump(args);
            case "ui_click": return Ui.ClickName(args);
            case "list_rows": return ListRead.Op(args);
            default: throw new OpException("unknown-op", op);
        }
    }

    private static JsonNode Ping() => new JsonObject
    {
        ["plugin"] = "fm-spike",
        ["version"] = Plugin.Version,
        ["game_build"] = UnityEngine.Application.version,
        ["bindings_captured"] = Plugin.Bindings != null,
        ["career_loaded"] = Tree.HumanClubUid() != null,
    };
}
