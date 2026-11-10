// op club: the human club's budgets and staff slots (read-only). See docs/protocol.md "club".
using System.Collections.Generic;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;

namespace FmAssistant;

internal static class Club
{
    private static readonly string[] ClubProps = { "Name", "TransferBudget", "WageBudget", "CommittedWageSpending", "RemainingWageBudget", "OverallBalance", "FinancialStatus", "MainTeam" };
    private static readonly (string Key, string Prop)[] Groups =
        { ("coaching", "StaffCoachingSubGroup"), ("recruitment", "StaffRecruitmentSubGroup"), ("medical", "StaffMedicalSubGroup") };

    public static Task<int> HumanUid(CancellationToken ct) => Reader.MainR(() => FmAssistant.Tree.HumanClubUid() is int u
        ? R<int>.Ok(u) : R<int>.Err("no-career-loaded", "load a career first"), ct);

    /// {} -> {uid, name, balance, financial_status, transfer_budget, wage_budget, wage_committed, wage_remaining: Money, staff_slots}
    public static async Task<JsonNode> Read(JsonObject a, CancellationToken ct)
    {
        var uid = await HumanUid(ct);
        await using var scope = new ReadScope(ct);
        var cp = await scope.ReadOne(() => Reader.ClubRef(uid), ClubProps);
        var c = (await scope.Collect(new List<Plant> { cp }))[0];
        Reader.Require(c, "club", "TransferBudget", "WageBudget", "CommittedWageSpending", "RemainingWageBudget", "MainTeam");
        var team = cp["MainTeam"]?.Value;
        var tp = await scope.ReadOne(() => team, new[] { Groups[0].Prop, Groups[1].Prop, Groups[2].Prop });
        var t = (await scope.Collect(new List<Plant> { tp }))[0];
        Reader.Require(t, "team", Groups[0].Prop, Groups[1].Prop, Groups[2].Prop);
        return await Reader.Main(() =>
        {
            var slots = new JsonObject();
            foreach (var (key, prop) in Groups)
            {
                if (t[prop] is not JsonObject g) { slots[key] = null; continue; }
                var jobs = new JsonArray();
                if (g["StaffSubGroupJobsData"] is JsonArray ja)
                    foreach (var j in ja)
                        if (j is JsonObject jo)
                            jobs.Add(new JsonObject { ["job"] = jo["JobString"].Copy(), ["job_type"] = jo["JobType"].Copy(),
                                ["used"] = jo["Count"].Copy(), ["max"] = jo["MaxValue"].Copy() });
                slots[key] = new JsonObject { ["used"] = g["Count"].Copy(), ["max"] = g["MaxValue"].Copy(),
                    ["summary"] = g["ShortString"].Copy(), ["board_feedback"] = g["StaffSubGroupCountFeedbackString"].Copy(),
                    ["jobs"] = jobs };
            }
            return (JsonNode)new JsonObject
            {
                ["uid"] = uid,
                ["name"] = c["Name"].Copy(),
                ["balance"] = Money.Of(c["OverallBalance"]),
                ["financial_status"] = (c["FinancialStatus"] as JsonObject)?["display"].Copy(),
                ["transfer_budget"] = Money.Of(c["TransferBudget"]),
                ["wage_budget"] = Money.Of(c["WageBudget"]),
                ["wage_committed"] = Money.Of(c["CommittedWageSpending"]),
                ["wage_remaining"] = Money.Of(c["RemainingWageBudget"]),
                ["staff_slots"] = slots,
            };
        }, ct);
    }
}
