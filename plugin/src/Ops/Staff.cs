// op staff_search: every row behind the Staff Search table (not only the rendered ones), with staff attributes.
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using SI.Core;

namespace FmAssistant;

internal static class Staff
{
    public const string Panel = "StaffSearchReport", Table = "nonplayertable";
    private const int Batch = 20, DefaultMax = 200, HardMax = 1000;

    /// Staff attributes (1-20) as FM27 names them (no "Attribute" prefix). Mental coaching: no property found yet.
    /// Authority is assumed to be the profile's "level of discipline" (docs/protocol.md).
    public static readonly string[] Attributes =
    {
        "Attacking", "Defending", "Tactical", "Technical", "SetPieces", "CoachingFitness", "GoalkeepingCoaching",
        "WorkingWithYoungster", "TacticalKnowledge", "JudgingPlayerAbility", "JudgingPlayerPotential", "JudgingStaffAbility",
        "PeopleManagement", "Motivating", "Adaptability", "Determination", "Authority",
        "Physiotherapy", "SportsScience", "Negotiating", "AnalysingData",
    };
    private static readonly string[] Props = new[] { "Name", "Age", "Club", "PreferredJob", "FullContract" }.Concat(Attributes).ToArray();

    /// {"max": 200} -> {count, returned, truncated, rows: [Staff]} (docs/protocol.md "staff_search").
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
            var cPlants = await scope.ReadMany(contracts.Select(v => (Func<TypedValue>)(() => v)).ToList(), new[] { "Wage" });
            var res = await scope.Collect(plants);
            var cRes = await scope.Collect(cPlants);
            for (var j = 0; j < chunk.Count; j++) rows.Add(Row(chunk[j], res[j], cRes[j]));
        }
        return new JsonObject { ["count"] = count, ["returned"] = rows.Count, ["truncated"] = rows.Count < count, ["rows"] = rows };
    }

    private static JsonObject Row(int uid, JsonObject o, JsonObject c)
    {
        var attrs = new JsonObject();
        foreach (var a in Attributes) if (o[a] is JsonValue v) attrs[a] = v.Copy();
        var job = o["PreferredJob"] as JsonObject;
        return new JsonObject
        {
            ["uid"] = uid,
            ["name"] = o["Name"].Copy(),
            ["age"] = o["Age"].Copy(),
            ["club_uid"] = (o["Club"] as JsonObject)?["uid"].Copy(),
            ["preferred_job"] = job?["JobString"].Copy(),
            ["preferred_job_type"] = job?["JobType"].Copy(),
            ["attributes"] = attrs,
            ["current_wage"] = (double?)(Squad.SortedMoney(c["Wage"]) as JsonObject)?["value"] > 0 ? Squad.SortedMoney(c["Wage"]) : null,
            ["wage_demand"] = null,   // not exposed headlessly (docs/protocol.md); current_wage is the closest proxy
        };
    }
}
