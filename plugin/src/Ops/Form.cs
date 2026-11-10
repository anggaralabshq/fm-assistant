// op form: season stats per competition, last-five-match form and squad concerns of one of the human club's teams
// (read-only). See docs/protocol.md "form".
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using SI.Core;

namespace FmAssistant;

internal static class Form
{
    private const int Batch = 10, MaxPlayers = 80, FullMatch = 90;
    private static readonly (string Key, string Prop)[] Areas =
        { ("playing_time", "HappinessPlayingTime"), ("club", "HappinessClub"), ("management", "HappinessManagement"), ("training", "HappinessTraining") };
    // Morale / Happiness* / CanViewHappinessInfo are context-bound (team, human): planted with Contexts.
    private static readonly string[] PlayerProps = new[] { "Name", "SeasonStatsList", "LastFiveClubMatchesForm", "CanViewHappinessInfo", "Morale", "MoraleString" }
        .Concat(Areas.Select(x => x.Prop)).ToArray();
    private static readonly string[] TeamProps = { "Name", "Players", "HappinessIssuesPlayers", "ClubAtmosphereFeedback" };

    /// {"team": "first"|"reserve"|"youth"} -> {today, team, players: [Form], concerns: [uid], atmosphere: {level, text}|null}
    public static async Task<JsonNode> Read(JsonObject a, CancellationToken ct)
    {
        var which = Meta.Str(a, "team") ?? "first";
        if (!Squad.Teams.TryGetValue(which, out var teamProp)) throw new OpException("bad-request", "team must be first|reserve|youth");
        var clubUid = await Club.HumanUid(ct);
        JsonObject team;
        List<int> uids;
        string today;
        int teamUid;
        await using (var scope = new ReadScope(ct))
        {
            var club = (await scope.Collect(new List<Plant> { await scope.ReadOne(() => Reader.ClubRef(clubUid), new[] { teamProp }) }))[0];
            teamUid = (int?)(club[teamProp] as JsonObject)?["uid"] ?? throw new OpException("ui-element-missing", $"club has no {teamProp}");
            team = (await scope.Collect(new List<Plant> { await scope.ReadOne(() => Reader.TeamRef(teamUid), TeamProps) }))[0];
            Reader.Require(team, "team", "Players");
            today = await Training.Today(scope);
            uids = Uids(team["Players"]).Take(MaxPlayers).ToList();
        }

        var compNames = new Dictionary<int, string>();
        var players = new JsonArray();
        for (var i = 0; i < uids.Count; i += Batch)
        {
            var chunk = uids.Skip(i).Take(Batch).ToList();
            await using var scope = new ReadScope(ct);
            var plants = await scope.ReadMany(chunk.Select(u => (Func<TypedValue>)(() => Reader.PersonRef(u))).ToList(), PlayerProps);
            var rows = await scope.Collect(plants);
            // Competition names: a list record's Competition is a comp ref; plant once per comp uid not seen yet.
            var want = new Dictionary<int, (int Player, int Index)>();
            for (var j = 0; j < rows.Count; j++)
            {
                var k = 0;
                foreach (var r in rows[j]["SeasonStatsList"] as JsonArray ?? new JsonArray())
                {
                    if (r is JsonObject o && o["Competition"] is JsonObject c && c["uid"].Int() is int cu && !compNames.ContainsKey(cu))
                        want.TryAdd(cu, (j, k));
                    k++;
                }
            }
            if (want.Count > 0)
            {
                var keys = want.Keys.ToList();
                var values = await Reader.Main(() => keys.Select(cu =>
                {
                    var (p, idx) = want[cu];
                    var l = Reader.ListField(plants[p]["SeasonStatsList"]?.Value, "Competition");
                    return idx < l.Count ? l[idx] : null;
                }).ToList(), ct);
                var cp = await scope.ReadMany(values.Select(v => (Func<TypedValue>)(() => v)).ToList(), new[] { "Name" });
                var cr = await scope.Collect(cp);
                for (var x = 0; x < keys.Count; x++) compNames[keys[x]] = (string)cr[x]["Name"];
            }
            for (var j = 0; j < chunk.Count; j++) players.Add(Player(chunk[j], rows[j], compNames));
        }

        var atm = team["ClubAtmosphereFeedback"] as JsonObject;
        return new JsonObject
        {
            ["today"] = today,
            ["team"] = new JsonObject { ["uid"] = teamUid, ["name"] = team["Name"].Copy(), ["kind"] = which },
            ["players"] = players,
            ["concerns"] = new JsonArray(Uids(team["HappinessIssuesPlayers"]).Select(u => (JsonNode)u).ToArray()),
            ["atmosphere"] = atm == null ? null
                : new JsonObject { ["level"] = atm["CurrentDynamicSupportLevel"].Int(), ["text"] = atm["CurrentDynamicSupportStringShort"].Copy() },
        };
    }

    private static IEnumerable<int> Uids(JsonNode list) => (list as JsonArray ?? new JsonArray()).OfType<JsonObject>()
        .Where(r => (string)r["$ref"] == "Person" && r["uid"].Int() != null).Select(r => r["uid"].Int().Value);

    private static double? Num(JsonNode n) => n is JsonValue v && v.TryGetValue<double>(out var d) ? d : null;

    private static JsonObject Player(int uid, JsonObject p, Dictionary<int, string> comps)
    {
        // Morale reads numbers for players the manager cannot view (other clubs): gate on CanViewHappinessInfo.
        var visible = Squad.Bool(p["CanViewHappinessInfo"]) == true;
        var season = new JsonArray();
        foreach (var r in p["SeasonStatsList"] as JsonArray ?? new JsonArray())
        {
            if (r is not JsonObject o) continue;
            var apps = o["Appearances"].Int() ?? 0;
            var rated = o["AppearancesForRating"].Int() ?? apps;
            season.Add(new JsonObject
            {
                ["competition"] = o["Competition"] is JsonObject c && c["uid"].Int() is int cu ? comps.GetValueOrDefault(cu) : null,
                ["apps"] = apps,
                ["starts"] = o["StartingAppearances"].Int(),
                ["subs"] = o["SubAppearances"].Int(),
                ["rating"] = rated > 0 ? Num(o["AverageRating"]) : null,   // no rated match: null, never 0.0
            });
        }
        return new JsonObject
        {
            ["uid"] = uid,
            ["name"] = p["Name"].Copy(),
            ["season"] = season,
            ["last5"] = Last5(p["LastFiveClubMatchesForm"] as JsonObject),
            ["morale"] = visible && p["Morale"].Int() is int m ? new JsonObject { ["value"] = m, ["text"] = Text.Plain(p["MoraleString"]) } : null,
            ["happiness"] = visible ? Happiness(p) : null,
        };
    }

    /// One record per area ({Severity, Description, HappinessRecentChange, …}); an area that did not land is null.
    private static JsonObject Happiness(JsonObject p)
    {
        var o = new JsonObject();
        foreach (var (key, prop) in Areas)
            o[key] = p[prop] is JsonObject r && r["Severity"].Int() is int sev
                ? new JsonObject { ["severity"] = sev, ["change"] = r["HappinessRecentChange"].Int(), ["text"] = Text.Plain(r["Description"]) }
                : null;
        return o;
    }

    private static JsonObject Last5(JsonObject f)
    {
        var minutes = new JsonArray();
        var list = f?["LastFiveMatchesList"] as JsonArray ?? new JsonArray();
        foreach (var m in list) minutes.Add(Minutes(m as JsonObject));
        var valid = Squad.Bool(f?["LastFiveMatchesListHasValidFixtures"]) == true && list.Count > 0;
        return new JsonObject
        {
            ["rating"] = valid ? Num(f["LastFiveMatchesRating"]) : null,
            ["valid"] = valid,
            ["minutes"] = minutes,
        };
    }

    /// 0/0 sub on/off = the full match (90). Sent off without a sub-off ends at the sending-off minute. Anything
    /// unreadable or inconsistent is null.
    private static int? Minutes(JsonObject m)
    {
        if (m == null || m["MinuteSubOn"].Int() is not int on || m["MinuteSubOff"].Int() is not int off) return null;
        var end = off > 0 ? off : (m["MinuteSentOff"].Int() is int so && so > 0 ? so : FullMatch);
        return end >= on && on >= 0 ? end - on : null;
    }
}
