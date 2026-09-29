using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Layout;
using Avalonia.Media;

namespace XAUPY.Desktop;

public partial class SettingsDashboard
{
    public Func<bool>? HasConflictingDraft { get; set; }
    public bool HasUnsavedChanges => _settings is not null && !JsonNode.DeepEquals(_settings, ReadDraft());

    private JsonObject ReadDraft()
    {
        var next = (_settings ?? throw new InvalidOperationException("Settings are not loaded.")).DeepClone().AsObject();
        next["startup"]!["auto_start_engine"] = AutoEngine.IsChecked == true;
        next["startup"]!["auto_restart_engine"] = AutoRestart.IsChecked == true;
        next["startup"]!["start_with_windows"] = WindowsStartup.IsChecked == true;
        next["notifications"]!["system_errors"] = ErrorNotifications.IsChecked == true;
        next["notifications"]!["connection_changes"] = ConnectionNotifications.IsChecked == true;
        next["backup"]!["auto_backup"] = AutoBackup.IsChecked == true;
        next["backup"]!["keep_count"] = (int)(BackupCount.Value ?? 30);
        next["connection"]!["mt5_path"] = Mt5Path.Text ?? "";
        next["connection"]!["port"] = (int)(BridgePort.Value ?? 39421);
        next["appearance"]!["theme"] = ThemeChoice.SelectedIndex == 1 ? "N30 Contrast" : "N30 Dark";
        next["appearance"]!["font_scale"] = (int)(FontScaleChoice.Value ?? 100);
        next["appearance"]!["language"] = LanguageChoice.SelectedIndex == 1 ? "English" : "Tiếng Việt";
        next["safety"]!["auto_start_trading"] = AutoTrading.IsChecked == true;
        next["safety"]!["require_reconciliation"] = RequireStartupSync.IsChecked == true;
        next["safety"]!["allow_real_account"] = AllowRealAccount.IsChecked == true;
        return next;
    }

    private void RequireCleanRestoreDrafts()
    {
        if (HasUnsavedChanges)
            throw new InvalidOperationException(LocalizationService.T("Cài đặt có bản nháp chưa lưu. Lưu hoặc Hủy thay đổi trước khi khôi phục."));
        if (HasConflictingDraft?.Invoke() == true)
            throw new InvalidOperationException(LocalizationService.T("Có bản nháp chưa lưu ở Cấu hình, Chiến lược, Công cụ hoặc Tổng quan. Giữ/lưu bản nháp trước khi khôi phục."));
    }

    private async Task RestoreReviewedAsync()
    {
        RequireCleanRestoreDrafts();
        if (_supervisor is null || BackupList.SelectedItem is not string id)
            throw new InvalidOperationException(LocalizationService.T("Chọn một bản sao lưu để khôi phục."));
        if (TopLevel.GetTopLevel(this) is not Window owner)
            throw new InvalidOperationException(LocalizationService.T("Không mở được cửa sổ xác nhận khôi phục."));
        var response = await _supervisor.PreviewBackupRestoreAsync(id);
        EnsureOk(response);
        var preview = response.GetProperty("preview").Clone();
        bool confirmed = false;
        var dialog = BuildRestoreReview(preview, value => confirmed = value);
        await dialog.ShowDialog(owner);
        if (!confirmed)
        {
            Status(LocalizationService.T("Đã hủy khôi phục. Không thay đổi cấu hình hoặc quyền giao dịch."), true);
            return;
        }
        RequireCleanRestoreDrafts();
        if (BackupList.SelectedItem is not string current || current != id)
            throw new InvalidOperationException(LocalizationService.T("Bản sao lưu đã đổi. Xem trước và xác nhận lại."));
        var result = await _supervisor.RestoreBackupAsync(id, preview.GetProperty("preview_hash").GetString()!, confirmed: true);
        EnsureOk(result);
        Apply(result);
        AppearanceService.Apply(_settings!["appearance"]!["theme"]!.GetValue<string>(), _settings["appearance"]!["font_scale"]!.GetValue<int>());
        LocalizationService.Apply(_settings["appearance"]!["language"]!.GetValue<string>());
        string? startupError = null;
        try { ApplyWindowsStartup(WindowsStartup.IsChecked == true); }
        catch (Exception error) { startupError = error.Message; }
        await ProbeAsync();
        ApplyExecutionStatus(_supervisor.Execution);
        Status(LocalizationService.T("Đã khôi phục. Giao dịch đã DỪNG; quyền REAL không tăng. Kiểm tra cấu hình rồi xác nhận lại chế độ.")
            + (startupError is null ? "" : "\n" + LocalizationService.T("Không cập nhật được khởi động Windows: ") + startupError), startupError is null);
    }

    internal static Window BuildRestoreReview(JsonElement preview, Action<bool> complete)
    {
        string T(string text) => LocalizationService.T(text);
        var text = new StringBuilder();
        text.AppendLine(T("Bản sao lưu: ") + preview.GetProperty("backup_id").GetString());
        text.AppendLine(T("Chế độ hiện tại: ") + preview.GetProperty("execution_before").GetString());
        text.AppendLine(T("Sau khôi phục: DỪNG. Hủy yêu cầu chưa gửi; giữ nguyên bằng chứng lệnh đã gửi/chưa rõ kết quả."));
        text.AppendLine(T("Quyền REAL không được tăng từ backup; không tự chạy giao dịch khi mở lại."));
        var before = preview.GetProperty("before");
        var after = preview.GetProperty("after");
        text.AppendLine();
        text.AppendLine(T("Rủi ro: trước → sau"));
        foreach (string name in new[] { "sizing_mode", "fixed_lot", "risk_percent", "max_lot", "max_open_positions", "max_daily_loss_pct" })
            text.AppendLine($"{name}: {before.GetProperty("profile").GetProperty("risk").GetProperty(name)} → {after.GetProperty("profile").GetProperty("risk").GetProperty(name)}");
        text.AppendLine();
        text.AppendLine(T("Các giá trị thay đổi:"));
        foreach (var change in preview.GetProperty("changes").EnumerateArray())
            text.AppendLine($"{change.GetProperty("path")}: {change.GetProperty("before")} → {change.GetProperty("after")}");
        var details = new TextBox { Name="RestorePreviewText", Text=text.ToString(), IsReadOnly=true,
            AcceptsReturn=true, TextWrapping=TextWrapping.Wrap, HorizontalAlignment=HorizontalAlignment.Stretch };
        var consent = new CheckBox { Name="RestoreReviewConfirm",
            [LocalizationService.TextProperty]="Tôi đã xem thay đổi và xác nhận khôi phục, dừng giao dịch." };
        var apply = new Button { Name="RestoreReviewApply", [LocalizationService.TextProperty]="Khôi phục đã xem", IsEnabled=false, Classes={"primary"} };
        var cancel = new Button { Name="RestoreReviewCancel", [LocalizationService.TextProperty]="Hủy", Classes={"secondary"} };
        var dialog = new Window { Name="RestoreReviewDialog", [LocalizationService.TitleProperty]="Xác nhận khôi phục an toàn", Width=790, Height=600,
            MinWidth=560, MinHeight=360, WindowStartupLocation=WindowStartupLocation.CenterOwner };
        consent.IsCheckedChanged += (_, _) => apply.IsEnabled = consent.IsChecked == true;
        apply.Click += (_, _) => { if (consent.IsChecked != true) return; complete(true); dialog.Close(); };
        cancel.Click += (_, _) => { complete(false); dialog.Close(); };
        var grid = new Grid { Margin=new Thickness(18), RowDefinitions=new RowDefinitions("*,Auto,Auto"), RowSpacing=12 };
        grid.Children.Add(details); Grid.SetRow(consent,1); grid.Children.Add(consent);
        var buttons = new StackPanel { Orientation=Orientation.Horizontal, Spacing=10, HorizontalAlignment=HorizontalAlignment.Right, Children={cancel,apply} };
        Grid.SetRow(buttons,2); grid.Children.Add(buttons); dialog.Content=grid;
        return dialog;
    }
}
