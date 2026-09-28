using System.Text.Json;

namespace XAUPY.Ipc;

public sealed record DemoOnceContext(long? AccountLogin, string? AccountServer, string? AccountMode,
    string? Symbol, long? Magic, string? ProfileHash, bool Capable)
{
    public bool CanArm => AccountMode == "DEMO" && Capable && AccountLogin > 0 && Magic > 0 &&
        !string.IsNullOrWhiteSpace(AccountServer) && !string.IsNullOrWhiteSpace(Symbol) &&
        ProfileHash is { Length: 64 } && ProfileHash.All(Uri.IsHexDigit);
    public static DemoOnceContext Empty { get; } = new(null, null, null, null, null, null, false);
}

public sealed record DemoOnceResponse(bool Accepted, DemoOnceSnapshot Status, DemoOnceContext Context)
{
    public static DemoOnceResponse Parse(JsonElement payload)
    {
        var status = DemoOnceSnapshot.FromHeartbeatPayload(payload);
        var context = DemoOnceContext.Empty;
        if (payload.TryGetProperty("demo_once_context", out var source) && source.ValueKind == JsonValueKind.Object)
        {
            string? Text(string key) => source.TryGetProperty(key, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() : null;
            long? Number(string key) => source.TryGetProperty(key, out var value) && value.ValueKind == JsonValueKind.Number && value.TryGetInt64(out var number) && number > 0 ? number : null;
            context = new(Number("account_login"), Text("account_server"), Text("account_trade_mode"), Text("symbol"), Number("magic"), Text("profile_hash"),
                source.TryGetProperty("demo_once_capable", out var capable) && capable.ValueKind == JsonValueKind.True);
        }
        return new(payload.TryGetProperty("accepted", out var accepted) && accepted.ValueKind == JsonValueKind.True, status, context);
    }
}
