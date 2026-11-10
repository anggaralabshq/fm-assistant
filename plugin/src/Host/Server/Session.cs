// Per-start session token, published to ~/.fm-assistant/session.json (0600) for local clients.
using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Nodes;

namespace FmAssistant;

internal static class Session
{
    public static string Token { get; private set; }
    private static byte[] _tokenBytes;

    [DllImport("libc", SetLastError = true)]
    private static extern int chmod(string path, uint mode);

    public static string Dir => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".fm-assistant");
    public static string FilePath => Path.Combine(Dir, "session.json");

    public static void Publish(int port, string gameBuild)
    {
        Token = Convert.ToHexString(RandomNumberGenerator.GetBytes(32)).ToLowerInvariant();
        _tokenBytes = Encoding.UTF8.GetBytes(Token);
        Directory.CreateDirectory(Dir);
        chmod(Dir, Convert.ToUInt32("700", 8));
        var json = new JsonObject
        {
            ["port"] = port, ["token"] = Token, ["pid"] = Environment.ProcessId,
            ["plugin_version"] = Plugin.Version, ["game_build"] = gameBuild,
        }.ToJsonString();
        var tmp = FilePath + ".tmp";
        File.WriteAllText(tmp, json);
        if (chmod(tmp, Convert.ToUInt32("600", 8)) != 0) throw new IOException($"chmod {tmp}: errno {Marshal.GetLastWin32Error()}");
        File.Move(tmp, FilePath, true);
    }

    public static bool Check(string given) =>
        given != null && _tokenBytes != null && CryptographicOperations.FixedTimeEquals(Encoding.UTF8.GetBytes(given), _tokenBytes);
}
