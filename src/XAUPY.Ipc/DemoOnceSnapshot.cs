using System.Text.Json;

namespace XAUPY.Ipc;

/// <summary>A reported single-demo-order attempt; it never enables general execution.</summary>
public sealed record DemoOnceSnapshot(
    bool HasReport,
    bool IsFresh,
    string State,
    string? Reason,
    string? Code,
    string? AttemptId,
    double? Volume,
    string? Side,
    long? OrderTicket,
    long? DealTicket)
{
    public bool? BudgetConsumed { get; init; }
    public DateTimeOffset? ArmedUntilUtc { get; init; }
    public double? AuthorizedVolume { get; init; }
    public string? LastBlocker { get; init; }
    public static DemoOnceSnapshot Disabled { get; } = new(
        false, false, "DISABLED", null, null, null, null, null, null, null);

    public DemoOnceSnapshot AsStale() => this with { IsFresh = false };

    public static DemoOnceSnapshot FromHeartbeatPayload(JsonElement payload)
    {
        if (payload.ValueKind != JsonValueKind.Object ||
            !payload.TryGetProperty("demo_once", out var report) ||
            report.ValueKind == JsonValueKind.Null)
            return Disabled;

        // Malformed/unsupported reports remain visible as uncertain, never as filled or disabled.
        if (report.ValueKind != JsonValueKind.Object)
            return Disabled with { HasReport = true, IsFresh = true, State = "UNKNOWN", Code = "INVALID_DEMO_ONCE_REPORT" };

        var state = ReadString(report, "state");
        bool knownState = state is "DISABLED" or "ARMED" or "DISPATCHED" or "FILLED" or
            "REJECTED" or "UNKNOWN" or "CANCELLED" or "SUSPENDED" or "EXPIRED";
        var result = new DemoOnceSnapshot(
            true, true, knownState ? state! : "UNKNOWN",
            ReadString(report, "reason"),
            knownState ? ReadString(report, "code") : "INVALID_DEMO_ONCE_STATE",
            ReadString(report, "attempt_id"),
            ReadPositiveDouble(report, "volume"),
            ReadString(report, "side"),
            ReadTicket(report, "order_ticket"),
            ReadTicket(report, "deal_ticket"))
        {
            BudgetConsumed = report.TryGetProperty("budget_consumed", out var consumed) &&
                consumed.ValueKind is JsonValueKind.True or JsonValueKind.False ? consumed.GetBoolean() : null,
            ArmedUntilUtc = DateTimeOffset.TryParse(ReadString(report, "armed_until_utc"), out var until) ? until : null,
            AuthorizedVolume = report.TryGetProperty("authorization", out var authorization) && authorization.ValueKind == JsonValueKind.Object
                ? ReadPositiveDouble(authorization, "max_volume") : ReadPositiveDouble(report, "authorized_volume"),
            LastBlocker = ReadString(report, "last_blocker")
        };
        if (result.State == "FILLED" &&
            (!Guid.TryParse(result.AttemptId, out _) || result.Side is not ("BUY" or "SELL") ||
             result.Volume is null || result.DealTicket is null))
            return result with { State = "UNKNOWN", Code = "INCOMPLETE_FILL_EVIDENCE" };
        return result;
    }

    private static string? ReadString(JsonElement source, string name) =>
        source.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String
            ? value.GetString() : null;

    private static double? ReadPositiveDouble(JsonElement source, string name) =>
        source.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.Number &&
        value.TryGetDouble(out var number) && double.IsFinite(number) && number > 0 ? number : null;

    private static long? ReadTicket(JsonElement source, string name) =>
        source.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.Number &&
        value.TryGetInt64(out var ticket) && ticket > 0 ? ticket : null;
}
