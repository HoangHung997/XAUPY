using Avalonia;
using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Layout;
using Avalonia.Media;
using XAUPY.Ipc;

namespace XAUPY.Desktop;

public partial class OrdersPositionsDashboard
{
    private DemoOnceSnapshot _demoOnceReport = DemoOnceSnapshot.Disabled;
    private DemoOnceContext _demoOnceContext = DemoOnceContext.Empty;
    private bool _demoOnceBusy;
    private Guid? _demoAttempt;

    public async Task RefreshDemoOnceAsync()
    {
        if (_demoOnceBusy || _supervisor?.State != EngineConnectionState.Ready) { RefreshDemoOnceControls(); return; }
        _demoOnceBusy = true; RefreshDemoOnceControls();
        try { ApplyDemoResponse(await _supervisor.GetDemoOnceStatusAsync()); }
        catch (Exception error) { Text("DemoOnceMessage").Text = error.Message; }
        finally { _demoOnceBusy = false; RefreshDemoOnceControls(); }
    }

    private void ApplyDemoResponse(DemoOnceResponse response)
    {
        _demoOnceContext = response.Context;
        ApplyDemoOnceStatus(response.Status);
        var reason = response.Status.LastBlocker ?? response.Status.Code ?? response.Status.Reason;
        Text("DemoOnceMessage").Text = string.IsNullOrWhiteSpace(reason)
            ? "Chỉ gửi khi có tín hiệu mới đúng chiến lược. Dừng chờ không đóng vị thế đã khớp." : reason;
    }

    private void RefreshDemoOnceControls()
    {
        bool ready = _supervisor?.State == EngineConnectionState.Ready && _book.Available && _book.TerminalConnected && _book.AccountTradeMode == "DEMO";
        bool unused = _demoOnceReport.BudgetConsumed == false && _demoOnceReport.State is "DISABLED" or "CANCELLED" or "SUSPENDED" or "EXPIRED";
        Button("DemoOnceStart").IsEnabled = !_demoOnceBusy && ready && _demoOnceReport.IsFresh && unused && _demoOnceContext.CanArm;
        Button("DemoOnceCancel").IsEnabled = !_demoOnceBusy && _supervisor?.State == EngineConnectionState.Ready &&
            _demoOnceReport.IsFresh && _demoOnceReport.State == "ARMED" && _demoOnceReport.BudgetConsumed == false && Guid.TryParse(_demoOnceReport.AttemptId, out _);
        this.FindControl<NumericUpDown>("DemoOnceVolume")!.IsEnabled = !_demoOnceBusy && unused;
        this.FindControl<NumericUpDown>("DemoOnceMinutes")!.IsEnabled = !_demoOnceBusy && unused;
        string account = _book.AccountLogin?.ToString() ?? _demoOnceContext.AccountLogin?.ToString() ?? "—";
        string mode = _book.AccountTradeMode ?? _demoOnceContext.AccountMode ?? "—";
        string until = _demoOnceReport.ArmedUntilUtc is { } end ? $" · đến {end.ToLocalTime():HH:mm:ss dd/MM}" : "";
        Text("DemoOnceContextText").Text = $"Tài khoản {account} · {mode} · {_book.Symbol ?? _demoOnceContext.Symbol ?? "—"}{until}";
        if (_demoOnceReport.BudgetConsumed == true)
            Text("DemoOnceMessage").Text = "Lần giao dịch này đã dùng quyền gửi. Không tự gửi lại; đối chiếu ticket trong MT5.";
    }

    private async void DemoOnceRefresh_OnClick(object? sender, RoutedEventArgs e) => await RefreshDemoOnceAsync();

    private async void DemoOnceStart_OnClick(object? sender, RoutedEventArgs e)
    {
        if (_demoOnceBusy || _supervisor?.State != EngineConnectionState.Ready) return;
        _demoOnceBusy = true; RefreshDemoOnceControls();
        try
        {
            var current = await _supervisor.GetDemoOnceStatusAsync(); ApplyDemoResponse(current);
            if (!current.Context.CanArm || current.Status.BudgetConsumed != false ||
                current.Status.State is not ("DISABLED" or "CANCELLED" or "SUSPENDED" or "EXPIRED"))
                throw new InvalidOperationException("Không thể bắt đầu: kiểm tra tài khoản DEMO và trạng thái lần chờ hiện tại.");
            double volume = (double)(this.FindControl<NumericUpDown>("DemoOnceVolume")!.Value ?? .01m);
            int seconds = checked((int)(this.FindControl<NumericUpDown>("DemoOnceMinutes")!.Value ?? 60) * 60);
            if (!await ConfirmDemoOnceAsync(current.Context, volume, seconds)) return;
            _demoAttempt ??= Guid.NewGuid();
            var result = await _supervisor.ArmDemoOnceAsync(current.Context, _demoAttempt.Value, volume, seconds, confirmed: true);
            ApplyDemoResponse(result);
            if (result.Accepted) _demoAttempt = null;
        }
        catch (Exception error) { Text("DemoOnceMessage").Text = $"{error.Message} Đọc lại trạng thái trước khi thử tiếp."; }
        finally { _demoOnceBusy = false; RefreshDemoOnceControls(); }
    }

    private async void DemoOnceCancel_OnClick(object? sender, RoutedEventArgs e)
    {
        if (_demoOnceBusy || _supervisor?.State != EngineConnectionState.Ready || _demoOnceReport.AttemptId is not { } attempt) return;
        _demoOnceBusy = true; RefreshDemoOnceControls();
        try { ApplyDemoResponse(await _supervisor.CancelDemoOnceAsync(attempt)); }
        catch (Exception error) { Text("DemoOnceMessage").Text = error.Message; }
        finally { _demoOnceBusy = false; RefreshDemoOnceControls(); }
    }

    private async Task<bool> ConfirmDemoOnceAsync(DemoOnceContext context, double volume, int seconds)
    {
        if (TopLevel.GetTopLevel(this) is not Window owner) return false;
        bool confirmed = false;
        var dialog = new Window { Title = "Bắt đầu DEMO một lệnh", Width = 540, Height = 275, CanResize = false,
            WindowStartupLocation = WindowStartupLocation.CenterOwner, Background = new SolidColorBrush(Color.Parse("#031426")) };
        var cancel = new Button { Content = "Quay lại", Classes = { "secondary" } };
        var start = new Button { Content = "Bắt đầu chờ tín hiệu DEMO", Classes = { "primary" } };
        cancel.Click += (_, _) => dialog.Close();
        start.Click += (_, _) => { confirmed = true; dialog.Close(); };
        dialog.Content = new StackPanel { Margin = new Thickness(18), Spacing = 12, Children =
        {
            new TextBlock { Text = $"DEMO {context.AccountLogin} · {context.AccountServer}\n{context.Symbol} · tối đa {volume:0.###} lot · chờ {seconds / 60} phút", FontSize = 17, TextWrapping = TextWrapping.Wrap },
            new TextBlock { Text = "Ứng dụng sẽ gửi tối đa một lệnh khi có tín hiệu mới theo cấu hình đang áp dụng, kèm SL/TP. Không tự gửi lại. Nút Dừng chờ chỉ hủy thời gian chờ, không đóng vị thế đã gửi.", TextWrapping = TextWrapping.Wrap, Foreground = Brushes.Gold },
            new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right, Spacing = 8, Children = { cancel, start } }
        } };
        await dialog.ShowDialog(owner); return confirmed;
    }
}
