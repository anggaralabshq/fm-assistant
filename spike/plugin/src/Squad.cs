// op "squad": human club's first-team players. Flow adapted from redznn/fm-dof-mcp SquadReport (MIT):
// club -> MainTeam -> Team.Players -> per-player props -> FullContract -> contract props.
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using SI.Core;

namespace FmSpike;

internal static class Squad
{
    private const int Batch = 20;
    private const int MaxPlayers = 80;

    private static readonly string[] PlayerProps =
    {
        "Name", "Age", "Position", "FullContract",
        "AttributeFinishing", "AttributePassing", "AttributeTackling", "AttributePace", "AttributeDetermination",
    };
    private static readonly string[] ContractProps = { "Wage", "EndDate", "ContractLength" };

    public static async Task<JsonNode> Run(JsonObject args)
    {
        var clubUid = await Reader.Main(Tree.HumanClubUid) ?? throw new OpException("no-career-loaded", "load a career first");

        var club = await ReadOne(() => Reader.ClubRef(clubUid), new[] { "Name", "MainTeam" });
        var teamUid = (int?)(club["MainTeam"] as JsonObject)?["uid"] ?? throw new OpException("read-failed", "club.MainTeam: " + club.ToJsonString());

        var team = await ReadOne(() => Reader.TeamRef(teamUid), new[] { "Name", "Players" });
        var uids = (team["Players"] as JsonArray ?? throw new OpException("read-failed", "team.Players: " + team.ToJsonString()))
            .OfType<JsonObject>().Where(r => (string)r["$ref"] == "Person").Select(r => (int)r["uid"]).Take(MaxPlayers).ToList();

        var players = new JsonArray();
        for (var i = 0; i < uids.Count; i += Batch)
        {
            var chunk = uids.Skip(i).Take(Batch).ToList();
            var plants = await Reader.ReadMany(chunk.Select(u => (Func<TypedValue>)(() => Reader.PersonRef(u))).ToList(), PlayerProps);
            // Contract chain: plant each landed FullContract value as a new parent.
            var contractVals = plants.Select(p => p.Props.First(x => x.Name == "FullContract").Value).ToList();
            var cPlants = await Reader.ReadMany(contractVals.Select(v => (Func<TypedValue>)(() => v)).ToList(), ContractProps);
            var rows = await Reader.Main(() =>
            {
                var res = new List<JsonObject>();
                for (var j = 0; j < plants.Count; j++)
                {
                    var o = Reader.Collect(plants[j]);
                    o.Remove("FullContract");
                    o["contract"] = Reader.Collect(cPlants[j]);
                    o["uid"] = chunk[j];
                    Reader.Close(plants[j]); Reader.Close(cPlants[j]);
                    res.Add(o);
                }
                return res;
            });
            foreach (var r in rows) players.Add(r);
        }

        return new JsonObject
        {
            ["club"] = new JsonObject { ["uid"] = clubUid, ["name"] = club["Name"]?.ToString() },
            ["team"] = new JsonObject { ["uid"] = teamUid, ["name"] = team["Name"]?.ToString() },
            ["count"] = players.Count,
            ["players"] = players,
        };
    }

    private static async Task<JsonObject> ReadOne(Func<TypedValue> parent, string[] props)
    {
        var plant = (await Reader.ReadMany(new List<Func<TypedValue>> { parent }, props))[0];
        var json = await Reader.Main(() => { var j = Reader.Collect(plant); Reader.Close(plant); return j; });
        return json;
    }
}

/// op "read": {"ref":"person|club|team|path", "uid":123 | "path":"Human.Club", "props":[...]} -> decoded props. Discovery aid.
internal static class GenericRead
{
    public static async Task<JsonNode> Run(JsonObject args)
    {
        var kind = (string)args["ref"] ?? throw new OpException("bad-request", "ref required");
        var props = (args["props"] as JsonArray ?? throw new OpException("bad-request", "props[] required")).Select(n => (string)n).ToArray();
        var uid = (int?)args["uid"] ?? 0;
        var path = (string)args["path"];
        Func<TypedValue> parent = kind switch
        {
            "person" => () => Reader.PersonRef(uid),
            "club" => () => Reader.ClubRef(uid),
            "team" => () => Reader.TeamRef(uid),
            "path" => () => Tree.Find(path ?? "")?.Value,
            _ => throw new OpException("bad-request", "ref must be person|club|team|path"),
        };
        var plant = (await Reader.ReadMany(new List<Func<TypedValue>> { parent }, props, (int?)args["wait_ms"] ?? 4000))[0];
        var json = await Reader.Main(() => Reader.Collect(plant));
        // "chain": {"FullContract": ["Wage", ...]} reads sub-props off a landed value.
        if (args["chain"] is JsonObject chain)
            foreach (var kv in chain)
            {
                var v = plant.Props.Find(x => x.Name == kv.Key)?.Value;
                var sub = (kv.Value as JsonArray)?.Select(n => (string)n).ToArray() ?? Array.Empty<string>();
                var cp = (await Reader.ReadMany(new List<Func<TypedValue>> { () => v }, sub))[0];
                json[kv.Key] = await Reader.Main(() => { var j = Reader.Collect(cp); Reader.Close(cp); return j; });
            }
        await Reader.Main(() => { Reader.Close(plant); return 0; });
        return json;
    }
}
