using System.Text.Json;

namespace XAUPY.Ipc;

public sealed record OptimizerStatusSnapshot(
    string? JobId,
    string? Mode,
    string Status,
    string Phase,
    string? DatasetFileName,
    string? DatasetFingerprint,
    string? BaseProfileHash,
    string? Objective,
    int CombinationCount,
    int TotalWork,
    int CompletedWork,
    int InFlight,
    int Workers,
    int CurrentFold,
    int FoldCount,
    double ProgressPct,
    double SpeedPerMinute,
    double? EtaSeconds,
    double ElapsedSeconds,
    string? ResultRunId,
    string? OptimizerHash,
    string? Error)
{
    public static OptimizerStatusSnapshot Idle { get; } = new(
        null, null, "IDLE", "IDLE", null, null, null, null,
        0, 0, 0, 0, 0, 0, 0, 0, 0, null, 0, null, null, null);

    public bool IsActive => Status is "QUEUED" or "RUNNING" or "STOPPING";

    public static OptimizerStatusSnapshot FromHeartbeatPayload(JsonElement payload)
    {
        if (!payload.TryGetProperty("optimizer_status", out var status) ||
            status.ValueKind != JsonValueKind.Object)
        {
            return Idle;
        }
        return FromElement(status);
    }

    internal static OptimizerStatusSnapshot FromElement(JsonElement status)
    {
        return new OptimizerStatusSnapshot(
            OverviewSnapshot.ReadString(status, "job_id"),
            OverviewSnapshot.ReadString(status, "mode"),
            OverviewSnapshot.ReadString(status, "status") ?? "IDLE",
            OverviewSnapshot.ReadString(status, "phase") ?? "IDLE",
            OverviewSnapshot.ReadString(status, "dataset_file_name"),
            OverviewSnapshot.ReadString(status, "dataset_fingerprint"),
            OverviewSnapshot.ReadString(status, "base_profile_hash"),
            OverviewSnapshot.ReadString(status, "objective"),
            OverviewSnapshot.ReadInt(status, "combination_count") ?? 0,
            OverviewSnapshot.ReadInt(status, "total_work") ?? 0,
            OverviewSnapshot.ReadInt(status, "completed_work") ?? 0,
            OverviewSnapshot.ReadInt(status, "in_flight") ?? 0,
            OverviewSnapshot.ReadInt(status, "workers") ?? 0,
            OverviewSnapshot.ReadInt(status, "current_fold") ?? 0,
            OverviewSnapshot.ReadInt(status, "fold_count") ?? 0,
            OverviewSnapshot.ReadDouble(status, "progress_pct") ?? 0,
            OverviewSnapshot.ReadDouble(status, "speed_per_minute") ?? 0,
            OverviewSnapshot.ReadDouble(status, "eta_seconds"),
            OverviewSnapshot.ReadDouble(status, "elapsed_seconds") ?? 0,
            OverviewSnapshot.ReadString(status, "result_run_id"),
            OverviewSnapshot.ReadString(status, "optimizer_hash"),
            OverviewSnapshot.ReadString(status, "error"));
    }
}

public sealed record OptimizerParameterRangeSnapshot(
    string Path,
    string Kind,
    IReadOnlyList<JsonElement> Values,
    int Count);

public sealed record OptimizerCandidateSnapshot(
    int Index,
    int? Rank,
    bool Eligible,
    double? Score,
    double TradeSharpe,
    IReadOnlyDictionary<string, JsonElement> Parameters,
    BacktestMetrics Metrics,
    string? ResultHash,
    string? RejectionReason);

public sealed record WalkForwardFoldSnapshot(
    int Fold,
    string TrainFrom,
    string TrainTo,
    string TestFrom,
    string TestTo,
    int TrainDateCount,
    int TestDateCount,
    bool Rolling,
    string SelectionSource,
    bool LeakageGuardPassed,
    IReadOnlyDictionary<string, JsonElement> BestParameters,
    double? TrainScore,
    double TrainTradeSharpe,
    string? TrainResultHash,
    BacktestMetrics TrainMetrics,
    string? TestResultHash,
    double TestTradeSharpe,
    BacktestMetrics TestMetrics);

public sealed record WalkForwardAggregateSnapshot(
    double AverageNetProfit,
    double AverageNetProfitPct,
    double AverageTradeSharpe,
    double AverageWinRate,
    double AverageMaxDrawdownPct,
    double? AverageProfitFactor,
    double PositiveFoldRatio,
    double Stability);

public sealed record OptimizerResultSnapshot(
    string RunId,
    string CreatedAtUtc,
    string Mode,
    string Model,
    string Objective,
    string BacktestModel,
    string OptimizerHash,
    string BaseProfileHash,
    string DatasetFileName,
    string DatasetFingerprint,
    string Symbol,
    string FromDate,
    string ToDate,
    double InitialBalance,
    double SpreadPips,
    double CommissionPerLot,
    int MinTrades,
    int WorkersUsed,
    IReadOnlyList<OptimizerParameterRangeSnapshot> ParameterRanges,
    int CombinationCount,
    int EligibleCount,
    int IneligibleCount,
    int CandidateTotal,
    int CandidateOffset,
    int CandidateLimit,
    IReadOnlyList<OptimizerCandidateSnapshot> Candidates,
    int FoldCount,
    bool LeakageGuardPassed,
    IReadOnlyList<WalkForwardFoldSnapshot> Folds,
    WalkForwardAggregateSnapshot? Aggregate);

public sealed record OptimizerHeatmapCell(
    JsonElement X,
    JsonElement Y,
    double? Value,
    int Samples);

public sealed record OptimizerHeatmapSnapshot(
    string XPath,
    string YPath,
    string Metric,
    bool HigherIsBetter,
    IReadOnlyList<JsonElement> XValues,
    IReadOnlyList<JsonElement> YValues,
    IReadOnlyList<OptimizerHeatmapCell> Cells,
    double? MinValue,
    double? MaxValue);

public sealed record OptimizerHistoryItem(
    string RunId,
    string CreatedAtUtc,
    string Mode,
    string Model,
    string Objective,
    string OptimizerHash,
    string BaseProfileHash,
    string DatasetFileName,
    string DatasetFingerprint,
    string FromDate,
    string ToDate,
    JsonElement Summary);

public sealed record OptimizerHistoryResult(
    bool Ok,
    IReadOnlyList<OptimizerHistoryItem> Items,
    IReadOnlyList<string> Errors);

public sealed record OptimizerDeleteResult(
    bool Ok,
    bool Deleted,
    string RunId,
    IReadOnlyList<string> Errors);

public static class OptimizerApiParser
{
    public static OptimizerStatusSnapshot ParseStartOrStatus(JsonElement payload)
    {
        EnsureOk(payload);
        if (!payload.TryGetProperty("status", out var status) ||
            status.ValueKind != JsonValueKind.Object)
        {
            throw new InvalidDataException("Optimizer response is missing status.");
        }
        return OptimizerStatusSnapshot.FromElement(status);
    }

    public static OptimizerResultSnapshot ParseResult(JsonElement payload)
    {
        EnsureOk(payload);
        if (!payload.TryGetProperty("result", out var result) ||
            result.ValueKind != JsonValueKind.Object)
        {
            throw new InvalidDataException("Optimizer response is missing result.");
        }

        var ranges = ReadRanges(result);
        var candidates = ReadCandidates(result);
        var folds = ReadFolds(result);
        WalkForwardAggregateSnapshot? aggregate = null;
        if (result.TryGetProperty("aggregate", out var aggregateElement) &&
            aggregateElement.ValueKind == JsonValueKind.Object)
        {
            aggregate = new WalkForwardAggregateSnapshot(
                OverviewSnapshot.ReadDouble(aggregateElement, "average_net_profit") ?? 0,
                OverviewSnapshot.ReadDouble(aggregateElement, "average_net_profit_pct") ?? 0,
                OverviewSnapshot.ReadDouble(aggregateElement, "average_trade_sharpe") ?? 0,
                OverviewSnapshot.ReadDouble(aggregateElement, "average_win_rate") ?? 0,
                OverviewSnapshot.ReadDouble(aggregateElement, "average_max_drawdown_pct") ?? 0,
                OverviewSnapshot.ReadDouble(aggregateElement, "average_profit_factor"),
                OverviewSnapshot.ReadDouble(aggregateElement, "positive_fold_ratio") ?? 0,
                OverviewSnapshot.ReadDouble(aggregateElement, "stability") ?? 0);
        }

        string symbol = string.Empty;
        if (result.TryGetProperty("dataset_metadata", out var metadata) &&
            metadata.ValueKind == JsonValueKind.Object)
        {
            symbol = OverviewSnapshot.ReadString(metadata, "symbol") ?? string.Empty;
        }

        return new OptimizerResultSnapshot(
            OverviewSnapshot.ReadString(result, "run_id") ?? string.Empty,
            OverviewSnapshot.ReadString(result, "created_at_utc") ?? string.Empty,
            OverviewSnapshot.ReadString(result, "mode") ?? string.Empty,
            OverviewSnapshot.ReadString(result, "model") ?? string.Empty,
            OverviewSnapshot.ReadString(result, "objective") ?? string.Empty,
            OverviewSnapshot.ReadString(result, "backtest_model") ?? string.Empty,
            OverviewSnapshot.ReadString(result, "optimizer_hash") ?? string.Empty,
            OverviewSnapshot.ReadString(result, "base_profile_hash") ?? string.Empty,
            OverviewSnapshot.ReadString(result, "dataset_file_name") ?? string.Empty,
            OverviewSnapshot.ReadString(result, "dataset_fingerprint") ?? string.Empty,
            symbol,
            OverviewSnapshot.ReadString(result, "from_date") ?? string.Empty,
            OverviewSnapshot.ReadString(result, "to_date") ?? string.Empty,
            OverviewSnapshot.ReadDouble(result, "initial_balance") ?? 0,
            OverviewSnapshot.ReadDouble(result, "spread_pips") ?? 0,
            OverviewSnapshot.ReadDouble(result, "commission_per_lot") ?? 0,
            OverviewSnapshot.ReadInt(result, "min_trades") ?? 0,
            OverviewSnapshot.ReadInt(result, "workers_used") ?? 0,
            ranges,
            OverviewSnapshot.ReadInt(result, "combination_count")
                ?? OverviewSnapshot.ReadInt(result, "combination_count_per_fold")
                ?? 0,
            OverviewSnapshot.ReadInt(result, "eligible_count") ?? 0,
            OverviewSnapshot.ReadInt(result, "ineligible_count") ?? 0,
            OverviewSnapshot.ReadInt(result, "candidate_total") ?? candidates.Count,
            OverviewSnapshot.ReadInt(result, "candidate_offset") ?? 0,
            OverviewSnapshot.ReadInt(result, "candidate_limit") ?? candidates.Count,
            candidates,
            OverviewSnapshot.ReadInt(result, "fold_count") ?? folds.Count,
            OverviewSnapshot.ReadBool(result, "leakage_guard_passed"),
            folds,
            aggregate);
    }

    public static OptimizerHeatmapSnapshot ParseHeatmap(JsonElement payload)
    {
        EnsureOk(payload);
        if (!payload.TryGetProperty("heatmap", out var heatmap) ||
            heatmap.ValueKind != JsonValueKind.Object)
        {
            throw new InvalidDataException("Optimizer response is missing heatmap.");
        }

        var xValues = ReadElementArray(heatmap, "x_values");
        var yValues = ReadElementArray(heatmap, "y_values");
        var cells = new List<OptimizerHeatmapCell>();
        if (heatmap.TryGetProperty("cells", out var cellArray) &&
            cellArray.ValueKind == JsonValueKind.Array)
        {
            foreach (var item in cellArray.EnumerateArray())
            {
                if (item.ValueKind != JsonValueKind.Object ||
                    !item.TryGetProperty("x", out var x) ||
                    !item.TryGetProperty("y", out var y))
                {
                    continue;
                }
                cells.Add(new OptimizerHeatmapCell(
                    x.Clone(),
                    y.Clone(),
                    OverviewSnapshot.ReadDouble(item, "value"),
                    OverviewSnapshot.ReadInt(item, "samples") ?? 0));
            }
        }

        return new OptimizerHeatmapSnapshot(
            OverviewSnapshot.ReadString(heatmap, "x_path") ?? string.Empty,
            OverviewSnapshot.ReadString(heatmap, "y_path") ?? string.Empty,
            OverviewSnapshot.ReadString(heatmap, "metric") ?? string.Empty,
            OverviewSnapshot.ReadBool(heatmap, "higher_is_better"),
            xValues,
            yValues,
            cells,
            OverviewSnapshot.ReadDouble(heatmap, "min_value"),
            OverviewSnapshot.ReadDouble(heatmap, "max_value"));
    }

    public static OptimizerHistoryResult ParseHistory(JsonElement payload)
    {
        bool ok = OverviewSnapshot.ReadBool(payload, "ok");
        var errors = ReadErrors(payload);
        if (!ok)
            return new OptimizerHistoryResult(false, Array.Empty<OptimizerHistoryItem>(), errors);

        var items = new List<OptimizerHistoryItem>();
        if (payload.TryGetProperty("history", out var history) &&
            history.ValueKind == JsonValueKind.Array)
        {
            foreach (var item in history.EnumerateArray())
            {
                if (item.ValueKind != JsonValueKind.Object)
                    continue;
                JsonElement summary = JsonSerializer.SerializeToElement(new { });
                if (item.TryGetProperty("summary", out var summaryElement) &&
                    summaryElement.ValueKind == JsonValueKind.Object)
                {
                    summary = summaryElement.Clone();
                }
                items.Add(new OptimizerHistoryItem(
                    OverviewSnapshot.ReadString(item, "run_id") ?? string.Empty,
                    OverviewSnapshot.ReadString(item, "created_at_utc") ?? string.Empty,
                    OverviewSnapshot.ReadString(item, "mode") ?? string.Empty,
                    OverviewSnapshot.ReadString(item, "model") ?? string.Empty,
                    OverviewSnapshot.ReadString(item, "objective") ?? string.Empty,
                    OverviewSnapshot.ReadString(item, "optimizer_hash") ?? string.Empty,
                    OverviewSnapshot.ReadString(item, "base_profile_hash") ?? string.Empty,
                    OverviewSnapshot.ReadString(item, "dataset_file_name") ?? string.Empty,
                    OverviewSnapshot.ReadString(item, "dataset_fingerprint") ?? string.Empty,
                    OverviewSnapshot.ReadString(item, "from_date") ?? string.Empty,
                    OverviewSnapshot.ReadString(item, "to_date") ?? string.Empty,
                    summary));
            }
        }
        return new OptimizerHistoryResult(true, items, errors);
    }

    public static OptimizerDeleteResult ParseDelete(JsonElement payload)
    {
        return new OptimizerDeleteResult(
            OverviewSnapshot.ReadBool(payload, "ok"),
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

    private static void EnsureOk(JsonElement payload)
    {
        if (OverviewSnapshot.ReadBool(payload, "ok"))
            return;
        var errors = ReadErrors(payload);
        throw new InvalidDataException(
            errors.Count > 0
                ? string.Join(" • ", errors)
                : "Optimizer request failed.");
    }

    private static IReadOnlyList<OptimizerParameterRangeSnapshot> ReadRanges(JsonElement result)
    {
        var ranges = new List<OptimizerParameterRangeSnapshot>();
        if (!result.TryGetProperty("parameter_ranges", out var array) ||
            array.ValueKind != JsonValueKind.Array)
        {
            return ranges;
        }

        foreach (var item in array.EnumerateArray())
        {
            if (item.ValueKind != JsonValueKind.Object)
                continue;
            ranges.Add(new OptimizerParameterRangeSnapshot(
                OverviewSnapshot.ReadString(item, "path") ?? string.Empty,
                OverviewSnapshot.ReadString(item, "kind") ?? string.Empty,
                ReadElementArray(item, "values"),
                OverviewSnapshot.ReadInt(item, "count") ?? 0));
        }
        return ranges;
    }

    private static IReadOnlyList<OptimizerCandidateSnapshot> ReadCandidates(JsonElement result)
    {
        var values = new List<OptimizerCandidateSnapshot>();
        if (!result.TryGetProperty("candidates", out var array) ||
            array.ValueKind != JsonValueKind.Array)
        {
            return values;
        }

        foreach (var item in array.EnumerateArray())
        {
            if (item.ValueKind != JsonValueKind.Object ||
                !item.TryGetProperty("metrics", out var metrics) ||
                metrics.ValueKind != JsonValueKind.Object)
            {
                continue;
            }

            values.Add(new OptimizerCandidateSnapshot(
                OverviewSnapshot.ReadInt(item, "index") ?? 0,
                OverviewSnapshot.ReadInt(item, "rank"),
                OverviewSnapshot.ReadBool(item, "eligible"),
                OverviewSnapshot.ReadDouble(item, "score"),
                OverviewSnapshot.ReadDouble(item, "trade_sharpe") ?? 0,
                ReadObjectMap(item, "parameters"),
                ParseMetrics(metrics),
                OverviewSnapshot.ReadString(item, "result_hash"),
                OverviewSnapshot.ReadString(item, "rejection_reason")));
        }
        return values;
    }

    private static IReadOnlyList<WalkForwardFoldSnapshot> ReadFolds(JsonElement result)
    {
        var values = new List<WalkForwardFoldSnapshot>();
        if (!result.TryGetProperty("folds", out var array) ||
            array.ValueKind != JsonValueKind.Array)
        {
            return values;
        }

        foreach (var item in array.EnumerateArray())
        {
            if (item.ValueKind != JsonValueKind.Object ||
                !item.TryGetProperty("train_metrics", out var trainMetrics) ||
                trainMetrics.ValueKind != JsonValueKind.Object ||
                !item.TryGetProperty("test_metrics", out var testMetrics) ||
                testMetrics.ValueKind != JsonValueKind.Object)
            {
                continue;
            }

            values.Add(new WalkForwardFoldSnapshot(
                OverviewSnapshot.ReadInt(item, "fold") ?? 0,
                OverviewSnapshot.ReadString(item, "train_from") ?? string.Empty,
                OverviewSnapshot.ReadString(item, "train_to") ?? string.Empty,
                OverviewSnapshot.ReadString(item, "test_from") ?? string.Empty,
                OverviewSnapshot.ReadString(item, "test_to") ?? string.Empty,
                OverviewSnapshot.ReadInt(item, "train_date_count") ?? 0,
                OverviewSnapshot.ReadInt(item, "test_date_count") ?? 0,
                OverviewSnapshot.ReadBool(item, "rolling"),
                OverviewSnapshot.ReadString(item, "selection_source") ?? string.Empty,
                OverviewSnapshot.ReadBool(item, "leakage_guard_passed"),
                ReadObjectMap(item, "best_parameters"),
                OverviewSnapshot.ReadDouble(item, "train_score"),
                OverviewSnapshot.ReadDouble(item, "train_trade_sharpe") ?? 0,
                OverviewSnapshot.ReadString(item, "train_result_hash"),
                ParseMetrics(trainMetrics),
                OverviewSnapshot.ReadString(item, "test_result_hash"),
                OverviewSnapshot.ReadDouble(item, "test_trade_sharpe") ?? 0,
                ParseMetrics(testMetrics)));
        }
        return values;
    }

    private static IReadOnlyDictionary<string, JsonElement> ReadObjectMap(
        JsonElement parent,
        string name)
    {
        var result = new Dictionary<string, JsonElement>(StringComparer.Ordinal);
        if (!parent.TryGetProperty(name, out var element) ||
            element.ValueKind != JsonValueKind.Object)
        {
            return result;
        }
        foreach (var property in element.EnumerateObject())
            result[property.Name] = property.Value.Clone();
        return result;
    }

    private static IReadOnlyList<JsonElement> ReadElementArray(
        JsonElement parent,
        string name)
    {
        if (!parent.TryGetProperty(name, out var element) ||
            element.ValueKind != JsonValueKind.Array)
        {
            return Array.Empty<JsonElement>();
        }
        return element.EnumerateArray().Select(item => item.Clone()).ToArray();
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
}
