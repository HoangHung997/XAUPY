# XAUPY Task 011 — Backtest Engine Parity

Status: DONE  
Dependencies: XAUPY-007, XAUPY-010  
Visual source-of-truth: docs/ui-reference/Tab BackTest.png

## 1. Goal

Implement a deterministic historical backtest that reuses the exact
`StrategyEngine` from Task 007 for Direction → Pullback → Trigger decisions,
persists reproducible results, journals run evidence, and replaces the Backtest
placeholder with the approved Backtest workspace.

Task 011 is research/backtest only. It does not enable broker execution.

## 2. UI source-of-truth

Follow docs/ui-reference/README.md and `Tab BackTest.png`:

- keep the common live status sidebar on the left;
- Backtest configuration card at the top;
- six result KPI cards;
- Equity Curve and Drawdown panels;
- saved backtest-run history table;
- trade list table;
- compare/export/save/load controls in the same information hierarchy.

Mock profits, dates, trade counts and curve shapes in the PNG are illustrative
only and must never appear as runtime results before a real backtest completes.

### Documented model-text departure

The approved PNG shows an “Every tick” model. Task 011 does not yet have an
authoritative historical tick feed. To avoid a false accuracy claim, the real
control displays **M1 OHLC deterministic parity**. The persisted/internal model
identifier is `M1_OHLC_PARITY_V1`. This is an explicit technical departure
allowed by the UI-reference README rule 10; layout and workflow remain aligned
with the approved mock.

## 3. Historical dataset contract v1

Task 011 accepts user-selected local historical files.

Canonical JSON:

{
  "schema_version": 1,
  "symbol": "XAUUSD",
  "timeframe": "M1",
  "point_size": 0.01,
  "tick_size": 0.01,
  "tick_value": 1.0,
  "volume_min": 0.01,
  "volume_max": 100.0,
  "volume_step": 0.01,
  "timezone_offset_minutes": 0,
  "bars": [
    {"time": 1704067200, "open": 2060.1, "high": 2060.5,
     "low": 2059.9, "close": 2060.3, "tick_volume": 100}
  ]
}

CSV is also supported. Required columns:

- time
- open
- high
- low
- close

Optional bar column:

- tick_volume

Required metadata columns (same value on every populated row):

- symbol
- point_size
- tick_size
- tick_value
- volume_min
- volume_max
- volume_step
- timezone_offset_minutes

Dataset bars must be M1 closed bars with strictly increasing timestamps.
Duplicate/out-of-order rows are rejected rather than silently reordered.

The Engine computes a SHA-256 dataset fingerprint and stores it in every result.

## 4. Timeframe reconstruction and strategy parity

M1 is the only input timeframe.

The replay engine deterministically aggregates complete epoch-aligned M1 buckets
into M3, M5, M15, M30, H1, H2 and H4. Incomplete/gapped higher-timeframe
buckets are not fabricated.

At each historical close event, the backtest calls the same:

`StrategyEngine.ingest_snapshot(...)`

used by live Engine processing.

No separate indicator/state-machine implementation is permitted.

A signal is accepted only when `signal_sequence` advances. A MARKET entry is
scheduled for the next M1 bar open, never on the signal bar itself. This avoids
look-ahead entry fills.

## 5. Deterministic execution model

Task 011 supports the currently testable execution subset:

- entry.mode = MARKET;
- stop_loss.mode = FIXED or STRUCTURE;
- take_profit.mode = FIXED or RR;
- risk.sizing_mode = FIXED_LOT or RISK_PERCENT;
- management.breakeven_enabled is supported;
- partial close, trailing, SL-tighten modes other than OFF, STOP_CONFIRM,
  ATR stop and ZRSI_DYNAMIC TP are rejected as unsupported in Task 011 rather
  than silently ignored.

Task 013 owns dynamic TP/SL + stop-confirm behavior.

### Fill assumptions

Historical OHLC bars represent bid prices.

- BUY opens at next-bar open + configured spread;
- SELL opens at next-bar bid open;
- BUY exits are evaluated on bid OHLC;
- SELL exits are evaluated on ask-equivalent OHLC = bid OHLC + spread;
- spread input is in pips and uses dataset point_size;
- commission input is USD per lot round turn and is deducted once per completed
  trade.

If an M1 bar touches both the existing SL and TP and the intrabar path is
unknown, Task 011 uses the conservative deterministic rule **SL first**.

Gap fills use the executable bar-open price when the open is already beyond the
protective/target level.

Breakeven tightening is only activated for the next bar after its trigger was
observed; Task 011 never grants same-bar benefit from unknown intrabar ordering.

Open trades at the end of the requested range close at the final executable
M1 close with reason END_OF_DATA.

## 6. Risk/session rules

The backtest applies, deterministically:

- fixed lot / risk-percent sizing;
- broker volume min/max/step from dataset metadata;
- active max_lot;
- max_open_positions;
- max_trades_per_day;
- cooldown_minutes;
- max_consecutive_losses;
- max_daily_loss_pct;
- optional daily target stop;
- configured weekday/session windows.

Dataset `timezone_offset_minutes` defines the broker/local clock used for
session/day boundaries when sessions.timezone= BROKER. UTC uses offset 0.

news.enabled=true is rejected in Task 011 because no historical news calendar is
available; it is never silently ignored.

## 7. Result metrics

Every successful run returns real calculated values:

- net_profit;
- net_profit_pct;
- total trades;
- wins/losses;
- win_rate;
- gross_profit;
- gross_loss;
- profit_factor;
- average_trade;
- max_drawdown_usd;
- max_drawdown_pct;
- final_balance/final_equity;
- skipped signals and reasons;
- equity/balance curve;
- drawdown curve;
- full completed trade list.

Each trade preserves:

- signal sequence/time/side;
- entry/exit time and price;
- volume;
- original/current SL and TP;
- gross P/L, commission, net P/L;
- duration;
- exit reason;
- profile hash and dataset fingerprint;
- MAE/MFE derived from post-entry M1 OHLC.

## 8. Persistence/reproducibility

Completed results are automatically stored under a backtest state directory
alongside Task 010 state storage.

Each result preserves:

- run id and run timestamp;
- active normalized profile + profile hash;
- dataset path basename + SHA-256;
- exact date range;
- initial balance;
- spread/commission assumptions;
- engine/model version;
- metrics, curves and trades;
- deterministic result_hash excluding run id/timestamp.

Running the same dataset/profile/range/assumptions twice must produce the same
`result_hash`, trades and curves.

Persisted run history can be queried, opened and deleted.

## 9. IPC

Task 011 adds:

- backtest_dataset_inspect → backtest_dataset_inspect_ack
- backtest_run → backtest_run_ack
- backtest_history_query → backtest_history_query_ack
- backtest_result_get → backtest_result_get_ack
- backtest_result_delete → backtest_result_delete_ack

All responses keep:

- trading_enabled=false
- execution_enabled=false

Backtest never uses `trade_intent` and never mutates MT5.

## 10. Journal evidence

Task 010 Journal records:

- BACKTEST_DATASET inspection;
- BACKTEST_RUN started/completed/rejected;
- dataset fingerprint;
- profile hash;
- range/assumptions;
- deterministic result hash and summary metrics.

No mock result is written.

## 11. Acceptance

- dataset JSON/CSV parser + metadata validation tests;
- M1 → multi-timeframe aggregation tests, including gap rejection;
- same StrategyEngine parity test against direct live-style replay;
- no-lookahead next-bar entry test;
- conservative same-bar SL/TP ambiguity test;
- sizing/risk/session/cooldown tests;
- structure-SL and FIXED/RR TP tests;
- MAE/MFE tests;
- deterministic repeated-run hash equality;
- persisted result history/get/delete tests;
- packaged restart history replay test;
- approved Backtest UI hierarchy source test;
- C# Backtest parser/IPC contract tests;
- all Task 001–010 regressions pass;
- Avalonia Release 0 warnings / 0 errors;
- packaged Task 011 deterministic backtest smoke passes;
- packaged Task 010/009/007/config smokes pass;
- MetaEditor bridge compile 0 errors / 0 warnings;
- complete Windows x64 artifact produced and independently inspected.
