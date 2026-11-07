using System;
using System.Collections.Concurrent;
using System.Threading.Tasks;

namespace FmSpike;

/// Jobs from the WebSocket thread, run on Unity's main thread by Plugin.Tick.
internal sealed class MainThreadQueue
{
    private readonly ConcurrentQueue<Action> _q = new ConcurrentQueue<Action>();

    public Task<T> Run<T>(Func<T> job)
    {
        var tcs = new TaskCompletionSource<T>(TaskCreationOptions.RunContinuationsAsynchronously);
        _q.Enqueue(() =>
        {
            try { tcs.SetResult(job()); }
            catch (Exception e) { tcs.SetException(e); }
        });
        return tcs.Task;
    }

    public void Drain()
    {
        while (_q.TryDequeue(out var a)) a();
    }
}
