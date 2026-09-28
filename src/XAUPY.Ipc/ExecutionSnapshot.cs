using System.Text.Json;

namespace XAUPY.Ipc;

public sealed record ExecutionSnapshot(string Mode, string Reason, bool Enabled, bool Fresh, JsonElement? Recent)
{
    public static ExecutionSnapshot Offline { get; } = new("OFF", "ENGINE_OFFLINE", false, false, null);
    public static ExecutionSnapshot Parse(JsonElement payload)
    {
        if (!payload.TryGetProperty("execution", out var value)) return Offline;
        return new(OverviewSnapshot.ReadString(value, "mode") ?? "OFF", OverviewSnapshot.ReadString(value, "reason") ?? "",
            OverviewSnapshot.ReadBool(value, "execution_enabled"), true,
            value.TryGetProperty("recent", out var recent) && recent.ValueKind == JsonValueKind.Array ? recent.Clone() : null);
    }
    public string Label => !Fresh ? "Mất kết nối" : Mode switch { "AUTO" => "Tự động", "MANUAL" => "Thủ công", _ => "Đã dừng" };
}
