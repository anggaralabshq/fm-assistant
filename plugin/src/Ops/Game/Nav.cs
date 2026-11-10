// op nav_open: open a screen by panel id (language-neutral). Allowlisted panels only.
//
// Two routes, both the game's own:
//  - PanelID asset already loaded (FindObjectsOfTypeAll by name) -> PanelManager.Open(PanelID).
//  - Otherwise the PanelID's Addressables GUID -> PanelManager.Open(AssetReferenceT<PanelID>), the call the
//    secondary navigation tabs make (their backing rows carry RowData.Value = this GUID).
// GUIDs were read from the game's own navigation data (list_rows OverviewTitleBar); see docs/protocol.md.
using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Il2CppInterop.Runtime;
using SI.Bindable;
using SI.Core;
using UnityEngine.AddressableAssets;

namespace FmAssistant;

internal static class Nav
{
    /// panel id -> Addressables GUID (null: the asset is normally loaded already). Anything else is refused:
    /// opening arbitrary panels could reach save/continue flows.
    public static readonly Dictionary<string, string> Allowed = new()
    {
        ["TrainingScreen"] = null,
        ["SquadScreen"] = null,
        ["ClubScreen"] = null,
        ["StaffSearchReport"] = null,
        ["ClubAllStaffTool"] = null,
    };

    private const string StaffTabGuid = "9ba550b513bf5144da547e7d87df80da";  // KLUB > Staf (ClubAllStaffTool)


    /// Screens that need the game's own navigation (opened by clicking a primary tab by element name, then a
    /// secondary tab chosen by its backing row's PanelID GUID). Opening them directly loses their data context.
    /// Optional last step: click the element with this name inside the sub-tab's panel (a tile).
    private static readonly Dictionary<string, (string Tab, string TabPanel, string SubtabGuid, string SubPanel, string Tile)> Routes = new()
    {
        ["ClubAllStaffTool"] = ("ClubButton", "ClubScreen", StaffTabGuid, "ClubAllStaffTool", null),
        ["StaffSearchReport"] = ("ClubButton", "ClubScreen", StaffTabGuid, "ClubAllStaffTool", "StaffSearch"),
    };

    /// Dev discovery: GUIDs not mapped to a name yet may be opened while ~/.fm-assistant/dev-nav exists.
    private static bool DevGuids => System.IO.File.Exists(System.IO.Path.Combine(Session.Dir, "dev-nav"));

    private static PanelID FindLoaded(string name)
    {
        foreach (var o in UnityEngine.Resources.FindObjectsOfTypeAll(Il2CppType.Of<PanelID>()))
        {
            var id = o.TryCast<PanelID>();
            if (id != null && id.name == name) return id;
        }
        return null;
    }

    /// {"panel": id} or {"guid": hex32} -> {"panel", "open": true} / {"guid", "open_panels"}.
    public static async Task<JsonNode> Open(JsonObject a, CancellationToken ct)
    {
        var panel = Meta.Str(a, "panel");
        var guid = Meta.Str(a, "guid");
        if (guid != null)
        {
            if (!DevGuids && !Allowed.ContainsValue(guid)) throw new OpException("bad-request", "guid not allowlisted");
            await Reader.MainR(() => OpenGuid(guid), ct);
            await Task.Delay(3000, ct);
            return new JsonObject { ["guid"] = guid, ["open_panels"] = await Reader.Main(Ui.OpenIds, ct) };
        }
        if (panel == null || !Allowed.ContainsKey(panel))
            throw new OpException("bad-request", $"panel must be one of {string.Join(", ", Allowed.Keys)}");
        await EnsureOpen(panel, ct);
        return new JsonObject { ["panel"] = panel, ["open"] = true };
    }

    private static R<bool> OpenGuid(string guid)
    {
        if (guid.Length != 32) return R<bool>.Err("bad-request", "guid must be 32 hex chars");
        ManualSingleton<PanelManager>.Instance.Open(new AssetReferenceT<PanelID>(guid), null);
        return true;
    }

    /// Click the primary navigation tab whose TemplateContainer has this element name.
    private static R<bool> ClickTab(string container)
    {
        var bar = Ui.OpenPanels().Find(p => Ui.PanelId(p) == "OverviewTitleBar");
        if (bar == null) return R<bool>.Err("wrong-screen", $"OverviewTitleBar not open: {Ui.OpenIds()}");
        // Search inside MenuBar only: the club badge left of it is an SIButton also named "ClubButton".
        UnityEngine.UIElements.VisualElement menu = null, tab = null, button = null;
        Ui.Walk(bar, 0, n => { if (menu == null && n.name == "MenuBar") menu = n; });
        if (menu == null) return R<bool>.Err("ui-element-missing", "MenuBar not found in OverviewTitleBar");
        Ui.Walk(menu, 0, n => { if (tab == null && n.name == container && n.TryCast<UnityEngine.UIElements.TemplateContainer>() != null) tab = n; });
        if (tab != null) Ui.Walk(tab, 0, n => { if (button == null && n.TryCast<SIButton>() != null && Ui.Visible(n)) button = n; });
        if (button == null) return R<bool>.Err("ui-element-missing", $"navigation tab {container} not found");
        Ui.Click(button);
        return true;
    }

    /// Click the secondary tab whose backing row has RowData.Value == guid. Rendered items are matched to rows
    /// by order and checked against the row's own text (both come from the game, so no language assumption).
    private static R<bool> ClickSubtab(string guid)
    {
        var list = ListRead.Widgets("OverviewTitleBar").Find(w => w.name == "SecondaryTabsList");
        if (list == null) return R<bool>.Err("ui-element-missing", "SecondaryTabsList not found");
        var rows = ListRead.Rows(list, 50);
        var index = -1; string label = null;
        for (var i = 0; i < rows.Count; i++)
        {
            var rd = (rows[i] as JsonObject)?["RowData"] as JsonObject;
            if ((string)rd?["Value"] == guid) { index = i; label = (string)rd["SubtabText"]; break; }
        }
        if (index < 0) return R<bool>.Err("ui-element-missing", $"no secondary tab with PanelID GUID {guid}");
        var items = new List<UnityEngine.UIElements.VisualElement>();
        Ui.Walk(list, 0, n => { if (n.name == "ButtonOrDropdownSwitch" && Ui.Visible(n)) items.Add(n); });
        if (items.Count <= index) return R<bool>.Err("ui-element-missing", $"secondary tab {index} not rendered ({items.Count} visible)");
        string shown = null; UnityEngine.UIElements.VisualElement button = null;
        Ui.Walk(items[index], 0, n =>
        {
            if (shown == null && Ui.BindPath(n) == "subtab.SubtabText") shown = Ui.OwnText(n);
            if (button == null && n.TryCast<SIButton>() != null && Ui.Visible(n)) button = n;
        });
        if (shown != label) return R<bool>.Err("ui-element-missing", $"secondary tab {index} shows '{shown}', row says '{label}'");
        if (button == null) return R<bool>.Err("ui-element-missing", $"secondary tab '{label}' has no button (dropdown?)");
        Ui.Click(button);
        return true;
    }

    private static async Task WaitOpen(string panel, int ms, CancellationToken ct)
    {
        var end = Environment.TickCount64 + ms;
        while (Environment.TickCount64 < end)
        {
            await Task.Delay(250, ct);
            if (await Reader.Main(() => Ui.IsOpen(panel), ct)) return;
        }
        var open = await Reader.Main(Ui.OpenIds, ct);
        throw new OpException("wrong-screen", $"expected {panel}, open: {open}");
    }

    private static R<bool> ClickNamed(string panel, string name)
    {
        var host = Ui.OpenPanels().Find(p => Ui.PanelId(p) == panel);
        if (host == null) return R<bool>.Err("wrong-screen", $"expected {panel}, open: {Ui.OpenIds()}");
        UnityEngine.UIElements.VisualElement hit = null;
        Ui.Walk(host, 0, n => { if (hit == null && n.name == name && Ui.Visible(n)) hit = n; });
        if (hit == null) return R<bool>.Err("ui-element-missing", $"{name} not visible in {panel}");
        Ui.Click(hit);
        return true;
    }

    private static async Task Route(string panel, CancellationToken ct)
    {
        var (tab, tabPanel, guid, subPanel, tile) = Routes[panel];
        if (!await Reader.Main(() => Ui.IsOpen(subPanel), ct))
        {
            if (!await Reader.Main(() => Ui.IsOpen(tabPanel), ct))
            {
                await Reader.MainR(() => ClickTab(tab), ct);
                await WaitOpen(tabPanel, 8000, ct);
                await Task.Delay(500, ct);  // secondary tabs rebind after the primary tab opens
            }
            await Reader.MainR(() => ClickSubtab(guid), ct);
            await WaitOpen(subPanel, 8000, ct);
        }
        if (tile == null) return;
        await Task.Delay(500, ct);  // tiles bind after the panel opens
        await Reader.MainR(() => ClickNamed(subPanel, tile), ct);
        await WaitOpen(panel, 8000, ct);
    }

    /// Used by read ops before reading a screen.
    public static async Task EnsureOpen(string panel, CancellationToken ct)
    {
        if (Routes.ContainsKey(panel))
        {
            if (await Reader.MainR(() => FmAssistant.Tree.HumanClubUid() == null
                    ? R<bool>.Err("no-career-loaded", "load a career first") : Ui.IsOpen(panel), ct)) return;
            await Route(panel, ct);
            return;
        }
        var already = await Reader.MainR(() =>
        {
            if (FmAssistant.Tree.HumanClubUid() == null) return R<bool>.Err("no-career-loaded", "load a career first");
            if (Ui.IsOpen(panel)) return true;
            var id = FindLoaded(panel);
            if (id != null) { ManualSingleton<PanelManager>.Instance.Open(id, null, null); return false; }
            var guid = Allowed[panel];
            if (guid == null) return R<bool>.Err("ui-element-missing", $"PanelID {panel} is not loaded and has no known GUID");
            var r = OpenGuid(guid);
            return r.Code == null ? false : r;
        }, ct);
        if (already) return;
        var end = Environment.TickCount64 + 8000;
        while (Environment.TickCount64 < end)
        {
            await Task.Delay(250, ct);
            if (await Reader.Main(() => Ui.IsOpen(panel), ct)) return;
        }
        var open = await Reader.Main(Ui.OpenIds, ct);
        throw new OpException("wrong-screen", $"expected {panel}, open: {open}");
    }
}
