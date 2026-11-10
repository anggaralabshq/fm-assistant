// op player_search: every row behind the Player Database table, as the manager knows them (scouting knowledge).
// Headless attribute reads already apply the game's knowledge masking: "-" (unknown), "6-10" (range), 14 (known).
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using SI.Core;

namespace FmAssistant;

internal static class Players
{
    public const string Panel = "PlayerSearchReport", Table = "playertable";
    private const int Batch = 20, DefaultMax = 200, HardMax = 1000;
    private static readonly string[] Props = new[] { "Name", "Age", "Position", "Club", "ScoutRecommendation", "TransferValueRange", "FullContract" }
        .Concat(Squad.Attributes.Select(a => "Attribute" + a)).ToArray();

    /// {"max": 200} -> {count, returned, truncated, rows: [Prospect]} (docs/protocol.md "player_search").
    public static async Task<JsonNode> Search(JsonObject a, CancellationToken ct)
    {
        var max = Meta.Int(a, "max", DefaultMax, 1, HardMax);
        await Nav.EnsureOpen(Panel, ct);
        var (count, uids) = await Reader.MainR(() =>
        {
            var w = ListRead.Widgets(Panel).Find(x => x.name == Table);
            if (w == null) return R<(int, List<int>)>.Err("ui-element-missing", $"{Table} not found in {Panel}");
            var ids = ListRead.Rows(w, max).OfType<JsonObject>()
                .Where(r => (string)r["$ref"] == "Person").Select(r => (int)r["uid"]).ToList();
            return (ListRead.Count(w), ids);
        }, ct);
        var rows = new JsonArray();
        for (var i = 0; i < uids.Count; i += Batch)
        {
            var chunk = uids.Skip(i).Take(Batch).ToList();
            await using var scope = new ReadScope(ct);
            var plants = await scope.ReadMany(chunk.Select(u => (Func<TypedValue>)(() => Reader.PersonRef(u))).ToList(), Props);
            var contracts = plants.Select(p => p["FullContract"]?.Value).ToList();
            var cPlants = await scope.ReadMany(contracts.Select(v => (Func<TypedValue>)(() => v)).ToList(), new[] { "Wage", "EndDate" });
            var res = await scope.Collect(plants);
            var cRes = await scope.Collect(cPlants);
            var money = await Reader.Main(() => res.Select(o => Money.Of((o["TransferValueRange"] as JsonObject)?["AskingPrice"])).ToList(), ct);
            for (var j = 0; j < chunk.Count; j++) rows.Add(Row(chunk[j], res[j], cRes[j], money[j]));
        }
        return new JsonObject { ["count"] = count, ["returned"] = rows.Count, ["truncated"] = rows.Count < count, ["rows"] = rows };
    }

    private static JsonObject Row(int uid, JsonObject o, JsonObject c, JsonNode asking)
    {
        var attrs = new JsonObject();
        foreach (var a in Squad.Attributes) attrs[a] = o["Attribute" + a].Copy();
        var tv = o["TransferValueRange"] as JsonObject;
        var know = tv?["ScoutingKnowledgeLevel"] as JsonObject;
        var top = (double?)tv?["TransferValueRangeMaxValue"] ?? 0;
        var wage = Squad.SortedMoney(c["Wage"]);
        return new JsonObject
        {
            ["uid"] = uid,
            ["name"] = o["Name"].Copy(),
            ["age"] = o["Age"].Copy(),
            ["position_mask"] = o["Position"].Copy(),
            ["club_uid"] = (o["Club"] as JsonObject)?["uid"].Copy(),
            // value: the game's guide range text; number = top of the range (what a careful buyer budgets for)
            ["value"] = top > 0 ? new JsonObject { ["display"] = tv["TransferValueRangeString"].Copy(), ["value"] = top } : null,
            ["asking_price"] = (double?)(asking as JsonObject)?["value"] > 0 ? asking : null,
            // wage: display may be a range ("Rp8,25Jt - Rp11Jt /mgg"); value is the game's sort value (low end)
            ["wage"] = (double?)(wage as JsonObject)?["value"] > 0 ? wage : null,
            ["contract_end"] = c["EndDate"].Copy(),
            ["value_knowledge"] = know == null ? null : new JsonObject { ["level"] = know["ActualValue"].Copy(), ["max"] = know["MaxValue"].Copy(), ["text"] = know["Text"].Copy() },
            ["scout_rating"] = o["ScoutRecommendation"].Copy(),
            ["attributes"] = attrs,
        };
    }
}
