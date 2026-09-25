using System.Text.Json;
using XAUPY.Ipc;

var passed = 0;

void Check(bool condition, string name)
{
    if (!condition)
        throw new Exception($"FAILED: {name}");

    passed++;
    Console.WriteLine($"PASS: {name}");
}

var hello = ProtocolEnvelope.Create("hello", new { component = "contract-test" });
var parsed = ProtocolEnvelope.Parse(hello.ToJson());

Check(parsed.Type == "hello", "round-trip message type");
Check(parsed.RequestId == hello.RequestId, "round-trip request_id");
Check(parsed.SchemaVersion == ProtocolEnvelope.CurrentSchemaVersion, "schema version");

var ack = ProtocolEnvelope.CreateResponse(
    "hello_ack",
    hello.RequestId,
    new { trading_enabled = false });

Check(ack.RequestId == hello.RequestId, "response correlation");
Check(!ack.Payload.GetProperty("trading_enabled").GetBoolean(), "trading disabled");

var another = ProtocolEnvelope.Create("heartbeat");
Check(another.RequestId != hello.RequestId, "request IDs are unique");

var raw = JsonSerializer.Deserialize<Dictionary<string, object?>>(hello.ToJson())!;
raw["schema_version"] = 999;
var invalidSchema = JsonSerializer.Serialize(raw);

var schemaRejected = false;
try
{
    ProtocolEnvelope.Parse(invalidSchema);
}
catch (InvalidDataException)
{
    schemaRejected = true;
}

Check(schemaRejected, "unsupported schema rejected");

var overviewPayload = JsonSerializer.SerializeToElement(new
{
    overview = new
    {
        available = true,
        snapshot_received_utc = "2026-09-24T14:45:00+00:00",
        symbol = "XAUUSD",
        account_trade_mode = "DEMO",
        terminal_connected = true,
        bid = 4281.10,
        ask = 4281.35,
        spread_points = 25.0,
        balance = 10000.0,
        equity = 10025.0,
        margin_free = 9900.0,
        account_currency = "USD",
        positions_count = 1,
        orders_count = 0,
        bars = new
        {
            M1 = new
            {
                time = 1790240000L,
                open = 4280.0,
                high = 4282.0,
                low = 4279.0,
                close = 4281.0,
                tick_volume = 123L
            }
        }
    }
});

var overview = OverviewSnapshot.FromHeartbeatPayload(overviewPayload);
Check(overview.Available, "overview snapshot available");
Check(overview.Symbol == "XAUUSD", "overview symbol");
Check(overview.Bid == 4281.10, "overview bid");
Check(overview.Bars.ContainsKey("M1"), "overview M1 bar");
Check(overview.PositionsCount == 1, "overview position count");

var strategyPayload = JsonSerializer.SerializeToElement(new
{
    strategy = new
    {
        available = true,
        ready = true,
        state = "ARMED_BUY",
        internal_state = "ARMED_BUY",
        blocked_reason = "WAIT_TRIGGER_REVERSAL",
        profile_name = "Baseline M30-M5-M1",
        profile_hash = "abcdef0123456789",
        symbol = "XAUUSD",
        timeframes = new { direction = "M30", pullback = "M5", trigger = "M1" },
        direction = "BUY",
        armed_side = "BUY",
        signal_sequence = 3,
        last_signal = new { sequence = 3, side = "BUY", bar_time = 1790240000L, direction = "BUY" },
        warmup_reasons = Array.Empty<string>(),
        bars_seen = new { M1 = 120, M5 = 80, M30 = 60 },
        indicators = new
        {
            direction = new { timeframe = "M30", ma = 4280.5, ma_previous = 4279.7, open_reference = (double?)null },
            pullback = new { timeframe = "M5", rsi = 31.2, z = -1.4 },
            trigger = new { timeframe = "M1", rsi = 44.5, z = -0.3 },
            filters = new { adx = 27.1, atr = 3.2, open_reference = 4275.0 }
        },
        conditions = new
        {
            pullback = new { BUY = true, SELL = false },
            trigger = new { passed = false }
        },
        last_data_error = (string?)null,
        last_reset_reason = "PROFILE_CHANGED",
        last_evaluated_trigger_time = 1790240000L,
        trading_enabled = false,
        execution_enabled = false
    }
});

var strategy = StrategySnapshot.FromHeartbeatPayload(strategyPayload);
Check(strategy.Available && strategy.Ready, "strategy projection available and ready");
Check(strategy.State == "ARMED_BUY" && strategy.Direction == "BUY", "strategy state and direction");
Check(strategy.DirectionTimeframe == "M30" && strategy.PullbackTimeframe == "M5" && strategy.TriggerTimeframe == "M1", "strategy independent timeframes");
Check(strategy.DirectionIndicators.Ma == 4280.5, "strategy MA projection");
Check(strategy.PullbackIndicators.Rsi == 31.2 && strategy.TriggerIndicators.Rsi == 44.5, "strategy RSI projections");
Check(strategy.Filters.Adx == 27.1 && strategy.Filters.Atr == 3.2, "strategy filter projections");
Check(strategy.PullbackBuyPassed == true && strategy.PullbackSellPassed == false, "strategy pullback condition evidence");
Check(strategy.LastSignal?.Side == "BUY" && strategy.SignalSequence == 3, "strategy signal evidence");
Check(!strategy.TradingEnabled && !strategy.ExecutionEnabled, "strategy execution remains disabled");

var emptyStrategy = StrategySnapshot.FromHeartbeatPayload(JsonSerializer.SerializeToElement(new { }));
Check(!emptyStrategy.Available && emptyStrategy.State == "STALE", "missing strategy projects explicit stale state");

var ordersPayload = JsonSerializer.SerializeToElement(new
{
    orders_positions = new
    {
        available = true,
        snapshot_received_utc = "2026-09-25T03:40:00+00:00",
        symbol = "XAUUSD",
        account_trade_mode = "DEMO",
        terminal_connected = true,
        account_login = 12345678L,
        account_currency = "USD",
        leverage = 100L,
        bid = 4282.00,
        ask = 4282.30,
        spread_points = 30.0,
        point = 0.01,
        balance = 10000.0,
        equity = 10000.0,
        margin_free = 9950.0,
        open_pl = 19.0,
        realized_pl = 43.5,
        exposure_lots = 0.10,
        risk_usd = 50.0,
        risk_pct = 0.5,
        risk_complete = true,
        positions_count = 1,
        orders_count = 1,
        positions = new[]
        {
            new
            {
                ticket = 32874561L,
                magic = 991188L,
                symbol = "XAUUSD",
                side = "BUY",
                volume = 0.10,
                price_open = 4280.0,
                price_current = 4282.0,
                sl = 4275.0,
                tp = 4290.0,
                profit = 20.0,
                swap = -1.0,
                time = 1790240000L,
                comment = "XAUPY"
            }
        },
        orders = new[]
        {
            new
            {
                ticket = 32874570L,
                magic = 991188L,
                symbol = "XAUUSD",
                type = "BUY STOP",
                volume_initial = 0.10,
                volume_current = 0.10,
                price_open = 4285.0,
                price_current = 4282.0,
                sl = 4281.0,
                tp = 4295.0,
                state = "PLACED",
                time_setup = 1790240100L,
                comment = "XAUPY"
            }
        },
        deals = new[]
        {
            new
            {
                ticket = 32874560L,
                order_ticket = 32874559L,
                magic = 991188L,
                symbol = "XAUUSD",
                side = "SELL",
                entry = "OUT",
                volume = 0.10,
                price_in = 4278.0,
                price_out = 4282.1,
                profit = 44.0,
                commission = -0.5,
                swap = 0.0,
                realized_total = 43.5,
                reason = "TP",
                time = 1790240200L,
                comment = "XAUPY"
            }
        },
        volume_min = 0.01,
        volume_max = 100.0,
        volume_step = 0.01,
        tick_size = 0.01,
        tick_value = 1.0,
        stops_level = 10,
        freeze_level = 5,
        guardian_reason = "TASK003_EXECUTION_LOCKED",
        broker_execution_locked = true,
        simulation_only = true
    }
});

var ordersBook = OrdersPositionsSnapshot.FromHeartbeatPayload(ordersPayload);
Check(ordersBook.Available, "orders positions projection available");
Check(ordersBook.Positions.Count == 1 && ordersBook.Positions[0].Ticket == 32874561L, "position ticket projection");
Check(ordersBook.Orders.Count == 1 && ordersBook.Orders[0].Ticket == 32874570L, "pending order ticket projection");
Check(ordersBook.Deals.Count == 1 && ordersBook.Deals[0].PriceIn == 4278.0 && ordersBook.Deals[0].PriceOut == 4282.1, "deal entry exit projection");
Check(ordersBook.OpenPl == 19.0 && ordersBook.RealizedPl == 43.5, "orders KPI projection");
Check(ordersBook.Point == 0.01 && ordersBook.RiskComplete, "orders broker metadata projection");
Check(ordersBook.BrokerExecutionLocked && ordersBook.SimulationOnly, "orders projection remains simulation-only");

var simulationPayload = JsonSerializer.SerializeToElement(new
{
    intent_id = Guid.NewGuid().ToString(),
    action = "MARKET_BUY",
    accepted = true,
    code = "SIMULATED_ACCEPTED",
    message = "preview only",
    simulated = true,
    broker_mutated = false,
    trading_enabled = false,
    execution_enabled = false,
    preview = new { volume = 0.10, broker_request_sent = false }
});
var simulation = ManualActionResult.FromAck(simulationPayload);
Check(simulation.Accepted && simulation.Simulated, "manual action result parser");
Check(!simulation.BrokerMutated && !simulation.ExecutionEnabled && !simulation.TradingEnabled, "manual simulation cannot report broker execution");

var configPayload = JsonSerializer.SerializeToElement(new
{
    profile = new
    {
        profile = new { name = "Baseline M30-M5-M1" },
        strategy = new { symbol = "XAUUSD", allow_buy = true, allow_sell = true },
        timeframes = new { direction = "M30", pullback = "M5", trigger = "M1" },
        direction = new { ma_type = "EMA", ma_period = 50 },
        take_profit = new { mode = "FIXED" },
        stop_loss = new { mode = "STRUCTURE" },
        risk = new { max_lot = 0.10, max_trades_per_day = 8 }
    }
});

var config = ConfigurationSummary.FromConfigDefaultsAck(configPayload);
Check(config.ProfileName == "Baseline M30-M5-M1", "overview config profile name");
Check(config.DirectionTimeframe == "M30", "overview direction timeframe");
Check(config.PullbackTimeframe == "M5", "overview pullback timeframe");
Check(config.TriggerTimeframe == "M1", "overview trigger timeframe");
Check(config.DirectionMaType == "EMA" && config.DirectionMaPeriod == 50, "overview MA summary");

var validConfigPayload = JsonSerializer.SerializeToElement(new
{
    valid = true,
    errors = Array.Empty<string>(),
    profile = new
    {
        schema_version = 1,
        timeframes = new { direction = "H1", pullback = "M15", trigger = "M3" }
    }
});

var validConfig = ConfigurationApiParser.ParseValidation(validConfigPayload);
Check(validConfig.Valid, "config validation parser valid");
Check(validConfig.Errors.Count == 0, "config validation parser empty errors");
Check(validConfig.Profile is not null, "config validation parser profile");

var invalidConfigPayload = JsonSerializer.SerializeToElement(new
{
    applied = false,
    errors = new[] { "execution.allow_real_account: locked safety value must be False" }
});

var invalidApply = ConfigurationApiParser.ParseApply(invalidConfigPayload);
Check(!invalidApply.Applied, "config apply parser rejects invalid");
Check(invalidApply.Errors.Count == 1, "config apply parser error count");
Check(invalidApply.Profile is null, "config apply parser no profile on rejection");

var journalHeartbeatPayload = JsonSerializer.SerializeToElement(new
{
    journal_summary = new
    {
        schema_version = 1,
        date_scope = "TODAY",
        total = 12,
        level_counts = new { INFO = 7, WARN = 2, ERROR = 1, DEBUG = 2 },
        source_counts = new Dictionary<string, int>
        {
            ["MT5"] = 2,
            ["EA Bridge"] = 2,
            ["Python Engine"] = 2,
            ["Strategy"] = 2,
            ["Orders"] = 2,
            ["Alerts"] = 1
        },
        latest_sequence = 44L,
        recent_alerts = new[]
        {
            new
            {
                schema_version = 1,
                sequence = 43L,
                event_id = Guid.NewGuid().ToString(),
                timestamp_utc = "2026-09-25T04:00:00+00:00",
                level = "WARN",
                source = "Alerts",
                tag = "RISK",
                message = "Safety guard blocked MARKET_BUY",
                details = new { code = "STALE_MARKET_DATA" },
                correlation_id = Guid.NewGuid().ToString(),
                symbol = "XAUUSD",
                profile_hash = "abc123",
                bookmarked = false
            }
        },
        bookmarks = new[]
        {
            new
            {
                schema_version = 1,
                sequence = 40L,
                event_id = Guid.NewGuid().ToString(),
                timestamp_utc = "2026-09-25T03:50:00+00:00",
                level = "INFO",
                source = "Orders",
                tag = "ORDER",
                message = "Manual action simulation CLOSE_POSITION",
                details = new { accepted = true },
                correlation_id = Guid.NewGuid().ToString(),
                symbol = "XAUUSD",
                profile_hash = (string?)null,
                bookmarked = true
            }
        },
        invalid_replay_lines = 1,
        duplicate_replay_lines = 2
    }
});

var journalSummary = JournalSummarySnapshot.FromHeartbeatPayload(journalHeartbeatPayload);
Check(journalSummary.Total == 12 && journalSummary.LatestSequence == 44, "journal summary counts");
Check(journalSummary.LevelCounts["WARN"] == 2 && journalSummary.SourceCounts["Orders"] == 2, "journal summary dictionaries");
Check(journalSummary.RecentAlerts.Count == 1 && journalSummary.RecentAlerts[0].Tag == "RISK", "journal recent alert parser");
Check(journalSummary.Bookmarks.Count == 1 && journalSummary.Bookmarks[0].Bookmarked, "journal bookmark summary parser");
Check(journalSummary.InvalidReplayLines == 1 && journalSummary.DuplicateReplayLines == 2, "journal replay integrity counters");

var journalQueryPayload = JsonSerializer.SerializeToElement(new
{
    ok = true,
    journal = new
    {
        schema_version = 1,
        date_scope = "ALL",
        total_matched = 1,
        latest_sequence = 44L,
        invalid_replay_lines = 1,
        events = new[]
        {
            new
            {
                schema_version = 1,
                sequence = 44L,
                event_id = Guid.NewGuid().ToString(),
                timestamp_utc = "2026-09-25T04:01:00+00:00",
                level = "DEBUG",
                source = "Strategy",
                tag = "DECISION_TRACE",
                message = "Strategy evaluation: ARMED_BUY",
                details = new { direction = "BUY", rsi = 31.2 },
                correlation_id = Guid.NewGuid().ToString(),
                symbol = "XAUUSD",
                profile_hash = "abcdef",
                bookmarked = false
            }
        }
    },
    summary = journalHeartbeatPayload.GetProperty("journal_summary"),
    trading_enabled = false,
    execution_enabled = false
});

var journalQuery = JournalQueryResult.FromAck(journalQueryPayload);
Check(journalQuery.Ok && journalQuery.TotalMatched == 1, "journal query parser");
Check(journalQuery.Events.Count == 1 && journalQuery.Events[0].Sequence == 44, "journal event row parser");
Check(journalQuery.Events[0].Details.GetProperty("direction").GetString() == "BUY", "journal structured details parser");
Check(journalQuery.Summary.Total == 12, "journal query summary parser");

var journalBookmarkPayload = JsonSerializer.SerializeToElement(new
{
    ok = true,
    @event = new
    {
        schema_version = 1,
        sequence = 44L,
        event_id = journalQuery.Events[0].EventId,
        timestamp_utc = journalQuery.Events[0].TimestampUtc,
        level = "DEBUG",
        source = "Strategy",
        tag = "DECISION_TRACE",
        message = "Strategy evaluation: ARMED_BUY",
        details = new { direction = "BUY" },
        correlation_id = journalQuery.Events[0].CorrelationId,
        symbol = "XAUUSD",
        profile_hash = "abcdef",
        bookmarked = true
    },
    summary = journalHeartbeatPayload.GetProperty("journal_summary"),
    trading_enabled = false,
    execution_enabled = false
});

var journalBookmark = JournalBookmarkResult.FromAck(journalBookmarkPayload);
Check(journalBookmark.Ok && journalBookmark.Event?.Bookmarked == true, "journal bookmark ack parser");
Check(journalBookmark.Summary.LatestSequence == 44, "journal bookmark summary parser");

var backtestDatasetPayload = JsonSerializer.SerializeToElement(new
{
    ok = true,
    dataset = new
    {
        schema_version = 1,
        path = @"C:\data\xau.json",
        file_name = "xau.json",
        dataset_fingerprint = new string('a', 64),
        timeframe = "M1",
        bar_count = 1000,
        first_time = 1704067200L,
        last_time = 1704127140L,
        first_date = "2024-01-01",
        last_date = "2024-01-01",
        metadata = new
        {
            symbol = "XAUUSD",
            point_size = 0.01,
            tick_size = 0.01,
            tick_value = 1.0,
            volume_min = 0.01,
            volume_max = 100.0,
            volume_step = 0.01,
            timezone_offset_minutes = 0
        }
    },
    trading_enabled = false,
    execution_enabled = false
});
var backtestDataset = BacktestDatasetInfo.FromAck(backtestDatasetPayload);
Check(backtestDataset.FileName == "xau.json" && backtestDataset.BarCount == 1000, "backtest dataset parser");
Check(backtestDataset.Metadata.Symbol == "XAUUSD" && backtestDataset.Metadata.TickValue == 1.0, "backtest dataset metadata parser");

var backtestResultObject = new
{
    run_id = Guid.NewGuid().ToString(),
    created_at_utc = "2026-09-25T07:00:00+00:00",
    result_hash = new string('b', 64),
    model = "M1_OHLC_PARITY_V1",
    dataset_file_name = "xau.json",
    dataset_fingerprint = new string('a', 64),
    engine_profile_hash = new string('c', 64),
    dataset_metadata = new
    {
        symbol = "XAUUSD",
        point_size = 0.01,
        tick_size = 0.01,
        tick_value = 1.0,
        volume_min = 0.01,
        volume_max = 100.0,
        volume_step = 0.01,
        timezone_offset_minutes = 0
    },
    from_date = "2024-01-01",
    to_date = "2024-06-30",
    initial_balance = 10000.0,
    spread_pips = 20.0,
    commission_per_lot = 7.0,
    metrics = new
    {
        net_profit = 1250.0,
        net_profit_pct = 12.5,
        gross_profit = 1800.0,
        gross_loss = -550.0,
        profit_factor = 3.2727,
        total_trades = 20,
        wins = 12,
        losses = 8,
        win_rate = 60.0,
        average_trade = 62.5,
        max_drawdown_usd = 400.0,
        max_drawdown_pct = 3.6,
        initial_balance = 10000.0,
        final_balance = 11250.0,
        final_equity = 11250.0
    },
    skipped_signals = new Dictionary<string, int>
    {
        ["COOLDOWN"] = 2
    },
    equity_curve = new[]
    {
        new { time = 1704067260L, balance = 10000.0, equity = 10000.0 },
        new { time = 1704067320L, balance = 10042.0, equity = 10042.0 }
    },
    drawdown_curve = new[]
    {
        new { time = 1704067260L, drawdown_usd = 0.0, drawdown_pct = 0.0 },
        new { time = 1704067320L, drawdown_usd = 12.0, drawdown_pct = 0.12 }
    },
    trade_total = 20,
    trade_offset = 0,
    trade_limit = 1,
    trades = new[]
    {
        new
        {
            trade_id = 1,
            signal_sequence = 1,
            signal_time = 1704067200L,
            side = "BUY",
            entry_time = 1704067260L,
            exit_time = 1704069000L,
            entry_price = 2039.28,
            exit_price = 2038.56,
            volume = 0.10,
            original_sl = 2037.28,
            final_sl = 2039.38,
            tp = 2042.28,
            breakeven_applied = true,
            gross_pl = -7.2,
            commission = 0.7,
            net_pl = -7.9,
            duration_seconds = 1740L,
            exit_reason = "SL",
            mae_price_units = 0.9,
            mfe_price_units = 1.4,
            mae_usd = 9.0,
            mfe_usd = 14.0,
            profile_hash = new string('c', 64),
            dataset_fingerprint = new string('a', 64)
        }
    }
};

var backtestRunPayload = JsonSerializer.SerializeToElement(new
{
    ok = true,
    result = backtestResultObject,
    trading_enabled = false,
    execution_enabled = false
});
var backtestResult = BacktestApiParser.ParseRunOrGet(backtestRunPayload);
Check(backtestResult.Model == "M1_OHLC_PARITY_V1" && backtestResult.Metrics.TotalTrades == 20, "backtest result metrics parser");
Check(backtestResult.EquityCurve.Count == 2 && backtestResult.DrawdownCurve.Count == 2, "backtest chart parser");
Check(backtestResult.TradeTotal == 20 && backtestResult.Trades.Count == 1, "backtest trade paging parser");
Check(backtestResult.Trades[0].SignalTime < backtestResult.Trades[0].EntryTime, "backtest next-bar trade parser");
Check(backtestResult.SkippedSignals["COOLDOWN"] == 2, "backtest skipped signal parser");

var backtestHistoryPayload = JsonSerializer.SerializeToElement(new
{
    ok = true,
    history = new[]
    {
        new
        {
            run_id = backtestResult.RunId,
            created_at_utc = backtestResult.CreatedAtUtc,
            symbol = "XAUUSD",
            model = backtestResult.Model,
            from_date = backtestResult.FromDate,
            to_date = backtestResult.ToDate,
            dataset_file_name = backtestResult.DatasetFileName,
            dataset_fingerprint = backtestResult.DatasetFingerprint,
            result_hash = backtestResult.ResultHash,
            profile_hash = backtestResult.ProfileHash,
            metrics = backtestResultObject.metrics
        }
    },
    trading_enabled = false,
    execution_enabled = false
});
var backtestHistory = BacktestApiParser.ParseHistory(backtestHistoryPayload);
Check(backtestHistory.Ok && backtestHistory.Items.Count == 1, "backtest history parser");
Check(backtestHistory.Items[0].Metrics.NetProfit == 1250.0, "backtest history metrics parser");

var backtestDeletePayload = JsonSerializer.SerializeToElement(new
{
    ok = true,
    deleted = true,
    run_id = backtestResult.RunId,
    trading_enabled = false,
    execution_enabled = false
});
var backtestDelete = BacktestApiParser.ParseDelete(backtestDeletePayload);
Check(backtestDelete.Ok && backtestDelete.Deleted, "backtest delete parser");

var optimizerStatusPayload = JsonSerializer.SerializeToElement(new
{
    optimizer_status = new
    {
        job_id = Guid.NewGuid().ToString(),
        mode = "SWEEP",
        status = "RUNNING",
        phase = "PARAMETER_SWEEP",
        dataset_file_name = "history.json",
        dataset_fingerprint = new string('d', 64),
        base_profile_hash = new string('p', 64),
        objective = "ROBUST_SCORE_V1",
        combination_count = 81,
        total_work = 81,
        completed_work = 27,
        in_flight = 4,
        workers = 4,
        current_fold = 0,
        fold_count = 0,
        progress_pct = 33.333,
        speed_per_minute = 120.0,
        eta_seconds = 27.0,
        elapsed_seconds = 13.5,
        result_run_id = (string?)null,
        optimizer_hash = (string?)null,
        error = (string?)null
    }
});
var optimizerStatus = OptimizerStatusSnapshot.FromHeartbeatPayload(optimizerStatusPayload);
Check(optimizerStatus.IsActive && optimizerStatus.ProgressPct == 33.333, "optimizer heartbeat status parser");
Check(optimizerStatus.CompletedWork == 27 && optimizerStatus.Workers == 4, "optimizer progress/resource parser");

var optimizerResultPayload = JsonSerializer.SerializeToElement(new
{
    ok = true,
    result = new
    {
        run_id = Guid.NewGuid().ToString(),
        created_at_utc = "2026-09-25T08:30:00+00:00",
        mode = "SWEEP",
        model = "PARAMETER_SWEEP_V1",
        objective = "ROBUST_SCORE_V1",
        backtest_model = "M1_OHLC_PARITY_V1",
        optimizer_hash = new string('o', 64),
        base_profile_hash = new string('p', 64),
        dataset_file_name = "history.json",
        dataset_fingerprint = new string('d', 64),
        dataset_metadata = new { symbol = "XAUUSD" },
        from_date = "2024-01-01",
        to_date = "2024-06-30",
        initial_balance = 10000.0,
        spread_pips = 20.0,
        commission_per_lot = 7.0,
        min_trades = 20,
        workers_used = 4,
        parameter_ranges = new object[]
        {
            new
            {
                path = "pullback.rsi_buy_level",
                kind = "float",
                values = new object[] { 35.0, 40.0, 45.0 },
                count = 3
            },
            new
            {
                path = "pullback.rsi_sell_level",
                kind = "float",
                values = new object[] { 55.0, 60.0, 65.0 },
                count = 3
            }
        },
        combination_count = 9,
        eligible_count = 8,
        ineligible_count = 1,
        candidate_total = 9,
        candidate_offset = 0,
        candidate_limit = 10,
        candidates = new object[]
        {
            new
            {
                index = 0,
                rank = 1,
                eligible = true,
                score = 12.34,
                trade_sharpe = 1.8,
                parameters = new Dictionary<string, object>
                {
                    ["pullback.rsi_buy_level"] = 35.0,
                    ["pullback.rsi_sell_level"] = 60.0
                },
                metrics = new
                {
                    net_profit = 1234.0,
                    net_profit_pct = 12.34,
                    gross_profit = 1600.0,
                    gross_loss = -366.0,
                    profit_factor = 4.37,
                    total_trades = 42,
                    wins = 27,
                    losses = 15,
                    win_rate = 64.28,
                    average_trade = 29.38,
                    max_drawdown_usd = 320.0,
                    max_drawdown_pct = 3.1,
                    initial_balance = 10000.0,
                    final_balance = 11234.0,
                    final_equity = 11234.0
                },
                result_hash = new string('r', 64),
                rejection_reason = (string?)null
            }
        },
        fold_count = 0,
        leakage_guard_passed = false,
        folds = Array.Empty<object>()
    },
    trading_enabled = false,
    execution_enabled = false
});
var optimizerResult = OptimizerApiParser.ParseResult(optimizerResultPayload);
Check(optimizerResult.Mode == "SWEEP" && optimizerResult.Objective == "ROBUST_SCORE_V1", "optimizer result header parser");
Check(optimizerResult.ParameterRanges.Count == 2 && optimizerResult.CandidateTotal == 9, "optimizer range/candidate count parser");
Check(optimizerResult.Candidates.Count == 1 && optimizerResult.Candidates[0].Rank == 1, "optimizer top candidate parser");
Check(optimizerResult.Candidates[0].Metrics.NetProfit == 1234.0, "optimizer candidate metrics parser");

var optimizerHeatmapPayload = JsonSerializer.SerializeToElement(new
{
    ok = true,
    heatmap = new
    {
        x_path = "pullback.rsi_buy_level",
        y_path = "pullback.rsi_sell_level",
        metric = "net_profit",
        higher_is_better = true,
        x_values = new object[] { 35.0, 40.0 },
        y_values = new object[] { 55.0, 60.0 },
        cells = new object[]
        {
            new { x = 35.0, y = 55.0, value = 100.0, samples = 2 },
            new { x = 35.0, y = 60.0, value = (double?)null, samples = 0 }
        },
        min_value = 100.0,
        max_value = 100.0
    }
});
var optimizerHeatmap = OptimizerApiParser.ParseHeatmap(optimizerHeatmapPayload);
Check(optimizerHeatmap.Cells.Count == 2 && optimizerHeatmap.Cells[0].Samples == 2, "optimizer heatmap cell parser");
Check(optimizerHeatmap.Cells[1].Value is null && optimizerHeatmap.Cells[1].Samples == 0, "optimizer heatmap missing-cell parser");

var walkForwardPayload = JsonSerializer.SerializeToElement(new
{
    ok = true,
    result = new
    {
        run_id = Guid.NewGuid().ToString(),
        created_at_utc = "2026-09-25T08:31:00+00:00",
        mode = "WALK_FORWARD",
        model = "WALK_FORWARD_V1",
        objective = "ROBUST_SCORE_V1",
        backtest_model = "M1_OHLC_PARITY_V1",
        optimizer_hash = new string('w', 64),
        base_profile_hash = new string('p', 64),
        dataset_file_name = "history.json",
        dataset_fingerprint = new string('d', 64),
        dataset_metadata = new { symbol = "XAUUSD" },
        from_date = "2024-01-01",
        to_date = "2024-12-31",
        initial_balance = 10000.0,
        spread_pips = 20.0,
        commission_per_lot = 7.0,
        min_trades = 20,
        workers_used = 4,
        parameter_ranges = Array.Empty<object>(),
        combination_count_per_fold = 10,
        candidate_total = 0,
        candidate_offset = 0,
        candidate_limit = 10,
        candidates = Array.Empty<object>(),
        fold_count = 1,
        leakage_guard_passed = true,
        folds = new object[]
        {
            new
            {
                fold = 1,
                train_from = "2024-01-01",
                train_to = "2024-08-31",
                test_from = "2024-09-01",
                test_to = "2024-10-15",
                train_date_count = 170,
                test_date_count = 30,
                rolling = true,
                selection_source = "TRAIN_ONLY",
                leakage_guard_passed = true,
                best_parameters = new Dictionary<string, object>
                {
                    ["pullback.rsi_buy_level"] = 40.0
                },
                train_score = 10.5,
                train_trade_sharpe = 1.2,
                train_result_hash = new string('t', 64),
                train_metrics = new
                {
                    net_profit = 500.0,
                    net_profit_pct = 5.0,
                    gross_profit = 700.0,
                    gross_loss = -200.0,
                    profit_factor = 3.5,
                    total_trades = 30,
                    wins = 20,
                    losses = 10,
                    win_rate = 66.67,
                    average_trade = 16.67,
                    max_drawdown_usd = 150.0,
                    max_drawdown_pct = 1.5,
                    initial_balance = 10000.0,
                    final_balance = 10500.0,
                    final_equity = 10500.0
                },
                test_result_hash = new string('u', 64),
                test_trade_sharpe = 0.8,
                test_metrics = new
                {
                    net_profit = 120.0,
                    net_profit_pct = 1.2,
                    gross_profit = 180.0,
                    gross_loss = -60.0,
                    profit_factor = 3.0,
                    total_trades = 8,
                    wins = 5,
                    losses = 3,
                    win_rate = 62.5,
                    average_trade = 15.0,
                    max_drawdown_usd = 80.0,
                    max_drawdown_pct = 0.8,
                    initial_balance = 10000.0,
                    final_balance = 10120.0,
                    final_equity = 10120.0
                }
            }
        },
        aggregate = new
        {
            average_net_profit = 120.0,
            average_net_profit_pct = 1.2,
            average_trade_sharpe = 0.8,
            average_win_rate = 62.5,
            average_max_drawdown_pct = 0.8,
            average_profit_factor = 3.0,
            positive_fold_ratio = 1.0,
            stability = 0.91
        }
    }
});
var walkForward = OptimizerApiParser.ParseResult(walkForwardPayload);
Check(walkForward.Mode == "WALK_FORWARD" && walkForward.LeakageGuardPassed, "walk-forward result parser");
Check(walkForward.Folds.Count == 1 && walkForward.Folds[0].SelectionSource == "TRAIN_ONLY", "walk-forward train-only fold parser");
Check(walkForward.Aggregate is { Stability: 0.91, PositiveFoldRatio: 1.0 }, "walk-forward aggregate parser");

Console.WriteLine($"XAUPY IPC contract self-test complete: {passed} checks passed.");
