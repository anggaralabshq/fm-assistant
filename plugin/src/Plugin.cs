// FM Assistant BepInEx plugin. Tick + bindings-capture pattern adapted from redznn/fm-dof-mcp (MIT).
using System;
using System.Threading;
using BepInEx;
using BepInEx.Logging;
using BepInEx.Unity.IL2CPP;
using HarmonyLib;
using SI.Bindable;

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

    private WsServer _server;
    private static bool _ticking;
    internal static long Ticks, LastTickMs;

    public override void Load()
    {
        L = Log;
        GameBuild = UnityEngine.Application.version;
        var h = new Harmony("dev.fmassistant");
        // Main-thread tick: prefix on UIElements repaint (stable frame boundary; no MonoBehaviour injection on arm64).
        var repaint = AccessTools.Method(AccessTools.TypeByName("UnityEngine.UIElements.UIElementsRuntimeUtility"), "RepaintPanels");
        if (repaint == null) { L.LogError("UIElementsRuntimeUtility.RepaintPanels not found; plugin disabled"); return; }
        h.Patch(repaint, prefix: new HarmonyMethod(typeof(Plugin), nameof(Tick)));
        h.Patch(AccessTools.Method(typeof(BindingSubsystem), "Initialise"),
            postfix: new HarmonyMethod(typeof(Plugin), nameof(BindingsInitialised)));

        _server = new WsServer(Port);
        _server.Start();
        Session.Publish(Port, GameBuild);
        L.LogInfo($"{Version} loaded, ws://127.0.0.1:{Port}/, game {GameBuild}");
    }

    // Harmony prefix: nothing may escape into the game's frame.
    private static void Tick()
    {
        if (Interlocked.Increment(ref Ticks) == 1) L.LogInfo("first main-thread tick");
        LastTickMs = Environment.TickCount64;
        if (_ticking) return;
        _ticking = true;
        try { Queue.Drain(); }
        catch (Exception e) { L.LogError($"tick: {e}"); }
        finally { _ticking = false; }
    }

    private static void BindingsInitialised(BindingSubsystem __instance)
    {
        try
        {
            if (Bindings != null) return;
            Reader.Owner = new Il2CppSystem.Object();   // bind owner made on the main thread
            Bindings = __instance;
            L.LogInfo("BindingSubsystem captured");
        }
        catch (Exception e) { L.LogError($"bindings capture: {e}"); }
    }
}
