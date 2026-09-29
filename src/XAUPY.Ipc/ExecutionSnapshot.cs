using System.Text.Json;

namespace XAUPY.Ipc;

/// <summary>A current gate is distinct from the outcome of a previous intent.</summary>
public sealed record ExecutionSnapshot(string Mode, string Reason, bool Enabled, bool Fresh, JsonElement? Recent)
{
    public bool EntryEnabled { get; init; } = Enabled;
    public bool ManagementEnabled { get; init; } = Enabled;
    public string EntryReason { get; init; } = Reason;
    public string ManagementReason { get; init; } = Reason;
    public bool BuyAllowed { get; init; } = true;
    public bool SellAllowed { get; init; } = true;
    public string? ProfileHash { get; init; }
    public string LastAttemptReason { get; init; } = "";
    public double? QuoteAgeMs { get; init; }
    public double? SnapshotAgeMs { get; init; }
    public string QuoteSource { get; init; } = "";
    public bool PermissionsKnown { get; init; }
    public bool LocalAllowReal { get; init; }
    public bool EffectiveAllowReal { get; init; }
    public bool ProfileAllowReal { get; init; }
    public bool ProfileDemoOnly { get; init; } = true;
    public bool BrokerCapabilitiesKnown { get; init; }
    public bool MarketOrdersAllowed { get; init; } = true;
    public bool StopOrdersAllowed { get; init; }
    public bool LimitOrdersAllowed { get; init; }
    public bool SpecifiedExpirationAllowed { get; init; }
    public string MarginMode { get; init; } = "UNKNOWN";
    public IReadOnlyDictionary<string,string> ManagementWarnings { get; init; } = new Dictionary<string,string>();


    public static ExecutionSnapshot Offline { get; } = new("OFF", "ENGINE_OFFLINE", false, false, null);
    public static ExecutionSnapshot Parse(JsonElement payload)
    {
        if (payload.ValueKind != JsonValueKind.Object ||
            !payload.TryGetProperty("execution", out var value) || value.ValueKind != JsonValueKind.Object)
            return Offline;
        string mode = OverviewSnapshot.ReadString(value, "mode") ?? "OFF";
        bool validMode = mode is "OFF" or "MANUAL" or "AUTO";
        bool available = !value.TryGetProperty("available", out var present) || present.ValueKind == JsonValueKind.True;
        string reason = OverviewSnapshot.ReadString(value, "reason") ?? "";
        bool enabled = validMode && available && mode != "OFF" && OverviewSnapshot.ReadBool(value, "execution_enabled");
        var result = new ExecutionSnapshot(validMode ? mode : "OFF", validMode ? reason : "INVALID_EXECUTION_MODE", enabled, available,
            value.TryGetProperty("recent", out var recent) && recent.ValueKind == JsonValueKind.Array ? recent.Clone() : null)
        {
            EntryEnabled = enabled && Flag(value, "entry_enabled", enabled),
            ManagementEnabled = enabled && Flag(value, "management_enabled", enabled),
            EntryReason = OverviewSnapshot.ReadString(value, "entry_reason") ?? reason,
            ManagementReason = OverviewSnapshot.ReadString(value, "management_reason") ?? reason,
            BuyAllowed = Flag(value,"allow_buy",true),
            SellAllowed = Flag(value,"allow_sell",true),
            ProfileHash = OverviewSnapshot.ReadString(value,"profile_hash"),
            LastAttemptReason = OverviewSnapshot.ReadString(value, "last_attempt_reason") ?? "",
            QuoteAgeMs = Number(value, "quote_age_ms"),
            SnapshotAgeMs = Number(value, "snapshot_age_ms"),
            QuoteSource = OverviewSnapshot.ReadString(value, "quote_source") ?? ""
        };
        if (value.TryGetProperty("permissions", out var permission) && permission.ValueKind == JsonValueKind.Object)
            result = result with
            {
                PermissionsKnown = true,
                LocalAllowReal = OverviewSnapshot.ReadBool(permission, "local_allow_real"),
                EffectiveAllowReal = OverviewSnapshot.ReadBool(permission, "effective_allow_real"),
                ProfileAllowReal = OverviewSnapshot.ReadBool(permission, "profile_allow_real"),
                ProfileDemoOnly = Flag(permission, "profile_demo_only", true)
            };
        if (value.TryGetProperty("broker_capabilities", out var caps) && caps.ValueKind == JsonValueKind.Object)
            result = result with {
                BrokerCapabilitiesKnown = caps.TryGetProperty("schema_version", out var version) && version.ValueKind == JsonValueKind.Number && version.TryGetInt32(out int schema) && schema == 1,
                MarketOrdersAllowed = Flag(caps,"market_orders",false),
                StopOrdersAllowed = Flag(caps,"stop_orders",false),
                LimitOrdersAllowed = Flag(caps,"limit_orders",false),
                SpecifiedExpirationAllowed = Flag(caps,"specified_expiration",false),
                MarginMode = OverviewSnapshot.ReadString(caps,"margin_mode") ?? "UNKNOWN"
            };
        if (value.TryGetProperty("management_warnings", out var warnings) && warnings.ValueKind == JsonValueKind.Object)
            result = result with { ManagementWarnings = warnings.EnumerateObject()
                .Where(item => item.Value.ValueKind == JsonValueKind.String)
                .ToDictionary(item => item.Name, item => item.Value.GetString() ?? "") };
        return result;
    }
    private static bool Flag(JsonElement value, string key, bool fallback) =>
        value.TryGetProperty(key, out var item) ? item.ValueKind == JsonValueKind.True : fallback;
    private static double? Number(JsonElement value, string key) =>
        value.TryGetProperty(key, out var item) && item.ValueKind == JsonValueKind.Number &&
        item.TryGetDouble(out double number) && double.IsFinite(number) ? number : null;
    public string Label => !Fresh ? "Mất kết nối" : Mode switch { "AUTO" => "Tự động", "MANUAL" => "Thủ công", _ => "Đã dừng" };
}
