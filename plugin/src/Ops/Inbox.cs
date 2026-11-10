// op inbox: the manager's inbox, headless (no screen). Human.HumanPortalFilteredMessages (contexts team, StringType,
// PortalMessagesTab) lists NewsItemReference values newest first; each element is planted directly for its fields.
// Read-only: nothing is marked read, nothing is answered. See docs/protocol.md "inbox".
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using SI.Core;

namespace FmAssistant;

internal static class Inbox
{
    private const int DefaultMax = 50, HardMax = 200, BodyMax = 600;
    private static readonly Dictionary<string, int> Tabs = new() { ["all"] = 0, ["unread"] = 3 };
    private static readonly string[] HumanProps = { "HumanPortalFilteredMessages", "NumberUnreadMessages" };
    private static readonly string[] ItemProps =
        { "NewsItemId", "Date", "NewsItemTimeSent", "NewsItemHasBeenRead", "NewsItemIsImportant", "MediaNewsCategory", "NewsTitleString", "NewsBodyString" };

    /// {"since": "YYYY-MM-DD"|null, "tab": "all"|"unread", "max": 50} -> {today, unread, items: [Item]}
    public static async Task<JsonNode> Read(JsonObject a, CancellationToken ct)
    {
        var since = Meta.Str(a, "since");
        if (since != null && !System.DateTime.TryParseExact(since, "yyyy-MM-dd", System.Globalization.CultureInfo.InvariantCulture,
                System.Globalization.DateTimeStyles.None, out _))
            throw new OpException("bad-request", "since must be YYYY-MM-DD");
        var tabName = Meta.Str(a, "tab") ?? "all";
        if (!Tabs.TryGetValue(tabName, out var tab)) throw new OpException("bad-request", "tab must be all|unread");
        var max = Meta.Int(a, "max", DefaultMax, 1, HardMax);
        await Club.HumanUid(ct);   // no-career-loaded before any plant

        await using var scope = new ReadScope(ct);
        var today = await Training.Today(scope);
        var hp = await scope.ReadOne(() => FmAssistant.Tree.Find("Human")?.Value, HumanProps,
            ctx: Contexts.Values(HumanProps, () => new Dictionary<string, TypedValue> { ["PortalMessagesTab"] = TypedValue.Create(tab) }));
        var h = (await scope.Collect(new List<Plant> { hp }))[0];
        Reader.Require(h, "inbox", HumanProps);
        var elems = await Reader.Main(() => Reader.ListElems(hp["HumanPortalFilteredMessages"]?.Value, max), ct);
        var rows = await scope.Collect(await scope.ReadMany(elems.Select(e => (Func<TypedValue>)(() => e)).ToList(), ItemProps));

        var items = new JsonArray();
        foreach (var r in rows)
        {
            var date = (string)r["Date"];
            // newest first: stop at the first item older than `since`
            if (since != null && date != null && string.CompareOrdinal(date, since) < 0) break;
            items.Add(new JsonObject
            {
                ["id"] = r["NewsItemId"].Int(),
                ["date"] = date,
                ["time"] = r["NewsItemTimeSent"].Copy(),
                ["read"] = Squad.Bool(r["NewsItemHasBeenRead"]),
                ["important"] = Squad.Bool(r["NewsItemIsImportant"]),
                ["category"] = r["MediaNewsCategory"].Int(),
                ["title"] = Text.Plain(r["NewsTitleString"]),
                ["body"] = Text.Cut(Text.Plain(r["NewsBodyString"]), BodyMax),
            });
        }
        return new JsonObject { ["today"] = today, ["unread"] = h["NumberUnreadMessages"].Int(), ["items"] = items };
    }
}

internal static class Text
{
    private static readonly System.Text.RegularExpressions.Regex Tag =
        new System.Text.RegularExpressions.Regex(@"<[^<>]{1,200}>", System.Text.RegularExpressions.RegexOptions.Compiled);

    /// A decoded display string with markup tags (`<b>`, `</b>`, …) removed; null for anything but a string.
    public static string Plain(JsonNode n) => n is JsonValue v && v.TryGetValue<string>(out var s) ? Tag.Replace(s, "") : null;

    public static string Cut(string s, int max) => s == null || s.Length <= max ? s : s.Substring(0, max);
}
