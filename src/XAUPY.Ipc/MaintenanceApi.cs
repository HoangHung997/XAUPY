using System.Text.Json;

namespace XAUPY.Ipc;

public sealed partial class EngineProcessSupervisor
{
    public bool AutoRestartEngine { get; private set; } = ReadStartupPreference("auto_restart_engine", true);
    public static bool ShouldAutoStartEngine => ReadStartupPreference("auto_start_engine", true);
    public bool ShowSystemErrors { get; private set; } = ReadPreference("notifications", "system_errors", true);
    public bool ShowConnectionChanges { get; private set; } = ReadPreference("notifications", "connection_changes", true);

    private static bool ReadStartupPreference(string key, bool fallback)
        => ReadPreference("startup", key, fallback);

    private static bool ReadPreference(string group, string key, bool fallback)
    {
        try
        {
            var root = Environment.GetEnvironmentVariable("XAUPY_STATE_DIR") ??
                (OperatingSystem.IsWindows()
                    ? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "XAUPY", "state")
                    : Path.Combine(Environment.GetEnvironmentVariable("XDG_STATE_HOME") ??
                                   Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".local", "state"), "xaupy", "state"));
            using var document = JsonDocument.Parse(File.ReadAllText(Path.Combine(root, "runtime-v1.json")));
            return document.RootElement.GetProperty("settings").GetProperty(group).GetProperty(key).GetBoolean();
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or JsonException or KeyNotFoundException or InvalidOperationException)
        {
            return fallback;
        }
    }

    public Task<JsonElement> QueryDiagnosticsAsync(CancellationToken cancellationToken = default) =>
        MaintenanceRequestAsync("diagnostics_get", new { }, cancellationToken);

    public Task<JsonElement> StartHistoryDownloadAsync(string terminal, string symbol, CancellationToken cancellationToken = default) =>
        MaintenanceRequestAsync("history_download_start", new { terminal, symbol }, cancellationToken);

    public Task<JsonElement> GetHistoryDownloadAsync(CancellationToken cancellationToken = default) =>
        MaintenanceRequestAsync("history_download_status", new { }, cancellationToken);

    public Task<JsonElement> GetSettingsAsync(CancellationToken cancellationToken = default) =>
        MaintenanceRequestAsync("settings_get", new { }, cancellationToken);

    public Task<JsonElement> GetDefaultSettingsAsync(CancellationToken cancellationToken = default) =>
        MaintenanceRequestAsync("settings_defaults_get", new { }, cancellationToken);

    public async Task<JsonElement> SaveSettingsAsync(JsonElement settings, CancellationToken cancellationToken = default)
    {
        var result = await MaintenanceRequestAsync("settings_set", new { settings }, cancellationToken);
        if (result.GetProperty("ok").GetBoolean())
        {
            AutoRestartEngine = result.GetProperty("settings").GetProperty("startup").GetProperty("auto_restart_engine").GetBoolean();
            ShowSystemErrors = result.GetProperty("settings").GetProperty("notifications").GetProperty("system_errors").GetBoolean();
            ShowConnectionChanges = result.GetProperty("settings").GetProperty("notifications").GetProperty("connection_changes").GetBoolean();
        }
        return result;
    }

    public Task<JsonElement> CreateBackupAsync(CancellationToken cancellationToken = default) =>
        MaintenanceRequestAsync("backup_create", new { }, cancellationToken);

    public async Task<JsonElement> RestoreBackupAsync(string backupId, CancellationToken cancellationToken = default)
    {
        var result = await MaintenanceRequestAsync("backup_restore", new { backup_id = backupId }, cancellationToken);
        if (result.GetProperty("ok").GetBoolean())
        {
            AutoRestartEngine = result.GetProperty("settings").GetProperty("startup").GetProperty("auto_restart_engine").GetBoolean();
            ShowSystemErrors = result.GetProperty("settings").GetProperty("notifications").GetProperty("system_errors").GetBoolean();
            ShowConnectionChanges = result.GetProperty("settings").GetProperty("notifications").GetProperty("connection_changes").GetBoolean();
            await GetActiveConfigAsync(cancellationToken);
        }
        return result;
    }

    private async Task<JsonElement> MaintenanceRequestAsync(string type, object payload, CancellationToken cancellationToken)
    {
        var response = await SendReceiveAsync(ProtocolEnvelope.Create(type, payload), TimeSpan.FromSeconds(10), cancellationToken);
        if (response.Type != type + "_ack")
            throw new InvalidDataException($"Unexpected maintenance response: {response.Type}");
        RejectUnexpectedExecutionEnable(response);
        return response.Payload.Clone();
    }
}
