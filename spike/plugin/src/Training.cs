// Training calendar read/change through the in-game UI. Elements are found by binding path and element name
// (language-neutral); session names themselves are localized display text.
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using UnityEngine.UIElements;
using Panel = SI.Bindable.Panel;

namespace FmSpike;

internal static class Training
{
    private const string Screen = "TrainingScreen", Card = "TrainingSessionSelectCard";
    private const string DayBind = "day.DayOfTheMonth", WeekBind = "week.TrainingScheduleName";
    private const string SessionBind = "Event.SessionName", OpponentBind = "Event.TeamOpponent.AbbreviatedName";
    private const string OptionBind = "item.DisplayValue";

    private sealed class El { public VisualElement E; public string Bind, Text; public float X, Y; }

    private sealed class Day { public string Label, Week; public List<El> Slots = new List<El>(); }

    private static Panel Find(string id) =>
        Ui.OpenPanels().FirstOrDefault(p => { try { return p.PanelID?.name == id; } catch { return false; } });

    private static List<El> Bound(Panel p)
    {
        var l = new List<El>();
        Ui.Walk(p, 0, n =>
        {
            var b = Ui.BindPath(n);
            if (b == null || !Ui.Visible(n)) return;
            var c = n.worldBound.center;
            l.Add(new El { E = n, Bind = b, Text = Ui.OwnText(n), X = c.x, Y = c.y });
        });
        return l;
    }

    /// Calendar days in screen order; each with its 3 slots (a match occupies a slot as "vs <opponent>").
    private static List<Day> Days()
    {
        var p = Find(Screen) ?? throw new OpException("wrong-screen", $"expected {Screen}");
        var els = Bound(p);
        var heads = els.Where(e => e.Bind == DayBind).OrderBy(e => e.Y).ThenBy(e => e.X).ToList();
        var weeks = els.Where(e => e.Bind == WeekBind).ToList();
        var cells = els.Where(e => e.Bind == SessionBind || e.Bind == OpponentBind).ToList();
        var days = heads.Select(h => new Day
        {
            Label = h.Text,
            Week = weeks.Where(w => Math.Abs(w.Y - h.Y) < 45).Select(w => w.Text).FirstOrDefault(),
        }).ToList();
        foreach (var c in cells)
        {
            // Owning day: same row band (cells sit 20-130 px below their header), right-most header left of the cell.
            var i = heads.Select((h, k) => (h, k)).Where(t => c.Y - t.h.Y > 15 && c.Y - t.h.Y < 135 && t.h.X <= c.X + 10)
                .OrderByDescending(t => t.h.X).Select(t => t.k).DefaultIfEmpty(-1).First();
            if (i >= 0) days[i].Slots.Add(c);
        }
        foreach (var d in days) d.Slots = d.Slots.OrderBy(s => s.Y).ToList();
        return days;
    }

    private static string SlotText(El s) => s.Bind == OpponentBind ? "vs " + s.Text : s.Text;

    public static JsonNode Get(JsonObject args)
    {
        var a = new JsonArray();
        var days = Days();
        for (var i = 0; i < days.Count; i++)
            a.Add(new JsonObject
            {
                ["index"] = i, ["label"] = days[i].Label, ["week"] = days[i].Week,
                ["sessions"] = new JsonArray(days[i].Slots.Select(s => (JsonNode)SlotText(s)).ToArray()),
            });
        return new JsonObject { ["screen"] = Screen, ["days"] = a };
    }

    /// {"index": day index from training_get, "slot": 0-2, "name": "<session display name>"} -> {before, after}
    public static async Task<JsonNode> Set(JsonObject args)
    {
        var index = (int?)args["index"] ?? throw new OpException("bad-request", "index required");
        var slot = (int?)args["slot"] ?? throw new OpException("bad-request", "slot required");
        var name = (string)args["name"] ?? throw new OpException("bad-request", "name required");

        var before = await Reader.Main(() =>
        {
            var days = Days();
            if (index < 0 || index >= days.Count || slot < 0 || slot >= days[index].Slots.Count)
                throw new OpException("ui-element-missing", $"day {index} slot {slot}");
            var cell = days[index].Slots[slot];
            if (cell.Bind != SessionBind) throw new OpException("match-slot", $"day {index} slot {slot} is a match");
            Ui.Click(cell.E);
            return cell.Text;
        });
        await Task.Delay(1500);

        try
        {
            // Option radios also include the category row (top-most row). Try the visible options, then each category.
            var picked = await Reader.Main(() => ClickOption(name, -1));
            for (var cat = 0; picked == null && cat < 8; cat++)
            {
                var hasCat = await Reader.Main(() => ClickCategory(cat));
                if (!hasCat) break;
                await Task.Delay(800);
                picked = await Reader.Main(() => ClickOption(name, -1));
            }
            if (picked == null) throw new OpException("ui-element-missing", $"session option '{name}'");
            await Task.Delay(800);
            await Reader.Main(() => ClickNamed("confirm"));
        }
        catch
        {
            try { await Reader.Main(() => ClickNamed("cancel")); } catch { }
            throw;
        }
        await Task.Delay(1500);
        var after = await Reader.Main(() => { var d = Days(); return SlotText(d[index].Slots[slot]); });
        return new JsonObject { ["before"] = before, ["after"] = after };
    }

    private static List<El> Options()
    {
        var p = Find(Card) ?? throw new OpException("ui-element-missing", Card + " did not open");
        return Bound(p).Where(e => e.Bind == OptionBind).ToList();
    }

    private static string ClickOption(string name, int _)
    {
        var opts = Options();
        var top = opts.Count == 0 ? 0 : opts.Min(o => o.Y);
        var hit = opts.FirstOrDefault(o => o.Y > top + 5 && o.Text == name);
        if (hit == null) return null;
        Ui.Click(hit.E);
        return hit.Text;
    }

    private static bool ClickCategory(int k)
    {
        var opts = Options();
        if (opts.Count == 0) return false;
        var top = opts.Min(o => o.Y);
        var cats = opts.Where(o => o.Y <= top + 5).OrderBy(o => o.X).ToList();
        if (k >= cats.Count) return false;
        Ui.Click(cats[k].E);
        return true;
    }

    private static bool ClickNamed(string elementName)
    {
        var p = Find(Card) ?? throw new OpException("ui-element-missing", Card);
        VisualElement hit = null;
        Ui.Walk(p, 0, n => { if (hit == null && n.name == elementName && Ui.Visible(n)) hit = n; });
        if (hit == null) throw new OpException("ui-element-missing", elementName);
        Ui.Click(hit);
        return true;
    }
}
