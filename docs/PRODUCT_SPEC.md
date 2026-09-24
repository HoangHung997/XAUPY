# XAUPY — Master Product & Implementation Specification

Version: 0.1  
Status: Approved foundation specification  
Primary market: XAUUSD  
Primary OS: Windows desktop  
Implementation rule: one task at a time, CI evidence before moving forward.

## 1. Product goal

XAUPY is a desktop trading control system designed for research-first XAUUSD scalping. It separates UI, strategy intelligence and broker execution so strategy work can evolve rapidly without weakening execution safety.

The current research direction is deliberately simple: use a configurable multi-timeframe Direction → Pullback → Trigger pipeline with MA/Open/Z-Score/RSI as the core research signals, while ADX and ATR remain optional/supporting inputs. The product must make parameter research easier than code editing.

XAUPY does not claim profitability. Backtest, optimization and demo evidence must remain distinguishable from live results.

## 2. Architecture boundaries

### 2.1 XAUPY.Desktop — Avalonia/C#

Responsibilities:
- implement the approved desktop UI under docs/ui-reference/;
- display market/account/strategy/order/log/backtest/optimization state;
- edit and validate strategy profiles;
- start/pause/stop the Python engine;
- present explicit risk confirmations;
- never become the source of trading calculations.

The UI must remain usable even if Python or MT5 is offline and must clearly show disconnected/degraded states.

### 2.2 XAUPY Engine — Python

Responsibilities:
- canonical strategy state machine;
- indicator/feature calculations used by research;
- Direction/Pullback/Trigger logic;
- dynamic TP/SL decisions;
- backtest, parameter sweep and walk-forward validation;
- configuration/profile management;
- analytics, logging and experiment comparison.

Python is the strategy authority but not the final broker safety authority.

### 2.3 MT5 Bridge EA — MQL5

Responsibilities:
- publish MT5 tick/bar/account/symbol/order/deal data;
- receive versioned trade intents from Python;
- broker validation: lot step, min/max volume, margin, stop/freeze levels, trade mode;
- execute/modify/cancel/close orders;
- reconcile every request with order/deal/position state;
- enforce hard safety rules independently of Python;
- maintain server-side protective SL for every live position.

If Python heartbeat is lost, the EA must block new entries, preserve protective stops and follow an explicit fail-safe policy.

## 3. IPC and reliability

Requirements:
- localhost-only transport by default;
- versioned message schema;
- monotonic/unique request_id for every command;
- idempotent handling of duplicate trade intents;
- heartbeat and connection-state reporting;
- timestamps include MT5 server time;
- reconnect must reconcile existing positions/orders before allowing new entries;
- ambiguous execution results must never be retried blindly.

Exact transport is implemented in a dedicated task after the foundation.

## 4. Strategy model

### 4.1 Three independent timeframes

Direction TF, Pullback TF and Trigger TF are independent configurable parameters.

Each must support at least:
M1, M3, M5, M15, M30, H1, H2, H4.

The application may warn about unusual ordering but must not hard-code one hierarchy.

Initial research baseline:
- Direction: M30
- Pullback: M5
- Trigger: M1

### 4.2 Allowed research indicators

Core allowed indicator families:
- Moving Average
- reference Open
- Z-Score / standard deviation
- RSI
- ADX
- ATR

Do not add new indicators merely to increase filtering. Parameter quality is preferred over condition count.

### 4.3 Baseline research behavior

Initial profile:
- Direction: EMA-based directional context
- Pullback: RSI-based arm region
- Trigger: RSI return/delta
- Z-Score: logged/optional gate
- ADX: logged/optional filter
- ATR: volatility/risk/SL/TP support
- Open: logged/optional hard filter

Every threshold, period, timeframe, AND/OR choice, enable flag and management parameter must be configuration, not hidden hard-coded strategy behavior.

## 5. Trade management modes

Entry modes:
- Market
- Stop-confirmation (Buy Stop / Sell Stop)

Stop-loss modes:
- Fixed
- ATR
- Structure
- Dynamic structure tightening

After entry, SL may tighten but must not be automatically widened to increase tolerated loss.

Take-profit modes:
- Fixed / RR
- ZRSI dynamic extension

Dynamic extension model:
1. calculate and remember original TP;
2. near original TP, evaluate momentum;
3. weak momentum → close at/near original TP;
4. strong continuation → allow extension;
5. after price passes original TP far enough, move protective SL to original TP subject to broker rules;
6. close extended position when configured Z/RSI reversal condition occurs;
7. optional maximum extension/time and emergency server TP.

Reverse is never triggered solely because a stop is hit. Opposite entry requires a complete valid opposite setup.

## 6. Configuration

Canonical application configuration will be versioned JSON/profile data owned by Python.

Requirements:
- all strategy/risk/session/news/management parameters editable;
- import/export MT5 .set for compatibility;
- preserve unknown .set keys when round-tripping;
- profile save/load/compare;
- validation with Vietnamese descriptions;
- high-risk changes require confirmation;
- real-account permission must not be silently enabled by importing a profile.

## 7. Desktop UI

The UI reference under docs/ui-reference/ is the visual source-of-truth.

Required top-level tabs:
1. Tổng quan
2. Cấu hình
3. Chiến lược
4. Giám sát
5. Lệnh & Vị thế
6. Backtest
7. Tối ưu
8. Nhật ký
9. Công cụ
10. Cài đặt

The mockups define information hierarchy and workflow, not literal trading results.

## 8. Data and diagnostics

Persist enough evidence to reconstruct why every trade was or was not taken:
- profile/config version/hash;
- Direction/Pullback/Trigger transitions;
- Z/RSI/ADX/ATR/MA/Open values;
- entry intent and broker check result;
- requested versus actual fill;
- SL/TP modifications;
- commissions, swaps and realized P/L;
- MAE/MFE where available;
- heartbeat/reconnect/reconciliation events.

## 9. Backtest and optimization

Backtest must use the same strategy state machine as live Python logic.

Optimization requirements:
- explicit train/test split;
- walk-forward option;
- parameter sweep without changing strategy code;
- trade count, net P/L, PF, drawdown, win rate, average trade, MAE/MFE and stability;
- preserve profile and data range for reproducibility.

## 10. Safety

Hard safety remains in the Bridge EA:
- real trading disabled by default;
- max daily loss;
- max lot/exposure;
- one-request/one-intent idempotency;
- no blind retry after ambiguous broker response;
- protective server-side SL;
- stale-data / lost-heartbeat block on new entries;
- ownership by symbol + strategy identity;
- startup reconciliation before new orders.

## 11. Build and release

- GitHub Actions is mandatory evidence for each implementation task.
- Windows x64 build artifacts are required for user-facing desktop milestones.
- Builds are versioned with task/commit metadata.
- A task is not DONE merely because source was committed.

## 12. Definition of product completion

Completion requires all tasks DONE, CI green, release artifact, demo acceptance, reproducible backtests, documented fail-safe/recovery behavior and no unresolved P0/P1 defects.
