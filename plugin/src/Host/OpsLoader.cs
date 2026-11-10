// Loads the ops assembly (FmAssistant.Ops) from bytes into its own AssemblyLoadContext, so a new build can be
// swapped in without restarting the game (op dev_reload). The file is read, never mapped, so overwriting it
// while the game runs is safe. Older contexts are not unloaded (non-collectible: Il2CppInterop delegate
// trampolines may still point into them); a reload leaks one small assembly, acceptable for development.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.Loader;
using System.Security.Cryptography;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;

namespace FmAssistant;

internal static class OpsLoader
{
    public const string FileName = "FmAssistant.Ops.ops";   // not .dll: BepInEx must not treat it as a plugin
    private static int _loads;
    private static string _sha, _loadedAt, _error;
    private static readonly object Lock = new object();

    public static string FilePath => Path.Combine(BepInEx.Paths.PluginPath, "FmAssistant", FileName);

    private sealed class OpsContext : AssemblyLoadContext
    {
        public OpsContext(string name) : base(name, isCollectible: false) { }

        // Everything except the ops assembly itself resolves to what the default context already has
        // (host, interop, BepInEx), so types are shared with the host.
        protected override Assembly Load(AssemblyName name) =>
            AppDomain.CurrentDomain.GetAssemblies().FirstOrDefault(a => a.GetName().Name == name.Name
                && AssemblyLoadContext.GetLoadContext(a) == AssemblyLoadContext.Default);
    }

    /// Load (or reload) the ops table. Never throws; on failure the previous table stays.
    public static bool Load(out string message)
    {
        lock (Lock)
        {
            try
            {
                var bytes = File.ReadAllBytes(FilePath);
                var sha = Convert.ToHexString(SHA256.HashData(bytes)).Substring(0, 12).ToLowerInvariant();
                var n = Interlocked.Increment(ref _loads);
                var asm = new OpsContext($"fm-assistant-ops-{n}").LoadFromStream(new MemoryStream(bytes));
                var entry = asm.GetType("FmAssistant.OpsEntry")?.GetMethod("Ops", BindingFlags.Static | BindingFlags.NonPublic | BindingFlags.Public)
                    ?? throw new MissingMethodException("FmAssistant.OpsEntry.Ops");
                var ops = (Dictionary<string, (OpHandler Handler, int TimeoutSeconds)>)entry.Invoke(null, null);
                var table = OpRegistry.HostOps();
                foreach (var kv in ops) if (!table.ContainsKey(kv.Key)) table[kv.Key] = kv.Value;
                OpRegistry.Ops = table;
                _sha = sha; _loadedAt = DateTime.Now.ToString("HH:mm:ss"); _error = null;
                message = $"ops {sha} loaded (#{n}, {ops.Count} ops)";
                return true;
            }
            catch (Exception e)
            {
                var inner = e is TargetInvocationException t && t.InnerException != null ? t.InnerException : e;
                _error = $"{inner.GetType().Name}: {inner.Message}";   // never ToString(): see MainThreadQueue
                message = $"ops load failed: {_error}";
                return false;
            }
        }
    }

    /// {} -> {"loaded": sha, "ops": n}. Re-reads the ops file from the plugin folder.
    public static Task<JsonNode> Reload(JsonObject a, CancellationToken ct)
    {
        if (!Load(out var msg)) throw new OpException("internal", msg);
        Plugin.L.LogInfo(msg);
        return Task.FromResult<JsonNode>(new JsonObject { ["loaded"] = _sha, ["ops"] = OpRegistry.Ops.Count, ["message"] = msg });
    }

    /// Answered on the WS thread (no main-thread hop): is the tick running, which ops build is loaded?
    public static Task<JsonNode> Diag(JsonObject a, CancellationToken ct)
    {
        var sources = new JsonObject();
        for (var i = 0; i < Plugin.TickSources.Length; i++) sources[Plugin.TickSources[i]] = Interlocked.Read(ref Plugin.SourceTicks[i]);
        return Task.FromResult<JsonNode>(new JsonObject
        {
            ["ticks"] = Interlocked.Read(ref Plugin.Ticks),
            ["last_tick_ms_ago"] = Plugin.Ticks == 0 ? null : Environment.TickCount64 - Plugin.LastTickMs,
            ["queued"] = Plugin.Queue.Count,
            ["sources"] = sources,
            ["bindings_captured"] = Plugin.Bindings != null,
            ["ops"] = new JsonObject { ["sha"] = _sha, ["loaded_at"] = _loadedAt, ["loads"] = _loads, ["error"] = _error },
        });
    }
}
