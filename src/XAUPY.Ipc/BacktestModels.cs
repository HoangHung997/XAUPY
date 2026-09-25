using System.Text.Json;

namespace XAUPY.Ipc;

public sealed record BacktestDatasetMetadata(
    string Symbol,
    double PointSize,
    double TickSize,
    double TickValue,
    double VolumeMin,
    double VolumeMax,
    double VolumeStep,
    int TimezoneOffsetMinutes);

public sealed record BacktestDatasetInfo(
    string Path,
    string FileName,
    string DatasetFingerprint,
    string Timeframe,
    int BarCount,
    long FirstTime,
    long LastTime,
    string FirstDate,
    string LastDate,
    BacktestDatasetMetadata Metadata)
{
    public static BacktestDatasetInfo FromAck(JsonElement payload)
    {
        if (!payload.TryGetProperty("ok", out var ok) ||
            ok.ValueKind != JsonValueKind.True)
        {
            throw new InvalidDataException(
                string.Join(" • ", BacktestApiParser.ReadErrors(payload)));
        }

        if (!payload.TryGetProperty("dataset", out var dataset) ||
            dataset.ValueKind != JsonValueKind.Object ||
            !dataset.TryGetProperty("metadata", out var metadata) ||
            metadata.ValueKind != JsonValueKind.Object)
        {
            throw new InvalidDataException("Backtest dataset response is incomplete.");
        }

        return new BacktestDatasetInfo(
            OverviewSnapshot.ReadString(dataset, "path") ?? string.Empty,
            OverviewSnapshot.ReadString(dataset, "file_name") ?? string.Empty,
            OverviewSnapshot.ReadString(dataset, "dataset_fingerprint") ?? string.Empty,
            OverviewSnapshot.ReadString(dataset, "timeframe") ?? "M1",
            OverviewSnapshot.ReadInt(dataset, "bar_count") ?? 0,
            OverviewSnapshot.ReadLong(dataset, "first_time") ?? 0,
            OverviewSnapshot.ReadLong(dataset, "last_time") ?? 0,
            OverviewSnapshot.ReadString(dataset, "first_date") ?? string.Empty,
            OverviewSnapshot.ReadString(dataset, "last_date") ?? string.Empty,
            new BacktestDatasetMetadata(
                OverviewSnapshot.ReadString(metadata, "symbol") ?? string.Empty,
                OverviewSnapshot.ReadDouble(metadata, "point_size") ?? 0,
                OverviewSnapshot.ReadDouble(metadata, "tick_size") ?? 0,
                OverviewSnapshot.ReadDouble(metadata, "tick_value") ?? 0,
                OverviewSnapshot.ReadDouble(metadata, "volume_min") ?? 0,
                OverviewSnapshot.ReadDouble(metadata, "volume_max") ?? 0,
                OverviewSnapshot.ReadDouble(metadata, "volume_step") ?? 0,
                OverviewSnapshot.ReadInt(metadata, "timezone_offset_minutes") ?? 0));
    }
}

public sealed record BacktestMetrics(
    double NetProfit,
    double NetProfitPct,
    double GrossProfit,
    double GrossLoss,
    double? ProfitFactor,
    int TotalTrades,
    int Wins,
    int Losses,
    double WinRate,
    double AverageTrade,
    double MaxDrawdownUsd,
    double MaxDrawdownPct,
    double InitialBalance,
    double FinalBalance,
    double FinalEquity);

public sealed record BacktestEquityPoint(
    long Time,
    double Balance,
    double Equity);

public sealed record BacktestDrawdownPoint(
    long Time,
    double DrawdownUsd,
    double DrawdownPct);

public sealed record BacktestTradeSnapshot(
    int TradeId,
    int SignalSequence,
    long SignalTime,
    string Side,
    long EntryTime,
    long ExitTime,
    double EntryPrice,
    double ExitPrice,
    double Volume,
    double OriginalSl,
    double FinalSl,
    double Tp,
    bool BreakevenApplied,
    double GrossPl,
    double Commission,
    double NetPl,
    long DurationSeconds,
    string ExitReason,
    double MaePriceUnits,
    double MfePriceUnits,
    double MaeUsd,
    double MfeUsd,
    string ProfileHash,
    string DatasetFingerprint);

public sealed record BacktestResultSnapshot(
    string RunId,
    string CreatedAtUtc,
    string ResultHash,
    string Model,
    string DatasetFileName,
    string DatasetFingerprint,
    string ProfileHash,
    string Symbol,
    string FromDate,
    string ToDate,
    double InitialBalance,
    double SpreadPips,
    double CommissionPerLot,
    BacktestMetrics Metrics,
    IReadOnlyDictionary<string, int> SkippedSignals,
    IReadOnlyList<BacktestEquityPoint> EquityCurve,
    IReadOnlyList<BacktestDrawdownPoint> DrawdownCurve,
    int TradeTotal,
    int TradeOffset,
    int TradeLimit,
    IReadOnlyList<BacktestTradeSnapshot> Trades);

public sealed record BacktestHistoryItem(
    string RunId,
    string CreatedAtUtc,
    string Symbol,
    string Model,
    string FromDate,
    string ToDate,
    string DatasetFileName,
    string DatasetFingerprint,
    string ResultHash,
    string ProfileHash,
    BacktestMetrics Metrics);

public sealed record BacktestHistoryResult(
    bool Ok,
    IReadOnlyList<BacktestHistoryItem> Items,
    IReadOnlyList<string> Errors);

public sealed record BacktestDeleteResult(
    bool Ok,
    bool Deleted,
    string RunId,
    IReadOnlyList<string> Errors);

public static class BacktestApiParser
{
    public static BacktestResultSnapshot ParseRunOrGet(JsonElement payload)
    {
        if (!OverviewSnapshot.ReadBool(payload, "ok"))
        {
            throw new InvalidDataException(
                string.Join(" • ", ReadErrors(payload)));
        }

        if (!payload.TryGetProperty("result", out var result) ||
            result.ValueKind != JsonValueKind.Object)
        {
            throw new InvalidDataException("Backtest response is missing result.");
        }

        return ParseResult(result);
    }

    public static BacktestHistoryResult ParseHistory(JsonElement payload)
    {
        bool ok = OverviewSnapshot.ReadBool(payload, "ok");
        var errors = ReadErrors(payload);
        if (!ok)
            return new BacktestHistoryResult(false, Array.Empty<BacktestHistoryItem>(), errors);

        var items = new List<BacktestHistoryItem>();
        if (payload.TryGetProperty("history", out var history) &&
            history.ValueKind == JsonValueKind.Array)
        {
            foreach (var item in history.EnumerateArray())
            {
                if (item.ValueKind != JsonValueKind.Object ||
                    !item.TryGetProperty("metrics", out var metricsElement) ||
                    metricsElement.ValueKind != JsonValueKind.Object)
                {
                    continue;
                }

                items.Add(
                    new BacktestHistoryItem(
                        OverviewSnapshot.ReadString(item, "run_id") ?? string.Empty,
                        OverviewSnapshot.ReadString(item, "created_at_utc") ?? string.Empty,
                        OverviewSnapshot.ReadString(item, "symbol") ?? string.Empty,
                        OverviewSnapshot.ReadString(item, "model") ?? string.Empty,
                        OverviewSnapshot.ReadString(item, "from_date") ?? string.Empty,
                        OverviewSnapshot.ReadString(item, "to_date") ?? string.Empty,
                        OverviewSnapshot.ReadString(item, "dataset_file_name") ?? string.Empty,
                        OverviewSnapshot.ReadString(item, "dataset_fingerprint") ?? string.Empty,
                        OverviewSnapshot.ReadString(item, "result_hash") ?? string.Empty,
                        OverviewSnapshot.ReadString(item, "profile_hash") ?? string.Empty,
                        ParseMetrics(metricsElement)));
            }
        }

        return new BacktestHistoryResult(true, items, errors);
    }

    public static BacktestDeleteResult ParseDelete(JsonElement payload)
    {
        bool ok = OverviewSnapshot.ReadBool(payload, "ok");
        return new BacktestDeleteResult(
            ok,
            OverviewSnapshot.ReadBool(payload, "deleted"),
            OverviewSnapshot.ReadString(payload, "run_id") ?? string.Empty,
            ReadErrors(payload));
    }

    public static IReadOnlyList<string> ReadErrors(JsonElement payload)
    {
        if (!payload.TryGetProperty("errors", out var errors) ||
            errors.ValueKind != JsonValueKind.Array)
        {
            return Array.Empty<string>();
        }

        return errors
            .EnumerateArray()
            .Where(item => item.ValueKind == JsonValueKind.String)
            .Select(item => item.GetString() ?? string.Empty)
            .Where(item => !string.IsNullOrWhiteSpace(item))
            .ToArray();
    }

    private static BacktestResultSnapshot ParseResult(JsonElement result)
    {
        if (!result.TryGetProperty("metrics", out var metricsElement) ||
            metricsElement.ValueKind != JsonValueKind.Object)
        {
            throw new InvalidDataException("Backtest result is missing metrics.");
        }

        string symbol = string.Empty;
        if (result.TryGetProperty("dataset_metadata", out var metadata) &&
            metadata.ValueKind == JsonValueKind.Object)
        {
            symbol = OverviewSnapshot.ReadString(metadata, "symbol") ?? string.Empty;
        }

        var skipped = new Dictionary<string, int>(StringComparer.Ordinal);
        if (result.TryGetProperty("skipped_signals", out var skippedElement) &&
            skippedElement.ValueKind == JsonValueKind.Object)
        {
            foreach (var property in skippedElement.EnumerateObject())
            {
                if (property.Value.ValueKind == JsonValueKind.Number &&
                    property.Value.TryGetInt32(out var value))
                {
                    skipped[property.Name] = value;
                }
            }
        }

        var equity = new List<BacktestEquityPoint>();
        if (result.TryGetProperty("equity_curve", out var equityElement) &&
            equityElement.ValueKind == JsonValueKind.Array)
        {
            foreach (var item in equityElement.EnumerateArray())
            {
                var time = OverviewSnapshot.ReadLong(item, "time");
                var balance = OverviewSnapshot.ReadDouble(item, "balance");
                var value = OverviewSnapshot.ReadDouble(item, "equity");
                if (time.HasValue && balance.HasValue && value.HasValue)
                    equity.Add(new BacktestEquityPoint(time.Value, balance.Value, value.Value));
            }
        }

        var drawdown = new List<BacktestDrawdownPoint>();
        if (result.TryGetProperty("drawdown_curve", out var drawdownElement) &&
            drawdownElement.ValueKind == JsonValueKind.Array)
        {
            foreach (var item in drawdownElement.EnumerateArray())
            {
                var time = OverviewSnapshot.ReadLong(item, "time");
                var usd = OverviewSnapshot.ReadDouble(item, "drawdown_usd");
                var pct = OverviewSnapshot.ReadDouble(item, "drawdown_pct");
                if (time.HasValue && usd.HasValue && pct.HasValue)
                    drawdown.Add(new BacktestDrawdownPoint(time.Value, usd.Value, pct.Value));
            }
        }

        var trades = new List<BacktestTradeSnapshot>();
        if (result.TryGetProperty("trades", out var tradesElement) &&
            tradesElement.ValueKind == JsonValueKind.Array)
        {
            foreach (var item in tradesElement.EnumerateArray())
            {
                if (TryParseTrade(item, out var trade))
                    trades.Add(trade);
            }
        }

        return new BacktestResultSnapshot(
            OverviewSnapshot.ReadString(result, "run_id") ?? string.Empty,
            OverviewSnapshot.ReadString(result, "created_at_utc") ?? string.Empty,
            OverviewSnapshot.ReadString(result, "result_hash") ?? string.Empty,
            OverviewSnapshot.ReadString(result, "model") ?? string.Empty,
            OverviewSnapshot.ReadString(result, "dataset_file_name") ?? string.Empty,
            OverviewSnapshot.ReadString(result, "dataset_fingerprint") ?? string.Empty,
            OverviewSnapshot.ReadString(result, "engine_profile_hash") ?? string.Empty,
            symbol,
            OverviewSnapshot.ReadString(result, "from_date") ?? string.Empty,
            OverviewSnapshot.ReadString(result, "to_date") ?? string.Empty,
            OverviewSnapshot.ReadDouble(result, "initial_balance") ?? 0,
            OverviewSnapshot.ReadDouble(result, "spread_pips") ?? 0,
            OverviewSnapshot.ReadDouble(result, "commission_per_lot") ?? 0,
            ParseMetrics(metricsElement),
            skipped,
            equity,
            drawdown,
            OverviewSnapshot.ReadInt(result, "trade_total") ?? trades.Count,
            OverviewSnapshot.ReadInt(result, "trade_offset") ?? 0,
            OverviewSnapshot.ReadInt(result, "trade_limit") ?? trades.Count,
            trades);
    }

    private static BacktestMetrics ParseMetrics(JsonElement metrics)
    {
        return new BacktestMetrics(
            OverviewSnapshot.ReadDouble(metrics, "net_profit") ?? 0,
            OverviewSnapshot.ReadDouble(metrics, "net_profit_pct") ?? 0,
            OverviewSnapshot.ReadDouble(metrics, "gross_profit") ?? 0,
            OverviewSnapshot.ReadDouble(metrics, "gross_loss") ?? 0,
            OverviewSnapshot.ReadDouble(metrics, "profit_factor"),
            OverviewSnapshot.ReadInt(metrics, "total_trades") ?? 0,
            OverviewSnapshot.ReadInt(metrics, "wins") ?? 0,
            OverviewSnapshot.ReadInt(metrics, "losses") ?? 0,
            OverviewSnapshot.ReadDouble(metrics, "win_rate") ?? 0,
            OverviewSnapshot.ReadDouble(metrics, "average_trade") ?? 0,
            OverviewSnapshot.ReadDouble(metrics, "max_drawdown_usd") ?? 0,
            OverviewSnapshot.ReadDouble(metrics, "max_drawdown_pct") ?? 0,
            OverviewSnapshot.ReadDouble(metrics, "initial_balance") ?? 0,
            OverviewSnapshot.ReadDouble(metrics, "final_balance") ?? 0,
            OverviewSnapshot.ReadDouble(metrics, "final_equity") ?? 0);
    }

    private static bool TryParseTrade(JsonElement item, out BacktestTradeSnapshot trade)
    {
        trade = default!;
        if (item.ValueKind != JsonValueKind.Object)
            return false;

        var tradeId = OverviewSnapshot.ReadInt(item, "trade_id");
        var signalSequence = OverviewSnapshot.ReadInt(item, "signal_sequence");
        var signalTime = OverviewSnapshot.ReadLong(item, "signal_time");
        var entryTime = OverviewSnapshot.ReadLong(item, "entry_time");
        var exitTime = OverviewSnapshot.ReadLong(item, "exit_time");
        var entryPrice = OverviewSnapshot.ReadDouble(item, "entry_price");
        var exitPrice = OverviewSnapshot.ReadDouble(item, "exit_price");
        var volume = OverviewSnapshot.ReadDouble(item, "volume");
        if (tradeId is null || signalSequence is null || signalTime is null ||
            entryTime is null || exitTime is null || entryPrice is null ||
            exitPrice is null || volume is null)
        {
            return false;
        }

        trade = new BacktestTradeSnapshot(
            tradeId.Value,
            signalSequence.Value,
            signalTime.Value,
            OverviewSnapshot.ReadString(item, "side") ?? "UNKNOWN",
            entryTime.Value,
            exitTime.Value,
            entryPrice.Value,
            exitPrice.Value,
            volume.Value,
            OverviewSnapshot.ReadDouble(item, "original_sl") ?? 0,
            OverviewSnapshot.ReadDouble(item, "final_sl") ?? 0,
            OverviewSnapshot.ReadDouble(item, "tp") ?? 0,
            OverviewSnapshot.ReadBool(item, "breakeven_applied"),
            OverviewSnapshot.ReadDouble(item, "gross_pl") ?? 0,
            OverviewSnapshot.ReadDouble(item, "commission") ?? 0,
            OverviewSnapshot.ReadDouble(item, "net_pl") ?? 0,
            OverviewSnapshot.ReadLong(item, "duration_seconds") ?? 0,
            OverviewSnapshot.ReadString(item, "exit_reason") ?? string.Empty,
            OverviewSnapshot.ReadDouble(item, "mae_price_units") ?? 0,
            OverviewSnapshot.ReadDouble(item, "mfe_price_units") ?? 0,
            OverviewSnapshot.ReadDouble(item, "mae_usd") ?? 0,
            OverviewSnapshot.ReadDouble(item, "mfe_usd") ?? 0,
            OverviewSnapshot.ReadString(item, "profile_hash") ?? string.Empty,
            OverviewSnapshot.ReadString(item, "dataset_fingerprint") ?? string.Empty);
        return true;
    }
}
