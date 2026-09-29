using System.Diagnostics;
using System.Text.Json;
using System.Text.Json.Nodes;
using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Media;
using Avalonia.Platform.Storage;
using XAUPY.Ipc;

namespace XAUPY.Desktop;

public partial class SettingsDashboard : UserControl
{
    private EngineProcessSupervisor? _supervisor;
    private JsonObject? _settings;
    private bool _busy;
    private bool _loaded;
    public SettingsDashboard() => InitializeComponent();
    public void AttachSupervisor(EngineProcessSupervisor supervisor) => _supervisor = supervisor;
    public void ApplyExecutionStatus(ExecutionSnapshot status)
    {
        string saved = ExecutionPresentation.Permission(status);
        bool dirtyPermission = status.PermissionsKnown && (AllowRealAccount.IsChecked == true) != status.LocalAllowReal;
        ExecutionModeSummary.Text = (dirtyPermission ? "Quyền REAL: bản nháp chưa lưu" : saved) + "\nGiao dịch: " + ExecutionPresentation.Mode(status);
        ToolTip.SetTip(ExecutionModeSummary, ExecutionPresentation.Summary(status));
    }
    public async Task EnsureLoadedAsync(bool force = false)
    {
        if (_busy || (_loaded && !force) || _supervisor?.State != EngineConnectionState.Ready) return;
        await RunAsync(async () =>
        {
            var result = await _supervisor.GetSettingsAsync(); EnsureOk(result); Apply(result);
            await ProbeAsync();
            _loaded = true;
            Status("Đã tải cài đặt. Điều khiển lần chờ lệnh tại tab Lệnh & Vị thế.", true);
        });
    }
    private void Apply(JsonElement payload)
    {
        _settings = JsonNode.Parse(payload.GetProperty("settings").GetRawText())!.AsObject();
        AutoEngine.IsChecked = Bool("startup", "auto_start_engine");
        AutoRestart.IsChecked = Bool("startup", "auto_restart_engine");
        WindowsStartup.IsChecked = Bool("startup", "start_with_windows");
        AutoTrading.IsChecked = Bool("safety", "auto_start_trading");
        RequireStartupSync.IsChecked = Bool("safety", "require_reconciliation");
        AllowRealAccount.IsChecked = Bool("safety", "allow_real_account");
        WindowsStartup.IsEnabled = OperatingSystem.IsWindows();
        ErrorNotifications.IsChecked = Bool("notifications", "system_errors");
        ConnectionNotifications.IsChecked = Bool("notifications", "connection_changes");
        AutoBackup.IsChecked = Bool("backup", "auto_backup");
        BackupCount.Value = _settings["backup"]!["keep_count"]!.GetValue<int>();
        Mt5Path.Text = _settings["connection"]!["mt5_path"]!.GetValue<string>();
        BridgePort.Value = _settings["connection"]!["port"]!.GetValue<int>();
        ThemeChoice.SelectedIndex=_settings["appearance"]!["theme"]!.GetValue<string>()=="N30 Contrast"?1:0;
        FontScaleChoice.Value=_settings["appearance"]!["font_scale"]!.GetValue<int>();
        LanguageChoice.SelectedIndex=_settings["appearance"]!["language"]!.GetValue<string>()=="English"?1:0;
        if (payload.TryGetProperty("backup_path", out var path)) BackupPath.Text = path.GetString();
        if (payload.TryGetProperty("state_path", out path)) StatePath.Text = Path.GetDirectoryName(path.GetString());
        if (payload.TryGetProperty("recovery_message", out var recovery)) RecoveryInfo.Text = recovery.GetString();
        if (payload.TryGetProperty("retention_warning", out var warning) && !string.IsNullOrWhiteSpace(warning.GetString())) RecoveryInfo.Text += "\n" + warning.GetString();
        if (payload.TryGetProperty("backups", out var backups))
        {
            var ids = backups.EnumerateArray().Select(item => item.GetProperty("id").GetString()!).ToArray();
            BackupList.ItemsSource = ids;
            if (ids.Length > 0) BackupList.SelectedIndex = 0;
            StorageInfo.Text = $"Số bản sao lưu: {ids.Length}\nLưu cấu hình: JSON schema v1\nSao lưu nguyên tử, kiểm tra khi khôi phục";
        }
        bool Bool(string group, string name) => _settings[group]![name]!.GetValue<bool>();
    }
    private async Task ProbeAsync()
    {
        if (_supervisor is null) return;
        var result = await _supervisor.QueryDiagnosticsAsync(); EnsureOk(result);
        var diag = result.GetProperty("diagnostics");
        var bridge = diag.GetProperty("bridge");
        bool connected = bridge.GetProperty("connected").GetBoolean() && bridge.GetProperty("terminal_connected").GetBoolean();
        Mt5Status.Text = connected ? "●  Kết nối thành công" : "●  Đang chờ EA Bridge / MT5";
        Mt5Status.Foreground = connected ? Brushes.SpringGreen : Brushes.Gold;
        AccountMode.Text = bridge.TryGetProperty("account_trade_mode", out var mode) ? mode.GetString() ?? "—" : "—";
        AccountLogin.Text = connected && _supervisor.OrdersPositions.Available
            ? _supervisor.OrdersPositions.AccountLogin?.ToString() ?? "—" : "—";
        var paths = diag.GetProperty("paths");
        StatePath.Text = paths.GetProperty("state").GetString();
        LogPath.Text = paths.GetProperty("logs").GetString();
        BacktestPath.Text = paths.GetProperty("backtests").GetString();
        HistoryPath.Text = Path.Combine(StatePath.Text ?? "", "market-history");
        SystemInfo.Text = $"Phiên bản: {diag.GetProperty("engine_version").GetString()}\nPython: {diag.GetProperty("python_version").GetString()}\nUptime: {diag.GetProperty("uptime_seconds")} giây\nEA Bridge: {(connected ? "Đã kết nối" : "Đang chờ")}\nExecution: {_supervisor.Execution.Label}";
        var profile = await _supervisor.GetActiveConfigAsync();
        var risk = profile.GetProperty("risk");
        RiskMaxLot.Text = Risk("max_lot");
        RiskDailyTrades.Text = Risk("max_trades_per_day");
        RiskDailyLoss.Text = Risk("max_daily_loss_pct");
        RiskPositions.Text = Risk("max_open_positions");
        string Risk(string field) => risk.TryGetProperty(field, out var value) ? value.ToString() : "—";
    }
    private async void Probe_OnClick(object? sender, RoutedEventArgs e) => await RunAsync(async () => { await ProbeAsync(); Status("Đã kiểm tra kết nối thực.", true); });
    private async void Cancel_OnClick(object? sender, RoutedEventArgs e) => await EnsureLoadedAsync(true);
    private async void Defaults_OnClick(object? sender, RoutedEventArgs e) => await RunAsync(async () =>
    {
        if (_supervisor is null) return;
        var result = await _supervisor.GetDefaultSettingsAsync(); EnsureOk(result); Apply(result);
        Status("Đã nạp mặc định vào biểu mẫu. Nhấn Lưu cài đặt để áp dụng.", true);
    });
    private async void Save_OnClick(object? sender, RoutedEventArgs e) => await RunAsync(async () =>
    {
        if (_settings is null || _supervisor is null) return;
        var next = ReadDraft();
        if (next["safety"]!["allow_real_account"]!.GetValue<bool>() != _settings["safety"]!["allow_real_account"]!.GetValue<bool>()
            && HasConflictingDraft?.Invoke() == true)
            throw new InvalidOperationException(LocalizationService.T("Lưu hoặc hủy bản nháp cấu hình trước khi đổi quyền REAL."));
        var wasStartup = _settings["startup"]!["start_with_windows"]!.GetValue<bool>();
        var newStartup = WindowsStartup.IsChecked == true;
        if (newStartup != wasStartup) ApplyWindowsStartup(newStartup);
        try
        {
            var result = await _supervisor.SaveSettingsAsync(JsonSerializer.SerializeToElement(next)); EnsureOk(result); Apply(result);
            AppearanceService.Apply(next["appearance"]!["theme"]!.GetValue<string>(),next["appearance"]!["font_scale"]!.GetValue<int>());
            LocalizationService.Apply(next["appearance"]!["language"]!.GetValue<string>());
            Status("Đã lưu cài đặt. Cổng và tùy chọn khởi động áp dụng từ lần mở app tiếp theo; đặt InpPort của EA cùng cổng đã chọn.", true);
        }
        catch { if (newStartup != wasStartup) ApplyWindowsStartup(wasStartup); throw; }
    });
    private async void Backup_OnClick(object? sender, RoutedEventArgs e) => await RunAsync(async () =>
    {
        if (_supervisor is null) return;
        if (HasUnsavedChanges) throw new InvalidOperationException(LocalizationService.T("Lưu hoặc Hủy cài đặt đang sửa trước khi tạo bản sao lưu."));
        var result = await _supervisor.CreateBackupAsync(); EnsureOk(result); Apply(result);
        Status($"Đã sao lưu: {result.GetProperty("backup").GetProperty("id").GetString()}", true);
    });
    private async void Restore_OnClick(object? sender, RoutedEventArgs e) => await RunAsync(RestoreReviewedAsync);
    private async void BrowseMt5_OnClick(object? sender, RoutedEventArgs e) => await RunAsync(async () =>
    {
        var top = TopLevel.GetTopLevel(this); if (top is null) return;
        var chosen = await top.StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions { Title = LocalizationService.T("Chọn terminal64.exe"), AllowMultiple = false, FileTypeFilter = new[] { new FilePickerFileType("MT5 Terminal") { Patterns = new[] { "terminal64.exe" } } } });
        if (chosen.Count > 0) Mt5Path.Text = chosen[0].TryGetLocalPath();
    });
    private void LaunchMt5_OnClick(object? sender,RoutedEventArgs e)
    {
        try
        {
            string path=Mt5Path.Text ?? "";
            if(!Path.IsPathFullyQualified(path) || !File.Exists(path) || !Path.GetFileName(path).Equals("terminal64.exe",StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("Chọn đường dẫn terminal64.exe hợp lệ.");
            Process.Start(new ProcessStartInfo {FileName=path,UseShellExecute=true});
            Status("Đã mở MT5 theo đường dẫn đã chọn.",true);
        }
        catch(Exception ex){Status(ex.Message,false);}
    }
    private void OpenFolder_OnClick(object? sender, RoutedEventArgs e)
    {
        var path = (sender as Button)?.Tag?.ToString() switch
        {
            "logs" => LogPath.Text, "backtests" => BacktestPath.Text,
            "backups" => BackupPath.Text, "history" => HistoryPath.Text, _ => StatePath.Text
        };
        try
        {
            if (Directory.Exists(path)) Process.Start(new ProcessStartInfo { FileName = path, UseShellExecute = true });
            else Status("Thư mục chưa tồn tại. Dữ liệu sẽ tạo khi tác vụ tương ứng chạy.", false);
        }
        catch (Exception ex) { Status(ex.Message, false); }
    }
    private static void ApplyWindowsStartup(bool enabled)
    {
        WindowsStartupRegistration.Update(enabled, Environment.ProcessPath);
    }
    private async Task RunAsync(Func<Task> action)
    {
        if (_busy) return; _busy = true;
        try { await action(); } catch (Exception ex) { Status(ex.Message, false); } finally { _busy = false; }
    }
    private void Status(string message, bool ok) { SettingsStatus.Text = message; SettingsStatus.Foreground = ok ? Brushes.SpringGreen : Brushes.OrangeRed; }
    private static void EnsureOk(JsonElement payload) { if (!payload.GetProperty("ok").GetBoolean()) throw new InvalidDataException(payload.GetProperty("errors").ToString()); }
}
