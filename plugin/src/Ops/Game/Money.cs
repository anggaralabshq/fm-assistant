// Money values as {"display", "value"}: value = the game's base-currency number, display = the game's own
// formatting in the owner's chosen currency (BindableTranslationUtils.FormatCashValue). Main thread only.
using System.Text.Json.Nodes;

namespace FmAssistant;

internal static class Money
{
    public static JsonNode Of(JsonNode raw)
    {
        if (raw is not JsonValue jv || !jv.TryGetValue<double>(out var v))
        {
            if (raw is JsonValue s && double.TryParse((string)s, System.Globalization.NumberStyles.Float,
                    System.Globalization.CultureInfo.InvariantCulture, out var p)) v = p;
            else return null;
        }
        return new JsonObject { ["display"] = SI.Bindable.BindableTranslationUtils.FormatCashValue(v), ["value"] = v };
    }
}

internal static class JsonCopy
{
    /// .NET 6 has no JsonNode.DeepClone; nodes already parented must be copied before reuse.
    public static JsonNode Copy(this JsonNode n) => n == null ? null : JsonNode.Parse(n.ToJsonString());
}

internal static class JsonNum
{
    /// Decoded numbers arrive as int or double depending on the property; null for anything else.
    public static int? Int(this JsonNode n) => n is JsonValue v
        ? (v.TryGetValue<int>(out var i) ? i : v.TryGetValue<double>(out var d) ? (int)d : null) : null;
}
