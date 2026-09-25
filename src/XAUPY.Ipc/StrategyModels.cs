using System.Text.Json;

namespace XAUPY.Ipc;

public sealed record DirectionIndicatorSnapshot(
    string? Timeframe,
    double? Ma,
    double? MaPrevious,
    double? OpenReference);

public sealed record OscillatorIndicatorSnapshot(
    string? Timeframe,
    double? Rsi,
    double? Z);

public sealed record StrategyFilterSnapshot(
    double? Adx,
    double? Atr,
    double? OpenReference);

public sealed record StrategySignalSnapshot(
    int Sequence,
    string? Side,
    long? BarTime,
    string? Direction);

public sealed record StrategySnapshot(
    bool Available,
    bool Ready,
    string State,
    string InternalState,
    string? BlockedReason,
    string ProfileName,
    string ProfileHash,
    string Symbol,
    string DirectionTimeframe,
    string PullbackTimeframe,
    string TriggerTimeframe,
    string Direction,
    string? ArmedSide,
    int SignalSequence,
    StrategySignalSnapshot? LastSignal,
    IReadOnlyList<string> WarmupReasons,
    IReadOnlyDictionary<string, int> BarsSeen,
    DirectionIndicatorSnapshot DirectionIndicators,
    OscillatorIndicatorSnapshot PullbackIndicators,
    OscillatorIndicatorSnapshot TriggerIndicators,
    StrategyFilterSnapshot Filters,
    bool? PullbackBuyPassed,
    bool? PullbackSellPassed,
    bool? TriggerPassed,
    string? LastDataError,
    string? LastResetReason,
    long? LastEvaluatedTriggerTime,
    bool TradingEnabled,
    bool ExecutionEnabled)
{
    public static StrategySnapshot Empty { get; } = new(
        false,
        false,
        "STALE",
        "WARMUP",
        "BRIDGE_STALE",
        "Baseline",
        string.Empty,
        "XAUUSD",
        "M30",
        "M5",
        "M1",
        "NEUTRAL",
        null,
        0,
        null,
        Array.Empty<string>(),
        new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase),
        new DirectionIndicatorSnapshot("M30", null, null, null),
        new OscillatorIndicatorSnapshot("M5", null, null),
        new OscillatorIndicatorSnapshot("M1", null, null),
        new StrategyFilterSnapshot(null, null, null),
        null,
        null,
        null,
        null,
        null,
        null,
        false,
        false);

    public static StrategySnapshot FromHeartbeatPayload(JsonElement heartbeatPayload)
    {
        if (!heartbeatPayload.TryGetProperty("strategy", out var strategy) ||
            strategy.ValueKind != JsonValueKind.Object)
        {
            return Empty;
        }

        string ReadString(string name, string fallback) =>
            OverviewSnapshot.ReadString(strategy, name) ?? fallback;

        var timeframes = ReadObject(strategy, "timeframes");
        string directionTf = ReadObjectString(timeframes, "direction", "M30");
        string pullbackTf = ReadObjectString(timeframes, "pullback", "M5");
        string triggerTf = ReadObjectString(timeframes, "trigger", "M1");

        var indicators = ReadObject(strategy, "indicators");
        var directionIndicators = ReadObject(indicators, "direction");
        var pullbackIndicators = ReadObject(indicators, "pullback");
        var triggerIndicators = ReadObject(indicators, "trigger");
        var filterIndicators = ReadObject(indicators, "filters");

        var barsSeen = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
        var barsSeenElement = ReadObject(strategy, "bars_seen");
        if (barsSeenElement.ValueKind == JsonValueKind.Object)
        {
            foreach (var item in barsSeenElement.EnumerateObject())
            {
                if (item.Value.ValueKind == JsonValueKind.Number &&
                    item.Value.TryGetInt32(out var count))
                {
                    barsSeen[item.Name] = count;
                }
            }
        }

        var warmup = new List<string>();
        if (strategy.TryGetProperty("warmup_reasons", out var warmupElement) &&
            warmupElement.ValueKind == JsonValueKind.Array)
        {
            foreach (var item in warmupElement.EnumerateArray())
            {
                if (item.ValueKind == JsonValueKind.String && item.GetString() is { } reason)
                    warmup.Add(reason);
            }
        }

        StrategySignalSnapshot? lastSignal = null;
        if (strategy.TryGetProperty("last_signal", out var signal) &&
            signal.ValueKind == JsonValueKind.Object)
        {
            lastSignal = new StrategySignalSnapshot(
                OverviewSnapshot.ReadInt(signal, "sequence") ?? 0,
                OverviewSnapshot.ReadString(signal, "side"),
                OverviewSnapshot.ReadLong(signal, "bar_time"),
                OverviewSnapshot.ReadString(signal, "direction"));
        }

        bool? pullbackBuy = null;
        bool? pullbackSell = null;
        bool? triggerPassed = null;
        var conditions = ReadObject(strategy, "conditions");
        var pullbackConditions = ReadObject(conditions, "pullback");
        if (pullbackConditions.ValueKind == JsonValueKind.Object)
        {
            pullbackBuy = ReadNullableBool(pullbackConditions, "BUY");
            pullbackSell = ReadNullableBool(pullbackConditions, "SELL");
        }

        var triggerConditions = ReadObject(conditions, "trigger");
        if (triggerConditions.ValueKind == JsonValueKind.Object)
            triggerPassed = ReadNullableBool(triggerConditions, "passed");

        return new StrategySnapshot(
            OverviewSnapshot.ReadBool(strategy, "available"),
            OverviewSnapshot.ReadBool(strategy, "ready"),
            ReadString("state", "STALE"),
            ReadString("internal_state", "WARMUP"),
            OverviewSnapshot.ReadString(strategy, "blocked_reason"),
            ReadString("profile_name", "Baseline"),
            ReadString("profile_hash", string.Empty),
            ReadString("symbol", "XAUUSD"),
            directionTf,
            pullbackTf,
            triggerTf,
            ReadString("direction", "NEUTRAL"),
            OverviewSnapshot.ReadString(strategy, "armed_side"),
            OverviewSnapshot.ReadInt(strategy, "signal_sequence") ?? 0,
            lastSignal,
            warmup,
            barsSeen,
            new DirectionIndicatorSnapshot(
                ReadObjectString(directionIndicators, "timeframe", directionTf),
                OverviewSnapshot.ReadDouble(directionIndicators, "ma"),
                OverviewSnapshot.ReadDouble(directionIndicators, "ma_previous"),
                OverviewSnapshot.ReadDouble(directionIndicators, "open_reference")),
            new OscillatorIndicatorSnapshot(
                ReadObjectString(pullbackIndicators, "timeframe", pullbackTf),
                OverviewSnapshot.ReadDouble(pullbackIndicators, "rsi"),
                OverviewSnapshot.ReadDouble(pullbackIndicators, "z")),
            new OscillatorIndicatorSnapshot(
                ReadObjectString(triggerIndicators, "timeframe", triggerTf),
                OverviewSnapshot.ReadDouble(triggerIndicators, "rsi"),
                OverviewSnapshot.ReadDouble(triggerIndicators, "z")),
            new StrategyFilterSnapshot(
                OverviewSnapshot.ReadDouble(filterIndicators, "adx"),
                OverviewSnapshot.ReadDouble(filterIndicators, "atr"),
                OverviewSnapshot.ReadDouble(filterIndicators, "open_reference")),
            pullbackBuy,
            pullbackSell,
            triggerPassed,
            OverviewSnapshot.ReadString(strategy, "last_data_error"),
            OverviewSnapshot.ReadString(strategy, "last_reset_reason"),
            OverviewSnapshot.ReadLong(strategy, "last_evaluated_trigger_time"),
            OverviewSnapshot.ReadBool(strategy, "trading_enabled"),
            OverviewSnapshot.ReadBool(strategy, "execution_enabled"));
    }

    private static JsonElement ReadObject(JsonElement parent, string name)
    {
        return parent.ValueKind == JsonValueKind.Object &&
               parent.TryGetProperty(name, out var value) &&
               value.ValueKind == JsonValueKind.Object
            ? value
            : default;
    }

    private static string ReadObjectString(JsonElement parent, string name, string fallback)
    {
        if (parent.ValueKind != JsonValueKind.Object)
            return fallback;

        return OverviewSnapshot.ReadString(parent, name) ?? fallback;
    }

    private static bool? ReadNullableBool(JsonElement parent, string name)
    {
        if (parent.ValueKind != JsonValueKind.Object ||
            !parent.TryGetProperty(name, out var value))
        {
            return null;
        }

        return value.ValueKind switch
        {
            JsonValueKind.True => true,
            JsonValueKind.False => false,
            _ => null
        };
    }
}
