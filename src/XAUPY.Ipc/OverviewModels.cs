using System.Text.Json;

namespace XAUPY.Ipc;

public sealed record MarketBar(
    long Time,
    double Open,
    double High,
    double Low,
    double Close,
    long TickVolume);

public sealed record OverviewSnapshot(
    bool Available,
    string? SnapshotReceivedUtc,
    string? Symbol,
    string? AccountTradeMode,
    bool TerminalConnected,
    double? Bid,
    double? Ask,
    double? SpreadPoints,
    double? Balance,
    double? Equity,
    double? MarginFree,
    string? AccountCurrency,
    int PositionsCount,
    int OrdersCount,
    IReadOnlyDictionary<string, MarketBar> Bars)
{
    public IReadOnlyDictionary<string, IReadOnlyList<MarketBar>> BarHistory { get; init; }
        = new Dictionary<string, IReadOnlyList<MarketBar>>(StringComparer.OrdinalIgnoreCase);
    public long? TickTimeMsc { get; init; }
    public long? ServerTime { get; init; }
    public IReadOnlyDictionary<string, MarketBar> FormingBars { get; init; } = new Dictionary<string, MarketBar>();

    public static OverviewSnapshot FromMarketUpdate(JsonElement payload, OverviewSnapshot previous)
    {
        var next = FromHeartbeatPayload(payload);
        if (next.Available && previous.Available && next.Symbol == previous.Symbol &&
            next.AccountTradeMode == previous.AccountTradeMode && payload.TryGetProperty("overview", out var raw) &&
            !raw.TryGetProperty("bar_history", out _))
            next = next with { BarHistory = previous.BarHistory };
        return next;
    }
    public double? TickAgeMilliseconds => Available && ServerTime is > 0 && TickTimeMsc is > 0 &&
        (double)ServerTime.Value * 1000 >= TickTimeMsc.Value - 1000
            ? Math.Max(0, (double)ServerTime.Value * 1000 - TickTimeMsc.Value) : null;

    public static OverviewSnapshot Empty { get; } = new(
        false,
        null,
        null,
        null,
        false,
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        0,
        0,
        new Dictionary<string, MarketBar>());

    public static OverviewSnapshot FromHeartbeatPayload(JsonElement heartbeatPayload)
    {
        if (!heartbeatPayload.TryGetProperty("overview", out var overview) ||
            overview.ValueKind != JsonValueKind.Object)
        {
            return Empty;
        }

        bool available = ReadBool(overview, "available");
        var bars = new Dictionary<string, MarketBar>(StringComparer.OrdinalIgnoreCase);

        if (overview.TryGetProperty("bars", out var barsElement) &&
            barsElement.ValueKind == JsonValueKind.Object)
        {
            foreach (var item in barsElement.EnumerateObject())
            {
                if (item.Value.ValueKind != JsonValueKind.Object)
                    continue;

                if (!TryReadBar(item.Value, out var bar))
                    continue;

                bars[item.Name] = bar;
            }
        }

        var history = new Dictionary<string, IReadOnlyList<MarketBar>>(StringComparer.OrdinalIgnoreCase);
        var forming = new Dictionary<string, MarketBar>(StringComparer.OrdinalIgnoreCase);
        if (available && overview.TryGetProperty("forming_bars", out var formingElement) && formingElement.ValueKind == JsonValueKind.Object)
            foreach (var item in formingElement.EnumerateObject())
                if (item.Value.ValueKind == JsonValueKind.Object && TryReadBar(item.Value, out var current) &&
                    (!bars.TryGetValue(item.Name, out var closed) || current.Time > closed.Time))
                    forming[item.Name] = current;
        string[] supportedTimeframes = ["M1", "M3", "M5", "M15", "M30", "H1", "H2", "H4", "D1"];
        if (overview.TryGetProperty("bar_history", out var historyElement) &&
            historyElement.ValueKind == JsonValueKind.Object)
        {
            foreach (var item in historyElement.EnumerateObject())
            {
                if (!supportedTimeframes.Contains(item.Name) || item.Value.ValueKind != JsonValueKind.Array ||
                    item.Value.GetArrayLength() > 256)
                    continue;
                var series = new List<MarketBar>();
                long previousTime = 0;
                bool valid = true;
                foreach (var rawBar in item.Value.EnumerateArray())
                {
                    if (rawBar.ValueKind != JsonValueKind.Object || !TryReadBar(rawBar, out var bar) ||
                        bar.Time <= previousTime || (bars.TryGetValue(item.Name, out var latest) && bar.Time > latest.Time))
                    {
                        valid = false;
                        break;
                    }
                    previousTime = bar.Time;
                    series.Add(bar);
                }
                if (valid)
                    history[item.Name] = series.AsReadOnly();
            }
        }

        return new OverviewSnapshot(
            available,
            ReadString(overview, "snapshot_received_utc"),
            ReadString(overview, "symbol"),
            ReadString(overview, "account_trade_mode"),
            ReadBool(overview, "terminal_connected"),
            ReadDouble(overview, "bid"),
            ReadDouble(overview, "ask"),
            ReadDouble(overview, "spread_points"),
            ReadDouble(overview, "balance"),
            ReadDouble(overview, "equity"),
            ReadDouble(overview, "margin_free"),
            ReadString(overview, "account_currency"),
            ReadInt(overview, "positions_count") ?? 0,
            ReadInt(overview, "orders_count") ?? 0,
            bars)
        {
            BarHistory = history,
            FormingBars = forming,
            TickTimeMsc = ReadLong(overview, "tick_time_msc") is > 0 and <= 253402300799999
                ? ReadLong(overview, "tick_time_msc") : null,
            ServerTime = ReadLong(overview, "server_time") is > 0 and <= 253402300799
                ? ReadLong(overview, "server_time") : null
        };
    }

    internal static bool TryReadBar(JsonElement value, out MarketBar bar)
    {
        var time = ReadLong(value, "time");
        var open = ReadDouble(value, "open");
        var high = ReadDouble(value, "high");
        var low = ReadDouble(value, "low");
        var close = ReadDouble(value, "close");
        var tickVolume = ReadLong(value, "tick_volume");

        if (time is null || open is null || high is null ||
            low is null || close is null || tickVolume is null ||
            time <= 0 || tickVolume < 0 || high < low ||
            high < Math.Max(open.Value, close.Value) || low > Math.Min(open.Value, close.Value) ||
            !double.IsFinite(open.Value) || !double.IsFinite(high.Value) ||
            !double.IsFinite(low.Value) || !double.IsFinite(close.Value))
        {
            bar = default!;
            return false;
        }

        bar = new MarketBar(
            time.Value,
            open.Value,
            high.Value,
            low.Value,
            close.Value,
            tickVolume.Value);
        return true;
    }

    internal static string? ReadString(JsonElement parent, string name)
    {
        return parent.ValueKind == JsonValueKind.Object && parent.TryGetProperty(name, out var value) &&
               value.ValueKind == JsonValueKind.String
            ? value.GetString()
            : null;
    }

    internal static bool ReadBool(JsonElement parent, string name)
    {
        return parent.ValueKind == JsonValueKind.Object && parent.TryGetProperty(name, out var value) &&
               value.ValueKind == JsonValueKind.True;
    }

    internal static double? ReadDouble(JsonElement parent, string name)
    {
        if (parent.ValueKind != JsonValueKind.Object || !parent.TryGetProperty(name, out var value) ||
            value.ValueKind != JsonValueKind.Number ||
            !value.TryGetDouble(out var number) || !double.IsFinite(number))
        {
            return null;
        }

        return number;
    }

    internal static int? ReadInt(JsonElement parent, string name)
    {
        if (parent.ValueKind != JsonValueKind.Object || !parent.TryGetProperty(name, out var value) ||
            value.ValueKind != JsonValueKind.Number ||
            !value.TryGetInt32(out var number))
        {
            return null;
        }

        return number;
    }

    internal static long? ReadLong(JsonElement parent, string name)
    {
        if (parent.ValueKind != JsonValueKind.Object || !parent.TryGetProperty(name, out var value) ||
            value.ValueKind != JsonValueKind.Number ||
            !value.TryGetInt64(out var number))
        {
            return null;
        }

        return number;
    }
}

public sealed record ConfigurationSummary(
    string ProfileName,
    string Symbol,
    string DirectionTimeframe,
    string PullbackTimeframe,
    string TriggerTimeframe,
    string DirectionMaType,
    int DirectionMaPeriod,
    bool AllowBuy,
    bool AllowSell,
    string TakeProfitMode,
    string StopLossMode,
    double MaxLot,
    int MaxTradesPerDay)
{
    public bool DirectionMaEnabled { get; init; } = true;
    public string DirectionRuleSummary => DirectionMaEnabled ? $"{DirectionMaType}{DirectionMaPeriod}" : "MA tắt";
    public static ConfigurationSummary Default { get; } = new(
        "Baseline",
        "XAUUSD",
        "M30",
        "M5",
        "M1",
        "EMA",
        50,
        true,
        true,
        "FIXED",
        "STRUCTURE",
        0.10,
        8);

    public static ConfigurationSummary FromConfigDefaultsAck(JsonElement payload)
    {
        if (!payload.TryGetProperty("profile", out var profile) ||
            profile.ValueKind != JsonValueKind.Object)
        {
            return Default;
        }

        string ReadNestedString(string section, string name, string fallback)
        {
            if (profile.TryGetProperty(section, out var node) &&
                node.ValueKind == JsonValueKind.Object)
            {
                return OverviewSnapshot.ReadString(node, name) ?? fallback;
            }
            return fallback;
        }

        bool ReadNestedBool(string section, string name, bool fallback)
        {
            if (profile.TryGetProperty(section, out var node) &&
                node.ValueKind == JsonValueKind.Object &&
                node.TryGetProperty(name, out var value))
            {
                if (value.ValueKind == JsonValueKind.True)
                    return true;
                if (value.ValueKind == JsonValueKind.False)
                    return false;
            }
            return fallback;
        }

        int ReadNestedInt(string section, string name, int fallback)
        {
            if (profile.TryGetProperty(section, out var node) &&
                node.ValueKind == JsonValueKind.Object)
            {
                return OverviewSnapshot.ReadInt(node, name) ?? fallback;
            }
            return fallback;
        }

        double ReadNestedDouble(string section, string name, double fallback)
        {
            if (profile.TryGetProperty(section, out var node) &&
                node.ValueKind == JsonValueKind.Object)
            {
                return OverviewSnapshot.ReadDouble(node, name) ?? fallback;
            }
            return fallback;
        }

        string profileName = "Baseline";
        if (profile.TryGetProperty("profile", out var profileMeta) &&
            profileMeta.ValueKind == JsonValueKind.Object)
        {
            profileName = OverviewSnapshot.ReadString(profileMeta, "name") ?? profileName;
        }

        string symbol = ReadNestedString("strategy", "symbol", "XAUUSD");
        string direction = ReadNestedString("timeframes", "direction", "M30");
        string pullback = ReadNestedString("timeframes", "pullback", "M5");
        string trigger = ReadNestedString("timeframes", "trigger", "M1");

        return new ConfigurationSummary(
            profileName,
            symbol,
            direction,
            pullback,
            trigger,
            ReadNestedString("direction", "ma_type", "EMA"),
            ReadNestedInt("direction", "ma_period", 50),
            ReadNestedBool("strategy", "allow_buy", true),
            ReadNestedBool("strategy", "allow_sell", true),
            ReadNestedString("take_profit", "mode", "FIXED"),
            ReadNestedString("stop_loss", "mode", "STRUCTURE"),
            ReadNestedDouble("risk", "max_lot", 0.10),
            ReadNestedInt("risk", "max_trades_per_day", 8))
        { DirectionMaEnabled = ReadNestedBool("direction", "ma_enabled", true) };
    }
}
