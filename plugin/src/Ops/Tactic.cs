// op tactic: the first team's active tactic as the game holds it (read-only; nothing is changed). Headless:
// Human.Team.Tactic (context Boolean) -> TacticalPositionsCombined (11 slots), players' TacticsRoleName (context team).
// See docs/protocol.md "tactic".
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using SI.Core;

namespace FmAssistant;

internal static class Tactic
{
    private const int Slots = 11;
    private const long LeftSided = 0x100000, RightSided = 0x200000;
    private static readonly string[] TacticProps =
        { "HasTactic", "CurrentTacticSlot", "TacticSlot1Name", "TacticSlot2Name", "TacticSlot3Name", "MentalityString", "TacticalPositionsCombined" };

    /// Slot position bit (the player Position bit scheme) -> the tactics screen's slot label. A central slot may also
    /// carry a side modifier (LeftSided/RightSided = half-space: left/right centre-back, left/right DM); the screen
    /// labels those as the central slot ("D (C)", "DM"), so the modifiers are ignored here.
    private static readonly (long Bit, string Label)[] Labels =
    {
        (1, "GK"), (4, "D (R)"), (8, "D (L)"), (16, "D (C)"), (32, "WB (R)"), (64, "WB (L)"), (128, "DM"),
        (256, "M (R)"), (512, "M (L)"), (1024, "M (C)"), (2048, "AM (R)"), (4096, "AM (L)"), (8192, "AM (C)"),
        (16384, "ST (C)"), (32768, "ST (C)"), (65536, "ST (C)"),
    };

    internal static string Label(long? mask)
    {
        if (mask is not long m) return null;
        m &= ~(LeftSided | RightSided);
        var hits = Labels.Where(x => (m & x.Bit) != 0).Select(x => x.Label).Distinct().ToList();
        return hits.Count == 1 ? hits[0] : null;   // empty, unknown or several positions: no single slot label
    }

    /// {} -> {name, mentality, slots: [{index, position_mask, position_label, role, player: {uid, name}|null}]}
    public static async Task<JsonNode> Read(JsonObject a, CancellationToken ct)
    {
        await Club.HumanUid(ct);
        await using var scope = new ReadScope(ct);
        var tp = await scope.ReadOne(() => FmAssistant.Tree.Find("Human.Team")?.Value, new[] { "Tactic" });
        Reader.Require((await scope.Collect(new List<Plant> { tp }))[0], "team", "Tactic");
        var tactic = tp["Tactic"].Value;
        var t = (await scope.Collect(new List<Plant> { await scope.ReadOne(() => tactic, TacticProps) }))[0];
        Reader.Require(t, "tactic", "HasTactic", "TacticalPositionsCombined");
        if (Squad.Bool(t["HasTactic"]) != true)
            return new JsonObject { ["name"] = null, ["mentality"] = null, ["slots"] = new JsonArray() };

        var bySlot = new Dictionary<int, JsonObject>();
        foreach (var r in t["TacticalPositionsCombined"] as JsonArray ?? new JsonArray())
            if (r is JsonObject o && o["TeamSelectionIndex"].Int() is int i && i >= 0 && i < Slots) bySlot.TryAdd(i, o);
        int? Uid(JsonObject o) => o?["Player"] is JsonObject p && (string)p["$ref"] == "Person" ? p["uid"].Int() : null;
        var uids = bySlot.Values.Select(Uid).Where(u => u != null).Select(u => u.Value).Distinct().ToList();
        var people = new Dictionary<int, JsonObject>();
        var pr = await scope.Collect(await scope.ReadMany(uids.Select(u => (Func<TypedValue>)(() => Reader.PersonRef(u))).ToList(),
            new[] { "Name", "TacticsRoleName" }));
        for (var i = 0; i < uids.Count; i++) people[uids[i]] = pr[i];

        var slots = new JsonArray();
        for (var i = 0; i < Slots; i++)
        {
            bySlot.TryGetValue(i, out var o);
            long? mask = o?["Position"] is JsonValue mv && mv.TryGetValue<double>(out var md) ? (long)md : null;
            var uid = Uid(o);
            var who = uid is int u ? people.GetValueOrDefault(u) : null;
            slots.Add(new JsonObject
            {
                ["index"] = i,
                ["position_mask"] = mask,
                ["position_label"] = Label(mask),
                ["role"] = who == null ? null : Text.Plain(who["TacticsRoleName"]),
                ["player"] = uid is int pu ? new JsonObject { ["uid"] = pu, ["name"] = who?["Name"].Copy() } : null,
            });
        }
        var current = t["CurrentTacticSlot"].Int() ?? 0;
        var name = Text.Plain(t[$"TacticSlot{Math.Clamp(current, 0, 2) + 1}Name"]) ?? Text.Plain(t["TacticSlot1Name"]);
        return new JsonObject { ["name"] = name, ["mentality"] = Text.Plain(t["MentalityString"]), ["slots"] = slots };
    }
}
