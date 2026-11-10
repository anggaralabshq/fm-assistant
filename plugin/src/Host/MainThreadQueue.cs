using System;
using System.Collections.Concurrent;
using System.Threading.Tasks;

namespace FmAssistant;

/// Jobs from the WebSocket thread, run on Unity's main thread by Plugin.Tick. Each job has a deadline; Drain
/// answers expired jobs with main-thread-timeout instead of running them late.
internal sealed class MainThreadQueue
{
    private sealed class Job
    {
        public long Deadline;
        public Action Run, Expire;
    }

    private readonly ConcurrentQueue<Job> _q = new ConcurrentQueue<Job>();

    public Task<R<T>> Run<T>(Func<R<T>> job, int timeoutMs)
    {
        var tcs = new TaskCompletionSource<R<T>>(TaskCreationOptions.RunContinuationsAsynchronously);
        _q.Enqueue(new Job
        {
            Deadline = Environment.TickCount64 + timeoutMs,
            Run = () =>
            {
                R<T> r;
                try { r = job(); }
                catch (Exception e)
                {
                    Plugin.L.LogError($"main-thread job: {e.GetType().Name}: {e.Message}");  // never e.ToString() here: capturing a stack trace through IL2CPP frames crashes CoreCLR (libunwind)
                    r = R<T>.Err("internal", $"{e.GetType().Name}: {e.Message}");
                }
                tcs.TrySetResult(r);
            },
            Expire = () => tcs.TrySetResult(R<T>.Err("main-thread-timeout", "job expired before the main thread ran it")),
        });
        return tcs.Task;
    }

    public int Count => _q.Count;

    public void Drain()
    {
        var now = Environment.TickCount64;
        while (_q.TryDequeue(out var j))
        {
            if (now > j.Deadline) j.Expire();
            else j.Run();
        }
    }
}
