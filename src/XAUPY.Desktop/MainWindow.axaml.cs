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
            ["overview"] = ("Tổng quan", "Task 002: Desktop tự quản lý Python Engine và giám sát IPC v1 qua localhost."),
            ["configuration"] = ("Cấu hình", "Placeholder. Canonical profile/config editor thuộc Task 004/006."),
            ["strategy"] = ("Chiến lược", "Placeholder. Direction → Pullback → Trigger thuộc Task 007."),
            ["monitoring"] = ("Giám sát", "IPC heartbeat đã hoạt động; realtime MT5/strategy monitoring thuộc Task 008."),
            ["orders"] = ("Lệnh & Vị thế", "Placeholder. Task 002 không có broker hoặc order command."),
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
        });
    }
}
