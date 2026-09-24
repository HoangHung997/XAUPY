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

Console.WriteLine($"XAUPY IPC contract self-test complete: {passed} checks passed.");
