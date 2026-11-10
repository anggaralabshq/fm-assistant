// Throwaway Phase 0 spike plugin. Tick + bindings-capture pattern adapted from redznn/fm-dof-mcp (MIT).
using System;
using BepInEx;
using BepInEx.Logging;
using BepInEx.Unity.IL2CPP;
using HarmonyLib;
using SI.Bindable;

namespace FmSpike;

[BepInPlugin("dev.fmassistant.spike", "FM Assistant Spike", Version)]
public class Plugin : BasePlugin
{
    public const string Version = "0.0.1";
    internal static ManualLogSource L;
    internal static readonly MainThreadQueue Queue = new MainThreadQueue();
    internal static BindingSubsystem Bindings { get; private set; }

    private WsServer _server;
    private static bool _ticking;

    public override void Load()
    {
        L = Log;
        var h = new Harmony("dev.fmassistant.spike");
        // Main-thread tick: prefix on UIElements repaint (stable frame boundary; no MonoBehaviour injection on arm64).
        var repaint = AccessTools.Method(AccessTools.TypeByName("UnityEngine.UIElements.UIElementsRuntimeUtility"), "RepaintPanels");
        if (repaint == null) throw new MissingMethodException("UIElementsRuntimeUtility.RepaintPanels");
        h.Patch(repaint, prefix: new HarmonyMethod(typeof(Plugin), nameof(Tick)));
        // Capture the game's binding subsystem when it initialises.
        h.Patch(AccessTools.Method(typeof(BindingSubsystem), "Initialise"),
            postfix: new HarmonyMethod(typeof(Plugin), nameof(BindingsInitialised)));

        _server = new WsServer(7788);
        _server.Start();
        L.LogInfo($"[FmSpike] {Version} loaded, ws://127.0.0.1:7788/");
    }

    private static void Tick()
    {
        if (_ticking) return;
        _ticking = true;
        try { Queue.Drain(); }
        catch (Exception e) { L.LogError($"[FmSpike] tick: {e}"); }
        finally { _ticking = false; }
    }

    private static void BindingsInitialised(BindingSubsystem __instance)
    {
        if (Bindings == null)
        {
            Bindings = __instance;
            L.LogInfo("[FmSpike] BindingSubsystem captured");
        }
    }
}
