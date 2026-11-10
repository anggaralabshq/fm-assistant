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

namespace FmSpike;

internal sealed class Plant
{
    public string Error;
    public FM.GamePlugin.GameInteropSubsystem Interop;
    public readonly List<Prop> Props = new List<Prop>();
}

internal sealed class Prop
{
    public string Name, Note;
    public Bindings.Key Key;
    public Bindings.ValueChangedCallback Cb;
    public bool Bound;
    public TypedValue Value;   // last landed value (kept for chained reads)
}

internal static class Reader
{
    private const int PollMs = 150;
    private static int _counter;
    private static readonly Il2CppSystem.Object Owner = new Il2CppSystem.Object();

    /// Read props off each parent value, all planted at once, one shared poll loop. WS thread.
    public static async Task<List<Plant>> ReadMany(List<Func<TypedValue>> parents, string[] props, int waitMs = 4000)
    {
        var plants = await Main(() => { var l = new List<Plant>(); foreach (var p in parents) l.Add(PlantOne(p(), props)); return l; });
        var deadline = Environment.TickCount64 + waitMs;
        while (Environment.TickCount64 < deadline)
        {
            var pending = await Main(() => { var n = 0; foreach (var p in plants) n += Pending(p); return n; });
            if (pending == 0) break;
            await Task.Delay(PollMs);
        }
        return plants;
    }

    public static Task<T> Main<T>(Func<T> f) => Plugin.Queue.Run(() =>
    {
        if (Plugin.Bindings == null) throw new OpException("bindings-not-captured", "BindingSubsystem not initialised yet");
        return f();
    });

    public static TypedValue Wrap(Il2CppSystem.Object o) => TypedValue.Create<Il2CppSystem.Object>(o);
    public static TypedValue PersonRef(int uid) => Wrap(new FM.UI.PersonReference(uid).Cast<Il2CppSystem.Object>());
    public static TypedValue ClubRef(int uid) => Wrap(new FM.UI.ClubReference(uid).Cast<Il2CppSystem.Object>());
    public static TypedValue TeamRef(int uid) => Wrap(new FM.UI.TeamReference(uid).Cast<Il2CppSystem.Object>());

    // ------------------------------------------------------------ main thread

    private static Plant PlantOne(TypedValue parent, string[] props)
    {
        var b = Plugin.Bindings;
        var plant = new Plant();
        if (parent == null) { plant.Error = "no-parent-value"; return plant; }
        if (!GameSubsystems.TryGet<FM.GamePlugin.GameInteropSubsystem>(out plant.Interop) || plant.Interop == null)
        { plant.Error = "game-interop-subsystem-not-found"; return plant; }

        var parentKey = Native.CreatePath(b, "__fmspike." + Interlocked.Increment(ref _counter), Bindings.NodeFlags.Default);
        foreach (var name in props)
        {
            var prop = new Prop { Name = name };
            plant.Props.Add(prop);
            if (PropertyIdentifierSet.Instance.GetID(Il2CppSystem.MemoryExtensions.AsSpan(name)).ID == 0)
            { prop.Note = "unknown-property"; continue; }
            prop.Key = Native.CreateRooted(b, parentKey, name, Bindings.NodeFlags.RequiresContext);
            prop.Cb = DelegateSupport.ConvertDelegate<Bindings.ValueChangedCallback>(
                (Action<Bindings.Key, TypedValue>)((k, v) => { if (Landed(v)) prop.Value = v; }));
            b.Bind(ref prop.Key, Owner, prop.Cb);
            prop.Bound = true;
        }
        // Children first, then the parent value, so the dirty walk sees children that need data.
        b.Set(ref parentKey, parent, Bindings.SetFlags.UpdateHandler | Bindings.SetFlags.ForceUpdateValue);
        return plant;
    }

    private static int Pending(Plant plant)
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

    /// Decode every prop to JSON and close channels. Main thread.
    public static JsonObject Collect(Plant plant)
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

    public static void Close(Plant plant)
    {
        foreach (var p in plant.Props)
        {
            if (!p.Bound) continue;
            var k = p.Key;
            try { Plugin.Bindings.Unbind(ref k, p.Cb); } catch { }
            try { plant.Interop?.CloseChannel(k); } catch { }
            p.Bound = false;
        }
    }

    private static bool Landed(TypedValue v)
    {
        if (v == null) return false;
        try { var rec = v.Get()?.TryCast<Record>(); if (rec != null) return rec.Count > 0; } catch { }
        return true;
    }

    private static readonly string[] RecordProbe = { "JobString", "Name", "Text", "Value", "Job", "Role" };

    private static uint Id(string name) => PropertyIdentifierSet.Instance.GetID(Il2CppSystem.MemoryExtensions.AsSpan(name)).ID;

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
        if (depth < 3)
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
                    // Unknown record shape: probe a few common keys (TryGetValue only, never enumerate).
                    var probed = new JsonObject { ["$record"] = type, ["count"] = rec.Count };
                    foreach (var k in RecordProbe)
                        if (rec.TryGetValue(Id(k), out var kv) && kv != null) probed[k] = Decode(kv, depth + 1);
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
        if (s != null && System.Text.RegularExpressions.Regex.IsMatch(s, @"^-?\d+(\.\d+)?[fmd]?$")
            && double.TryParse(s?.TrimEnd('f', 'm', 'd'), System.Globalization.NumberStyles.Float,
                System.Globalization.CultureInfo.InvariantCulture, out var num))
            return num;
        return s;
    }
}

/// Native Bindings.Create overloads (span-by-ref doesn't marshal through the interop wrappers).
internal static class Native
{
    private static IntPtr _rooted, _path;

    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate ulong RootedDel(IntPtr self, IntPtr rootKey, IntPtr span, int flags, IntPtr mi);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate ulong PathDel(IntPtr self, IntPtr span, int flags, IntPtr mi);

    private static void Resolve()
    {
        if (_rooted != IntPtr.Zero && _path != IntPtr.Zero) return;
        var klass = Il2CppClassPointerStore<Bindings>.NativeClassPtr;
        var iter = IntPtr.Zero;
        IntPtr m;
        while ((m = IL2CPP.il2cpp_class_get_methods(klass, ref iter)) != IntPtr.Zero)
        {
            if (Marshal.PtrToStringAnsi(IL2CPP.il2cpp_method_get_name(m)) != "Create") continue;
            var pc = (int)IL2CPP.il2cpp_method_get_param_count(m);
            if (pc == 3 && _rooted == IntPtr.Zero) _rooted = m;
            else if (pc == 2 && _path == IntPtr.Zero) _path = m;
        }
        if (_rooted == IntPtr.Zero || _path == IntPtr.Zero) throw new OpException("binding-api-changed", "Bindings.Create overloads not found");
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
        Resolve();
        var fn = Marshal.GetDelegateForFunctionPointer<PathDel>(Marshal.ReadIntPtr(_path));
        return new Bindings.Key(WithSpan(path, sp => fn(b.Pointer, sp, (int)flags, _path)));
    }

    public static Bindings.Key CreateRooted(Bindings b, Bindings.Key root, string rel, Bindings.NodeFlags flags)
    {
        Resolve();
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
