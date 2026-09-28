using System.Text.Json;

namespace XAUPY.Ipc;

public sealed partial class EngineProcessSupervisor
{
    public static (string Theme,int FontScale,string Language) ReadAppearancePreference()
    {
        try
        {
            using var doc=ReadLocalSettings();var value=doc.RootElement.GetProperty("settings").GetProperty("appearance");
            return (value.GetProperty("theme").GetString() ?? "N30 Dark",value.GetProperty("font_scale").GetInt32(),value.GetProperty("language").GetString() ?? "Tiếng Việt");
        }
        catch(Exception ex) when(ex is IOException or UnauthorizedAccessException or JsonException or KeyNotFoundException or InvalidOperationException)
        {return ("N30 Dark",100,"Tiếng Việt");}
    }
    public static int? ReadSavedPort()
    {
        try
        {
            using var settings=ReadLocalSettings();
            int port=settings.RootElement.GetProperty("settings").GetProperty("connection").GetProperty("port").GetInt32();
            return port is >=1024 and <=65535 ? port : null;
        }
        catch(Exception ex) when(ex is IOException or UnauthorizedAccessException or JsonException or KeyNotFoundException or InvalidOperationException) {return null;}
    }
    private static JsonDocument ReadLocalSettings()
    {
        var root=Environment.GetEnvironmentVariable("XAUPY_STATE_DIR") ??
            (OperatingSystem.IsWindows() ? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"XAUPY","state") :
             Path.Combine(Environment.GetEnvironmentVariable("XDG_STATE_HOME") ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),".local","state"),"xaupy","state"));
        return JsonDocument.Parse(File.ReadAllText(Path.Combine(root,"runtime-v1.json")));
    }
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

    public Task<JsonElement> StartTickDownloadAsync(string terminal,string symbol,string fromDate,string toDate,CancellationToken cancellationToken=default) =>
        MaintenanceRequestAsync("history_download_start", new { terminal,symbol,from_date=fromDate,to_date=toDate,model="REAL_TICKS" },cancellationToken);

    public Task<JsonElement> PrepareOptimizerCandidateAsync(string runId,int index,CancellationToken cancellationToken=default) =>
        MaintenanceRequestAsync("optimizer_candidate_prepare", new {run_id=runId,index},cancellationToken);

    public async Task<OptimizerStatusSnapshot> StartParameterResearchAsync(string path,string fromDate,string toDate,double balance,double spread,double commission,int minTrades,int maxWorkers,CancellationToken cancellationToken=default)
    {
        var result=await MaintenanceRequestAsync("research_start",new {path,from_date=fromDate,to_date=toDate,initial_balance=balance,spread_pips=spread,commission_per_lot=commission,min_trades=minTrades,max_workers=maxWorkers},cancellationToken);
        if(!result.GetProperty("ok").GetBoolean())throw new InvalidDataException(result.GetProperty("errors").ToString());
        return OptimizerStatusSnapshot.FromElement(result.GetProperty("status"));
    }

    public Task<JsonElement> GetOptimizerEvidenceAsync(string runId,CancellationToken cancellationToken=default) =>
        MaintenanceRequestAsync("optimizer_result_get",new {run_id=runId,candidate_offset=0,candidate_limit=10},cancellationToken);

    public Task<JsonElement> StartBrokerHistoryAsync(CancellationToken cancellationToken = default) =>
        MaintenanceRequestAsync("broker_history_start", new { }, cancellationToken);
    public Task<JsonElement> GetBrokerHistoryStatusAsync(CancellationToken cancellationToken = default) =>
        MaintenanceRequestAsync("broker_history_status", new { }, cancellationToken);
    public Task<JsonElement> QueryBrokerHistoryAsync(int page=0, int limit=100, string? symbol=null, string? reportId=null, CancellationToken cancellationToken=default) =>
        MaintenanceRequestAsync("broker_history_query", new { page, limit, symbol, report_id=reportId }, cancellationToken);

    public Task<JsonElement> GetSettingsAsync(CancellationToken cancellationToken = default) =>
        MaintenanceRequestAsync("settings_get", new { }, cancellationToken);

    public Task<JsonElement> QueryHistoryCatalogAsync(CancellationToken token=default) =>
        MaintenanceRequestAsync("history_catalog",new {},token);
    public Task<JsonElement> QueryProfileLibraryAsync(CancellationToken token=default) =>
        MaintenanceRequestAsync("library_profile_list",new {},token);
    public Task<JsonElement> SaveLibraryProfileAsync(string id,JsonElement profile,CancellationToken token=default) =>
        MaintenanceRequestAsync("library_profile_save",new {id,profile},token);
    public Task<JsonElement> SaveStartupProfileAsync(JsonElement profile,CancellationToken token=default) =>
        MaintenanceRequestAsync("startup_profile_set",new {profile},token);
    public Task<JsonElement> ClearStartupProfileAsync(CancellationToken token=default) =>
        MaintenanceRequestAsync("startup_profile_clear",new {},token);
    public Task<JsonElement> StartDataTransferAsync(string mode,string path,CancellationToken token=default) =>
        MaintenanceRequestAsync("data_transfer_start",new {mode,path},token);
    public Task<JsonElement> GetDataTransferAsync(CancellationToken token=default) =>
        MaintenanceRequestAsync("data_transfer_status",new {},token);
    public Task<JsonElement> CancelDataTransferAsync(CancellationToken token=default) =>
        MaintenanceRequestAsync("data_transfer_cancel",new {},token);
    public Task<JsonElement> GetLibraryProfileAsync(string id,string revision,CancellationToken token=default) =>
        MaintenanceRequestAsync("library_profile_get",new {id,revision},token);
    public Task<JsonElement> GetCalendarAsync(CancellationToken token=default) =>
        MaintenanceRequestAsync("calendar_get",new {},token);
    public Task<JsonElement> ValidateCalendarAsync(JsonElement calendar,CancellationToken token=default) =>
        MaintenanceRequestAsync("calendar_validate",new {calendar},token);
    public Task<JsonElement> ImportCalendarAsync(JsonElement calendar,CancellationToken token=default) =>
        MaintenanceRequestAsync("calendar_import",new {calendar},token);

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
