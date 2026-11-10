// op squad: one of the human club's teams with visible attributes, condition, injury, contract (read-only).
// Flow adapted from redznn/fm-dof-mcp SquadReport (MIT): club -> team -> Team.Players -> person props -> FullContract.
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using SI.Core;

namespace FmAssistant;

internal static class Squad
{
    private const int Batch = 10, MaxPlayers = 80;
    public static readonly Dictionary<string, string> Teams = new()
        { ["first"] = "MainTeam", ["reserve"] = "HighestLevelYouthTeam", ["youth"] = "YouthTeam" };

    /// Visible player attributes only (what the manager sees on a player profile). Hidden ones are never requested.
    public static readonly string[] Attributes =
    {
        "Corners", "Crossing", "Dribbling", "Finishing", "FirstTouch", "FreeKicks", "Heading", "LongShots", "LongThrows",
        "Marking", "Passing", "PenaltyTaking", "Tackling", "Technique",
        "Aggression", "Anticipation", "Bravery", "Composure", "Concentration", "Decisions", "Determination", "Flair",
        "Leadership", "Movement", "Positioning", "Teamwork", "Vision", "WorkRate",
        "Acceleration", "Agility", "Balance", "JumpingReach", "NaturalFitness", "Pace", "Stamina", "Strength",
        "AerialReach", "CommandOfArea", "Communication", "Eccentricity", "Handling", "Kicking", "OneOnOnes", "Reflexes",
        "RushingOut", "TendencyToPunch", "Throwing",
    };
    private static readonly string[] PlayerProps = new[] { "Name", "Age", "Position", "Condition", "Fatigue", "IsInjured", "CurrentInjury", "FullContract" }
        .Concat(Attributes.Select(a => "Attribute" + a)).ToArray();
    private static readonly string[] ContractProps = { "Wage", "EndDate", "ContractLength" };

    /// {"team": "first"|"reserve"|"youth"} -> {club, team, today, count, players: [Player]} (docs/protocol.md "squad").
    public static async Task<JsonNode> Read(JsonObject a, CancellationToken ct)
    {
        var which = Meta.Str(a, "team") ?? "first";
        if (!Teams.TryGetValue(which, out var teamProp)) throw new OpException("bad-request", "team must be first|reserve|youth");
        var clubUid = await Club.HumanUid(ct);
        JsonObject club, team;
        List<int> uids;
        string today;
        await using (var scope = new ReadScope(ct))
        {
            club = (await scope.Collect(new List<Plant> { await scope.ReadOne(() => Reader.ClubRef(clubUid), new[] { "Name", teamProp }) }))[0];
            var teamUid = (int?)(club[teamProp] as JsonObject)?["uid"] ?? throw new OpException("ui-element-missing", $"club has no {teamProp}");
            team = (await scope.Collect(new List<Plant> { await scope.ReadOne(() => Reader.TeamRef(teamUid), new[] { "Name", "Players" }) }))[0];
            Reader.Require(team, "team", "Players");
            today = await Training.Today(scope);
            team["uid"] = teamUid;
            uids = (team["Players"] as JsonArray ?? new JsonArray()).OfType<JsonObject>()
                .Where(r => (string)r["$ref"] == "Person").Select(r => (int)r["uid"]).Take(MaxPlayers).ToList();
        }
        var players = new JsonArray();
        for (var i = 0; i < uids.Count; i += Batch)
        {
            var chunk = uids.Skip(i).Take(Batch).ToList();
            await using var scope = new ReadScope(ct);
            var plants = await scope.ReadMany(chunk.Select(u => (Func<TypedValue>)(() => Reader.PersonRef(u))).ToList(), PlayerProps);
            var contracts = plants.Select(p => p["FullContract"]?.Value).ToList();
            var cPlants = await scope.ReadMany(contracts.Select(v => (Func<TypedValue>)(() => v)).ToList(), ContractProps);
            var rows = await scope.Collect(plants);
            var cRows = await scope.Collect(cPlants);
            for (var j = 0; j < chunk.Count; j++) players.Add(Player(chunk[j], rows[j], cRows[j]));
        }
        return new JsonObject
        {
            ["club"] = new JsonObject { ["uid"] = clubUid, ["name"] = club["Name"].Copy() },
            ["team"] = new JsonObject { ["uid"] = team["uid"].Copy(), ["name"] = team["Name"].Copy(), ["kind"] = which },
            ["today"] = today,
            ["count"] = players.Count,
            ["players"] = players,
        };
    }

    public static bool? Bool(JsonNode n) => n is JsonValue v && v.TryGetValue<string>(out var s) && bool.TryParse(s, out var b) ? b : null;

    /// {display, sort} -> Money {display, value}; anything else -> null.
    public static JsonNode SortedMoney(JsonNode n) => n is JsonObject o && o["sort"] != null
        ? new JsonObject { ["display"] = o["display"].Copy(), ["value"] = o["sort"].Copy() } : null;

    private static JsonObject Player(int uid, JsonObject p, JsonObject c)
    {
        var attrs = new JsonObject();
        foreach (var a in Attributes) attrs[a] = p["Attribute" + a].Copy();
        var injured = Bool(p["IsInjured"]);
        var inj = p["CurrentInjury"] as JsonObject;
        return new JsonObject
        {
            ["uid"] = uid,
            ["name"] = p["Name"].Copy(),
            ["age"] = p["Age"].Copy(),
            ["position_mask"] = p["Position"].Copy(),
            ["attributes"] = attrs,
            ["condition"] = p["Condition"].Copy(),
            ["fatigue"] = p["Fatigue"].Copy(),
            ["injured"] = injured,
            ["injury"] = injured == true && inj != null
                ? new JsonObject { ["description"] = inj["InjuryDescription"].Copy(), ["return_days"] = inj["InjuryReturnDays"].Copy() }
                : null,
            ["contract"] = new JsonObject
            {
                ["wage"] = SortedMoney(c["Wage"]),
                ["end_date"] = c["EndDate"].Copy(),
                ["length_days"] = c["ContractLength"].Copy(),
            },
        };
    }
}
