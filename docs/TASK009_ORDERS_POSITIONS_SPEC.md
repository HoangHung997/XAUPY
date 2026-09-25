# XAUPY Task 009 — Orders & Positions + Guarded Manual Actions

Status: DONE
Dependencies: XAUPY-003, XAUPY-005
Visual source-of-truth: docs/ui-reference/Tab Lệnh & Vị thế.png

## 1. Goal

Implement the approved Orders & Positions workspace using real ticket-level MT5
state while keeping broker mutation locked.

Task 009 adds the execution-control contract and deterministic guarded simulator
needed to test manual actions safely before any future broker executor is enabled.

## 2. Visual layout

The Avalonia tab follows the approved reference zoning:

- top KPI cards: open P/L, realized P/L, exposure, current risk, pending count;
- open positions table with per-ticket actions;
- active pending orders table with modify/cancel actions;
- guarded bulk-action strip;
- recent realized deals table;
- right XAUUSD quote/chart panel;
- right manual Market order panel with lot, SL, TP, quick-lot buttons, BUY/SELL,
  confirmation state and spread.

Mock prices/P&L/tickets from the PNG are not copied into runtime data.

## 3. MT5 read-only order book

The MQL5 Bridge snapshot is extended with strategy-owned data filtered by symbol
and magic:

- positions: ticket, side, volume, open/current price, SL, TP, profit, swap,
  open time and comment;
- pending orders: ticket, type, initial/current volume, order price, SL, TP,
  state, setup time and comment;
- recent realized deals: deal/order ticket, side, volume, entry/exit price,
  profit, commission, swap, realized total, reason, time and comment;
- account leverage.

The Task 003 guardian remains hard locked and the EA still contains no OrderSend,
OrderSendAsync or CTrade execution call.

## 4. Orders projection

Python exposes an orders_positions projection in heartbeat derived only from the
latest fresh Bridge snapshot.

It includes:

- availability/account/symbol/quote fields;
- real positions, pending orders and recent deals;
- open P/L;
- realized P/L represented by real deal totals;
- open exposure lots;
- estimated current risk from server SL + symbol tick size/value when complete;
- explicit risk completeness flag;
- counts and snapshot timestamp.

If Bridge data is stale/unavailable, ticket rows and live values are cleared.

## 5. Guarded manual action simulator

Desktop sends manual_action_simulate with a unique intent_id.

Supported actions:

- MARKET_BUY
- MARKET_SELL
- CLOSE_POSITION
- PARTIAL_CLOSE
- MOVE_SL_BE
- START_TRAILING
- MODIFY_PENDING
- CANCEL_PENDING
- CLOSE_ALL
- CLOSE_PROFIT
- CLOSE_LOSS
- CANCEL_ALL_PENDING

Task 009 is simulation-only. An accepted result means the intent passed the
current safety checks and a deterministic execution preview was produced. It
does not mutate the broker account.

## 6. Guards

Before a simulation can be accepted:

- Bridge snapshot must be fresh and terminal connected;
- account must be DEMO;
- active profile must still lock demo_only=true, allow_real_account=false and
  max_retry_count=0;
- symbol must match active profile;
- target position/order must exist in the latest strategy-owned snapshot;
- volume must respect symbol min/max/step and active max lot;
- new position count must respect active max_open_positions;
- destructive actions require explicit confirmation;
- server-side SL requirement applies to new-entry previews;
- MOVE_SL_BE must never widen an existing SL;
- stale market data blocks the action;
- duplicate intent_id returns the same result;
- reusing an intent_id with different content is rejected.

No automatic retry exists.

## 7. Desktop behavior

- The UI must display a persistent SIMULATION ONLY / BROKER EXECUTION LOCKED
  indicator.
- Confirmation is required before destructive/broker-like actions.
- Action result text must clearly say SIMULATED and must never claim an MT5
  trade was executed.
- Per-row actions only target tickets present in the latest fresh snapshot.
- Unavailable backend values show — / explicit unavailable state, never mock data.

## 8. IPC

Heartbeat adds orders_positions.

Desktop-to-Engine adds:

manual_action_simulate → manual_action_simulate_ack

The response keeps:

- trading_enabled=false
- execution_enabled=false
- broker_mutated=false

trade_intent remains unsupported.

## 9. Acceptance

- approved Orders & Positions reference is preserved and packaged;
- MT5 snapshot exposes real owned positions/orders/deals;
- Python rejects malformed/unowned ticket data;
- stale snapshot clears orders projection;
- KPI calculations are deterministic;
- manual simulator guards demo-only, volume, max positions, confirmation,
  ownership and never-widen-SL;
- idempotent duplicate intent test passes;
- intent-id conflict test passes;
- trade_intent remains unsupported;
- MQL5 source still contains no OrderSend/OrderSendAsync/CTrade;
- Desktop Orders & Positions layout matches the approved reference zones;
- manual controls are wired to simulator, never to broker execution;
- all prior Python regressions pass;
- C# IPC/order-book contract tests pass;
- Avalonia Release build passes with 0 warnings / 0 errors;
- packaged Engine execution-simulation smoke passes;
- packaged config regression smoke passes;
- MT5 Bridge compiles 0 errors / 0 warnings;
- complete Windows x64 Task 009 artifact is produced and independently inspected.
