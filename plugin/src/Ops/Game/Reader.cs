// Headless entity reads: plant a reference at a private binding path, bind child props, poll until they land.
// Pattern and native Create() calls adapted from redznn/fm-dof-mcp ReadEntity/NativeBindings (MIT).
// FM27 differences: Bind takes an owner object; DisplayValue/SortValue ids resolved by name, not hardcoded.
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Il2CppInterop.Runtime;
using SI.Bindable;
using SI.Bindable.Reference.Core;
using SI.Core;

namespace FmAssistant;

internal sealed class Plant
{
    public string Error;
    public FM.GamePlugin.GameInteropSubsystem Interop;
    public Bindings.Key ParentKey;
    public bool HasParent;
    public readonly List<Prop> Props = new List<Prop>();
    public Prop this[string name] => Props.Find(p => p.Name == name);
}

internal sealed class Prop
{
    public string Name, Note;
    public Bindings.Key Key;
    // Both delegates stay referenced until Close so neither side is collected while the game may call back.
    public Action<Bindings.Key, TypedValue> Managed;
    public Bindings.ValueChangedCallback Cb;
    public bool Bound;
    public TypedValue Value;
}

/// Owns every plant made through it. Plants are registered on the main thread the moment they exist (so a
/// cancelled op or a throw half-way through a batch still releases them), and DisposeAsync always enqueues the
/// close job, which the FIFO main-thread queue runs after any plant job still waiting.
internal sealed class ReadScope : IAsyncDisposable
{
    private readonly List<Plant> _owned = new List<Plant>();   // main thread only
    private readonly CancellationToken _ct;
    public ReadScope(CancellationToken ct) { _ct = ct; }

    public async Task<List<Plant>> ReadMany(List<Func<TypedValue>> parents, string[] props, int waitMs = 4000)
    {
        var plants = await Reader.MainR(() =>
        {
            if (!Native.Resolve(out var problem)) return R<List<Plant>>.Err("binding-api-changed", problem);
            var l = new List<Plant>();
            try
            {
                foreach (var p in parents) l.Add(Reader.PlantOne(p(), props, _owned));
            }
            catch (Exception e)  // never e.ToString() on the main thread
            {
                return R<List<Plant>>.Err("binding-api-changed", $"plant: {e.GetType().Name}: {e.Message}");
            }
            return l;
        }, _ct);
        var deadline = Environment.TickCount64 + waitMs;
        while (Environment.TickCount64 < deadline)
        {
            var pending = await Reader.Main(() => { var n = 0; foreach (var p in plants) n += Reader.Pending(p); return n; }, _ct);
            if (pending == 0) break;
            await Task.Delay(Reader.PollMs, _ct);
        }
        return plants;
    }

    public async Task<Plant> ReadOne(Func<TypedValue> parent, string[] props, int waitMs = 4000) =>
        (await ReadMany(new List<Func<TypedValue>> { parent }, props, waitMs))[0];

    public Task<List<JsonObject>> Collect(List<Plant> plants) =>
        Reader.Main(() => plants.ConvertAll(Reader.Collect), _ct);

    public async ValueTask DisposeAsync()
    {
        // Always enqueued, never tied to the op's token, long deadline: cleanup must run even after a cancel or a
        // stalled main thread. Waits a bounded time, never throws (it must not mask the op's own error).
        var job = Plugin.Queue.Run(() =>
        {
            foreach (var p in _owned) Reader.Close(p);
            _owned.Clear();
            return R<int>.Ok(0);
        }, CleanupDeadlineMs);
        await Task.WhenAny(job, Task.Delay(Reader.HopTimeoutMs));
    }

    private const int CleanupDeadlineMs = 10 * 60 * 1000;
}

internal static class Reader
{
    public const int PollMs = 150;
    internal const int HopTimeoutMs = 10000;
    // Seeded so node names from a reloaded ops assembly never collide with an earlier load's.
    private static int _counter = Environment.TickCount & 0x3fffffff;

    /// Run f on the main thread; errors come back as values and are thrown here, on the calling (WS) thread.
    public static async Task<T> MainR<T>(Func<R<T>> f, CancellationToken ct, bool needBindings = true)
    {
        if (needBindings && Plugin.Bindings == null) throw new OpException("bindings-not-captured", "game is still starting");
        var job = Plugin.Queue.Run(f, HopTimeoutMs);
        if (await Task.WhenAny(job, Task.Delay(HopTimeoutMs + 1000, ct)) != job)
        {
            ct.ThrowIfCancellationRequested();
            throw new OpException("main-thread-timeout", "the game's main thread did not answer");
        }
        return (await job).Unwrap();
    }

    public static Task<T> Main<T>(Func<T> f, CancellationToken ct, bool needBindings = true) =>
        MainR(() => R<T>.Ok(f()), ct, needBindings);

    public static TypedValue Wrap(Il2CppSystem.Object o) => TypedValue.Create<Il2CppSystem.Object>(o);
    public static TypedValue PersonRef(int uid) => Wrap(new FM.UI.PersonReference(uid).Cast<Il2CppSystem.Object>());
    public static TypedValue ClubRef(int uid) => Wrap(new FM.UI.ClubReference(uid).Cast<Il2CppSystem.Object>());
    public static TypedValue TeamRef(int uid) => Wrap(new FM.UI.TeamReference(uid).Cast<Il2CppSystem.Object>());

    /// WS thread: required props that did not land mean the game build renamed or moved them.
    public static void Require(JsonObject o, string what, params string[] names)
    {
        var missing = System.Linq.Enumerable.ToList(System.Linq.Enumerable.Where(names, n => o[n] == null));
        if (missing.Count > 0)
            throw new OpException("binding-api-changed", $"{what}: {string.Join(", ", missing)} did not resolve (renamed in this game build?)");
    }

    public static uint Id(string name) => PropertyIdentifierSet.Instance.GetID(Il2CppSystem.MemoryExtensions.AsSpan(name)).ID;

    /// Main thread. The value under `field` in each record of the list held by `list`, in list order (at most `max`);
    /// null where the entry is not a record, lacks the field, or holds a null reference. Values inside list records
    /// can be UI references with no uid (FixtureReference), so callers plant on these values directly (ReadMany).
    public static List<TypedValue> ListField(TypedValue list, string field, int max = 200)
    {
        var res = new List<TypedValue>();
        Il2CppSystem.Collections.IList l = null;
        try { l = list?.Get()?.TryCast<Il2CppSystem.Collections.IList>(); } catch { }
        if (l == null) return res;
        var id = Id(field);
        var n = Math.Min(l.Cast<Il2CppSystem.Collections.ICollection>().Count, max);  // indexer only, never foreach
        for (var i = 0; i < n; i++)
        {
            TypedValue v = null;
            try
            {
                var rec = l[i]?.TryCast<TypedValue>()?.Get()?.TryCast<Record>();
                if (rec != null && rec.TryGetValue(id, out var kv)) v = kv;
            }
            catch { }
            res.Add(IsNullRef(v) ? null : v);
        }
        return res;
    }

    /// Main thread. True for a missing value or the game's NullReference placeholder (e.g. a friendly's competition).
    public static bool IsNullRef(TypedValue v)
    {
        if (v == null) return true;
        try { return (v.AsString() ?? "").EndsWith("NullReference", StringComparison.Ordinal); } catch { return true; }
    }

    // ------------------------------------------------------------ main thread

    internal static Plant PlantOne(TypedValue parent, string[] props, List<Plant> owner = null)
    {
        var b = Plugin.Bindings;
        var plant = new Plant();
        if (parent == null) { plant.Error = "no-parent-value"; return plant; }
        if (!GameSubsystems.TryGet<FM.GamePlugin.GameInteropSubsystem>(out plant.Interop) || plant.Interop == null)
        { plant.Error = "game-interop-subsystem-not-found"; return plant; }

        // Flat name at the root (no dotted path) so Remove leaves no intermediate node behind.
        plant.ParentKey = Native.CreatePath(b, "__fm_" + Interlocked.Increment(ref _counter), Bindings.NodeFlags.Default);
        plant.HasParent = true;
        owner?.Add(plant);   // registered before any Bind, so a throw below still gets it closed
        foreach (var name in props)
        {
            var prop = new Prop { Name = name };
            plant.Props.Add(prop);
            if (Id(name) == 0) { prop.Note = "unknown-property"; continue; }
            prop.Key = Native.CreateRooted(b, plant.ParentKey, name, Bindings.NodeFlags.RequiresContext);
            prop.Managed = (k, v) => { if (Landed(v)) prop.Value = v; };
            prop.Cb = DelegateSupport.ConvertDelegate<Bindings.ValueChangedCallback>(prop.Managed);
            b.Bind(ref prop.Key, Plugin.BindOwner, prop.Cb);
            prop.Bound = true;
        }
        // Children first, then the parent value, so the dirty walk sees children that need data.
        b.Set(ref plant.ParentKey, parent, Bindings.SetFlags.UpdateHandler | Bindings.SetFlags.ForceUpdateValue);
        return plant;
    }

    internal static int Pending(Plant plant)
    {
        var n = 0;
        foreach (var p in plant.Props)
        {
            if (!p.Bound || p.Value != null) continue;
            try { var v = Plugin.Bindings.Get(ref p.Key); if (Landed(v)) p.Value = v; } catch { }
            if (p.Value == null) n++;
        }
        return n;
    }

    /// Decode every prop to JSON. Missing props listed under _missing.
    internal static JsonObject Collect(Plant plant)
    {
        var o = new JsonObject();
        var missing = new JsonArray();
        foreach (var p in plant.Props)
        {
            if (p.Value != null) o[p.Name] = Decode(p.Value);
            else missing.Add(p.Note != null ? $"{p.Name} ({p.Note})" : p.Name);
        }
        if (plant.Error != null) o["_error"] = plant.Error;
        if (missing.Count > 0) o["_missing"] = missing;
        return o;
    }

    /// Unbind and close every child, then remove the parent node. Failures are logged.
    internal static void Close(Plant plant)
    {
        var b = Plugin.Bindings;
        foreach (var p in plant.Props)
        {
            if (!p.Bound) continue;
            var k = p.Key;
            try { b.Unbind(ref k, p.Cb); } catch (Exception e) { Plugin.L.LogWarning($"unbind {p.Name}: {e.Message}"); }
            try { plant.Interop?.CloseChannel(k); } catch (Exception e) { Plugin.L.LogWarning($"close channel {p.Name}: {e.Message}"); }
            p.Bound = false;
        }
        if (plant.HasParent)
        {
            try { b.Remove(ref plant.ParentKey); } catch (Exception e) { Plugin.L.LogWarning($"remove parent: {e.Message}"); }
            plant.HasParent = false;
        }
    }

    private static bool Landed(TypedValue v)
    {
        if (v == null) return false;
        try { var rec = v.Get()?.TryCast<Record>(); if (rec != null) return rec.Count > 0; } catch { }
        return true;
    }

    private static readonly System.Text.RegularExpressions.Regex Numeric =
        new System.Text.RegularExpressions.Regex(@"^-?\d+(\.\d+)?[fmd]?$", System.Text.RegularExpressions.RegexOptions.Compiled);

    /// TypedValue -> JSON. Order: entity ref, date, record (PropertyValue / DisplayValue+SortValue), list, string/number.
    public static JsonNode Decode(TypedValue v, int depth = 0)
    {
        if (v == null) return null;
        string type = "?";
        try { type = v.DataType?.Name ?? "?"; } catch { }
        Il2CppSystem.Object boxed = null;
        try { boxed = v.Get(); } catch { }

        try
        {
            var r = boxed?.TryCast<FM.UI.DatabaseRecordReference>();
            if (r != null) return new JsonObject { ["$ref"] = r.Type.ToString(), ["uid"] = r.m_index };
        }
        catch { }
        if (type == "GameDate")
        {
            try { return FM.GamePlugin.GameDate.ToDateTime(FM.UI.VisualFunctions.GameDateFunctions.GetGameDate(v)).ToString("yyyy-MM-dd"); }
            catch { }
        }
        if (depth < 6)
        {
            try
            {
                var rec = boxed?.TryCast<Record>();
                if (rec != null)
                {
                    if (rec.TryGetValue(Id("PropertyValue"), out var pv) && pv != null) return Decode(pv, depth + 1);
                    if (rec.TryGetValue(Id("DisplayValue"), out var dv) && dv != null)
                    {
                        var node = new JsonObject { ["display"] = Decode(dv, depth + 1) };
                        if (rec.TryGetValue(Id("SortValue"), out var sv) && sv != null) node["sort"] = Decode(sv, depth + 1);
                        return node;
                    }
                    // Unknown record shape: copy the key ids out (no enumerator), name them, decode each value.
                    var probed = new JsonObject { ["$record"] = type };
                    var n = Math.Min(rec.Count, 40);
                    var ids = new Il2CppInterop.Runtime.InteropTypes.Arrays.Il2CppStructArray<uint>(rec.Count);
                    rec.Keys.CopyTo(ids, 0);
                    for (var i = 0; i < n; i++)
                    {
                        string name;
                        try { name = PropertyIdentifierSet.Instance.GetInfo(ids[i])?.Name ?? $"#{ids[i]}"; } catch { name = $"#{ids[i]}"; }
                        if (rec.TryGetValue(ids[i], out var kv) && kv != null) probed[name] = Decode(kv, depth + 1);
                    }
                    return probed;
                }
            }
            catch { }
            try
            {
                var list = boxed?.TryCast<Il2CppSystem.Collections.IList>();
                if (list != null)
                {
                    var arr = new JsonArray();
                    var n = Math.Min(list.Cast<Il2CppSystem.Collections.ICollection>().Count, 200);  // indexer only, never foreach (fm-dof-mcp crash-safety rule)
                    for (var i = 0; i < n; i++) arr.Add(Decode(list[i]?.TryCast<TypedValue>(), depth + 1));
                    return arr;
                }
            }
            catch { }
        }
        string s;
        try { s = v.AsString(); } catch { return $"<{type}>"; }
        if (!string.IsNullOrEmpty(s) && s.IndexOf('\u0001') >= 0)
        {
            try
            {
                var len = TextFunctions.StringLength(s);
                var plain = TextFunctions.SubString(s, 0, len, true, out _);
                if (!string.IsNullOrEmpty(plain)) s = plain;
            }
            catch { }
        }
        // Numbers arrive as numeric types or as plain digit strings (attribute PropertyValue). Names never are pure digits.
        if (s != null && Numeric.IsMatch(s)
            && double.TryParse(s.TrimEnd('f', 'm', 'd'), System.Globalization.NumberStyles.Float,
                System.Globalization.CultureInfo.InvariantCulture, out var num))
            return num;
        return s;
    }
}

/// Native Bindings.Create overloads (span-by-ref doesn't marshal through the interop wrappers).
/// Resolved by parameter types: Create(ReadOnlySpan<char> path, NodeFlags) and Create(Key root, ReadOnlySpan<char>, NodeFlags).
internal static class Native
{
    private static IntPtr _rooted, _path;
    private static string _problem;

    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate ulong RootedDel(IntPtr self, IntPtr rootKey, IntPtr span, int flags, IntPtr mi);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate ulong PathDel(IntPtr self, IntPtr span, int flags, IntPtr mi);

    private static string ParamType(IntPtr m, uint i)
    {
        var t = IL2CPP.il2cpp_method_get_param(m, i);
        return t == IntPtr.Zero ? "" : (Marshal.PtrToStringAnsi(IL2CPP.il2cpp_type_get_name(t)) ?? "").TrimEnd('&');  // by-ref params end in &
    }

    /// Main thread. False (with a description of what was found) when the game changed these methods.
    public static bool Resolve(out string problem)
    {
        if (_rooted != IntPtr.Zero && _path != IntPtr.Zero) { problem = null; return true; }
        if (_problem != null) { problem = _problem; return false; }
        var klass = Il2CppClassPointerStore<Bindings>.NativeClassPtr;
        var iter = IntPtr.Zero;
        IntPtr m;
        var seen = new List<string>();
        while ((m = IL2CPP.il2cpp_class_get_methods(klass, ref iter)) != IntPtr.Zero)
        {
            if (Marshal.PtrToStringAnsi(IL2CPP.il2cpp_method_get_name(m)) != "Create") continue;
            var pc = IL2CPP.il2cpp_method_get_param_count(m);
            var types = new List<string>();
            for (uint i = 0; i < pc; i++) types.Add(ParamType(m, i));
            seen.Add($"Create({string.Join(", ", types)})");
            bool Span(int i) => types[i].Contains("ReadOnlySpan") && types[i].Contains("Char");
            bool Flags(int i) => types[i].EndsWith("NodeFlags");
            if (pc == 3 && types[0].EndsWith("Key") && Span(1) && Flags(2)) _rooted = m;
            else if (pc == 2 && Span(0) && Flags(1)) _path = m;
        }
        if (_rooted == IntPtr.Zero || _path == IntPtr.Zero)
            _problem = "Bindings.Create overloads not found; saw " + string.Join("; ", seen);
        problem = _problem;
        return _problem == null;
    }

    private static ulong WithSpan(string s, Func<IntPtr, ulong> call)
    {
        var str = Marshal.StringToHGlobalUni(s);
        var span = Marshal.AllocHGlobal(IntPtr.Size + 8);
        try
        {
            Marshal.WriteIntPtr(span, 0, str);
            Marshal.WriteInt32(span, IntPtr.Size, s.Length);
            return call(span);
        }
        finally { Marshal.FreeHGlobal(span); Marshal.FreeHGlobal(str); }
    }

    public static Bindings.Key CreatePath(Bindings b, string path, Bindings.NodeFlags flags)
    {
        var fn = Marshal.GetDelegateForFunctionPointer<PathDel>(Marshal.ReadIntPtr(_path));
        return new Bindings.Key(WithSpan(path, sp => fn(b.Pointer, sp, (int)flags, _path)));
    }

    public static Bindings.Key CreateRooted(Bindings b, Bindings.Key root, string rel, Bindings.NodeFlags flags)
    {
        var fn = Marshal.GetDelegateForFunctionPointer<RootedDel>(Marshal.ReadIntPtr(_rooted));
        var rootMem = Marshal.AllocHGlobal(8);
        try
        {
            Marshal.WriteInt64(rootMem, unchecked((long)root.m_key));
            return new Bindings.Key(WithSpan(rel, sp => fn(b.Pointer, rootMem, sp, (int)flags, _rooted)));
        }
        finally { Marshal.FreeHGlobal(rootMem); }
    }
}
