// FM Assistant BepInEx plugin. Tick + bindings-capture pattern adapted from redznn/fm-dof-mcp (MIT).
using System;
using System.Threading;
using BepInEx;
using BepInEx.Logging;
using BepInEx.Unity.IL2CPP;
using HarmonyLib;
using SI.Bindable;

[assembly: System.Runtime.CompilerServices.InternalsVisibleTo("FmAssistant.Ops")]

namespace FmAssistant;

[BepInPlugin("dev.fmassistant", "FM Assistant", Version)]
public class Plugin : BasePlugin
{
    public const string Version = "0.1.0";
    public const int Port = 7788;
    internal static ManualLogSource L;
    internal static readonly MainThreadQueue Queue = new MainThreadQueue();
    internal static BindingSubsystem Bindings { get; private set; }
    internal static string GameBuild { get; private set; }
    internal static Il2CppSystem.Object BindOwner { get; private set; }   // created on the main thread at bindings capture

    private WsServer _server;
    private static bool _ticking;
    private static int _mainThreadId;
    internal static long Ticks, LastTickMs;
    // Per-source tick counts (diag). RepaintPanels alone is not reliable: some launches never call our prefix.
    internal static readonly string[] TickSources = { "UIElementsRuntimeUtility.RepaintPanels", "PanelManager.Tick", "Bindings.Update" };
    internal static readonly long[] SourceTicks = new long[3];

    public override void Load()
    {
        L = Log;
        GameBuild = UnityEngine.Application.version;
        var h = new Harmony("dev.fmassistant");
        _mainThreadId = Thread.CurrentThread.ManagedThreadId;  // chainloader runs on Unity's main thread
        // Main-thread tick from several per-frame game methods (no MonoBehaviour injection on arm64). Drain is
        // idempotent per frame and only runs on the main thread, so extra sources cost nothing.
        var patched = 0;
        patched += Hook(h, AccessTools.Method(AccessTools.TypeByName("UnityEngine.UIElements.UIElementsRuntimeUtility"), "RepaintPanels"), nameof(Tick0));
        patched += Hook(h, AccessTools.Method(typeof(PanelManager), "Tick"), nameof(Tick1));
        patched += Hook(h, AccessTools.Method(typeof(SI.Bindable.Bindings), "Update"), nameof(Tick2));
        if (patched == 0) { L.LogError("no tick source found; plugin disabled"); return; }
        h.Patch(AccessTools.Method(typeof(BindingSubsystem), "Initialise"),
            postfix: new HarmonyMethod(typeof(Plugin), nameof(BindingsInitialised)));

        OpsLoader.Load(out var opsMessage);
        L.LogInfo(opsMessage);
        _server = new WsServer(Port);
        _server.Start();
        Session.Publish(Port, GameBuild);
        L.LogInfo($"{Version} loaded, ws://127.0.0.1:{Port}/, game {GameBuild}");
    }

    private static int Hook(Harmony h, System.Reflection.MethodInfo m, string prefix)
    {
        if (m == null) { L.LogWarning($"tick source missing: {prefix}"); return 0; }
        try { h.Patch(m, prefix: new HarmonyMethod(typeof(Plugin), prefix)); return 1; }
        catch (Exception e) { L.LogWarning($"tick source {m.Name}: {e.GetType().Name}: {e.Message}"); return 0; }
    }

    private static void Tick0() => Tick(0);
    private static void Tick1() => Tick(1);
    private static void Tick2() => Tick(2);

    // Harmony prefix: nothing may escape into the game's frame.
    private static void Tick(int source)
    {
        if (Thread.CurrentThread.ManagedThreadId != _mainThreadId) return;
        if (Interlocked.Increment(ref SourceTicks[source]) == 1) L.LogInfo($"first tick from {TickSources[source]}");
        Interlocked.Increment(ref Ticks);
        LastTickMs = Environment.TickCount64;
        if (_ticking) return;
        _ticking = true;
        try { Queue.Drain(); }
        catch (Exception e) { L.LogError($"tick: {e.GetType().Name}: {e.Message}"); }
        finally { _ticking = false; }
    }

    private static void BindingsInitialised(BindingSubsystem __instance)
    {
        try
        {
            if (Bindings != null) return;
            BindOwner = new Il2CppSystem.Object();
            Bindings = __instance;
            L.LogInfo("BindingSubsystem captured");
        }
        catch (Exception e) { L.LogError($"bindings capture: {e.GetType().Name}: {e.Message}"); }
    }
}
