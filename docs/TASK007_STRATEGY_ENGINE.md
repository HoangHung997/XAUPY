# XAUPY Task 007 — Strategy Engine Specification

Status: DONE
Dependencies: XAUPY-002, XAUPY-004
UI delivery: outside Task 007; Strategy/Monitoring UI belongs to XAUPY-008

## 1. Goal

Implement one deterministic Python strategy authority for the configurable
Direction → Pullback → Trigger research pipeline.

Task 007 produces state and signal evidence only. It does not create, send,
modify, cancel or close broker orders.

## 2. Market-data boundary

The Task 003 MT5 Bridge publishes the latest closed bar for each supported
timeframe:

M1, M3, M5, M15, M30, H1, H2, H4

The Strategy Engine accumulates those real closed bars by timestamp.

Rules:

- a newer timestamp appends one closed bar;
- the same timestamp replaces the current last bar without advancing state;
- an older out-of-order bar is ignored;
- no historical bar is invented or back-filled by Task 007;
- strategy warm-up remains explicit until enough real bars have accumulated.

This means a fresh installation may remain in WARMUP for a meaningful period,
especially with the baseline Direction EMA50.

## 3. Direction stage

Direction uses the active canonical profile.

When direction.ma_enabled=true:

- MA type is SMA / EMA / SMMA / LWMA;
- source is the configured Direction price source;
- require_close_side=true:
  - close > MA permits BUY direction;
  - close < MA permits SELL direction;
  - equality is neutral;
- require_close_side=false:
  - rising MA permits BUY;
  - falling MA permits SELL;
  - flat MA is neutral.

When MA is disabled, both sides remain candidates until other configured
direction/filter rules reduce them.

strategy.allow_buy / strategy.allow_sell are always respected.

The optional Direction Open gate is applied only when enabled and its reference
mode is not NONE.

## 4. Pullback stage

Pullback uses the configured Pullback timeframe independently from Direction and
Trigger.

Supported Task 007 conditions:

- RSI level;
- Z-Score level;
- AND / OR combination.

BUY pullback:

- RSI <= pullback.rsi_buy_level when RSI is enabled;
- Z <= pullback.z_buy_level when Z is enabled.

SELL pullback:

- RSI >= pullback.rsi_sell_level when RSI is enabled;
- Z >= pullback.z_sell_level when Z is enabled.

A valid pullback arms only the direction side that is currently permitted.

## 5. Trigger stage

Trigger uses the configured Trigger timeframe independently.

Task 007 is closed-bar conservative because the current Bridge publishes closed
bars only. trigger.confirm_closed_bar therefore remains satisfied by the data
contract; Task 007 never fabricates an intrabar trigger.

When a pullback first arms a side, the current Trigger bar establishes the
starting extreme. A signal cannot fire on that same bar.

On each later closed Trigger bar:

- BUY RSI trigger requires RSI to rise from the lowest armed RSI by at least
  trigger.rsi_reversal_delta;
- SELL RSI trigger requires RSI to fall from the highest armed RSI by at least
  trigger.rsi_reversal_delta;
- Z reversal uses the same directional extreme/reversal rule when enabled;
- trigger.logic combines enabled RSI/Z conditions with AND or OR.

One armed setup can emit only one trigger signal until the setup resets.

## 6. Optional research filters

Task 007 implements the indicator gates that belong to the approved research
model:

- ADX min/max;
- ATR min/max;
- Open reference + buffer;
- Direction Open reference.

Disabled filters do not require warm-up data.

Reference-open modes use observed M1 closed-bar timestamps. If the exact
required reference bar has not yet been observed, the strategy remains WARMUP
rather than guessing a value.

Session/news/cost/risk/order-execution eligibility is not promoted into broker
execution by this task. Later tasks add execution and management boundaries.

## 7. State model

Externally visible strategy states include:

- STALE — Bridge/terminal is not currently usable;
- WARMUP — insufficient real closed-bar history;
- WAIT_DIRECTION;
- FILTER_BLOCKED;
- WAIT_PULLBACK_BUY / WAIT_PULLBACK_SELL / WAIT_PULLBACK_BOTH;
- AMBIGUOUS;
- ARMED_BUY / ARMED_SELL;
- TRIGGERED_BUY / TRIGGERED_SELL.

Projection also exposes:

- blocked_reason;
- profile name/hash;
- exact Direction/Pullback/Trigger timeframes;
- direction;
- armed side;
- signal sequence;
- last signal;
- warm-up reasons;
- bars seen per timeframe;
- indicator values;
- condition evidence;
- last reset/data-error information.

## 8. Reset and reconnect rules

Active-profile changes:

- validate/normalize through the existing Task 004 authority;
- reset any armed/triggered setup;
- preserve accumulated raw bar history because indicator history is market data,
  not profile state.

Bridge/market reconnection:

- resets the setup before processing resumed data;
- prevents a stale pre-disconnect arm from immediately becoming a trigger.

A stale/disconnected projection never advertises the strategy as live.

## 9. Indicator reproducibility

Task 007 owns deterministic Python implementations for:

- SMA / EMA / SMMA / LWMA;
- Wilder RSI;
- rolling population Z-Score;
- Wilder ATR;
- ADX from smoothed TR/+DM/-DM and DX.

These same pure calculations are intended to be reused by later backtest parity
work instead of creating a second strategy interpretation.

## 10. Hard execution boundary

Task 007 does not add:

- trade_intent;
- OrderSend / CTrade;
- broker retry;
- live-account permission;
- position management;
- dynamic TP/SL execution.

Every strategy projection and Engine response continues to report:

- trading_enabled=false;
- execution_enabled=false.

The Task 003 EA guardian remains execution-locked.

## 11. Acceptance

- deterministic indicator tests pass;
- deterministic BUY pipeline reaches ARMED_BUY then TRIGGERED_BUY;
- deterministic SELL pipeline is symmetric;
- no trigger can occur on the same closed bar that arms the setup;
- duplicate bar timestamps do not duplicate signals;
- all three timeframe selectors are independent;
- profile changes reset setup while preserving raw history;
- stale/disconnected market state is not presented as live;
- terminal reconnect resets setup;
- heartbeat and bridge_snapshot_ack expose strategy projection;
- all prior Python, C#, Avalonia and MT5 Bridge regressions remain green;
- packaged Windows Engine passes Task 007 strategy/safety smoke test;
- full Windows x64 artifact is produced.
