// op loans: the human club's players out on loan and the next youth intake (read-only). See docs/protocol.md "loans".
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using SI.Core;

namespace FmAssistant;

internal static class Loans
{
    private const int Batch = 10, MaxLoans = 80;
    private static readonly string[] ClubProps = { "PlayersOutOnLoan", "IntakeDate", "DaysUntilYouthIntake" };
    private static readonly string[] PlayerProps =
        { "Name", "Age", "LoanClub", "LoanContract", "LoanAppearances", "LoanAverageRating", "LoanHappiness", "LoanReport" };
    private static readonly string[] ContractProps = { "StartDate", "EndDate" };

    /// {} -> {today, out: [Loan], intake: {date, days}}
    public static async Task<JsonNode> Read(JsonObject a, CancellationToken ct)
    {
        var clubUid = await Club.HumanUid(ct);
        JsonObject club;
        string today;
        await using (var scope = new ReadScope(ct))
        {
            club = (await scope.Collect(new List<Plant> { await scope.ReadOne(() => Reader.ClubRef(clubUid), ClubProps) }))[0];
            Reader.Require(club, "club", "PlayersOutOnLoan", "IntakeDate", "DaysUntilYouthIntake");
            today = await Training.Today(scope);
        }
        var uids = (club["PlayersOutOnLoan"] as JsonArray ?? new JsonArray()).OfType<JsonObject>()
            .Where(r => (string)r["$ref"] == "Person" && r["uid"].Int() != null).Select(r => r["uid"].Int().Value).Take(MaxLoans).ToList();

        var rows = new List<(int Uid, JsonObject P, JsonObject C)>();
        for (var i = 0; i < uids.Count; i += Batch)   // no per-player reads when nobody is out on loan
        {
            var chunk = uids.Skip(i).Take(Batch).ToList();
            await using var scope = new ReadScope(ct);
            var plants = await scope.ReadMany(chunk.Select(u => (Func<TypedValue>)(() => Reader.PersonRef(u))).ToList(), PlayerProps);
            var contracts = plants.Select(p => p["LoanContract"]?.Value).ToList();
            var cPlants = await scope.ReadMany(contracts.Select(v => (Func<TypedValue>)(() => v)).ToList(), ContractProps);
            var pr = await scope.Collect(plants);
            var cr = await scope.Collect(cPlants);
            for (var j = 0; j < chunk.Count; j++) rows.Add((chunk[j], pr[j], cr[j]));
        }

        var clubUids = rows.Select(r => (r.P["LoanClub"] as JsonObject)?["uid"].Int()).Where(u => u != null).Select(u => u.Value).Distinct().ToList();
        var names = new Dictionary<int, string>();
        if (clubUids.Count > 0)
        {
            await using var scope = new ReadScope(ct);
            var cr = await scope.Collect(await scope.ReadMany(clubUids.Select(u => (Func<TypedValue>)(() => Reader.ClubRef(u))).ToList(), new[] { "Name" }));
            for (var i = 0; i < clubUids.Count; i++) names[clubUids[i]] = (string)cr[i]["Name"];
        }

        var outList = new JsonArray();
        foreach (var (uid, p, c) in rows)
        {
            var apps = p["LoanAppearances"].Int();
            var report = p["LoanReport"] as JsonObject;
            outList.Add(new JsonObject
            {
                ["uid"] = uid,
                ["name"] = p["Name"].Copy(),
                ["age"] = p["Age"].Copy(),
                ["club"] = (p["LoanClub"] as JsonObject)?["uid"].Int() is int cu ? new JsonObject { ["uid"] = cu, ["name"] = names.GetValueOrDefault(cu) } : null,
                ["start_date"] = c["StartDate"].Copy(),
                ["end_date"] = c["EndDate"].Copy(),
                ["apps"] = apps,
                ["rating"] = apps > 0 && p["LoanAverageRating"] is JsonValue rv && rv.TryGetValue<double>(out var rating) ? rating : null,
                ["happiness"] = p["LoanHappiness"].Int(),
                ["agreed_time"] = Text(report?["AgreedPlayingTime"]),
                ["actual_time"] = Text(report?["ActualPlayingTime"]),
            });
        }
        return new JsonObject
        {
            ["today"] = today,
            ["out"] = outList,
            ["intake"] = new JsonObject { ["date"] = club["IntakeDate"].Copy(), ["days"] = club["DaysUntilYouthIntake"].Int() },
        };
    }

    /// Loan report strings are display only; "-" (nothing reported yet) and empty are null.
    private static string Text(JsonNode n) => n is JsonValue v && v.TryGetValue<string>(out var s) && s.Trim() is var t && t.Length > 0 && t != "-" ? s : null;
}
