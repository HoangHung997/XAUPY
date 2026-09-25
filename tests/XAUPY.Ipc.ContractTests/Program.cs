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

Console.WriteLine($"XAUPY IPC contract self-test complete: {passed} checks passed.");
