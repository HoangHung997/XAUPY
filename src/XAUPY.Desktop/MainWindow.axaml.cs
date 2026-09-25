using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Media;
using Avalonia.Threading;
using XAUPY.Ipc;

namespace XAUPY.Desktop;

public partial class MainWindow : Window
{
    private const int ChartPointCount = 10;

    private readonly EngineProcessSupervisor _engineSupervisor;
    private readonly ConfigurationEditor _configurationEditor;
    private readonly StrategyDashboard _strategyDashboard;
    private readonly MonitoringDashboard _monitoringDashboard;
    private readonly List<double> _priceHistory = new();
    private readonly Queue<string> _quickLogs = new();

    private EngineConnectionState? _lastEngineState;
    private bool? _lastBridgeConnected;
    private bool _hadMarketData;

    private static readonly IReadOnlyDictionary<string, (string Title, string Subtitle)> Pages =
        new Dictionary<string, (string, string)>
        {
            ["overview"] = (
                "Tổng quan",
                "Giá XAUUSD, trạng thái hệ thống, tài khoản, chart, chiến lược, lệnh gần đây và log nhanh."),
            ["configuration"] = (
                "Cấu hình",
                "Full schema-driven editor: 133 tham số, JSON profile, MT5 .set import/export, validation và active profile."),
            ["strategy"] = (
                "Chiến lược",
                "Direction → Pullback → Trigger realtime từ Python Strategy Engine và active profile."),
            ["monitoring"] = (
                "Giám sát",
                "Quote, closed bars, indicator và condition state realtime; không hiển thị dữ liệu giả."),
            ["orders"] = (
                "Lệnh & Vị thế",
                "Execution và màn hình quản lý lệnh thuộc Task 009."),
            ["backtest"] = (
                "Backtest",
                "Backtest parity engine thuộc Task 011."),
            ["optimization"] = (
                "Tối ưu",
                "Parameter sweep và walk-forward thuộc Task 012."),
            ["logs"] = (
                "Nhật ký",
                "Structured trading journal thuộc Task 010."),
            ["tools"] = (
                "Công cụ",
                "Diagnostics suite thuộc Task 014."),
            ["settings"] = (
                "Cài đặt",
                "Startup/backup/fail-safe settings thuộc Task 015.")
        };

    public MainWindow()
    {
        InitializeComponent();

        _engineSupervisor = new EngineProcessSupervisor();
        _engineSupervisor.StateChanged += EngineSupervisor_OnStateChanged;

        _configurationEditor = this.FindControl<ConfigurationEditor>("ConfigurationEditor")
            ?? throw new InvalidOperationException("ConfigurationEditor missing.");
        _configurationEditor.AttachSupervisor(_engineSupervisor);
        _strategyDashboard = this.FindControl<StrategyDashboard>("StrategyDashboard")
            ?? throw new InvalidOperationException("StrategyDashboard missing.");
        _monitoringDashboard = this.FindControl<MonitoringDashboard>("MonitoringDashboard")
            ?? throw new InvalidOperationException("MonitoringDashboard missing.");

        AppendQuickLog("Control Center Task 008 khởi tạo.");
        ApplyConfigurationSummary(ConfigurationSummary.Default);
        ResetOverviewValues();

        Opened += async (_, _) =>
        {
            AppendQuickLog("Yêu cầu khởi động Python Engine.");
            await _engineSupervisor.StartAsync();
        };

        Closed += (_, _) => _engineSupervisor.Dispose();
    }

    private void NavButton_OnClick(object? sender, RoutedEventArgs e)
    {
        if (sender is not Button { Tag: string key } || !Pages.TryGetValue(key, out var page))
            return;

        FindText("PageTitle").Text = page.Title;
        FindText("PageSubtitle").Text = page.Subtitle;

        bool overview = string.Equals(key, "overview", StringComparison.Ordinal);
        bool configuration = string.Equals(key, "configuration", StringComparison.Ordinal);
        bool strategy = string.Equals(key, "strategy", StringComparison.Ordinal);
        bool monitoring = string.Equals(key, "monitoring", StringComparison.Ordinal);

        this.FindControl<StackPanel>("OverviewContent")!.IsVisible = overview;
        _configurationEditor.IsVisible = configuration;
        _strategyDashboard.IsVisible = strategy;
        _monitoringDashboard.IsVisible = monitoring;
        this.FindControl<Border>("PlaceholderContent")!.IsVisible =
            !overview && !configuration && !strategy && !monitoring;

        if (configuration)
        {
            _ = _configurationEditor.EnsureLoadedAsync();
        }
        else if (!overview && !strategy && !monitoring)
        {
            FindText("PlaceholderTitle").Text = $"{page.Title} — chưa triển khai";
            FindText("PlaceholderDetail").Text =
                $"Task 008 đã triển khai Tổng quan + Cấu hình + Chiến lược + Giám sát. {page.Subtitle}";
        }
    }

    private async void StartEngine_OnClick(object? sender, RoutedEventArgs e)
    {
        AppendQuickLog("Người dùng yêu cầu khởi động Engine.");
        await _engineSupervisor.StartAsync();
    }

    private async void StopEngine_OnClick(object? sender, RoutedEventArgs e)
    {
        AppendQuickLog("Người dùng yêu cầu dừng Engine.");
        await _engineSupervisor.StopAsync();
    }

    private void EngineSupervisor_OnStateChanged(object? sender, EngineStateChangedEventArgs e)
    {
        Dispatcher.UIThread.Post(() => ApplyEngineState(e));
    }

    private void ApplyEngineState(EngineStateChangedEventArgs e)
    {
        var engineText = GetEngineStateLabel(e.State);
        var engineColor = EngineStateColor(e.State);

        FindText("EngineStateText").Text = engineText;
        FindText("EngineStateText").Foreground = engineColor;
        FindText("HeaderEnginePillText").Text = $"ENGINE {engineText}";
        FindText("HeaderEnginePillText").Foreground = engineColor;
        FindText("EngineDetailText").Text = e.Detail;
        FindText("LastHeartbeatText").Text = e.LastHeartbeatUtc.HasValue
            ? $"Heartbeat: {e.LastHeartbeatUtc.Value.ToLocalTime():HH:mm:ss}"
            : "Heartbeat: —";

        if (_lastEngineState != e.State)
        {
            AppendQuickLog($"Engine → {engineText}: {e.Detail}");
            _lastEngineState = e.State;
        }

        ApplyBridgeStatus(e.Mt5Bridge);
        ApplyConfigurationSummary(e.Configuration);
        ApplyOverviewSnapshot(e.Overview);
        ApplyStrategySnapshot(e.Strategy);
        _strategyDashboard.Apply(e.Strategy, e.Configuration);
        _monitoringDashboard.Apply(e.Strategy, e.Overview, e.Mt5Bridge, e.Configuration);
        _ = _configurationEditor.NotifyEngineStateAsync(e.State);
    }

    private void ApplyBridgeStatus(Mt5BridgeStatus bridge)
    {
        var bridgeText = bridge.Connected ? "CONNECTED" : "WAITING";
        var bridgeColor = bridge.Connected ? Brushes.LightGreen : Brushes.Gold;

        FindText("BridgeStateText").Text = bridgeText;
        FindText("BridgeStateText").Foreground = bridgeColor;
        FindText("HeaderBridgePillText").Text = bridge.Connected ? "MT5 CONNECTED" : "MT5 WAITING";
        FindText("HeaderBridgePillText").Foreground = bridgeColor;
        FindText("BridgeAgeText").Text = bridge.AgeMs.HasValue
            ? $"Snapshot age: {bridge.AgeMs.Value} ms"
            : "Snapshot age: —";

        var symbol = string.IsNullOrWhiteSpace(bridge.Symbol) ? "?" : bridge.Symbol;
        var mode = string.IsNullOrWhiteSpace(bridge.AccountTradeMode) ? "?" : bridge.AccountTradeMode;

        FindText("BridgeDetailText").Text = bridge.Connected
            ? $"{symbol} • {mode} • terminal={(bridge.TerminalConnected ? "online" : "offline")} • snapshots={bridge.SnapshotsTotal}"
            : "Chưa nhận snapshot hợp lệ hoặc Bridge đã stale.";

        FindText("GuardianReasonValue").Text = bridge.GuardianReason;

        if (_lastBridgeConnected != bridge.Connected)
        {
            AppendQuickLog(
                bridge.Connected
                    ? $"MT5 Bridge → CONNECTED ({symbol}, {mode})."
                    : "MT5 Bridge → WAITING/OFFLINE.");
            _lastBridgeConnected = bridge.Connected;

            if (!bridge.Connected)
            {
                _priceHistory.Clear();
                UpdateChart();
            }
        }
    }

    private void ApplyConfigurationSummary(ConfigurationSummary config)
    {
        FindText("ProfileValue").Text = $"Profile: {config.ProfileName}";
        FindText("DirectionTfValue").Text = config.DirectionTimeframe;
        FindText("PullbackTfValue").Text = config.PullbackTimeframe;
        FindText("TriggerTfValue").Text = config.TriggerTimeframe;
        FindText("DirectionRuleValue").Text =
            $"Direction: {config.DirectionMaType}{config.DirectionMaPeriod} • BUY={(config.AllowBuy ? "ON" : "OFF")} • SELL={(config.AllowSell ? "ON" : "OFF")}";
        FindText("TpSlValue").Text =
            $"SL {config.StopLossMode} • TP {config.TakeProfitMode} • Max lot {config.MaxLot:0.###} • {config.MaxTradesPerDay} lệnh/ngày";
    }

    private void ApplyStrategySnapshot(StrategySnapshot strategy)
    {
        FindText("StrategyStateValue").Text = strategy.State;
        FindText("StrategyStateValue").Foreground = StrategyStateColor(strategy.State);

        if (!string.IsNullOrWhiteSpace(strategy.ProfileName))
            FindText("ProfileValue").Text = $"Profile: {strategy.ProfileName}";

        FindText("DirectionTfValue").Text = strategy.DirectionTimeframe;
        FindText("PullbackTfValue").Text = strategy.PullbackTimeframe;
        FindText("TriggerTfValue").Text = strategy.TriggerTimeframe;
    }

    private void ApplyOverviewSnapshot(OverviewSnapshot overview)
    {
        if (!overview.Available)
        {
            if (_hadMarketData)
            {
                AppendQuickLog("Overview market snapshot trở thành unavailable/stale.");
                _hadMarketData = false;
            }

            ResetOverviewValues();
            return;
        }

        var symbol = string.IsNullOrWhiteSpace(overview.Symbol) ? "XAUUSD" : overview.Symbol!;
        var currency = string.IsNullOrWhiteSpace(overview.AccountCurrency) ? "" : overview.AccountCurrency!;

        FindText("SymbolValue").Text = symbol;
        FindText("BidValue").Text = FormatPrice(overview.Bid);
        FindText("AskValue").Text = FormatPrice(overview.Ask);
        FindText("SpreadValue").Text = overview.SpreadPoints.HasValue
            ? $"Spread: {overview.SpreadPoints.Value:0.##} points"
            : "Spread: —";

        FindText("BalanceValue").Text = FormatMoney(overview.Balance, currency);
        FindText("EquityValue").Text = FormatMoney(overview.Equity, currency);
        FindText("MarginFreeValue").Text = FormatMoney(overview.MarginFree, currency);
        FindText("CurrencyValue").Text = string.IsNullOrWhiteSpace(currency)
            ? "Currency: —"
            : $"Currency: {currency}";
        FindText("AccountModeValue").Text = string.IsNullOrWhiteSpace(overview.AccountTradeMode)
            ? "MT5: connected"
            : $"MT5: {overview.AccountTradeMode}";

        FindText("PositionsCountValue").Text = overview.PositionsCount.ToString();
        FindText("OrdersCountValue").Text = overview.OrdersCount.ToString();

        FindText("RecentOrdersEmptyText").Text =
            overview.PositionsCount == 0 && overview.OrdersCount == 0
                ? "Không có position/pending order thuộc bridge snapshot hiện tại. Execution vẫn khóa."
                : $"Bridge báo {overview.PositionsCount} position và {overview.OrdersCount} order. Chi tiết ticket thuộc Task 009.";

        if (overview.Bid.HasValue)
        {
            _priceHistory.Add(overview.Bid.Value);
            while (_priceHistory.Count > ChartPointCount)
                _priceHistory.RemoveAt(0);
            UpdateChart();
        }

        if (!_hadMarketData)
        {
            AppendQuickLog($"Overview nhận dữ liệu thật: {symbol} BID {FormatPrice(overview.Bid)}.");
            _hadMarketData = true;
        }
    }

    private void ResetOverviewValues()
    {
        FindText("BidValue").Text = "—";
        FindText("AskValue").Text = "—";
        FindText("SpreadValue").Text = "Spread: —";
        FindText("BalanceValue").Text = "—";
        FindText("EquityValue").Text = "—";
        FindText("MarginFreeValue").Text = "—";
        FindText("CurrencyValue").Text = "Currency: —";
        FindText("AccountModeValue").Text = "MT5: waiting";
        FindText("PositionsCountValue").Text = "0";
        FindText("OrdersCountValue").Text = "0";
        FindText("RecentOrdersEmptyText").Text =
            "Chưa có dữ liệu lệnh. Task 008 chỉ hiển thị dữ liệu thật; execution hiện đang khóa.";
    }

    private void UpdateChart()
    {
        double min = _priceHistory.Count > 0 ? _priceHistory.Min() : 0;
        double max = _priceHistory.Count > 0 ? _priceHistory.Max() : 0;
        double range = Math.Max(max - min, 0.000001);

        for (int i = 0; i < ChartPointCount; i++)
        {
            var bar = this.FindControl<Border>($"ChartBar{i}")!;
            int sourceIndex = _priceHistory.Count - ChartPointCount + i;

            if (sourceIndex < 0 || sourceIndex >= _priceHistory.Count)
            {
                bar.Height = 18;
                bar.Opacity = 0.22;
                continue;
            }

            double value = _priceHistory[sourceIndex];
            double normalized = (value - min) / range;
            bar.Height = 28 + (normalized * 145);
            bar.Opacity = 0.45 + (0.05 * i);
        }

        if (_priceHistory.Count == 0)
        {
            FindText("ChartLastValue").Text = "Last: —";
            FindText("ChartRangeValue").Text = "Range: —";
            FindText("ChartMinValue").Text = "Min —";
            FindText("ChartMaxValue").Text = "Max —";
            return;
        }

        double last = _priceHistory[^1];
        FindText("ChartLastValue").Text = $"Last: {last:0.00}";
        FindText("ChartRangeValue").Text = $"Range: {(max - min):0.00}";
        FindText("ChartMinValue").Text = $"Min {min:0.00}";
        FindText("ChartMaxValue").Text = $"Max {max:0.00}";
    }

    private void AppendQuickLog(string message)
    {
        _quickLogs.Enqueue($"[{DateTime.Now:HH:mm:ss}] {message}");
        while (_quickLogs.Count > 8)
            _quickLogs.Dequeue();

        var log = this.FindControl<TextBlock>("QuickLogText");
        if (log is not null)
            log.Text = string.Join(Environment.NewLine, _quickLogs);
    }

    private TextBlock FindText(string name) =>
        this.FindControl<TextBlock>(name)
        ?? throw new InvalidOperationException($"Missing UI TextBlock: {name}");

    private static string GetEngineStateLabel(EngineConnectionState state) => state switch
    {
        EngineConnectionState.Ready => "READY",
        EngineConnectionState.Starting => "STARTING",
        EngineConnectionState.Connecting => "CONNECTING",
        EngineConnectionState.Reconnecting => "RECONNECTING",
        EngineConnectionState.Stopped => "STOPPED",
        EngineConnectionState.MissingEngine => "ENGINE MISSING",
        EngineConnectionState.Faulted => "FAULTED",
        _ => state.ToString().ToUpperInvariant()
    };

    private static IBrush StrategyStateColor(string state)
    {
        if (state.StartsWith("TRIGGERED_", StringComparison.Ordinal))
            return Brushes.LightGreen;
        if (state.StartsWith("ARMED_", StringComparison.Ordinal))
            return Brushes.LightBlue;
        if (state is "STALE" or "FILTER_BLOCKED")
            return Brushes.Gold;
        return Brushes.LightGray;
    }

    private static IBrush EngineStateColor(EngineConnectionState state) => state switch
    {
        EngineConnectionState.Ready => Brushes.LightGreen,
        EngineConnectionState.Faulted or EngineConnectionState.MissingEngine => Brushes.IndianRed,
        EngineConnectionState.Stopped => Brushes.LightGray,
        _ => Brushes.Gold
    };

    private static string FormatPrice(double? value) =>
        value.HasValue ? value.Value.ToString("0.00") : "—";

    private static string FormatMoney(double? value, string currency)
    {
        if (!value.HasValue)
            return "—";

        return string.IsNullOrWhiteSpace(currency)
            ? value.Value.ToString("N2")
            : $"{value.Value:N2} {currency}";
    }
}
