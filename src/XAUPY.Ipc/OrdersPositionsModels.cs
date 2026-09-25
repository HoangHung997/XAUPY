using System.Text.Json;

namespace XAUPY.Ipc;

public sealed record PositionSnapshot(
    long Ticket,
    long Magic,
    string Symbol,
    string Side,
    double Volume,
    double PriceOpen,
    double PriceCurrent,
    double Sl,
    double Tp,
    double Profit,
    double Swap,
    long Time,
    string Comment);

public sealed record PendingOrderSnapshot(
    long Ticket,
    long Magic,
    string Symbol,
    string Type,
    double VolumeInitial,
    double VolumeCurrent,
    double PriceOpen,
    double PriceCurrent,
    double Sl,
    double Tp,
    string State,
    long TimeSetup,
    string Comment);

public sealed record DealSnapshot(
    long Ticket,
    long OrderTicket,
    long Magic,
    string Symbol,
    string Side,
    string Entry,
    double Volume,
    double PriceIn,
    double PriceOut,
    double Profit,
    double Commission,
    double Swap,
    double RealizedTotal,
    string Reason,
    long Time,
    string Comment);

public sealed record OrdersPositionsSnapshot(
    bool Available,
    string? SnapshotReceivedUtc,
    string? Symbol,
    string? AccountTradeMode,
    bool TerminalConnected,
    long? AccountLogin,
    string? AccountCurrency,
    long? Leverage,
    double? Bid,
    double? Ask,
    double? SpreadPoints,
    double? Point,
    double? Balance,
    double? Equity,
    double? MarginFree,
    double? OpenPl,
    double? RealizedPl,
    double ExposureLots,
    double? RiskUsd,
    double? RiskPct,
    bool RiskComplete,
    int PositionsCount,
    int OrdersCount,
    IReadOnlyList<PositionSnapshot> Positions,
    IReadOnlyList<PendingOrderSnapshot> Orders,
    IReadOnlyList<DealSnapshot> Deals,
    double? VolumeMin,
    double? VolumeMax,
    double? VolumeStep,
    double? TickSize,
    double? TickValue,
    int? StopsLevel,
    int? FreezeLevel,
    string GuardianReason,
    bool BrokerExecutionLocked,
    bool SimulationOnly)
{
    public static OrdersPositionsSnapshot Empty { get; } = new(
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
        null,
        null,
        null,
        null,
        null,
        0,
        null,
        null,
        false,
        0,
        0,
        Array.Empty<PositionSnapshot>(),
        Array.Empty<PendingOrderSnapshot>(),
        Array.Empty<DealSnapshot>(),
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        "TASK003_EXECUTION_LOCKED",
        true,
        true);

    public static OrdersPositionsSnapshot FromHeartbeatPayload(JsonElement heartbeatPayload)
    {
        if (!heartbeatPayload.TryGetProperty("orders_positions", out var book) ||
            book.ValueKind != JsonValueKind.Object)
        {
            return Empty;
        }

        var positions = new List<PositionSnapshot>();
        if (book.TryGetProperty("positions", out var positionsElement) &&
            positionsElement.ValueKind == JsonValueKind.Array)
        {
            foreach (var item in positionsElement.EnumerateArray())
            {
                if (TryReadPosition(item, out var position))
                    positions.Add(position);
            }
        }

        var orders = new List<PendingOrderSnapshot>();
        if (book.TryGetProperty("orders", out var ordersElement) &&
            ordersElement.ValueKind == JsonValueKind.Array)
        {
            foreach (var item in ordersElement.EnumerateArray())
            {
                if (TryReadOrder(item, out var order))
                    orders.Add(order);
            }
        }

        var deals = new List<DealSnapshot>();
        if (book.TryGetProperty("deals", out var dealsElement) &&
            dealsElement.ValueKind == JsonValueKind.Array)
        {
            foreach (var item in dealsElement.EnumerateArray())
            {
                if (TryReadDeal(item, out var deal))
                    deals.Add(deal);
            }
        }

        return new OrdersPositionsSnapshot(
            OverviewSnapshot.ReadBool(book, "available"),
            OverviewSnapshot.ReadString(book, "snapshot_received_utc"),
            OverviewSnapshot.ReadString(book, "symbol"),
            OverviewSnapshot.ReadString(book, "account_trade_mode"),
            OverviewSnapshot.ReadBool(book, "terminal_connected"),
            OverviewSnapshot.ReadLong(book, "account_login"),
            OverviewSnapshot.ReadString(book, "account_currency"),
            OverviewSnapshot.ReadLong(book, "leverage"),
            OverviewSnapshot.ReadDouble(book, "bid"),
            OverviewSnapshot.ReadDouble(book, "ask"),
            OverviewSnapshot.ReadDouble(book, "spread_points"),
            OverviewSnapshot.ReadDouble(book, "point"),
            OverviewSnapshot.ReadDouble(book, "balance"),
            OverviewSnapshot.ReadDouble(book, "equity"),
            OverviewSnapshot.ReadDouble(book, "margin_free"),
            OverviewSnapshot.ReadDouble(book, "open_pl"),
            OverviewSnapshot.ReadDouble(book, "realized_pl"),
            OverviewSnapshot.ReadDouble(book, "exposure_lots") ?? 0,
            OverviewSnapshot.ReadDouble(book, "risk_usd"),
            OverviewSnapshot.ReadDouble(book, "risk_pct"),
            OverviewSnapshot.ReadBool(book, "risk_complete"),
            OverviewSnapshot.ReadInt(book, "positions_count") ?? positions.Count,
            OverviewSnapshot.ReadInt(book, "orders_count") ?? orders.Count,
            positions,
            orders,
            deals,
            OverviewSnapshot.ReadDouble(book, "volume_min"),
            OverviewSnapshot.ReadDouble(book, "volume_max"),
            OverviewSnapshot.ReadDouble(book, "volume_step"),
            OverviewSnapshot.ReadDouble(book, "tick_size"),
            OverviewSnapshot.ReadDouble(book, "tick_value"),
            OverviewSnapshot.ReadInt(book, "stops_level"),
            OverviewSnapshot.ReadInt(book, "freeze_level"),
            OverviewSnapshot.ReadString(book, "guardian_reason") ?? "TASK003_EXECUTION_LOCKED",
            !book.TryGetProperty("broker_execution_locked", out var locked) ||
                locked.ValueKind != JsonValueKind.False,
            OverviewSnapshot.ReadBool(book, "simulation_only"));
    }

    private static bool TryReadPosition(JsonElement item, out PositionSnapshot position)
    {
        position = default!;
        if (item.ValueKind != JsonValueKind.Object)
            return false;

        var ticket = OverviewSnapshot.ReadLong(item, "ticket");
        var magic = OverviewSnapshot.ReadLong(item, "magic");
        var volume = OverviewSnapshot.ReadDouble(item, "volume");
        var priceOpen = OverviewSnapshot.ReadDouble(item, "price_open");
        var priceCurrent = OverviewSnapshot.ReadDouble(item, "price_current");
        var time = OverviewSnapshot.ReadLong(item, "time");
        if (ticket is null || magic is null || volume is null ||
            priceOpen is null || priceCurrent is null || time is null)
        {
            return false;
        }

        position = new PositionSnapshot(
            ticket.Value,
            magic.Value,
            OverviewSnapshot.ReadString(item, "symbol") ?? string.Empty,
            OverviewSnapshot.ReadString(item, "side") ?? "UNKNOWN",
            volume.Value,
            priceOpen.Value,
            priceCurrent.Value,
            OverviewSnapshot.ReadDouble(item, "sl") ?? 0,
            OverviewSnapshot.ReadDouble(item, "tp") ?? 0,
            OverviewSnapshot.ReadDouble(item, "profit") ?? 0,
            OverviewSnapshot.ReadDouble(item, "swap") ?? 0,
            time.Value,
            OverviewSnapshot.ReadString(item, "comment") ?? string.Empty);
        return true;
    }

    private static bool TryReadOrder(JsonElement item, out PendingOrderSnapshot order)
    {
        order = default!;
        if (item.ValueKind != JsonValueKind.Object)
            return false;

        var ticket = OverviewSnapshot.ReadLong(item, "ticket");
        var magic = OverviewSnapshot.ReadLong(item, "magic");
        var volumeInitial = OverviewSnapshot.ReadDouble(item, "volume_initial");
        var volumeCurrent = OverviewSnapshot.ReadDouble(item, "volume_current");
        var priceOpen = OverviewSnapshot.ReadDouble(item, "price_open");
        var timeSetup = OverviewSnapshot.ReadLong(item, "time_setup");
        if (ticket is null || magic is null || volumeInitial is null ||
            volumeCurrent is null || priceOpen is null || timeSetup is null)
        {
            return false;
        }

        order = new PendingOrderSnapshot(
            ticket.Value,
            magic.Value,
            OverviewSnapshot.ReadString(item, "symbol") ?? string.Empty,
            OverviewSnapshot.ReadString(item, "type") ?? "UNKNOWN",
            volumeInitial.Value,
            volumeCurrent.Value,
            priceOpen.Value,
            OverviewSnapshot.ReadDouble(item, "price_current") ?? 0,
            OverviewSnapshot.ReadDouble(item, "sl") ?? 0,
            OverviewSnapshot.ReadDouble(item, "tp") ?? 0,
            OverviewSnapshot.ReadString(item, "state") ?? "UNKNOWN",
            timeSetup.Value,
            OverviewSnapshot.ReadString(item, "comment") ?? string.Empty);
        return true;
    }

    private static bool TryReadDeal(JsonElement item, out DealSnapshot deal)
    {
        deal = default!;
        if (item.ValueKind != JsonValueKind.Object)
            return false;

        var ticket = OverviewSnapshot.ReadLong(item, "ticket");
        var orderTicket = OverviewSnapshot.ReadLong(item, "order_ticket");
        var magic = OverviewSnapshot.ReadLong(item, "magic");
        var volume = OverviewSnapshot.ReadDouble(item, "volume");
        var priceIn = OverviewSnapshot.ReadDouble(item, "price_in");
        var priceOut = OverviewSnapshot.ReadDouble(item, "price_out");
        var time = OverviewSnapshot.ReadLong(item, "time");
        if (ticket is null || orderTicket is null || magic is null ||
            volume is null || priceIn is null || priceOut is null || time is null)
        {
            return false;
        }

        deal = new DealSnapshot(
            ticket.Value,
            orderTicket.Value,
            magic.Value,
            OverviewSnapshot.ReadString(item, "symbol") ?? string.Empty,
            OverviewSnapshot.ReadString(item, "side") ?? "UNKNOWN",
            OverviewSnapshot.ReadString(item, "entry") ?? "UNKNOWN",
            volume.Value,
            priceIn.Value,
            priceOut.Value,
            OverviewSnapshot.ReadDouble(item, "profit") ?? 0,
            OverviewSnapshot.ReadDouble(item, "commission") ?? 0,
            OverviewSnapshot.ReadDouble(item, "swap") ?? 0,
            OverviewSnapshot.ReadDouble(item, "realized_total") ?? 0,
            OverviewSnapshot.ReadString(item, "reason") ?? "UNKNOWN",
            time.Value,
            OverviewSnapshot.ReadString(item, "comment") ?? string.Empty);
        return true;
    }
}

public sealed record ManualActionResult(
    string? IntentId,
    string? Action,
    bool Accepted,
    string Code,
    string Message,
    bool Simulated,
    bool BrokerMutated,
    bool TradingEnabled,
    bool ExecutionEnabled,
    JsonElement? Preview)
{
    public static ManualActionResult FromAck(JsonElement payload)
    {
        JsonElement? preview = null;
        if (payload.TryGetProperty("preview", out var previewElement) &&
            previewElement.ValueKind == JsonValueKind.Object)
        {
            preview = previewElement.Clone();
        }

        return new ManualActionResult(
            OverviewSnapshot.ReadString(payload, "intent_id"),
            OverviewSnapshot.ReadString(payload, "action"),
            OverviewSnapshot.ReadBool(payload, "accepted"),
            OverviewSnapshot.ReadString(payload, "code") ?? "UNKNOWN",
            OverviewSnapshot.ReadString(payload, "message") ?? string.Empty,
            OverviewSnapshot.ReadBool(payload, "simulated"),
            OverviewSnapshot.ReadBool(payload, "broker_mutated"),
            OverviewSnapshot.ReadBool(payload, "trading_enabled"),
            OverviewSnapshot.ReadBool(payload, "execution_enabled"),
            preview);
    }
}
