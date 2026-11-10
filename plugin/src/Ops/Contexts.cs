// Binding contexts of the context-bound props production ops read (phase 1d). Each prop's data handler names the
// contexts it needs (Bindings.GetHandler's outRequiredContext); Reader.PlantOne plants them as sibling nodes.
// The table is fixed (docs/discovery/2026-11-10-phase1d.md); op ctx_check compares it with the running game so a
// renamed context fails loudly instead of reading as `_missing`.
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using SI.Bindable;
using SI.Bindable.Reference.Core;
using SI.Core;

namespace FmAssistant;

internal static class Contexts
{
    private enum Src { Person, Team }

    private static readonly (Src Source, string Prop, string[] Ctx)[] Table =
    {
        (Src.Person, "Morale", new[] { "team", "human" }),
        (Src.Person, "MoraleString", new[] { "team", "human" }),
        (Src.Person, "CurrentAbilityStarRange", new[] { "team", "human" }),
        (Src.Person, "PotentialAbilityStarRange", new[] { "team", "human" }),
        (Src.Person, "CanViewHappinessInfo", new[] { "human", "team" }),
        (Src.Person, "HappinessPlayingTime", new[] { "human", "team" }),
        (Src.Person, "HappinessClub", new[] { "human", "team" }),
        (Src.Person, "HappinessManagement", new[] { "human", "team" }),
        (Src.Person, "HappinessTraining", new[] { "human", "team" }),
        (Src.Person, "TacticsRoleName", new[] { "team" }),
        (Src.Team, "Tactic", new[] { "Boolean" }),
        (Src.Team, "HasTeamReport", new[] { "TeamRequestingReport" }),
        (Src.Person, "HumanPortalFilteredMessages", new[] { "team", "StringType", "PortalMessagesTab" }),
        (Src.Person, "NumberUnreadMessages", new[] { "team" }),
    };

    /// The contexts a prop needs ([] for a headless prop).
    public static string[] For(string prop)
    {
        foreach (var e in Table) if (e.Prop == prop) return e.Ctx;
        return Array.Empty<string>();
    }

    /// The union of the contexts the props need.
    public static string[] For(IEnumerable<string> props) => props.SelectMany(For).Distinct().ToArray();

    /// Context values for ReadScope.ReadMany (invoked on the main thread): the viewer's own team, person and club,
    /// so the game applies the manager's knowledge masking. `extra` adds/overrides values (inbox tab, search text).
    /// Never another team for `team`: star ranges and morale are masked by it.
    public static Func<Dictionary<string, TypedValue>> Values(IEnumerable<string> props, Func<Dictionary<string, TypedValue>> extra = null)
    {
        var names = For(props);
        if (names.Length == 0 && extra == null) return null;
        return () =>
        {
            var d = new Dictionary<string, TypedValue>();
            foreach (var n in names)
            {
                var v = Value(n);
                if (v != null) d[n] = v;
            }
            if (extra != null) foreach (var kv in extra()) d[kv.Key] = kv.Value;
            return d;
        };
    }

    /// Main thread. null for a context the caller must supply (PortalMessagesTab) or an unreadable node.
    private static TypedValue Value(string name) => name switch
    {
        "team" or "TeamRequestingReport" => FmAssistant.Tree.Find("Human.Team")?.Value,
        "human" => FmAssistant.Tree.Find("Human")?.Value,
        "club" => FmAssistant.Tree.Find("Human.Club")?.Value,
        "Boolean" => TypedValue.Create(false),   // true reads the same; meaning unknown (phase 1d spike)
        "StringType" => TypedValue.Create(""),
        _ => null,
    };

    /// {} -> {checked, mismatches: [{prop, expected, game}]}: GetHandler per table prop on the viewer's own person
    /// (`Human`) / team (`Human.Team`). No channel is opened, nothing is read.
    public static Task<JsonNode> Check(JsonObject a, CancellationToken ct) => Reader.MainR<JsonNode>(() =>
    {
        if (FmAssistant.Tree.HumanClubUid() == null) return R<JsonNode>.Err("no-career-loaded", "load a career first");
        var person = FmAssistant.Tree.Find("Human")?.Value;
        var team = FmAssistant.Tree.Find("Human.Team")?.Value;
        if (person == null || team == null) return R<JsonNode>.Err("ui-element-missing", "Human / Human.Team not in the binding tree");
        var mismatches = new JsonArray();
        foreach (var (src, prop, ctx) in Table)
        {
            string[] game;
            try
            {
                var id = PropertyIdentifierSet.Instance.GetID(Il2CppSystem.MemoryExtensions.AsSpan(prop));
                if (id.ID == 0) game = new[] { "(unknown-property)" };
                else
                {
                    var list = new Il2CppSystem.Collections.Generic.List<string>();
                    var h = Plugin.Bindings.GetHandler(src == Src.Person ? person : team, new Bindings.Property(prop, id), list);
                    if (h == null) game = new[] { "(no-handler)" };
                    else { game = new string[list.Count]; for (var i = 0; i < list.Count; i++) game[i] = list[i]; }
                }
            }
            catch (Exception e) { game = new[] { $"(error: {e.GetType().Name}: {e.Message})" }; }   // never e.ToString() here
            if (!new HashSet<string>(game).SetEquals(ctx))
                mismatches.Add(new JsonObject
                {
                    ["prop"] = prop,
                    ["expected"] = new JsonArray(ctx.Select(c => (JsonNode)c).ToArray()),
                    ["game"] = new JsonArray(game.Select(c => (JsonNode)c).ToArray()),
                });
        }
        return new JsonObject { ["checked"] = Table.Length, ["mismatches"] = mismatches };
    }, ct);
}
