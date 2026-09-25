using Avalonia.Controls;
using Avalonia.Media;
using XAUPY.Ipc;

namespace XAUPY.Desktop;

public partial class StrategyDashboard : UserControl
{
    public StrategyDashboard()
    {
        InitializeComponent();
        Apply(StrategySnapshot.Empty, ConfigurationSummary.Default);
    }

    public void Apply(StrategySnapshot strategy, ConfigurationSummary config)
    {
        Text("StrategyStateText").Text = strategy.State;
        Text("StrategyStateText").Foreground = StateBrush(strategy.State);
        Text("BlockedReasonText").Text = strategy.BlockedReason ?? "Không bị block";
        Text("ProfileText").Text = strategy.ProfileName;
        Text("ProfileHashText").Text = string.IsNullOrWhiteSpace(strategy.ProfileHash)
            ? "Hash: —"
            : $"Hash: {strategy.ProfileHash[..Math.Min(12, strategy.ProfileHash.Length)]}";
        Text("DirectionText").Text = strategy.Direction;
        Text("DirectionText").Foreground = DirectionBrush(strategy.Direction);
        Text("ArmedSideText").Text = $"Armed: {strategy.ArmedSide ?? "—"}";

        Text("DirectionTfText").Text = strategy.DirectionTimeframe;
        Text("PullbackTfText").Text = strategy.PullbackTimeframe;
        Text("TriggerTfText").Text = strategy.TriggerTimeframe;
        Text("DirectionRuleText").Text = $"{config.DirectionMaType}{config.DirectionMaPeriod}";
        Text("DirectionMaText").Text = $"MA: {Format(strategy.DirectionIndicators.Ma)}";
        Text("DirectionOpenText").Text = $"Open ref: {Format(strategy.DirectionIndicators.OpenReference)}";
        Text("PullbackRsiText").Text = $"RSI: {Format(strategy.PullbackIndicators.Rsi)}";
        Text("PullbackZText").Text = $"Z: {Format(strategy.PullbackIndicators.Z)}";
        Text("PullbackConditionText").Text =
            $"BUY {Flag(strategy.PullbackBuyPassed)} • SELL {Flag(strategy.PullbackSellPassed)}";
        Text("TriggerRsiText").Text = $"RSI: {Format(strategy.TriggerIndicators.Rsi)}";
        Text("TriggerZText").Text = $"Z: {Format(strategy.TriggerIndicators.Z)}";
        Text("TriggerConditionText").Text = $"Reversal: {Flag(strategy.TriggerPassed)}";

        Text("AdxText").Text = Format(strategy.Filters.Adx);
        Text("AtrText").Text = Format(strategy.Filters.Atr);
        Text("OpenFilterText").Text = Format(strategy.Filters.OpenReference);

        string bars = strategy.BarsSeen.Count == 0
            ? "—"
            : string.Join(
                "  ",
                strategy.BarsSeen
                    .OrderBy(item => TimeframeOrder(item.Key))
                    .Select(item => $"{item.Key}:{item.Value}"));
        Text("BarsSeenText").Text = $"Bars: {bars}";
        Text("WarmupText").Text = strategy.WarmupReasons.Count == 0
            ? "Warm-up: đủ dữ liệu cho các indicator đang bật."
            : $"Warm-up: {string.Join(" • ", strategy.WarmupReasons)}";
        Text("DataErrorText").Text = string.IsNullOrWhiteSpace(strategy.LastDataError)
            ? "Data error: none"
            : $"Data error: {strategy.LastDataError}";

        Text("SymbolText").Text = strategy.Symbol;
        Text("TimeframeSummaryText").Text =
            $"{strategy.DirectionTimeframe} → {strategy.PullbackTimeframe} → {strategy.TriggerTimeframe}";
        Text("ConfigSummaryText").Text =
            $"Direction {config.DirectionMaType}{config.DirectionMaPeriod} • BUY={(config.AllowBuy ? "ON" : "OFF")} • SELL={(config.AllowSell ? "ON" : "OFF")}";
        Text("ResetReasonText").Text = $"Reset: {strategy.LastResetReason ?? "—"}";

        Text("DirectionConditionText").Text = strategy.Direction;
        Text("DirectionConditionText").Foreground = DirectionBrush(strategy.Direction);
        Text("PullbackStateText").Text = strategy.ArmedSide is not null
            ? $"ARMED {strategy.ArmedSide}"
            : strategy.State.StartsWith("WAIT_PULLBACK", StringComparison.Ordinal)
                ? "WAIT"
                : PullbackEvidence(strategy);
        Text("TriggerStateText").Text = strategy.State.StartsWith("TRIGGERED_", StringComparison.Ordinal)
            ? strategy.State
            : strategy.ArmedSide is not null ? "WAIT REVERSAL" : "WAIT";
        Text("TriggerStateText").Foreground =
            strategy.State.StartsWith("TRIGGERED_", StringComparison.Ordinal)
                ? Brushes.LightGreen
                : Brushes.LightGray;
        Text("ReadyText").Text = strategy.Available && strategy.Ready ? "YES" : "NO";
        Text("ReadyText").Foreground = strategy.Available && strategy.Ready
            ? Brushes.LightGreen
            : Brushes.Gold;

        Text("SignalSequenceText").Text = $"Sequence: {strategy.SignalSequence}";
        Text("LastSignalText").Text = strategy.LastSignal is null
            ? "Chưa có signal."
            : $"{strategy.LastSignal.Side ?? "?"} • bar {strategy.LastSignal.BarTime?.ToString() ?? "—"} • direction {strategy.LastSignal.Direction ?? "—"}";
    }

    private TextBlock Text(string name) =>
        this.FindControl<TextBlock>(name)
        ?? throw new InvalidOperationException($"Missing StrategyDashboard control: {name}");

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

    private static string Flag(bool? value) => value switch
    {
        true => "PASS",
        false => "NO",
        _ => "—"
    };

    private static string Format(double? value) =>
        value.HasValue ? value.Value.ToString("0.###") : "—";

    private static IBrush StateBrush(string state)
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

    private static int TimeframeOrder(string timeframe) => timeframe switch
    {
        "M1" => 1,
        "M3" => 2,
        "M5" => 3,
        "M15" => 4,
        "M30" => 5,
        "H1" => 6,
        "H2" => 7,
        "H4" => 8,
        _ => 99
    };
}
