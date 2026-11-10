// Narrow game-control op: load the most recent save from the main menu. No generic click op exists.
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine.UIElements;

namespace FmAssistant;

internal static class GameOps
{
    /// {} -> {"clicked": true}. Only on MainMenu with no career loaded; never saves anything.
    public static Task<JsonNode> LoadRecentSave(JsonObject a, CancellationToken ct) => Reader.MainR<JsonNode>(() =>
    {
        if (Tree.HumanClubUid() != null) return R<JsonNode>.Err("bad-request", "a career is already loaded");
        var menu = Ui.OpenPanels().Find(p => Ui.PanelId(p) == "MainMenu");
        if (menu == null) return R<JsonNode>.Err("wrong-screen", $"expected MainMenu, open: {Ui.OpenIds()}");
        VisualElement hit = null;
        Ui.Walk(menu, 0, n => { if (hit == null && n.name == "LoadMostRecentSave" && Ui.Visible(n)) hit = n; });
        if (hit == null) return R<JsonNode>.Err("ui-element-missing", "LoadMostRecentSave tile not visible yet");
        Ui.Click(hit);
        return new JsonObject { ["clicked"] = true };
    }, ct, needBindings: false);
}
