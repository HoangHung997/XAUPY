using System.Text.Json;

namespace XAUPY.Ipc;

/// <summary>Correlates an IPC peer with the launched process, including a PyInstaller child.</summary>
public static class EngineInstanceGuard
{
    public static void Validate(JsonElement payload, string expectedInstanceId)
    {
        if (string.IsNullOrWhiteSpace(expectedInstanceId) ||
            payload.ValueKind != JsonValueKind.Object ||
            !payload.TryGetProperty("engine_instance_id", out var instance) ||
            instance.ValueKind != JsonValueKind.String ||
            !string.Equals(instance.GetString(), expectedInstanceId, StringComparison.Ordinal))
        {
            throw new InvalidDataException("Cổng IPC đang được một Engine khác sử dụng. Đóng bản XAUPY cũ hoặc giải phóng cổng; ứng dụng không nhận kết nối nhầm tiến trình.");
        }
    }
}
