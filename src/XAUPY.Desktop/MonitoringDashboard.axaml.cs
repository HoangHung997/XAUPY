using Avalonia.Controls;
using Avalonia.Layout;
using Avalonia.Media;
using XAUPY.Ipc;

namespace XAUPY.Desktop;

public partial class MonitoringDashboard : UserControl
{
    private const int MaxQuotePoints = 24;
    private readonly List<double> _quotes = new();
    private string? _lastSnapshotToken;

    public MonitoringDashboard()
    {
        InitializeComponent();
        Apply(StrategySnapshot.Empty, OverviewSnapshot.Empty, Mt5BridgeStatus.Offline, ConfigurationSummary.Default);
        UpdateQuoteChart();
    }

    public void Apply(
        StrategySnapshot strategy,
        OverviewSnapshot overview,
        Mt5BridgeStatus bridge,
        ConfigurationSummary config)
    {
        Text("MonitorBidText").Text = Price(overview.Bid);
        Text("MonitorAskText").Text = Price(overview.Ask);
        Text("MonitorBridgeText").Text = bridge.Connected ? "CONNECTED" : "WAITING";
        Text("MonitorBridgeText").Foreground = bridge.Connected ? Brushes.LightGreen : Brushes.Gold;
        Text("MonitorAgeText").Text = bridge.AgeMs.HasValue ? $"Age: {bridge.AgeMs.Value} ms" : "Age: —";

        Text("MonitorStrategyText").Text = strategy.State;
        Text("MonitorStrategyText").Foreground = StrategyBrush(strategy.State);
        Text("MonitorDirectionText").Text = $"Direction: {strategy.Direction}";

        if (overview.Available && overview.Bid.HasValue &&
            !string.IsNullOrWhiteSpace(overview.SnapshotReceivedUtc) &&
            !string.Equals(_lastSnapshotToken, overview.SnapshotReceivedUtc, StringComparison.Ordinal))
        {
            _lastSnapshotToken = overview.SnapshotReceivedUtc;
            _quotes.Add(overview.Bid.Value);
            while (_quotes.Count > MaxQuotePoints)
                _quotes.RemoveAt(0);
            UpdateQuoteChart();
        }
        else if (!overview.Available && _quotes.Count > 0)
        {
            _quotes.Clear();
            _lastSnapshotToken = null;
            UpdateQuoteChart();
        }

        ApplyBar("Direction", strategy.DirectionTimeframe, overview, "DirectionBarRoleText", "DirectionBarText", "DirectionBarTimeText");
        ApplyBar("Pullback", strategy.PullbackTimeframe, overview, "PullbackBarRoleText", "PullbackBarText", "PullbackBarTimeText");
        ApplyBar("Trigger", strategy.TriggerTimeframe, overview, "TriggerBarRoleText", "TriggerBarText", "TriggerBarTimeText");

        Text("MonitorMaText").Text = Metric(strategy.DirectionIndicators.Ma);
        Text("MonitorPbRsiText").Text = Metric(strategy.PullbackIndicators.Rsi);
        Text("MonitorTriggerRsiText").Text = Metric(strategy.TriggerIndicators.Rsi);
        Text("MonitorAdxText").Text = Metric(strategy.Filters.Adx);
        Text("MonitorAtrText").Text = Metric(strategy.Filters.Atr);

        Text("MonitorDirectionTfText").Text = strategy.DirectionTimeframe;
        Text("MonitorPullbackTfText").Text = strategy.PullbackTimeframe;
        Text("MonitorTriggerTfText").Text = strategy.TriggerTimeframe;
        Text("MonitorDirectionStateText").Text = strategy.Direction;
        Text("MonitorDirectionStateText").Foreground = DirectionBrush(strategy.Direction);
        Text("MonitorPullbackStateText").Text = strategy.ArmedSide is not null
            ? $"ARMED {strategy.ArmedSide}"
            : strategy.State.StartsWith("WAIT_PULLBACK", StringComparison.Ordinal)
                ? "WAIT"
                : PullbackEvidence(strategy);
        Text("MonitorTriggerStateText").Text = strategy.State.StartsWith("TRIGGERED_", StringComparison.Ordinal)
            ? strategy.State
            : strategy.ArmedSide is not null ? "WAIT REVERSAL" : "WAIT";

        Text("MonitorTerminalText").Text =
            $"Terminal: {(bridge.TerminalConnected ? "online" : "offline")} • account {bridge.AccountTradeMode ?? "—"}";
        Text("MonitorSnapshotCountText").Text = $"Snapshots: {bridge.SnapshotsTotal}";
        Text("MonitorProfileText").Text =
            $"Profile: {strategy.ProfileName} • {config.DirectionTimeframe}→{config.PullbackTimeframe}→{config.TriggerTimeframe}";

        Text("MonitorAlertText").Text = AlertText(strategy, bridge);
        Text("MonitorAlertText").Foreground = strategy.Available && bridge.Connected
            ? Brushes.LightGreen
            : Brushes.Gold;
    }

    private void ApplyBar(
        string role,
        string timeframe,
        OverviewSnapshot overview,
        string roleControl,
        string barControl,
        string timeControl)
    {
        Text(roleControl).Text = $"{role.ToUpperInvariant()} • {timeframe}";

        if (!overview.Available || !overview.Bars.TryGetValue(timeframe, out var bar))
        {
            Text(barControl).Text = "OHLC: —";
            Text(timeControl).Text = "Closed: —";
            return;
        }

        Text(barControl).Text =
            $"O {bar.Open:0.00}  H {bar.High:0.00}  L {bar.Low:0.00}  C {bar.Close:0.00}";

        try
        {
            var closed = DateTimeOffset.FromUnixTimeSeconds(bar.Time).ToLocalTime();
            Text(timeControl).Text = $"Closed: {closed:HH:mm:ss}";
        }
        catch (ArgumentOutOfRangeException)
        {
            Text(timeControl).Text = $"Closed epoch: {bar.Time}";
        }
    }

    private void UpdateQuoteChart()
    {
        var panel = this.FindControl<StackPanel>("QuoteChartBars")
            ?? throw new InvalidOperationException("QuoteChartBars missing.");
        panel.Children.Clear();

        if (_quotes.Count == 0)
        {
            for (int i = 0; i < MaxQuotePoints; i++)
            {
                panel.Children.Add(new Border
                {
                    Width = 9,
                    Height = 18,
                    Background = new SolidColorBrush(Color.Parse("#24415D")),
                    CornerRadius = new Avalonia.CornerRadius(2),
                    Opacity = 0.28,
                    VerticalAlignment = VerticalAlignment.Bottom
                });
            }

            Text("ChartLastText").Text = "Last: —";
            Text("ChartRangeText").Text = "Range: —";
            Text("ChartMinText").Text = "Min —";
            Text("ChartMaxText").Text = "Max —";
            return;
        }

        double min = _quotes.Min();
        double max = _quotes.Max();
        double range = Math.Max(max - min, 0.000001);
        int blank = MaxQuotePoints - _quotes.Count;

        for (int i = 0; i < MaxQuotePoints; i++)
        {
            bool hasValue = i >= blank;
            double height = 18;
            double opacity = 0.22;

            if (hasValue)
            {
                double value = _quotes[i - blank];
                double normalized = (value - min) / range;
                height = 28 + normalized * 150;
                opacity = 0.48 + (0.40 * (i + 1) / MaxQuotePoints);
            }

            panel.Children.Add(new Border
            {
                Width = 9,
                Height = height,
                Background = new SolidColorBrush(Color.Parse(hasValue ? "#2D9CFF" : "#24415D")),
                CornerRadius = new Avalonia.CornerRadius(2),
                Opacity = opacity,
                VerticalAlignment = VerticalAlignment.Bottom
            });
        }

        Text("ChartLastText").Text = $"Last: {_quotes[^1]:0.00}";
        Text("ChartRangeText").Text = $"Range: {(max - min):0.00}";
        Text("ChartMinText").Text = $"Min {min:0.00}";
        Text("ChartMaxText").Text = $"Max {max:0.00}";
    }

    private TextBlock Text(string name) =>
        this.FindControl<TextBlock>(name)
        ?? throw new InvalidOperationException($"Missing MonitoringDashboard control: {name}");

    private static string PullbackEvidence(StrategySnapshot strategy)
    {
        if (strategy.PullbackBuyPassed == true)
            return "BUY PASS";
        if (strategy.PullbackSellPassed == true)
            return "SELL PASS";
        if (strategy.PullbackBuyPassed == false || strategy.PullbackSellPassed == false)
            return "NOT READY";
        return "—";
    }

    private static string AlertText(StrategySnapshot strategy, Mt5BridgeStatus bridge)
    {
        if (!bridge.Connected)
            return "Alert: MT5 Bridge chưa connected hoặc đã stale.";
        if (!bridge.TerminalConnected)
            return "Alert: MT5 terminal offline.";
        if (!strategy.Available)
            return "Alert: Strategy projection chưa available.";
        if (strategy.WarmupReasons.Count > 0)
            return $"Alert: WARMUP • {strategy.WarmupReasons[0]}";
        if (!string.IsNullOrWhiteSpace(strategy.LastDataError))
            return $"Alert: strategy data error • {strategy.LastDataError}";
        return "Alert: realtime data path đang healthy; execution vẫn locked.";
    }

    private static string Price(double? value) => value.HasValue ? value.Value.ToString("0.00") : "—";
    private static string Metric(double? value) => value.HasValue ? value.Value.ToString("0.###") : "—";

    private static IBrush StrategyBrush(string state)
    {
        if (state.StartsWith("TRIGGERED_", StringComparison.Ordinal))
            return Brushes.LightGreen;
        if (state.StartsWith("ARMED_", StringComparison.Ordinal))
            return Brushes.LightBlue;
        if (state is "STALE" or "FILTER_BLOCKED")
            return Brushes.Gold;
        return Brushes.LightGray;
    }

    private static IBrush DirectionBrush(string direction) => direction switch
    {
        "BUY" => Brushes.LightGreen,
        "SELL" => Brushes.IndianRed,
        "BOTH" => Brushes.LightBlue,
        _ => Brushes.LightGray
    };
}
