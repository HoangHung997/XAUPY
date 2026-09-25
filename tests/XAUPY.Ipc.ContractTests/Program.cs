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
            ["System"] = 1,
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

Console.WriteLine($"XAUPY IPC contract self-test complete: {passed} checks passed.");
