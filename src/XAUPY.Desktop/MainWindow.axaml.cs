using Avalonia.Controls;
using Avalonia.Input;
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
    private readonly OrdersPositionsDashboard _ordersPositionsDashboard;
    private readonly JournalDashboard _journalDashboard;
    private readonly BacktestDashboard _backtestDashboard;
    private readonly OptimizerDashboard _optimizerDashboard;
    private readonly List<double> _priceHistory = new();
    private readonly Queue<string> _quickLogs = new();
    private readonly DispatcherTimer _clockTimer;

    private EngineConnectionState? _lastEngineState;
    private bool? _lastBridgeConnected;
    private bool _hadMarketData;

    private static readonly IReadOnlyDictionary<string, (string Title, string Subtitle, string NavName)> Pages =
        new Dictionary<string, (string, string, string)>
        {
            ["overview"] = (
                "Tổng quan",
                "Giá XAUUSD, trạng thái hệ thống, tài khoản, chart, chiến lược, lệnh gần đây và log nhanh.",
                "NavOverview"),
            ["configuration"] = (
                "Cấu hình",
                "Full schema-driven editor: 133 tham số, JSON profile, MT5 .set import/export, validation và active profile.",
                "NavConfiguration"),
            ["strategy"] = (
                "Chiến lược",
                "Direction → Pullback → Trigger realtime từ Python Strategy Engine và active profile.",
                "NavStrategy"),
            ["monitoring"] = (
                "Giám sát",
                "Quote, closed bars, indicator và condition state realtime; không hiển thị dữ liệu giả.",
                "NavMonitoring"),
            ["orders"] = (
                "Lệnh & Vị thế",
                "Vị thế, pending orders, deals và manual-action simulation có guard; broker execution vẫn khóa.",
                "NavOrders"),
            ["backtest"] = (
                "Backtest",
                "Deterministic M1 OHLC replay dùng cùng StrategyEngine live, history và trade evidence.",
                "NavBacktest"),
            ["optimization"] = (
                "Tối ưu",
                "Deterministic parameter sweep, Top setups, heatmap và train-only walk-forward validation.",
                "NavOptimization"),
            ["logs"] = (
                "Nhật ký",
                "Structured journal persisted/replay: MT5, Bridge, Engine, Strategy, Orders, Alerts, filter/search/bookmark.",
                "NavLogs"),
            ["tools"] = (
                "Công cụ",
                "Diagnostics suite thuộc Task 014.",
                "NavTools"),
            ["settings"] = (
                "Cài đặt",
                "Startup/backup/fail-safe settings thuộc Task 015.",
                "NavSettings")
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
        _ordersPositionsDashboard = this.FindControl<OrdersPositionsDashboard>("OrdersPositionsDashboard")
            ?? throw new InvalidOperationException("OrdersPositionsDashboard missing.");
        _ordersPositionsDashboard.AttachSupervisor(_engineSupervisor);
        _journalDashboard = this.FindControl<JournalDashboard>("JournalDashboard")
            ?? throw new InvalidOperationException("JournalDashboard missing.");
        _journalDashboard.AttachSupervisor(_engineSupervisor);
        _backtestDashboard = this.FindControl<BacktestDashboard>("BacktestDashboard")
            ?? throw new InvalidOperationException("BacktestDashboard missing.");
        _backtestDashboard.AttachSupervisor(_engineSupervisor);
        _optimizerDashboard = this.FindControl<OptimizerDashboard>("OptimizerDashboard")
            ?? throw new InvalidOperationException("OptimizerDashboard missing.");
        _optimizerDashboard.AttachSupervisor(_engineSupervisor);

        _clockTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1) };
        _clockTimer.Tick += (_, _) => UpdateClock();
        _clockTimer.Start();
        UpdateClock();

        AppendQuickLog("N30 Control Center khởi tạo.");
        ApplyConfigurationSummary(ConfigurationSummary.Default);
        ApplyStrategySnapshot(StrategySnapshot.Empty);
        ResetOverviewValues();
        SetNavActive("overview");

        Opened += async (_, _) =>
        {
            AppendQuickLog("Yêu cầu khởi động Python Engine.");
            await _engineSupervisor.StartAsync();
        };

        Closed += (_, _) =>
        {
            _clockTimer.Stop();
            _engineSupervisor.Dispose();
        };
    }

    private void NavButton_OnClick(object? sender, RoutedEventArgs e)
    {
        if (sender is not Button { Tag: string key } || !Pages.TryGetValue(key, out var page))
            return;

        FindText("PageTitle").Text = page.Title;
        FindText("PageSubtitle").Text = page.Subtitle;
        SetNavActive(key);

        bool overview = string.Equals(key, "overview", StringComparison.Ordinal);
        bool configuration = string.Equals(key, "configuration", StringComparison.Ordinal);
        bool strategy = string.Equals(key, "strategy", StringComparison.Ordinal);
        bool monitoring = string.Equals(key, "monitoring", StringComparison.Ordinal);
        bool orders = string.Equals(key, "orders", StringComparison.Ordinal);
        bool backtest = string.Equals(key, "backtest", StringComparison.Ordinal);
        bool optimization = string.Equals(key, "optimization", StringComparison.Ordinal);
        bool logs = string.Equals(key, "logs", StringComparison.Ordinal);
        bool liveSidebar = overview || strategy || monitoring || backtest || optimization;

        this.FindControl<ScrollViewer>("OverviewScroll")!.IsVisible = overview;
        this.FindControl<StackPanel>("OverviewContent")!.IsVisible = overview;
        this.FindControl<ScrollViewer>("LiveSidebar")!.IsVisible = liveSidebar;
        _configurationEditor.IsVisible = configuration;
        _strategyDashboard.IsVisible = strategy;
        _monitoringDashboard.IsVisible = monitoring;
        _ordersPositionsDashboard.IsVisible = orders;
        _backtestDashboard.IsVisible = backtest;
        _optimizerDashboard.IsVisible = optimization;
        _journalDashboard.IsVisible = logs;
        this.FindControl<Border>("PlaceholderContent")!.IsVisible =
            !overview && !configuration && !strategy && !monitoring && !orders && !backtest && !optimization && !logs;

        if (configuration)
        {
            _ = _configurationEditor.EnsureLoadedAsync();
        }
        else if (backtest)
        {
            _ = _backtestDashboard.EnsureLoadedAsync(force: true);
        }
        else if (optimization)
        {
            _ = _optimizerDashboard.EnsureLoadedAsync(force: true);
        }
        else if (logs)
        {
            _ = _journalDashboard.EnsureLoadedAsync(force: true);
        }
        else if (!overview && !strategy && !monitoring && !orders && !backtest && !optimization && !logs)
        {
            FindText("PlaceholderTitle").Text = $"{page.Title} — chưa triển khai";
            FindText("PlaceholderDetail").Text =
                $"Task 013 đã triển khai Tổng quan + Cấu hình + Chiến lược + Giám sát + Lệnh & Vị thế + Backtest + Tối ưu + Nhật ký; đồng thời bổ sung STOP_CONFIRM + ATR SL + Dynamic TP/SL trên Backtest/Tối ưu; broker execution vẫn khóa. {page.Subtitle}";
        }
    }

    private void SetNavActive(string activeKey)
    {
        foreach (var item in Pages)
        {
            var button = this.FindControl<Button>(item.Value.NavName);
            if (button is null)
                continue;

            bool active = string.Equals(item.Key, activeKey, StringComparison.Ordinal);
            bool has = button.Classes.Contains("active");
            if (active && !has)
                button.Classes.Add("active");
            else if (!active && has)
                button.Classes.Remove("active");
        }
    }

    private void TitleBar_OnPointerPressed(object? sender, PointerPressedEventArgs e)
    {
        if (e.GetCurrentPoint(this).Properties.IsLeftButtonPressed)
            BeginMoveDrag(e);
    }

    private void Minimize_OnClick(object? sender, RoutedEventArgs e) =>
        WindowState = WindowState.Minimized;

    private void Maximize_OnClick(object? sender, RoutedEventArgs e) =>
        WindowState = WindowState == WindowState.Maximized ? WindowState.Normal : WindowState.Maximized;

    private void Close_OnClick(object? sender, RoutedEventArgs e) => Close();

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
        FindText("FooterEngineStateText").Text = engineText;
        FindText("FooterEngineStateText").Foreground = engineColor;
        FindText("EngineDetailText").Text = e.Detail;
        FindText("LastHeartbeatText").Text = e.LastHeartbeatUtc.HasValue
            ? e.LastHeartbeatUtc.Value.ToLocalTime().ToString("HH:mm:ss")
            : "—";

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
        _ordersPositionsDashboard.Apply(e.OrdersPositions, e.Overview, e.Mt5Bridge, e.Configuration);
        _journalDashboard.ApplySummary(e.JournalSummary);
        _backtestDashboard.ApplyConfiguration(e.Configuration);
        _optimizerDashboard.ApplyStatus(e.OptimizerStatus);
        _optimizerDashboard.ApplyEngineState(e.State);
        ApplyOrdersFooter(e.OrdersPositions);
        _ = _configurationEditor.NotifyEngineStateAsync(e.State);
    }

    private void ApplyBridgeStatus(Mt5BridgeStatus bridge)
    {
        var bridgeText = bridge.Connected ? "OK" : "WAIT";
        var bridgeColor = bridge.Connected ? Brushes.LightGreen : Brushes.Gold;

        FindText("BridgeStateText").Text = bridgeText;
        FindText("BridgeStateText").Foreground = bridgeColor;
        FindText("HeaderBridgePillText").Text =
            bridge.Connected ? "●  Connected to MT5" : "●  Waiting for MT5";
        FindText("HeaderBridgePillText").Foreground = bridgeColor;
        FindText("BridgeAgeText").Text = bridge.AgeMs.HasValue
            ? $"{bridge.AgeMs.Value} ms"
            : "—";

        var symbol = string.IsNullOrWhiteSpace(bridge.Symbol) ? "?" : bridge.Symbol;
        var mode = string.IsNullOrWhiteSpace(bridge.AccountTradeMode) ? "?" : bridge.AccountTradeMode;

        FindText("BridgeDetailText").Text = bridge.Connected
            ? $"{symbol} • {mode} • terminal={(bridge.TerminalConnected ? "online" : "offline")} • snapshots={bridge.SnapshotsTotal}"
            : "Chưa nhận snapshot hợp lệ hoặc Bridge đã stale.";

        FindText("GuardianReasonValue").Text = bridge.Connected ? "OK" : bridge.GuardianReason;

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

        FindText("OverviewDirectionState").Text =
            $"{strategy.Direction} ({strategy.DirectionTimeframe})";
        FindText("OverviewDirectionState").Foreground = DirectionColor(strategy.Direction);
        FindText("OverviewPullbackState").Text = PullbackState(strategy);
        FindText("OverviewTriggerState").Text = TriggerState(strategy);
        FindText("OverviewZTrigger").Text = FormatMetric(strategy.TriggerIndicators.Z);
        FindText("OverviewRsiTrigger").Text = FormatMetric(strategy.TriggerIndicators.Rsi);
        FindText("OverviewZPullback").Text = FormatMetric(strategy.PullbackIndicators.Z);
        FindText("OverviewRsiPullback").Text = FormatMetric(strategy.PullbackIndicators.Rsi);
        FindText("OverviewMaValue").Text = FormatMetric(strategy.DirectionIndicators.Ma);
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
            ? $"Spread {overview.SpreadPoints.Value:0.##} pt"
            : "Spread —";

        FindText("BalanceValue").Text = FormatMoney(overview.Balance, currency);
        FindText("EquityValue").Text = FormatMoney(overview.Equity, currency);
        FindText("MarginFreeValue").Text = FormatMoney(overview.MarginFree, currency);
        FindText("CurrencyValue").Text = string.IsNullOrWhiteSpace(currency)
            ? "Currency: —"
            : $"Currency: {currency}";
        FindText("AccountModeValue").Text = string.IsNullOrWhiteSpace(overview.AccountTradeMode)
            ? "MT5: connected"
            : overview.AccountTradeMode!;

        FindText("PositionsCountValue").Text = overview.PositionsCount.ToString();
        FindText("OrdersCountValue").Text = overview.OrdersCount.ToString();
        FindText("SidebarPositionsText").Text = overview.PositionsCount.ToString();
        FindText("FooterSpreadText").Text = overview.SpreadPoints.HasValue
            ? overview.SpreadPoints.Value.ToString("0.##")
            : "—";

        FindText("RecentOrdersEmptyText").Text =
            overview.PositionsCount == 0 && overview.OrdersCount == 0
                ? "Không có position/pending order thuộc bridge snapshot hiện tại. Broker execution vẫn khóa."
                : $"Bridge báo {overview.PositionsCount} position và {overview.OrdersCount} order. Mở tab Lệnh & Vị thế để xem ticket thật.";

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
        FindText("SpreadValue").Text = "Spread —";
        FindText("BalanceValue").Text = "—";
        FindText("EquityValue").Text = "—";
        FindText("MarginFreeValue").Text = "—";
        FindText("CurrencyValue").Text = "Currency: —";
        FindText("AccountModeValue").Text = "MT5: waiting";
        FindText("PositionsCountValue").Text = "0";
        FindText("OrdersCountValue").Text = "0";
        FindText("SidebarPositionsText").Text = "0";
        FindText("FooterSpreadText").Text = "—";
        FindText("RecentOrdersEmptyText").Text =
            "Chưa có dữ liệu lệnh. Task 009 chỉ hiển thị dữ liệu thật; broker execution hiện đang khóa.";
    }

    private void ApplyOrdersFooter(OrdersPositionsSnapshot orders)
    {
        FindText("FooterAccountText").Text = orders.AccountLogin.HasValue
            ? orders.AccountLogin.Value.ToString()
            : "—";
        FindText("FooterLeverageText").Text = orders.Leverage.HasValue
            ? $"1:{orders.Leverage.Value}"
            : "—";
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
            bar.Opacity = 0.50 + (0.045 * i);
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

    private void UpdateClock()
    {
        var now = DateTime.Now;
        FindText("HeaderClockText").Text = now.ToString("HH:mm:ss");
        FindText("HeaderDateText").Text = now.ToString("dd/MM/yyyy");
        FindText("FooterServerTimeText").Text = now.ToString("yyyy.MM.dd HH:mm:ss");
    }

    private void AppendQuickLog(string message)
    {
        _quickLogs.Enqueue($"[{DateTime.Now:HH:mm:ss}] {message}");
        while (_quickLogs.Count > 6)
            _quickLogs.Dequeue();

        var log = this.FindControl<TextBlock>("QuickLogText");
        if (log is not null)
            log.Text = string.Join(Environment.NewLine, _quickLogs);
    }

    private TextBlock FindText(string name) =>
        this.FindControl<TextBlock>(name)
        ?? throw new InvalidOperationException($"Missing UI TextBlock: {name}");

    private static string PullbackState(StrategySnapshot strategy)
    {
        if (strategy.ArmedSide is not null)
            return $"ARMED {strategy.ArmedSide}";
        if (strategy.PullbackBuyPassed == true)
            return "BUY READY";
        if (strategy.PullbackSellPassed == true)
            return "SELL READY";
        return strategy.State.StartsWith("WAIT_PULLBACK", StringComparison.Ordinal) ? "ĐANG CHỜ" : "—";
    }

    private static string TriggerState(StrategySnapshot strategy) =>
        strategy.State.StartsWith("TRIGGERED_", StringComparison.Ordinal)
            ? strategy.State
            : strategy.ArmedSide is not null ? "CHỜ TÍN HIỆU" : "—";

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

    private static IBrush DirectionColor(string direction) => direction switch
    {
        "BUY" => Brushes.LightGreen,
        "SELL" => Brushes.IndianRed,
        "BOTH" => Brushes.LightBlue,
        _ => Brushes.LightGray
    };

    private static IBrush EngineStateColor(EngineConnectionState state) => state switch
    {
        EngineConnectionState.Ready => Brushes.LightGreen,
        EngineConnectionState.Faulted or EngineConnectionState.MissingEngine => Brushes.IndianRed,
        EngineConnectionState.Stopped => Brushes.LightGray,
        _ => Brushes.Gold
    };

    private static string FormatPrice(double? value) =>
        value.HasValue ? value.Value.ToString("0.00") : "—";

    private static string FormatMetric(double? value) =>
        value.HasValue ? value.Value.ToString("0.###") : "—";

    private static string FormatMoney(double? value, string currency)
    {
        if (!value.HasValue)
            return "—";

        return string.IsNullOrWhiteSpace(currency)
            ? value.Value.ToString("N2")
            : $"{value.Value:N2} {currency}";
    }
}
