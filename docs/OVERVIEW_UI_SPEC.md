# XAUPY Task 005 — Overview Tab Specification

Status: implementation task
Visual source-of-truth: docs/ui-reference/Tab Tổng Quan.png

## 1. Goal

Implement the real Avalonia Overview tab without inventing trading results.

The Overview must present the same information hierarchy as the approved mockup:

- XAUUSD price;
- system status;
- account summary;
- live chart area;
- realtime strategy summary;
- recent orders;
- quick logs.

Task 005 must use real data already available from Task 003/004. Anything whose backend does not exist yet must be shown explicitly as unavailable/not running.

## 2. Real data sources

### MT5 Bridge

The Task 003 Bridge snapshot supplies:

- symbol;
- terminal state;
- demo/contest/real account mode;
- balance;
- equity;
- free margin;
- account currency;
- bid;
- ask;
- spread;
- open position count;
- pending order count;
- latest closed bars for M1/M3/M5/M15/M30/H1/H2/H4.

### Python Engine

Heartbeat supplies:

- Engine health;
- Bridge health;
- stale detection;
- Overview projection.

### Canonical config

Task 004 config_defaults_get supplies the baseline profile summary:

- profile name;
- symbol;
- Direction TF;
- Pullback TF;
- Trigger TF;
- Direction MA type/period;
- BUY/SELL enable flags;
- SL mode;
- TP mode;
- max lot;
- max trades/day.

## 3. Chart policy

The Overview chart in Task 005 is a lightweight live quote history visualization based only on actual BID values received through Bridge snapshots.

It is not:

- a fake candlestick chart;
- a historical backtest chart;
- a strategy signal chart.

If Bridge data is unavailable or stale, the chart is cleared rather than continuing to present stale values as live.

Full market/indicator charting belongs to Task 008.

## 4. Strategy card policy

Task 005 may display the configured baseline Direction/Pullback/Trigger setup.

It must also state that the Strategy Engine is not running because the actual state machine belongs to Task 007.

The UI must not generate synthetic BUY/SELL states.

## 5. Recent orders policy

Task 003 currently exposes position/order counts but not detailed ticket history.

Task 005 therefore:

- shows real position/order counts;
- displays an honest empty/detail-unavailable message;
- does not fabricate recent trades.

Detailed position/order rows belong to Task 009.

## 6. Quick log policy

Quick log contains local UI lifecycle events only:

- Engine state transitions;
- Bridge connect/disconnect transitions;
- first valid Overview market snapshot;
- user Start/Stop Engine actions;
- stale/unavailable transitions.

Structured persistent trading logs belong to Task 010.

## 7. Navigation policy

Task 005 implements only Overview.

When another navigation item is clicked:

- show its correct title and task description;
- show a clear placeholder;
- do not keep Overview content visible under another tab;
- do not fabricate unfinished functionality.

## 8. Safety

Execution remains locked.

The Overview must keep a persistent visible EXECUTION LOCKED indicator.

Task 005 must not add:

- trade_intent;
- order placement;
- order modification;
- live account enablement.

## 9. Acceptance

- UI matches the approved Overview information hierarchy.
- XAML compiles.
- Overview reads real Bridge/config data.
- stale Bridge removes live market values.
- exact Direction/Pullback/Trigger configuration is shown.
- unimplemented tabs show placeholders.
- packaged Windows build includes Desktop, Engine, config tool, profiles, MT5 Bridge and UI reference.
