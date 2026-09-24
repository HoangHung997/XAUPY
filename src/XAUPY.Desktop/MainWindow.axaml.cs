using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Media;
using Avalonia.Threading;
using XAUPY.Ipc;

namespace XAUPY.Desktop;

public partial class MainWindow : Window
{
    private readonly EngineProcessSupervisor _engineSupervisor;

    private static readonly IReadOnlyDictionary<string, (string Title, string Subtitle)> Pages =
        new Dictionary<string, (string, string)>
        {
            ["overview"] = ("Tổng quan", "Task 004: canonical profile JSON + MT5 .set import/export; execution vẫn khóa."),
            ["configuration"] = ("Cấu hình", "Backend schema/profile/.set đã hoàn thành ở Task 004; full editor Avalonia thuộc Task 006."),
            ["strategy"] = ("Chiến lược", "Placeholder. Direction → Pullback → Trigger thuộc Task 007."),
            ["monitoring"] = ("Giám sát", "MT5 Bridge health từ Task 003 vẫn hoạt động; monitoring chi tiết thuộc Task 008."),
            ["orders"] = ("Lệnh & Vị thế", "Placeholder. Task 004 vẫn không thêm API đặt/sửa/đóng lệnh."),
            ["backtest"] = ("Backtest", "Placeholder. Backtest parity engine thuộc Task 011."),
            ["optimization"] = ("Tối ưu", "Placeholder. Parameter sweep/walk-forward thuộc Task 012."),
            ["logs"] = ("Nhật ký", "Placeholder. Structured trading journal thuộc Task 010."),
            ["tools"] = ("Công cụ", "Placeholder. Diagnostics suite thuộc Task 014."),
            ["settings"] = ("Cài đặt", "Placeholder. Startup/backup/fail-safe settings thuộc Task 015.")
        };

    public MainWindow()
    {
        InitializeComponent();

        _engineSupervisor = new EngineProcessSupervisor();
        _engineSupervisor.StateChanged += EngineSupervisor_OnStateChanged;

        Opened += async (_, _) => await _engineSupervisor.StartAsync();
        Closed += (_, _) => _engineSupervisor.Dispose();
    }

    private void NavButton_OnClick(object? sender, RoutedEventArgs e)
    {
        if (sender is not Button { Tag: string key } || !Pages.TryGetValue(key, out var page))
            return;

        this.FindControl<TextBlock>("PageTitle")!.Text = page.Title;
        this.FindControl<TextBlock>("PageSubtitle")!.Text = page.Subtitle;
    }

    private async void StartEngine_OnClick(object? sender, RoutedEventArgs e)
    {
        await _engineSupervisor.StartAsync();
    }

    private async void StopEngine_OnClick(object? sender, RoutedEventArgs e)
    {
        await _engineSupervisor.StopAsync();
    }

    private void EngineSupervisor_OnStateChanged(object? sender, EngineStateChangedEventArgs e)
    {
        Dispatcher.UIThread.Post(() =>
        {
            var stateText = this.FindControl<TextBlock>("EngineStateText")!;
            var detailText = this.FindControl<TextBlock>("EngineDetailText")!;
            var heartbeatText = this.FindControl<TextBlock>("LastHeartbeatText")!;
            var bridgeStateText = this.FindControl<TextBlock>("BridgeStateText")!;
            var bridgeDetailText = this.FindControl<TextBlock>("BridgeDetailText")!;
            var bridgeGuardianText = this.FindControl<TextBlock>("BridgeGuardianText")!;

            stateText.Text = e.State switch
            {
                EngineConnectionState.Ready => "READY",
                EngineConnectionState.Starting => "STARTING",
                EngineConnectionState.Connecting => "CONNECTING",
                EngineConnectionState.Reconnecting => "RECONNECTING",
                EngineConnectionState.Stopped => "STOPPED",
                EngineConnectionState.MissingEngine => "ENGINE MISSING",
                EngineConnectionState.Faulted => "FAULTED",
                _ => e.State.ToString().ToUpperInvariant()
            };

            stateText.Foreground = e.State switch
            {
                EngineConnectionState.Ready => Brushes.LightGreen,
                EngineConnectionState.Faulted or EngineConnectionState.MissingEngine => Brushes.IndianRed,
                EngineConnectionState.Stopped => Brushes.LightGray,
                _ => Brushes.Gold
            };

            detailText.Text = e.Detail;
            heartbeatText.Text = e.LastHeartbeatUtc.HasValue
                ? $"Heartbeat: {e.LastHeartbeatUtc.Value.ToLocalTime():HH:mm:ss}"
                : "Heartbeat: —";

            var bridge = e.Mt5Bridge;
            bridgeStateText.Text = bridge.Connected ? "CONNECTED" : "WAITING";
            bridgeStateText.Foreground = bridge.Connected ? Brushes.LightGreen : Brushes.Gold;

            if (bridge.Connected)
            {
                var age = bridge.AgeMs.HasValue ? $"{bridge.AgeMs.Value} ms" : "—";
                var symbol = string.IsNullOrWhiteSpace(bridge.Symbol) ? "?" : bridge.Symbol;
                var mode = string.IsNullOrWhiteSpace(bridge.AccountTradeMode) ? "?" : bridge.AccountTradeMode;
                bridgeDetailText.Text =
                    $"{symbol} • {mode} • terminal={(bridge.TerminalConnected ? "online" : "offline")} • age={age} • snapshots={bridge.SnapshotsTotal}";
            }
            else
            {
                bridgeDetailText.Text = "Chưa nhận snapshot hợp lệ hoặc Bridge đã stale.";
            }

            bridgeGuardianText.Text = $"Guardian: {bridge.GuardianReason} • EXECUTION LOCKED";
            bridgeGuardianText.Foreground = Brushes.Gold;
        });
    }
}
