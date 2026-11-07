// op "staff_search_visible": every row behind the Staff Search table, enriched with headless person reads.
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using SI.Core;

namespace FmSpike;

internal static class Staff
{
    public const string Panel = "StaffSearchReport";
    private const int Batch = 20;

    // Staff attributes (1-20) as named in FM27 (no "Attribute" prefix, unlike player attributes).
    public static readonly string[] Attributes =
    {
        "Attacking", "Defending", "Tactical", "Technical", "SetPieces", "CoachingFitness",
        "TacticalKnowledge", "JudgingPlayerAbility", "JudgingPlayerPotential", "JudgingStaffAbility",
        "PeopleManagement", "Motivating", "Adaptability", "Determination",
        "Physiotherapy", "SportsScience", "Negotiating", "AnalysingData",
    };
    private static readonly string[] Props = new[] { "Name", "Age", "Nation", "Club", "PreferredJob" }.Concat(Attributes).ToArray();

    public static async Task<JsonNode> Run(JsonObject args)
    {
        var max = (int?)args["max"] ?? 50;
        var (count, uids) = await Reader.Main(() =>
        {
            var ws = ListRead.Widgets(Panel);
            if (ws.Count == 0)
            {
                var open = string.Join(",", Ui.OpenPanels().Select(p => { try { return p.PanelID?.name; } catch { return "?"; } }));
                throw new OpException("wrong-screen", $"expected {Panel}, got {open}");
            }
            var ids = ListRead.Rows(ws[0], max).OfType<JsonObject>()
                .Where(r => (string)r["$ref"] == "Person").Select(r => (int)r["uid"]).ToList();
            return (ws[0].ItemCount, ids);
        });

        var rows = new JsonArray();
        for (var i = 0; i < uids.Count; i += Batch)
        {
            var chunk = uids.Skip(i).Take(Batch).ToList();
            var plants = await Reader.ReadMany(chunk.Select(u => (Func<TypedValue>)(() => Reader.PersonRef(u))).ToList(), Props);
            var res = await Reader.Main(() =>
            {
                var l = new List<JsonObject>();
                for (var j = 0; j < plants.Count; j++)
                {
                    var o = Reader.Collect(plants[j]);
                    Reader.Close(plants[j]);
                    var attrs = new JsonObject();
                    foreach (var a in Attributes) if (o[a] is JsonValue v) { o.Remove(a); attrs[a] = v; }
                    l.Add(new JsonObject
                    {
                        ["uid"] = chunk[j],
                        ["name"] = (string)o["Name"],
                        ["age"] = o["Age"]?.GetValue<double>(),
                        ["role"] = (o["PreferredJob"] as JsonObject)?["JobString"]?.ToString(),
                        ["club"] = (o["Club"] as JsonObject)?["uid"]?.GetValue<int>(),
                        ["wage_demand"] = null,  // not exposed in the search view; Phase 1 reads it from the contract-offer screen
                        ["attributes"] = attrs,
                        ["raw"] = o,
                    });
                }
                return l;
            });
            foreach (var r in res) rows.Add(r);
        }
        return new JsonObject { ["screen"] = Panel, ["count"] = count, ["returned"] = rows.Count, ["rows"] = rows };
    }
}
