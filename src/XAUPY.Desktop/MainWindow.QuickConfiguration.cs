using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Media;
using System.Text.Json;
using System.Text.Json.Nodes;
using XAUPY.Ipc;

namespace XAUPY.Desktop;

public partial class MainWindow
{
    private bool _quickConfigurationSync;
    private bool _quickConfigurationDirty;
    private ConfigurationSummary? _quickConfigurationBaseline;
    private string? _quickLogicBaseline;
    private string? _quickDetailsHash;
    private bool _quickDetailsLoading;

    private void InitializeQuickConfiguration()
    {
        foreach (var name in new[] { "QuickDirection", "QuickPullback", "QuickTrigger" })
        {
            var combo = this.FindControl<ComboBox>(name)!;
            combo.ItemsSource = new[] { "M1", "M3", "M5", "M15", "M30", "H1", "H2", "H4" };
            combo.SelectionChanged += (_, _) => MarkQuickConfigurationChanged();
        }
        this.FindControl<CheckBox>("QuickAllowBuy")!.IsCheckedChanged += (_, _) => MarkQuickConfigurationChanged();
        this.FindControl<CheckBox>("QuickAllowSell")!.IsCheckedChanged += (_, _) => MarkQuickConfigurationChanged();
        this.FindControl<ComboBox>("QuickLogic")!.ItemsSource = new[] { "AND", "OR" };
        this.FindControl<ComboBox>("QuickLogic")!.SelectionChanged += (_, _) => MarkQuickConfigurationChanged();
    }

    private void MarkQuickConfigurationChanged()
    {
        if (_quickConfigurationSync || _quickConfigurationBaseline is not { } baseline) return;
        _quickConfigurationDirty =
            this.FindControl<ComboBox>("QuickDirection")!.SelectedItem?.ToString() != baseline.DirectionTimeframe ||
            this.FindControl<ComboBox>("QuickPullback")!.SelectedItem?.ToString() != baseline.PullbackTimeframe ||
            this.FindControl<ComboBox>("QuickTrigger")!.SelectedItem?.ToString() != baseline.TriggerTimeframe ||
            (this.FindControl<CheckBox>("QuickAllowBuy")!.IsChecked == true) != baseline.AllowBuy ||
            (this.FindControl<CheckBox>("QuickAllowSell")!.IsChecked == true) != baseline.AllowSell ||
            (_quickLogicBaseline is not null && this.FindControl<ComboBox>("QuickLogic")!.SelectedItem?.ToString() != _quickLogicBaseline);
        this.FindControl<Button>("QuickApply")!.Content = _quickConfigurationDirty ? "Áp dụng thay đổi" : "Áp dụng cấu hình nhanh";
    }

    private void UpdateQuickConfiguration(ConfigurationSummary config)
    {
        if (_quickConfigurationDirty) return;
        _quickConfigurationSync = true;
        _quickConfigurationBaseline = config;
        try
        {
            this.FindControl<ComboBox>("QuickDirection")!.SelectedItem = config.DirectionTimeframe;
            this.FindControl<ComboBox>("QuickPullback")!.SelectedItem = config.PullbackTimeframe;
            this.FindControl<ComboBox>("QuickTrigger")!.SelectedItem = config.TriggerTimeframe;
            this.FindControl<CheckBox>("QuickAllowBuy")!.IsChecked = config.AllowBuy;
            this.FindControl<CheckBox>("QuickAllowSell")!.IsChecked = config.AllowSell;
        }
        finally { _quickConfigurationSync = false; }
        _ = RefreshQuickDetailsAsync();
    }

    private async Task RefreshQuickDetailsAsync()
    {
        if (_quickDetailsLoading || _quickConfigurationDirty || _engineSupervisor.State != EngineConnectionState.Ready) return;
        var hash = _engineSupervisor.Strategy.ProfileHash;
        if (_quickDetailsHash == hash && _quickLogicBaseline is not null) return;
        _quickDetailsLoading = true;
        try
        {
            var profile = await _engineSupervisor.GetActiveConfigAsync();
            // A heartbeat or a user edit can arrive while the profile is being read.
            if (_quickConfigurationDirty || hash != _engineSupervisor.Strategy.ProfileHash) return;
            var logic = profile.GetProperty("pullback").GetProperty("logic").GetString();
            _quickConfigurationSync = true;
            try
            {
                _quickLogicBaseline = logic;
                _quickDetailsHash = hash;
                var combo = this.FindControl<ComboBox>("QuickLogic")!;
                combo.SelectedItem = logic;
                combo.IsEnabled = true;
            }
            finally { _quickConfigurationSync = false; }
        }
        catch (Exception ex)
        {
            ToolTip.SetTip(this.FindControl<ComboBox>("QuickLogic")!, $"Chưa tải logic Pullback: {ex.Message}");
        }
        finally { _quickDetailsLoading = false; }
    }

    private async void QuickApply_OnClick(object? sender, RoutedEventArgs e)
    {
        var button = this.FindControl<Button>("QuickApply")!;
        button.IsEnabled = false;
        try
        {
            if (_configurationEditor.HasUnsavedChanges)
                throw new InvalidOperationException("Tab Cấu hình có thay đổi chưa áp dụng. Hãy áp dụng hoặc hoàn tác bản nháp đó trước.");
            if (_strategyDashboard.HasUnsavedChanges)
                throw new InvalidOperationException("Tab Chiến lược có thay đổi chưa áp dụng. Hãy áp dụng hoặc hoàn tác bản nháp đó trước.");
            if (_toolsDashboard.HasUnsavedChanges)
                throw new InvalidOperationException("Tab Công cụ có thay đổi chưa áp dụng. Hãy áp dụng hoặc hoàn tác bản nháp đó trước.");
            var active = await _engineSupervisor.GetActiveConfigAsync();
            var profile = JsonNode.Parse(active.GetRawText())!.AsObject();
            var baseline = _quickConfigurationBaseline ?? throw new InvalidOperationException("Chưa tải cấu hình nhanh.");
            void PatchChangedValue(string section, string key, JsonNode? proposed, JsonNode? original)
            {
                if (JsonNode.DeepEquals(proposed, original)) return;
                if (!JsonNode.DeepEquals(profile[section]![key], original))
                    throw new InvalidOperationException("Cấu hình đang chạy đã thay đổi từ nơi khác. Bản nháp được giữ; hoàn tác lựa chọn nhanh để tải lại trước khi áp dụng.");
                profile[section]![key] = proposed;
            }
            PatchChangedValue("timeframes", "direction", JsonValue.Create(this.FindControl<ComboBox>("QuickDirection")!.SelectedItem?.ToString()), JsonValue.Create(baseline.DirectionTimeframe));
            PatchChangedValue("timeframes", "pullback", JsonValue.Create(this.FindControl<ComboBox>("QuickPullback")!.SelectedItem?.ToString()), JsonValue.Create(baseline.PullbackTimeframe));
            PatchChangedValue("timeframes", "trigger", JsonValue.Create(this.FindControl<ComboBox>("QuickTrigger")!.SelectedItem?.ToString()), JsonValue.Create(baseline.TriggerTimeframe));
            PatchChangedValue("strategy", "allow_buy", JsonValue.Create(this.FindControl<CheckBox>("QuickAllowBuy")!.IsChecked == true), JsonValue.Create(baseline.AllowBuy));
            PatchChangedValue("strategy", "allow_sell", JsonValue.Create(this.FindControl<CheckBox>("QuickAllowSell")!.IsChecked == true), JsonValue.Create(baseline.AllowSell));
            if (_quickLogicBaseline is not null)
                PatchChangedValue("pullback", "logic", JsonValue.Create(this.FindControl<ComboBox>("QuickLogic")!.SelectedItem?.ToString()), JsonValue.Create(_quickLogicBaseline));
            var result = await _engineSupervisor.ApplyActiveConfigAsync(JsonSerializer.SerializeToElement(profile));
            if (!result.Applied) throw new InvalidDataException("Các khung thời gian chưa hợp lệ. Kiểm tra ở tab Cấu hình.");
            _quickConfigurationDirty = false;
            _quickDetailsHash = null;
            button.Content = "Đã áp dụng";
            UpdateQuickConfiguration(_engineSupervisor.Configuration);
            if (!_configurationEditor.HasUnsavedChanges)
                await _configurationEditor.EnsureLoadedAsync(force: true);
            AppendQuickLog($"Đã áp dụng cấu hình nhanh. Chế độ giao dịch: {_engineSupervisor.Execution.Label}.");
        }
        catch (Exception ex)
        {
            button.Content = "Chưa áp dụng";
            AppendQuickLog($"Cấu hình nhanh: {ex.Message}");
            ToolTip.SetTip(button, ex.Message);
        }
        finally { button.IsEnabled = true; }
    }

    private async void ConfigurationShortcut_OnClick(object? sender, RoutedEventArgs e)
    {
        if (sender is not Button { Tag: string action }) return;
        NavButton_OnClick(this.FindControl<Button>("NavConfiguration"), new RoutedEventArgs());
        await _configurationEditor.OpenShortcutAsync(action);
    }

    private async void QuickHelp_OnClick(object? sender, RoutedEventArgs e)
    {
        var content = new StackPanel { Margin = new Avalonia.Thickness(24), Spacing = 18 };
        content.Children.Add(new TextBlock { [LocalizationService.TextProperty] = "Sử dụng Control Center", [AppearanceService.BaseFontSizeProperty] = 24d, FontWeight = FontWeight.SemiBold });
        content.Children.Add(new TextBlock
        {
            Text = "1. Mở MT5 và gắn XAUPY Bridge vào biểu đồ XAUUSD.\n\n" +
                   "2. Kiểm tra Python READY, EA Bridge kết nối và thời điểm giá. Khi nghỉ phiên, hệ thống giữ giá và nến gần nhất.\n\n" +
                   "3. Chỉnh tham số ở Cấu hình, xác thực rồi áp dụng. Các nút Nhập / Xuất giúp lưu profile JSON và preset MT5 .set.\n\n" +
                   "4. Backtest và Tối ưu sử dụng dữ liệu lịch sử đã chọn. Quyền giao dịch được chọn tại tab Lệnh & Vị thế.",
            TextWrapping = TextWrapping.Wrap
        });
        var dialog = new Window { Title = "Hướng dẫn", Width = 600, Height = 470, CanResize = false, Content = content, WindowStartupLocation = WindowStartupLocation.CenterOwner };
        var close = new Button { [LocalizationService.TextProperty] = "Đóng", HorizontalAlignment = Avalonia.Layout.HorizontalAlignment.Right };
        close.Click += (_, _) => dialog.Close();
        content.Children.Add(close);
        await dialog.ShowDialog(this);
    }
}
