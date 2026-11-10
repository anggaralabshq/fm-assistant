// Phase 2 actions (act_* ops) and the negotiation read. See docs/protocol.md "Actions" and
// docs/discovery/2026-11-10-phase2.md.
//
// Rules every act op follows:
//  - Gate first: a one-use apply token written by `fm apply` (~/.fm-assistant/apply/<token>), consumed before acting;
//    an untested game build refuses every action.
//  - Person actions go through the game's own dispatcher (PluginContextActionsModule.HandleActionEvent), only for
//    the allow-listed ActionIDs below; the id is never an argument.
//  - A confirmation dialog the action opens is confirmed by the op, or cancelled on any error path.
//  - Results are read back headless and returned as {verified, before, after, answer?}.
//  - No generic clicks: the element names each op touches are fixed here.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using SI.Bindable;
using SI.Core;

namespace FmAssistant;

internal static class Act
{
    // ------------------------------------------------------------------ gate

    // FM.GamePlugin.ActionID values (interop ints) the plugin may perform. Own-player profiles also carry release,
    // termination and transfer-list actions next to these: those ids are never reachable.
    internal const int ApproachToSign = 1749837424, OfferContract = 2000111204, ShortlistAdd = 1097488485,
        ShortlistRemove = 1500280650, AssignScout = 1363818831;
    private static readonly HashSet<int> AllowedIds = new() { ApproachToSign, OfferContract, ShortlistAdd, ShortlistRemove, AssignScout };

    /// Action kind (fm_assistant.actions.REGISTRY) -> op. A token written for one kind does not open another op.
    private static readonly Dictionary<string, string> KindOps = new()
    {
        ["staff.approach"] = "act_staff_approach", ["staff.offer"] = "act_staff_offer",
        ["shortlist.add"] = "act_shortlist_add", ["shortlist.remove"] = "act_shortlist_remove",
        ["scout.request_report"] = "act_scout_request",
        ["training.set_sessions"] = "act_training_sessions", ["training.set_focus"] = "act_training_focus",
        ["contract.open_renewal"] = "act_contract_open", ["contract.offer_renewal"] = "act_contract_offer",
    };

    private static readonly Regex Hex32 = new Regex("^[0-9a-f]{32}$", RegexOptions.Compiled);

    internal static string TokenDir => Path.Combine(Session.Dir, "apply");

    /// WS thread. Refuses (forbidden) unless the build is tested and args.apply_token names an unused token file;
    /// the file is consumed (renamed, then deleted) before anything is performed, so a token works once.
    internal static void Gate(string op, JsonObject a)
    {
        if (!Meta.TestedBuilds.Contains(Plugin.GameBuild))
            throw new OpException("forbidden", $"actions are disabled on untested build {Plugin.GameBuild}");
        var tok = a["apply_token"] is JsonValue v && v.TryGetValue<string>(out var s) ? s : null;
        if (tok == null || !Hex32.IsMatch(tok))
            throw new OpException("forbidden", "apply_token (32 hex chars) required: actions run only through fm apply");
        var path = Path.Combine(TokenDir, tok);
        var used = path + ".used";
        try { File.Move(path, used); }   // atomic: of two calls with one token, only one wins
        catch (Exception) { throw new OpException("forbidden", "apply token unknown or already used"); }
        string body = null;
        try { body = File.ReadAllText(used); } catch { }
        finally { try { File.Delete(used); } catch { } }
        string kind = null;
        try { kind = (JsonNode.Parse(body ?? "") as JsonObject)?["kind"]?.GetValue<string>(); } catch { }
        if (kind != null && (!KindOps.TryGetValue(kind, out var forOp) || forOp != op))
            throw new OpException("forbidden", $"apply token was written for {kind}, not {op}");
    }

    /// Op wrapper: gate, then the handler. OpsEntry adds the UI lock.
    internal static OpHandler Gated(string op, OpHandler h) => (a, ct) => { Gate(op, a); return h(a, ct); };

    // ------------------------------------------------------------------ profile route

    private static FM.UI.EmbeddedDataHandler.PersonReferenceClickedHandler PersonClick()
    {
        foreach (var o in UnityEngine.Resources.FindObjectsOfTypeAll(Il2CppInterop.Runtime.Il2CppType.Of<FM.UI.EmbeddedDataHandler>()))
        {
            var h = o.TryCast<FM.UI.EmbeddedDataHandler>()?.m_personReferenceClickedHandler;
            if (h != null) return h;
        }
        return null;
    }

    private static string Guid(UnityEngine.AddressableAssets.AssetReference r)
    {
        try { return r?.AssetGUID; } catch { return null; }
    }

    /// uid of gameworldsubtabsandbookmarks.CurrentViewedPlayer (the profile the secondary tabs belong to), or null.
    internal static async Task<int?> ViewedPerson(CancellationToken ct)
    {
        await using var scope = new ReadScope(ct);
        var p = await scope.ReadOne(() => FmAssistant.Tree.Find("gameworldsubtabsandbookmarks")?.Value, new[] { "CurrentViewedPlayer" }, 1500);
        var o = (await scope.Collect(new List<Plant> { p }))[0];
        return (o["CurrentViewedPlayer"] as JsonObject)?["uid"].Int();
    }

    /// Opens the person's profile the way a person link does (PanelManager.Open(profile PanelID, param, person)) and
    /// waits until the secondary tabs belong to that person. player: player profile, else the non-player one.
    internal static async Task OpenProfile(int uid, bool player, CancellationToken ct)
    {
        await Reader.MainR(Nav.OnGameScreens, ct);
        await Reader.MainR<bool>(() =>
        {
            var h = PersonClick();
            if (h == null) return R<bool>.Err("ui-element-missing", "EmbeddedDataHandler not loaded");
            var guid = Guid(player ? h.m_playerPanelRef : h.m_nonPlayerPanelRef);
            var param = player ? h.m_playerParamName : h.m_nonPlayerParamName;
            if (string.IsNullOrEmpty(guid) || string.IsNullOrEmpty(param)) return R<bool>.Err("binding-api-changed", "profile panel ref missing");
            ManualSingleton<PanelManager>.Instance.Open(new UnityEngine.AddressableAssets.AssetReferenceT<PanelID>(guid), param,
                Reader.PersonRef(uid), null, null, RebindMethod.None);
            return true;
        }, ct);
        int? seen = null;
        var end = Environment.TickCount64 + 8000;
        while (Environment.TickCount64 < end)
        {
            await Task.Delay(300, ct);
            seen = await ViewedPerson(ct);
            if (seen == uid) { await Task.Delay(400, ct); return; }   // secondary tabs rebind right after
        }
        throw new OpException("precondition", $"profile of {uid} did not open (viewed person: {seen?.ToString() ?? "none"})");
    }

    // ------------------------------------------------------------------ action tree

    /// One ActionEntry of the profile's secondary tabs: a folder (children, Event 0) or a leaf.
    internal sealed class Node
    {
        public TypedValue Entry;
        public Node Parent;
        public readonly List<Node> Kids = new();
        public int Id;
        public uint Event;
        public bool Disabled;
        public string Text;
    }

    /// Main thread. Field of a record; a row value can be wrapped as {DisplayValue, PropertyValue}: look inside.
    internal static TypedValue Field(TypedValue v, string name) => Field(v, Reader.Id(name));

    internal static TypedValue Field(TypedValue v, uint id, int depth = 0)
    {
        try
        {
            var rec = v?.Get()?.TryCast<Record>();
            if (rec == null) return null;
            if (rec.TryGetValue(id, out var f)) return f;
            if (depth < 3 && rec.TryGetValue(Reader.Id("PropertyValue"), out var inner) && inner != null) return Field(inner, id, depth + 1);
        }
        catch { }
        return null;
    }

    internal static int IntOf(TypedValue v) { try { return int.Parse(v.AsString()); } catch { return int.MinValue; } }

    internal static bool BoolOf(TypedValue v) { try { return v?.AsString() == "True"; } catch { return false; } }

    /// Main thread. The action entries under OverviewTitleBar > SecondaryTabsList as a tree (rows and their ChildLists).
    internal static List<Node> ActionTree()
    {
        var roots = new List<Node>();
        var list = ListRead.Widgets("OverviewTitleBar").Find(w => w.name == "SecondaryTabsList");
        var items = list == null ? null : ListRead.Items(list);
        if (items == null) return roots;
        var n = Math.Min(items.Cast<Il2CppSystem.Collections.ICollection>().Count, 50);
        var budget = 400;
        for (var i = 0; i < n; i++) AddRow(items[i]?.TryCast<TypedValue>(), null, roots, 0, ref budget);
        return roots;
    }

    private static void AddRow(TypedValue row, Node parent, List<Node> into, int depth, ref int budget)
    {
        if (row == null || depth > 6 || budget-- <= 0) return;
        var ae = Field(Field(row, "RowData"), "ActionEntry");
        var node = parent;
        if (ae != null && !Reader.IsNullRef(ae))
        {
            node = new Node
            {
                Entry = ae, Parent = parent, Id = IntOf(Field(ae, "ID")), Event = (uint)Math.Max(0, IntOf(Field(ae, "Event"))),
                Disabled = BoolOf(Field(ae, "Disabled")), Text = Field(ae, "Text")?.AsString(),
            };
            into.Add(node);
        }
        var kids = node == parent ? into : node.Kids;
        foreach (var c in Reader.ListElems(Field(row, "ChildList"), 60)) AddRow(c, node, kids, depth + 1, ref budget);
    }

    internal static IEnumerable<Node> Flatten(IEnumerable<Node> nodes)
    {
        foreach (var n in nodes)
        {
            yield return n;
            foreach (var k in Flatten(n.Kids)) yield return k;
        }
    }

    internal static TypedValue ActionData(Node n) => Field(n.Entry, "ActionData");

    /// Main thread. A database reference encoded in ActionData as {DatabaseReferenceField: (type << 24) | uid}:
    /// the uid when the type is Person (1), else null.
    internal static int? EncodedPerson(TypedValue v)
    {
        var inner = Field(v, "DatabaseReferenceField");
        var n = IntOf(inner ?? v);
        if (n == int.MinValue || (n >> 24) != 1) return null;
        return n & 0xFFFFFF;
    }

    private const uint TargetsId = 1685218636;   // unnamed ActionData list: the persons the action is about

    /// Main thread. Person uids an entry's ActionData names: its DatabaseReferenceField, the targets list and the
    /// ActionDataReferences (Person refs).
    internal static List<int> DataPersons(TypedValue entry)
    {
        var res = new List<int>();
        var ad = Field(entry, "ActionData");
        var top = EncodedPerson(Field(ad, "DatabaseReferenceField"));
        if (top != null) res.Add(top.Value);
        foreach (var t in Reader.ListElems(Field(ad, TargetsId), 20)) { var u = EncodedPerson(t); if (u != null) res.Add(u.Value); }
        foreach (var r in Reader.ListElems(Field(ad, "ActionDataReferences"), 20))
        {
            try
            {
                var rf = Field(r, "NewsItemActionDataReference")?.Get()?.TryCast<FM.UI.DatabaseRecordReference>();
                if (rf != null && rf.Type.ToString() == "Person") res.Add(rf.m_index);
            }
            catch { }
        }
        return res;
    }

    private static bool HasRecord(TypedValue v)
    {
        if (Reader.IsNullRef(v)) return false;
        try { var rec = v.Get()?.TryCast<Record>(); return rec != null && rec.Count > 0; } catch { return false; }
    }

    /// Main thread. The subtab ActionReference bound for this action id (root node subtab-action<N>.game.Action,
    /// persistent identity ending ":<ActionID>").
    private static SI.Interop.InteropReference ActionRef(int id)
    {
        foreach (var c in Plugin.Bindings.RootNode.Children)
        {
            var nm = FmAssistant.Tree.Name(c);
            if (!nm.StartsWith("subtab-action") || nm.StartsWith("subtab-action-group")) continue;
            var r = FmAssistant.Tree.Find(nm + ".game.Action")?.Value?.Get()?.TryCast<SI.Interop.InteropReference>();
            string idn = null; try { idn = r?.GetPersistentIdentity(); } catch { }
            if (r != null && idn != null && idn.EndsWith(":" + id)) return r;
        }
        return null;
    }

    // ------------------------------------------------------------------ dialogs

    private const string DialogPanel = "GenericModalDialog", DialogConfirm = "buttons-button-primary-default";

    private static SI.Bindable.Panel Dialog() => Ui.OpenPanels().Find(p => Ui.PanelId(p) == DialogPanel);

    /// Main thread. Clicks the named SIButton of the open confirmation dialog; false when there is none.
    private static bool ClickDialog(string button)
    {
        var d = Dialog();
        if (d == null) return false;
        UnityEngine.UIElements.VisualElement hit = null;
        Ui.Walk(d, 0, n => { if (hit == null && n.name == button && n.TryCast<SIButton>() != null && Ui.Visible(n)) hit = n; });
        if (hit == null) return false;
        Ui.Click(hit);
        return true;
    }

    /// Main thread. Element names of the dialog's visible SIButtons (diagnostics).
    private static JsonArray DialogButtons()
    {
        var arr = new JsonArray();
        var d = Dialog();
        if (d != null) Ui.Walk(d, 0, n =>
        {
            if (!Ui.Visible(n) || !(n.name.StartsWith("buttons-") || n.TryCast<SIButton>() != null)) return;
            string t = "?"; try { t = n.GetIl2CppType().Name; } catch { }
            arr.Add($"{n.name}:{t}");
        });
        return arr;
    }

    private static async Task<bool> WaitDialog(bool open, int ms, CancellationToken ct)
    {
        var end = Environment.TickCount64 + ms;
        while (Environment.TickCount64 < end)
        {
            if (await Reader.Main(() => Dialog() != null, ct) == open) return true;
            await Task.Delay(200, ct);
        }
        return false;
    }

    // ------------------------------------------------------------------ perform

    /// Waits for the profile's action tree to offer `actionId`, picks the one leaf (an entry without children) with
    /// that id where leafMatch holds and whose ActionData names `target`, and performs it through the game's
    /// dispatcher with checkForConfirmation: true. A confirmation dialog it opens is confirmed; on any error after the
    /// dialog appeared it is cancelled. Returns {performed, text, dialog}.
    internal static async Task<JsonObject> Perform(int actionId, int target, Func<Node, bool> leafMatch, CancellationToken ct)
    {
        if (!AllowedIds.Contains(actionId)) throw new OpException("bad-request", $"action {actionId} is not allow-listed");
        R<JsonObject> res = default;
        var end = Environment.TickCount64 + 4000;
        while (true)
        {
            res = await Reader.Main(() => Dispatch(actionId, target, leafMatch), ct);
            if (res.Code == null || res.Code != "ui-element-missing" || Environment.TickCount64 > end) break;
            await Task.Delay(300, ct);
        }
        var info = res.Unwrap();
        if (!(bool)info["confirm"]) { await Task.Delay(300, ct); info["dialog"] = await Reader.Main(() => Dialog() != null, ct); return info; }
        var appeared = false;
        try
        {
            appeared = await WaitDialog(true, 6000, ct);
            if (!appeared) throw new OpException("ui-element-missing", "the action's confirmation dialog did not open");
            // The dialog lays out a few frames after it opens; a click before that is lost.
            await Until(() => Reader.Main(() => DialogButtons().Count > 0, ct), x => x, 3000, ct);
            await Task.Delay(500, ct);
            info["dialog_buttons"] = await Reader.Main(DialogButtons, ct);
            if (!await Reader.Main(() => ClickDialog(DialogConfirm), ct))
                throw new OpException("ui-element-missing", $"{DialogConfirm} not in {DialogPanel}");
            if (!await WaitDialog(false, 5000, ct))
                throw new OpException("ui-element-missing", $"confirmation dialog did not close (buttons {info["dialog_buttons"]?.ToJsonString()})");
            info["dialog"] = "confirmed";
            return info;
        }
        catch
        {
            if (appeared) await CancelDialog();
            throw;
        }
    }

    private const string DialogCancel = "buttons-button-secondary-default";

    /// Closes an open confirmation dialog without confirming (best effort, own deadline, never throws).
    internal static async Task CancelDialog()
    {
        try { await Reader.Main(() => ClickDialog(DialogCancel), CancellationToken.None); } catch { }
    }

    /// Main thread.
    private static R<JsonObject> Dispatch(int actionId, int target, Func<Node, bool> leafMatch)
    {
        var all = Flatten(ActionTree()).ToList();
        var leaves = all.Where(x => x.Id == actionId && x.Kids.Count == 0).ToList();
        if (leaves.Count == 0)
            return R<JsonObject>.Err("ui-element-missing", $"action {actionId} not offered on this profile ({all.Count} entries)");
        var hits = leaves.Where(x => leafMatch(x)).ToList();
        if (hits.Count != 1)
            return R<JsonObject>.Err("precondition", $"{hits.Count} entries of action {actionId} match (of {leaves.Count})");
        var hit = hits[0];
        var persons = DataPersons(hit.Entry);
        if (!persons.Contains(target))
            return R<JsonObject>.Err("precondition", $"action entry is not for person {target} (names {string.Join(",", persons)})");
        if (hit.Disabled) return R<JsonObject>.Err("precondition", $"action {actionId} is disabled: {hit.Text}");
        var aref = ActionRef(actionId);
        if (aref == null) return R<JsonObject>.Err("ui-element-missing", $"no subtab ActionReference for action {actionId}");
        // The confirmation dialog the dispatcher shows (checkForConfirmation) is described in the ActionData.
        var confirm = HasRecord(Field(Field(hit.Entry, "ActionData"), "ConfirmationDialogData")) || HasRecord(Field(hit.Entry, "ConfirmationDialogData"));
        try
        {
            FM.Game.PluginContextActionsModule.HandleActionEvent((FM.GamePlugin.ActionID)actionId, hit.Event, aref, Field(hit.Entry, "ActionData"), true, null);
        }
        catch (Exception e) { return R<JsonObject>.Err("internal", $"HandleActionEvent: {e.GetType().Name}: {e.Message}"); }
        return new JsonObject { ["performed"] = true, ["text"] = hit.Text, ["confirm"] = confirm };
    }

    // ------------------------------------------------------------------ negotiation read

    private static Func<Dictionary<string, TypedValue>> NegotiationCtx => () => new Dictionary<string, TypedValue>
    {
        ["human"] = FmAssistant.Tree.Find("Human")?.Value,
        ["BuyingClub"] = FmAssistant.Tree.Find("Human.Club")?.Value,
    };

    private static readonly string[] SessionProps =
    {
        "Wage", "WeeklyWageComponentInfo", "NegotiationPatience", "BaseDetailsTabChangedByOtherParty", "NegotiationReadOnly",
        "ContractNegotiationKeyInformation", "EndDate", "SelectedJobIsRecruitment", "SelectedJobIsCoaching", "SelectedJobIsMedical",
    };

    private const string NegotiationPanel = "ContractNegotiationTool";

    /// Main thread. The negotiation screen's stage: "promises" (a player's pre-contract promises row is rendered),
    /// "contract" (the wage row is rendered), or null when the screen is not open.
    private static string ScreenStage()
    {
        var p = Ui.OpenPanels().Find(x => Ui.PanelId(x) == NegotiationPanel);
        if (p == null) return null;
        string stage = null;
        Ui.Walk(p, 0, n =>
        {
            if (stage != null || !Ui.Visible(n)) return;
            if (n.name == "playing-time-promise") stage = "promises";
            else if (n.name == "wage-term") stage = "contract";
        });
        return stage;
    }

    private static bool NegotiationScreen() => ScreenStage() != null;

    /// A negotiation date int (session EndDate) as YYYY-MM-DD: (year << 17) | (1-based day of year << 8). Checked
    /// against the game's own key-information lines; null for anything else.
    internal static string DateOf(JsonNode raw)
    {
        var v = raw.Int();
        if (v == null || v <= 0) return null;
        int year = v.Value >> 17, doy = (v.Value >> 8) & 0x1FF;
        if (year < 1900 || year > 2200 || doy < 1 || doy > 366) return null;
        return new System.DateTime(year, 1, 1).AddDays(doy - 1).ToString("yyyy-MM-dd");
    }

    /// {uid} -> the person's negotiation with the human club, read headless. See docs/protocol.md "negotiation".
    public static async Task<JsonNode> Negotiation(JsonObject a, CancellationToken ct)
    {
        var uid = Uid(a);
        await Career(ct);
        return await ReadNegotiation(uid, ct);
    }

    /// The game computes a session for anyone (the prefilled terms it would offer), so `open` is: the negotiation
    /// screen shows this person, or the session carries a reply (changed by the other party, patience moved,
    /// read-only after an offer). Session props are read with contexts human + BuyingClub.
    internal static async Task<JsonObject> ReadNegotiation(int uid, CancellationToken ct)
    {
        await using var scope = new ReadScope(ct);
        var p = await scope.ReadOne(() => Reader.PersonRef(uid), new[] { "ContractEditSession", "IsPlayer" }, 2000, NegotiationCtx);
        var session = p["ContractEditSession"]?.Value;
        if (session == null) throw new OpException("binding-api-changed", "person ContractEditSession did not resolve");
        var sp = await scope.ReadOne(() => session, SessionProps, 3000, NegotiationCtx);
        var both = await scope.Collect(new List<Plant> { sp, p });
        var s = both[0];
        Reader.Require(s, "ContractEditSession", "Wage", "NegotiationPatience", "NegotiationReadOnly");
        var isPlayer = Str(both[1]["IsPlayer"]) == "True";
        var (wage, maxWage, screenStage) = await Reader.Main(() =>
        {
            var intervals = (s["WeeklyWageComponentInfo"]?["CashSelectionIntervalsInfo"]?["IntervalValues"] as JsonArray)?.Select(x => x.Int()).Where(x => x != null).ToList();
            return (Money.Of(s["Wage"]), intervals is { Count: > 0 } ? Money.Of((double)intervals.Max().Value) : null, ScreenStage());
        }, ct);
        var screen = screenStage != null;
        var viewedUid = screen ? await ViewedPerson(ct) : null;
        var patience = s["NegotiationPatience"] as JsonObject;
        var status = patience?["NegotiationPatienceStatus"].Int() ?? 0;
        var changed = Str(s["BaseDetailsTabChangedByOtherParty"]) == "True";
        var readOnly = Str(s["NegotiationReadOnly"]) == "True";
        var onScreen = screen && viewedUid == uid;
        var wi = s["WeeklyWageComponentInfo"]?["BaseComponentData"] as JsonObject;
        string group = isPlayer ? null : Str(s["SelectedJobIsRecruitment"]) == "True" ? "recruitment" : Str(s["SelectedJobIsCoaching"]) == "True" ? "coaching"
            : Str(s["SelectedJobIsMedical"]) == "True" ? "medical" : null;
        var keyInfo = new JsonArray();
        if (s["ContractNegotiationKeyInformation"] is JsonArray ki) foreach (var k in ki) keyInfo.Add(k.Copy());
        return new JsonObject
        {
            ["open"] = onScreen || changed || readOnly || status != 0,
            ["on_screen"] = onScreen,
            // off screen, an open negotiation carries a reply to terms, so it is past the promises
            ["stage"] = onScreen ? screenStage : (changed || readOnly || status != 0) ? "contract" : null,
            ["wage"] = wage,
            ["job"] = group,
            ["end_date"] = DateOf(s["EndDate"]),
            ["board_max_wage"] = maxWage,
            ["wage_over_board_max"] = Str(wi?["HasInvalidOrDisabledReason"]) == "True",
            ["patience"] = new JsonObject { ["status"] = status, ["value"] = patience?["NegotiationPatienceValue"].Int() },
            ["changed_by_other_party"] = changed,
            ["read_only"] = readOnly,
            ["key_info"] = keyInfo,
        };
    }

    // ------------------------------------------------------------------ shared arg / state helpers

    internal static int Uid(JsonObject a, string key = "uid")
    {
        var u = Meta.Int(a, key, 0);
        return u > 0 ? u : throw new OpException("bad-request", $"{key} (positive integer) required");
    }

    private static async Task Career(CancellationToken ct)
    {
        if (await Reader.Main(() => FmAssistant.Tree.HumanClubUid() == null, ct)) throw new OpException("no-career-loaded", "load a career first");
    }

    private static Func<Dictionary<string, TypedValue>> Ctx(params (string Name, Func<TypedValue> Val)[] c) => () =>
    {
        var d = new Dictionary<string, TypedValue>();
        foreach (var (n, f) in c) { var v = f(); if (v != null) d[n] = v; }
        return d;
    };

    private static TypedValue Path_(string p) => FmAssistant.Tree.Find(p)?.Value;

    /// Polls `read` until `done` holds or the deadline passes; returns the last value.
    private static async Task<T> Until<T>(Func<Task<T>> read, Func<T, bool> done, int ms, CancellationToken ct)
    {
        var end = Environment.TickCount64 + ms;
        var v = await read();
        while (!done(v) && Environment.TickCount64 < end) { await Task.Delay(300, ct); v = await read(); }
        return v;
    }

    private static string Str(JsonNode n) => n is JsonValue v ? v.ToString() : null;

    // ------------------------------------------------------------------ F6: shortlist and scout request

    private const uint ShortlistMonthsId = 1818719336;   // unnamed ActionData int on shortlist leaves (0 = indefinite)
    private const uint ScoutDurationId = 1098073173;     // unnamed ActionData int on scout leaves (days; 100 = full knowledge)
    private static readonly int[] ShortlistMonths = { 0, 1, 3, 6, 12 };
    private static readonly Dictionary<string, int> ScoutDurations = new() { ["week"] = 7, ["month"] = 30, ["full"] = 100 };

    /// {shortlisted, count}: person IsShortlisted (ctx human), Human.HumanShortlistPersonCount (ctx team, IsPlayerRecruitment).
    private static async Task<JsonObject> ShortlistState(int uid, CancellationToken ct)
    {
        await using var scope = new ReadScope(ct);
        var ps = await scope.ReadMany(new List<Func<TypedValue>> { () => Reader.PersonRef(uid) }, new[] { "IsShortlisted" }, 2500,
            Ctx(("human", () => Path_("Human"))));
        var hs = await scope.ReadMany(new List<Func<TypedValue>> { () => Path_("Human") }, new[] { "HumanShortlistPersonCount" }, 2500,
            Ctx(("team", () => Path_("Human.Team")), ("IsPlayerRecruitment", () => TypedValue.Create(true))));
        var p = (await scope.Collect(ps))[0];
        var h = (await scope.Collect(hs))[0];
        Reader.Require(p, "person", "IsShortlisted");
        Reader.Require(h, "Human", "HumanShortlistPersonCount");
        return new JsonObject { ["shortlisted"] = Str(p["IsShortlisted"]) == "True", ["count"] = h["HumanShortlistPersonCount"].Int() };
    }

    private static async Task<bool> BeingScouted(int uid, CancellationToken ct)
    {
        await using var scope = new ReadScope(ct);
        var p = await scope.ReadOne(() => Reader.PersonRef(uid), new[] { "IsBeingScouted" }, 2500, Ctx(("human", () => Path_("Human"))));
        var o = (await scope.Collect(new List<Plant> { p }))[0];
        Reader.Require(o, "person", "IsBeingScouted");
        return Str(o["IsBeingScouted"]) == "True";
    }

    /// {uid, months=0, apply_token} -> {verified, before: {shortlisted, count}, after, answer?}.
    public static async Task<JsonNode> ShortlistAddOp(JsonObject a, CancellationToken ct)
    {
        var uid = Uid(a);
        var months = Meta.Int(a, "months", 0);
        if (!ShortlistMonths.Contains(months)) throw new OpException("bad-request", "months must be one of 0, 1, 3, 6, 12");
        await Career(ct);
        var before = await ShortlistState(uid, ct);
        if ((bool)before["shortlisted"]) return new JsonObject { ["verified"] = true, ["answer"] = "already", ["before"] = before, ["after"] = before.Copy() };
        await OpenProfile(uid, true, ct);
        var perf = await Perform(ShortlistAdd, uid, n => IntOf(Field(ActionData(n), ShortlistMonthsId)) == months, ct);
        var after = await Until(() => ShortlistState(uid, ct), s => (bool)s["shortlisted"], 5000, ct);
        var ok = (bool)after["shortlisted"] && after["count"].Int() == before["count"].Int() + 1;
        return new JsonObject { ["verified"] = ok, ["before"] = before, ["after"] = after, ["performed"] = perf };
    }

    /// {uid, apply_token} -> {verified, before, after, answer?}. The game asks for confirmation; the op confirms.
    public static async Task<JsonNode> ShortlistRemoveOp(JsonObject a, CancellationToken ct)
    {
        var uid = Uid(a);
        await Career(ct);
        var before = await ShortlistState(uid, ct);
        if (!(bool)before["shortlisted"]) return new JsonObject { ["verified"] = true, ["answer"] = "already", ["before"] = before, ["after"] = before.Copy() };
        await OpenProfile(uid, true, ct);
        var perf = await Perform(ShortlistRemove, uid, n => true, ct);
        var after = await Until(() => ShortlistState(uid, ct), s => !(bool)s["shortlisted"], 5000, ct);
        var ok = !(bool)after["shortlisted"] && after["count"].Int() == before["count"].Int() - 1;
        return new JsonObject { ["verified"] = ok, ["before"] = before, ["after"] = after, ["performed"] = perf };
    }

    /// {uid, scout_uid, duration=week|month|full, apply_token} -> {verified, before: {being_scouted}, after, answer}.
    /// The leaf is the one under scout_uid's folder (its ActionData names that staff member) with that duration.
    public static async Task<JsonNode> ScoutRequestOp(JsonObject a, CancellationToken ct)
    {
        var uid = Uid(a);
        var scout = Uid(a, "scout_uid");
        var duration = Meta.Str(a, "duration") ?? "week";
        if (!ScoutDurations.TryGetValue(duration, out var days)) throw new OpException("bad-request", "duration must be week, month or full");
        await Career(ct);
        var before = await BeingScouted(uid, ct);
        if (before) return new JsonObject { ["verified"] = true, ["answer"] = "already", ["before"] = new JsonObject { ["being_scouted"] = true }, ["after"] = new JsonObject { ["being_scouted"] = true } };
        await OpenProfile(uid, true, ct);
        var perf = await Perform(AssignScout, uid, n =>
            EncodedPerson(Field(ActionData(n), "DatabaseReferenceField")) == scout && IntOf(Field(ActionData(n), ScoutDurationId)) == days, ct);
        var after = await Until(() => BeingScouted(uid, ct), b => b, 5000, ct);
        return new JsonObject
        {
            ["verified"] = after, ["answer"] = "pending",   // the report arrives after the date advances
            ["before"] = new JsonObject { ["being_scouted"] = before }, ["after"] = new JsonObject { ["being_scouted"] = after }, ["performed"] = perf,
        };
    }

    // ------------------------------------------------------------------ F11: staff approach and offer

    private static async Task<bool> WaitPanel(string panel, int ms, CancellationToken ct)
    {
        var end = Environment.TickCount64 + ms;
        while (Environment.TickCount64 < end)
        {
            if (await Reader.Main(() => Ui.IsOpen(panel), ct)) return true;
            await Task.Delay(250, ct);
        }
        return false;
    }

    /// {uid, apply_token} -> {verified, negotiation, demand: {job, wage, end_date}}: approaches a staff member
    /// (PersonApproachToSign). The prefilled offer the game shows is the staff member's demand.
    public static async Task<JsonNode> StaffApproachOp(JsonObject a, CancellationToken ct)
    {
        var uid = Uid(a);
        await Career(ct);
        await OpenProfile(uid, false, ct);
        await Perform(ApproachToSign, uid, n => true, ct);
        var opened = await Until(() => Reader.Main(NegotiationScreen, ct), x => x, 8000, ct);
        await Task.Delay(500, ct);
        var neg = await ReadNegotiation(uid, ct);
        return new JsonObject
        {
            ["verified"] = opened && (bool)neg["open"],
            ["negotiation"] = neg,
            ["demand"] = new JsonObject { ["job"] = neg["job"].Copy(), ["wage"] = neg["wage"].Copy(), ["end_date"] = neg["end_date"].Copy() },
        };
    }

    private const int ProposeEvent = 20, FinalizeEvent = 41;   // speak-to actions: propose terms / finalize deal (terms = demand)

    /// Main thread. The negotiation's speak-to actions in screen order: [{event, title, disabled, exit, confirm}].
    private static List<(int Event, string Title, bool Disabled, bool Exit, bool Confirm)> SpeakActions(TypedValue actions, out int buttonsCount)
    {
        var res = new List<(int, string, bool, bool, bool)>();
        buttonsCount = Reader.ListElems(Field(actions, "ActionsForButtonsList"), 20).Count;
        foreach (var r in Reader.ListElems(Field(actions, "ActionsForDropdown"), 20))
        {
            var row = Field(r, "RowData") ?? r;
            res.Add((IntOf(Field(row, "Event")), Field(row, "ActionTitle")?.AsString(), BoolOf(Field(row, "IsDisabled")),
                BoolOf(Field(row, "IsExitButton")), HasRecord(Field(row, "ConfirmationDialogData"))));
        }
        return res;
    }

    /// Main thread. The speak-to StandardButtons of the negotiation screen (SpeakToOptionalActionButton), in order.
    private static List<UnityEngine.UIElements.VisualElement> SpeakButtons()
    {
        var res = new List<UnityEngine.UIElements.VisualElement>();
        var p = Ui.OpenPanels().Find(x => Ui.PanelId(x) == NegotiationPanel);
        if (p == null) return res;
        Ui.Walk(p, 0, n =>
        {
            if (n.name != "SpeakToOptionalActionButton" || !Ui.Visible(n)) return;
            Ui.Walk(n, 0, c => { if (c.name == "StandardButton" && Ui.Visible(c)) res.Add(c); });
        });
        return res;
    }

    private static string InnerText(UnityEngine.UIElements.VisualElement e)
    {
        string t = null;
        Ui.Walk(e, 0, c => { if (t == null) t = Ui.OwnText(c); });
        return t;
    }

    /// Main thread. Clicks the speak-to button for the action with this event: the button at the action's position,
    /// which must show the action's own title (both game text). Returns an error when the screen does not match.
    private static R<string> ClickSpeak(TypedValue actions, Func<int, bool> wanted)
    {
        var acts = SpeakActions(actions, out var buttonsCount);
        var buttons = SpeakButtons();
        if (acts.Count != buttonsCount || buttons.Count != acts.Count)
            return R<string>.Err("ui-element-missing", $"{acts.Count} speak-to actions, {buttonsCount} in the button list, {buttons.Count} buttons on screen");
        var i = acts.FindIndex(x => wanted(x.Event) && !x.Exit);
        if (i < 0) return R<string>.Err("precondition", $"no such negotiation action (events: {string.Join(",", acts.Select(x => x.Event))})");
        if (acts[i].Disabled) return R<string>.Err("precondition", $"negotiation action disabled: {acts[i].Title}");
        if (acts[i].Confirm) return R<string>.Err("precondition", "negotiation action asks for confirmation (not handled)");
        var shown = InnerText(buttons[i]);
        if (shown != acts[i].Title) return R<string>.Err("ui-element-missing", $"button {i} shows '{shown}', action is '{acts[i].Title}'");
        Ui.Click(buttons[i]);
        return acts[i].Event.ToString();
    }

    /// Main thread. The wage row's step button ("-" or "+": symbols, not words).
    private static R<bool> ClickWageStep(string sign)
    {
        var p = Ui.OpenPanels().Find(x => Ui.PanelId(x) == NegotiationPanel);
        UnityEngine.UIElements.VisualElement row = null, hit = null;
        if (p != null) Ui.Walk(p, 0, n => { if (row == null && n.name == "wage-term" && Ui.Visible(n)) row = n; });
        if (row != null) Ui.Walk(row, 0, n => { if (hit == null && n.TryCast<SIButton>() != null && Ui.Visible(n) && InnerText(n) == sign) hit = n; });
        if (hit == null) return R<bool>.Err("ui-element-missing", $"wage step button '{sign}' not on the negotiation screen");
        Ui.Click(hit);
        return true;
    }

    private static async Task<(int Wage, List<int> Steps, bool CanUp, bool CanDown)> WageState(int uid, CancellationToken ct)
    {
        await using var scope = new ReadScope(ct);
        var p = await scope.ReadOne(() => Reader.PersonRef(uid), new[] { "ContractEditSession" }, 2000, NegotiationCtx);
        var session = p["ContractEditSession"]?.Value;
        var sp = await scope.ReadOne(() => session, new[] { "Wage", "WeeklyWageComponentInfo" }, 3000, NegotiationCtx);
        var s = (await scope.Collect(new List<Plant> { sp }))[0];
        Reader.Require(s, "ContractEditSession", "Wage", "WeeklyWageComponentInfo");
        var info = s["WeeklyWageComponentInfo"]?["CashSelectionIntervalsInfo"];
        var steps = (info?["IntervalValues"] as JsonArray)?.Select(x => x.Int() ?? 0).ToList() ?? new List<int>();
        return (s["Wage"].Int() ?? -1, steps, Str(info?["CanIncrementValue"]) == "True", Str(info?["CanDecrementValue"]) == "True");
    }

    /// Clicks the negotiation's speak-to button for the first non-exit action whose event `wanted` accepts. The action
    /// list is read headless (ContractEditSession.SpeakTo.Actions) in the same scope the click uses it in.
    private static async Task<int> Speak(int uid, Func<int, bool> wanted, CancellationToken ct, string sessionProp = "ContractEditSession")
    {
        await using var scope = new ReadScope(ct);
        var p = await scope.ReadOne(() => Reader.PersonRef(uid), new[] { sessionProp }, 2000, NegotiationCtx);
        var session = p[sessionProp]?.Value ?? throw new OpException("binding-api-changed", $"person {sessionProp} did not resolve");
        var sp = await scope.ReadOne(() => session, new[] { "SpeakTo" }, 3000, NegotiationCtx);
        var speakTo = sp["SpeakTo"]?.Value ?? throw new OpException("binding-api-changed", $"{sessionProp}.SpeakTo did not resolve");
        var ap = await scope.ReadOne(() => speakTo, new[] { "Actions" }, 3000, NegotiationCtx);
        var actions = ap["Actions"]?.Value ?? throw new OpException("binding-api-changed", "SpeakTo.Actions did not resolve");
        return int.Parse(await Reader.MainR(() => ClickSpeak(actions, wanted), ct));
    }

    /// {uid, wage (base currency), apply_token} -> {verified, offered: {wage, job}, answer, counter, patience, before, after}.
    /// Needs the negotiation screen of uid (staff.approach first). One offer: the job stays as the game prefilled it,
    /// the wage is stepped with the screen's -/+ to the largest step <= wage (or kept when it already equals wage).
    public static async Task<JsonNode> StaffOfferOp(JsonObject a, CancellationToken ct)
    {
        var uid = Uid(a);
        var target = Meta.Int(a, "wage", 0);
        if (target <= 0) throw new OpException("bad-request", "wage (positive base-currency integer) required");
        await Career(ct);
        var before = await ReadNegotiation(uid, ct);
        if (!(bool)before["on_screen"]) throw new OpException("precondition", "approach first: the negotiation screen for this person is not open (staff.approach)");
        if ((bool)before["read_only"]) throw new OpException("precondition", "negotiation is read-only (an offer is already pending)");
        var max = before["board_max_wage"]?["value"].Int();
        if (max == null) throw new OpException("binding-api-changed", "board maximum (wage step list) did not resolve");
        if (target > max) throw new OpException("precondition", $"wage {target} exceeds the board maximum {max}; nothing sent");
        var st = await WageState(uid, ct);
        for (var clicks = 0; clicks < 40; clicks++)
        {
            string sign = null;
            if (st.Wage > target && st.CanDown) sign = "-";
            else if (st.Wage < target && st.CanUp && st.Steps.Any(x => x > st.Wage && x <= target)) sign = "+";
            if (sign == null) break;
            await Reader.MainR(() => ClickWageStep(sign), ct);
            var prev = st.Wage;
            st = await Until(() => WageState(uid, ct), x => x.Wage != prev, 2000, ct);
            if (st.Wage == prev) throw new OpException("ui-element-missing", $"wage did not move from {prev} after '{sign}'");
        }
        if (st.Wage > target) throw new OpException("precondition", $"wage could not be lowered to {target} (at {st.Wage}); nothing sent");
        var offered = await ReadNegotiation(uid, ct);
        if ((bool)offered["wage_over_board_max"]) throw new OpException("precondition", "the game says the wage exceeds the board maximum; nothing sent");
        var ev = await Speak(uid, e => e == ProposeEvent || e == FinalizeEvent, ct);
        var after = await Until(() => ReadNegotiation(uid, ct), n => (bool)n["changed_by_other_party"] || (bool)n["read_only"]
            || (n["patience"]["status"].Int() ?? 0) != 0 || !(bool)n["on_screen"], 6000, ct);
        await Task.Delay(1000, ct);   // the reply lands in several fields over a few frames
        after = await ReadNegotiation(uid, ct);
        var hired = await EmployedByHuman(uid, ct);
        // A staff member answers at once: a counter rewrites the session terms (the wage, sometimes the job);
        // talks ending closes the screen or empties patience; a deferred answer leaves the session read-only.
        var rewritten = after["wage"]?["value"].Int() != offered["wage"]?["value"].Int() || (bool)after["changed_by_other_party"];
        var ended = (after["patience"]["value"].Int() ?? 1) <= 0 || (!(bool)after["on_screen"] && !(bool)after["read_only"]);
        var answer = hired ? "accepted" : ended ? "rejected" : rewritten ? "countered" : "pending";
        return new JsonObject
        {
            ["verified"] = true,   // the offer was sent and the answer recorded (accepted, countered, rejected or pending)
            ["offered"] = new JsonObject { ["wage"] = offered["wage"].Copy(), ["job"] = offered["job"].Copy(), ["event"] = ev },
            ["answer"] = answer,
            ["counter"] = answer == "countered" ? new JsonObject { ["wage"] = after["wage"].Copy(), ["job"] = after["job"].Copy() } : null,
            ["patience"] = after["patience"].Copy(),
            ["before"] = before, ["after"] = after,
        };
    }

    private static async Task<bool> EmployedByHuman(int uid, CancellationToken ct)
    {
        await using var scope = new ReadScope(ct);
        var p = await scope.ReadOne(() => Reader.PersonRef(uid), new[] { "Club" }, 2000);
        var o = (await scope.Collect(new List<Plant> { p }))[0];
        var club = await Reader.Main(() => FmAssistant.Tree.HumanClubUid(), ct);
        return (o["Club"] as JsonObject)?["uid"].Int() == club;
    }
}
