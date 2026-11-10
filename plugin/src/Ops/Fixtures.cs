// op fixtures: the first team's next fixtures, the assistant's threat note and the next opponent's most used
// formation (read-only). See docs/protocol.md "fixtures".
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using SI.Core;

namespace FmAssistant;

internal static class Fixtures
{
    private const int HomeLocation = 1;   // NextMatchLocation seen as 1 when the own team was HomeTeam
    private static readonly string[] FixtureProps = { "FixtureDate", "HomeTeam", "AwayTeam", "Competition" };

    /// {"n": 5} (1-10) -> {today, team_uid, next: Fixture|null, upcoming: [Fixture], threat, opponent_formation}
    public static async Task<JsonNode> Read(JsonObject a, CancellationToken ct)
    {
        var n = Meta.Int(a, "n", 5, 1, 10);
        var clubUid = await Club.HumanUid(ct);
        await using var scope = new ReadScope(ct);
        var club = (await scope.Collect(new List<Plant> { await scope.ReadOne(() => Reader.ClubRef(clubUid), new[] { "MainTeam" }) }))[0];
        var teamUid = (club["MainTeam"] as JsonObject)?["uid"].Int() ?? throw new OpException("ui-element-missing", "club has no MainTeam");
        // Next5FixturesData holds 5 entries; more than 5 come from the league list (league fixtures only).
        var teamProps = new List<string> { "NextFixture", "NextMatchOpponent", "NextMatchLocation", "Next5FixturesData", "NextOppositionThreatLevelAssessment" };
        if (n > 5) teamProps.Add("RemainingLeagueFixtures");
        var tp = await scope.ReadOne(() => Reader.TeamRef(teamUid), teamProps.ToArray());
        var t = (await scope.Collect(new List<Plant> { tp }))[0];
        Reader.Require(t, "team", "Next5FixturesData");
        var today = await Training.Today(scope);

        // Fixture values: NextFixture first, then the list records' Fixture values (no uid: planted directly).
        // Each list record also names the opponent (Team): the fallback when the own team is in neither slot.
        var recTeams = new List<int?>();
        foreach (var (prop, cap) in n > 5 ? new[] { ("Next5FixturesData", 5), ("RemainingLeagueFixtures", n) } : new[] { ("Next5FixturesData", 5) })
            recTeams.AddRange((t[prop] as JsonArray ?? new JsonArray()).Take(cap).Select(r => ((r as JsonObject)?["Team"] as JsonObject)?["uid"].Int()));
        var (nextVal, listVals) = await Reader.Main(() =>
        {
            var nv = Reader.IsNullRef(tp["NextFixture"]?.Value) ? null : tp["NextFixture"].Value;
            var lv = Reader.ListField(tp["Next5FixturesData"]?.Value, "Fixture", 5);
            if (n > 5) lv.AddRange(Reader.ListField(tp["RemainingLeagueFixtures"]?.Value, "Fixture", n));
            return (nv, lv);
        }, ct);
        var all = new List<(TypedValue V, int? Team)>();
        if (nextVal != null) all.Add((nextVal, (t["NextMatchOpponent"] as JsonObject)?["uid"].Int()));
        for (var i = 0; i < listVals.Count; i++)
            if (listVals[i] != null) all.Add((listVals[i], i < recTeams.Count ? recTeams[i] : null));
        var fp = await scope.ReadMany(all.Select(x => (Func<TypedValue>)(() => x.V)).ToList(), FixtureProps);
        var fr = await scope.Collect(fp);

        // Competition names (planted on each fixture's Competition value, once per comp uid) and team names.
        var compAt = new Dictionary<int, int>();
        for (var i = 0; i < fr.Count; i++)
            if (fr[i]["Competition"] is JsonObject c && c["uid"].Int() is int cu) compAt.TryAdd(cu, i);
        var compUids = compAt.Keys.ToList();
        var cp = await scope.ReadMany(compUids.Select(cu => (Func<TypedValue>)(() => fp[compAt[cu]]["Competition"]?.Value)).ToList(), new[] { "Name" });
        var cr = await scope.Collect(cp);
        var comps = new Dictionary<int, string>();
        for (var i = 0; i < compUids.Count; i++) comps[compUids[i]] = (string)cr[i]["Name"];

        var fixtures = fr.Select((f, i) => Raw(f, teamUid, all[i].Team)).ToList();
        var teamUids = fixtures.Select(f => f.Opp).Where(u => u != null).Select(u => u.Value).Distinct().ToList();
        var tr = await scope.Collect(await scope.ReadMany(teamUids.Select(u => (Func<TypedValue>)(() => Reader.TeamRef(u))).ToList(), new[] { "Name" }));
        var names = new Dictionary<int, string>();
        for (var i = 0; i < teamUids.Count; i++) names[teamUids[i]] = (string)tr[i]["Name"];
        string formation = null;
        if (nextVal != null && fixtures[0].Opp is int ou)
        {
            var orow = (await scope.Collect(new List<Plant> { await scope.ReadOne(() => Reader.TeamRef(ou), new[] { "MostUsedFormation" }) }))[0];
            formation = NonEmpty(orow["MostUsedFormation"]);
        }

        JsonObject next = null;
        if (nextVal != null)
        {
            var f = fixtures[0];
            // NextMatchLocation disagreeing with the HomeTeam/AwayTeam comparison (e.g. a neutral venue): unknown.
            var loc = t["NextMatchLocation"].Int();
            if (f.Home != null && loc != null && (loc == HomeLocation) != f.Home) f = f with { Home = null };
            next = Out(f, names, comps);
        }
        var upcoming = fixtures.Skip(nextVal != null ? 1 : 0)
            .Where(f => f.Date != null && string.CompareOrdinal(f.Date, today) >= 0)
            .GroupBy(f => (f.Date, f.Opp)).Select(g => g.First())
            .OrderBy(f => f.Date, StringComparer.Ordinal).Take(n)
            .Select(f => next != null && f.Date == (string)next["date"] && f.Opp == next["opponent"]?["uid"].Int() ? next.Copy() : Out(f, names, comps))
            .ToList();
        return new JsonObject
        {
            ["today"] = today,
            ["team_uid"] = teamUid,
            ["next"] = next,
            ["upcoming"] = new JsonArray(upcoming.ToArray()),
            ["threat"] = nextVal != null ? NonEmpty(t["NextOppositionThreatLevelAssessment"]) : null,
            ["opponent_formation"] = formation,
        };
    }

    private record Fx(string Date, int? Opp, bool? Home, int? Comp);

    private static Fx Raw(JsonObject f, int own, int? listedOpp)
    {
        var h = (f["HomeTeam"] as JsonObject)?["uid"].Int();
        var aw = (f["AwayTeam"] as JsonObject)?["uid"].Int();
        bool? home = h == own ? true : aw == own ? false : null;
        int? opp = home == true ? aw : home == false ? h : listedOpp;
        return new Fx((string)f["FixtureDate"], opp, home, (f["Competition"] as JsonObject)?["uid"].Int());
    }

    private static JsonObject Out(Fx f, Dictionary<int, string> names, Dictionary<int, string> comps) => new()
    {
        ["date"] = f.Date,
        ["opponent"] = f.Opp is int u ? new JsonObject { ["uid"] = u, ["name"] = names.GetValueOrDefault(u) } : null,
        ["home"] = f.Home,
        ["competition"] = f.Comp is int c ? comps.GetValueOrDefault(c) : null,
    };

    private static string NonEmpty(JsonNode n) => n is JsonValue v && v.TryGetValue<string>(out var s) && s.Trim().Length > 0 ? s : null;
}
