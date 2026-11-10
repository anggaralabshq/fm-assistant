// op training: the Training screen's month view as data (read-only). Days come from the screen's per-day
// EventsList widgets (backing rows: session name + language-neutral session type, or a match with its opponent),
// paired in screen order with the day headers (binding day.DayOfTheMonth). Dates are assigned client-side from
// today (game.CurrentGameDate), see fm_assistant.training.assign_dates.
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using SI.Core;

namespace FmAssistant;

internal static class Training
{
    public const string Panel = "TrainingScreen";
    private const int MatchEvent = 1001;

    private static R<(List<string> Heads, List<string> Weeks, List<JsonArray> Days)> Screen()
    {
        var p = Ui.OpenPanels().Find(x => Ui.PanelId(x) == Panel);
        if (p == null) return R<(List<string>, List<string>, List<JsonArray>)>.Err("wrong-screen", $"expected {Panel}, open: {Ui.OpenIds()}");
        var heads = new List<string>(); var weeks = new List<string>();
        Ui.Walk(p, 0, n =>
        {
            if (!Ui.Visible(n)) return;
            var b = Ui.BindPath(n);
            if (b == "day.DayOfTheMonth") heads.Add(Ui.OwnText(n));
            else if (b == "week.TrainingScheduleName") weeks.Add(Ui.OwnText(n));
        });
        var days = ListRead.Widgets(Panel).Where(w => w.name == "EventsList").Select(w => ListRead.Rows(w, 3)).ToList();
        return (heads, weeks, days);
    }

    /// {} -> {today, days: [{index, day_label, day_of_month, weekday, schedule, sessions[3], session_types[3], match}]}
    public static async Task<JsonNode> Read(JsonObject a, CancellationToken ct)
    {
        await Nav.EnsureOpen(Panel, ct);
        // Day lists, headers and week names bind a few frames after the panel opens: poll until complete.
        (List<string> heads, List<string> weeks, List<JsonArray> days) screen = default;
        for (var tries = 0; tries < 20; tries++)
        {
            screen = await Reader.MainR(Screen, ct);
            var (h, w, d) = screen;
            if (h.Count > 0 && h.Count == d.Count && h.Count % 7 == 0 && w.Count == h.Count / 7) break;
            await Task.Delay(250, ct);
        }
        var (heads, weeks, days) = screen;
        if (heads.Count == 0 || heads.Count != days.Count)
            throw new OpException("ui-element-missing", $"{heads.Count} day headers vs {days.Count} day lists");
        if (weeks.Count != heads.Count / 7) weeks = new List<string>();   // never pair a partial list by position
        var opponents = days.SelectMany(d => d.OfType<JsonObject>())
            .Where(e => e["EventType"].Int() == MatchEvent && e["TeamOpponent"] is JsonObject)
            .Select(e => e["TeamOpponent"]["uid"].Int() ?? 0).Distinct().ToList();
        string today;
        var names = new Dictionary<int, string>();
        await using (var scope = new ReadScope(ct))
        {
            var g = await scope.ReadOne(() => FmAssistant.Tree.Find("game")?.Value, new[] { "CurrentGameDate" });
            today = (string)(await scope.Collect(new List<Plant> { g }))[0]["CurrentGameDate"]
                ?? throw new OpException("ui-element-missing", "game.CurrentGameDate");
            var tp = await scope.ReadMany(opponents.Select(u => (Func<TypedValue>)(() => Reader.TeamRef(u))).ToList(), new[] { "AbbreviatedName", "Name" });
            var tr = await scope.Collect(tp);
            for (var i = 0; i < opponents.Count; i++) names[opponents[i]] = (string)tr[i]["AbbreviatedName"] ?? (string)tr[i]["Name"];
        }
        var outDays = new JsonArray();
        for (var k = 0; k < days.Count; k++)
        {
            var sessions = new JsonArray(); var types = new JsonArray(); string match = null; int? weekday = null;
            foreach (var e in days[k].OfType<JsonObject>().Take(3))
            {
                if (e["EventType"].Int() == MatchEvent)
                {
                    match = e["TeamOpponent"] is JsonObject t ? names.GetValueOrDefault(t["uid"].Int() ?? 0) : "?";
                    sessions.Add(null); types.Add(null);
                    continue;
                }
                weekday ??= e["DayIndex"].Int();
                sessions.Add(e["SessionName"].Copy()); types.Add(e["SessionType"].Copy());
            }
            while (sessions.Count < 3) { sessions.Add(null); types.Add(null); }   // always 3 slots
            // The header is localized ("31 Agu", "1 Sep", "Sep 1"): take the first ASCII digit run anywhere.
            var digits = System.Text.RegularExpressions.Regex.Match(heads[k], "[0-9]+").Value;
            if (digits.Length == 0) throw new OpException("ui-element-missing", $"day header {k} has no day number: '{heads[k]}'");
            outDays.Add(new JsonObject
            {
                ["index"] = k,
                ["day_label"] = heads[k],
                ["day_of_month"] = int.TryParse(digits, out var dom) ? dom : null,
                ["weekday"] = weekday,
                ["schedule"] = k / 7 < weeks.Count ? weeks[k / 7] : null,
                ["sessions"] = sessions,
                ["session_types"] = types,
                ["match"] = match,
            });
        }
        return new JsonObject { ["today"] = today, ["days"] = outDays };
    }
}
