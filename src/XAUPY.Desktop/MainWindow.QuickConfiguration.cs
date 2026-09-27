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
    }

    private void MarkQuickConfigurationChanged()
    {
        if (_quickConfigurationSync || _quickConfigurationBaseline is not { } baseline) return;
        _quickConfigurationDirty =
            this.FindControl<ComboBox>("QuickDirection")!.SelectedItem?.ToString() != baseline.DirectionTimeframe ||
            this.FindControl<ComboBox>("QuickPullback")!.SelectedItem?.ToString() != baseline.PullbackTimeframe ||
            this.FindControl<ComboBox>("QuickTrigger")!.SelectedItem?.ToString() != baseline.TriggerTimeframe ||
            (this.FindControl<CheckBox>("QuickAllowBuy")!.IsChecked == true) != baseline.AllowBuy ||
            (this.FindControl<CheckBox>("QuickAllowSell")!.IsChecked == true) != baseline.AllowSell;
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
    }

    private async void QuickApply_OnClick(object? sender, RoutedEventArgs e)
    {
        var button = this.FindControl<Button>("QuickApply")!;
        button.IsEnabled = false;
        try
        {
            if (_configurationEditor.HasUnsavedChanges)
                throw new InvalidOperationException("Tab Cấu hình có thay đổi chưa áp dụng. Hãy áp dụng hoặc hoàn tác bản nháp đó trước.");
            var active = await _engineSupervisor.GetActiveConfigAsync();
            var profile = JsonNode.Parse(active.GetRawText())!.AsObject();
            profile["timeframes"]!["direction"] = this.FindControl<ComboBox>("QuickDirection")!.SelectedItem?.ToString();
            profile["timeframes"]!["pullback"] = this.FindControl<ComboBox>("QuickPullback")!.SelectedItem?.ToString();
            profile["timeframes"]!["trigger"] = this.FindControl<ComboBox>("QuickTrigger")!.SelectedItem?.ToString();
            profile["strategy"]!["allow_buy"] = this.FindControl<CheckBox>("QuickAllowBuy")!.IsChecked == true;
            profile["strategy"]!["allow_sell"] = this.FindControl<CheckBox>("QuickAllowSell")!.IsChecked == true;
            var result = await _engineSupervisor.ApplyActiveConfigAsync(JsonSerializer.SerializeToElement(profile));
            if (!result.Applied) throw new InvalidDataException("Các khung thời gian chưa hợp lệ. Kiểm tra ở tab Cấu hình.");
            _quickConfigurationDirty = false;
            button.Content = "Đã áp dụng";
            UpdateQuickConfiguration(_engineSupervisor.Configuration);
            if (!_configurationEditor.HasUnsavedChanges)
                await _configurationEditor.EnsureLoadedAsync(force: true);
            AppendQuickLog("Đã áp dụng cấu hình nhanh. Giao dịch vẫn khóa.");
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
        content.Children.Add(new TextBlock { Text = "Sử dụng Control Center", FontSize = 24, FontWeight = FontWeight.SemiBold });
        content.Children.Add(new TextBlock
        {
            Text = "1. Mở MT5 và gắn XAUPY Bridge vào biểu đồ XAUUSD.\n\n" +
                   "2. Kiểm tra Python READY, EA Bridge kết nối và thời điểm giá. Khi nghỉ phiên, hệ thống giữ giá và nến gần nhất.\n\n" +
                   "3. Chỉnh tham số ở Cấu hình, xác thực rồi áp dụng. Các nút Nhập / Xuất giúp lưu profile JSON và preset MT5 .set.\n\n" +
                   "4. Backtest và Tối ưu sử dụng dữ liệu lịch sử đã chọn. Lệnh thử chỉ mô phỏng; gửi lệnh broker vẫn khóa.",
            TextWrapping = TextWrapping.Wrap
        });
        var dialog = new Window { Title = "Hướng dẫn", Width = 600, Height = 470, CanResize = false, Content = content, WindowStartupLocation = WindowStartupLocation.CenterOwner };
        var close = new Button { Content = "Đóng", HorizontalAlignment = Avalonia.Layout.HorizontalAlignment.Right };
        close.Click += (_, _) => dialog.Close();
        content.Children.Add(close);
        await dialog.ShowDialog(this);
    }
}
