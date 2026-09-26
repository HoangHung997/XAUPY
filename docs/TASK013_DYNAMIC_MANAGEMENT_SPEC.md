# XAUPY Task 013 — Dynamic TP/SL + Stop-Confirm Entry

Status: ACTIVE  
Task: XAUPY-013  
Dependencies: XAUPY-003, XAUPY-007, XAUPY-011

## 1. Goal

Extend the deterministic research/execution-simulation model so the canonical
configuration can exercise the trade-management modes that Task 011 deliberately
rejected:

- `entry.mode=STOP_CONFIRM`;
- `stop_loss.mode=ATR`;
- `take_profit.mode=ZRSI_DYNAMIC`;
- partial close;
- trailing;
- post-entry SL tightening.

Task 013 does **not** unlock MT5 broker mutation. The MQL5 guardian remains
execution-locked, and all Task 009 demo/idempotency/server-SL/never-widen
boundaries remain in force.

## 2. Deterministic historical broker model

Task 013 continues to use Task 011 `M1_OHLC_PARITY_V1` bid-OHLC assumptions.
No tick path is invented.

When an intrabar path is ambiguous, the model chooses the conservative outcome:
an already-active protective SL is resolved before a target/management benefit.
Any management change discovered from a bar becomes effective only on the next
M1 bar.

## 3. Stop-confirm entry

A strategy signal creates a pending stop-confirm state instead of an immediate
position.

- BUY STOP trigger = signal Trigger-TF high + configured pending buffer + spread.
- SELL STOP trigger = signal Trigger-TF low - configured pending buffer.
- BUY fills against ask-equivalent OHLC; SELL fills against bid OHLC.
- A gap through the trigger fills at executable M1 open; otherwise fill is at
  the trigger price.
- Expiration uses `entry.pending_expiration_minutes` from the signal close.
- `entry.max_signal_age_bars` remains an independent stale-signal guard.
- `entry.cancel_on_opposite_setup` cancels an opposite pending state when a
  newer opposite signal arrives.
- `entry.cancel_on_direction_change` cancels a pending state when the live
  StrategyEngine direction no longer permits that side.
- Risk/session/daily/max-position guards are checked again at fill time.

Pending stop-confirm states are deterministic research state only; they are not
MT5 orders in Task 013.

## 4. Initial ATR stop

`stop_loss.mode=ATR` uses the configured stop ATR timeframe, Wilder ATR period
and multiplier from already-closed StrategyEngine history.

The resulting distance is clamped by the canonical SL min/max limits. Insufficient
closed history causes an explicit warm-up skip rather than a fabricated value.

## 5. ZRSI dynamic take-profit

For `take_profit.mode=ZRSI_DYNAMIC`:

1. original TP distance is `take_profit.fixed_price_units`;
2. the original TP is always recorded;
3. once price reaches the configured near-TP zone, continuation strength is
   evaluated from already-closed Trigger-TF Z-Score and RSI;
4. enabled Z/RSI continuation conditions use `extend_logic=BOTH|EITHER`;
5. weak/unavailable required continuation evidence keeps the original TP;
6. strong continuation arms extension;
7. after extension, the active hard target is capped by
   `max_extension_price_units`; if emergency server TP is enabled, the nearer
   configured emergency distance is also respected but never moves inside the
   original TP;
8. if `lock_sl_at_original_tp` is enabled, a favorable move beyond original TP
   plus lock buffer may tighten SL to original TP plus/minus the configured
   buffer; it never widens SL;
9. extension exits on configured Z/RSI reversal, max extension time, hard
   extension target, protective SL, or end-of-data.

Reversal/extension observations made at a bar close take effect on the next M1
bar so the historical model does not use future intrabar information.

## 6. Partial close

If enabled, partial close is eligible once favorable excursion reaches
`management.partial_close_at_rr * original_risk`.

The configured percentage is normalized to dataset volume step/minimum. A partial
that would create an invalid broker-sized remainder is skipped. Realized partial
P/L and commission are recorded and included in trade/account metrics.

A partial close can execute once per position.

## 7. Trailing and SL tightening

All stop updates obey `safety.never_widen_sl=true`.

Trailing modes:

- STRUCTURE: uses already-closed structure timeframe bars and configured
  `trailing_structure_lookback`;
- ATR: uses already-closed stop ATR timeframe/period with
  `management.trailing_atr_multiplier`;
- `trailing_step_price_units` is the minimum improvement before applying an
  update.

`management.sl_tighten_mode`:

- OFF: no extra tightening;
- STRUCTURE: structure candidate;
- ATR: ATR candidate;
- ZRSI_ASSIST: available only with `ZRSI_DYNAMIC`; after extension evidence it
  may tighten toward protected profit but never beyond currently justified
  price evidence and never widen.

Every update observed from the current bar applies to subsequent bars only.

## 8. Optimizer parity

Task 012 continues to call the same BacktestEngine. Task 013 expands its canonical
optimizer allow-list/relevance rules for newly supported entry/SL/TP/management
parameters. Locked safety/execution fields remain non-optimizable.

No optimizer-specific trading model is permitted.

## 9. Execution safety boundary

Task 013 keeps:

- `trading_enabled=false`;
- `execution_enabled=false`;
- `broker_mutated=false` for Task 009 simulations;
- `execution.demo_only=true`;
- `execution.allow_real_account=false`;
- `execution.max_retry_count=0`;
- `safety.require_server_sl=true`;
- `safety.never_widen_sl=true`;
- `safety.block_on_stale_market_data=true`.

The MQL5 source must still contain no `OrderSend`, `OrderSendAsync`, `CTrade`,
`PositionModify`, `PositionClose`, or `OrderDelete` execution path.

## 10. Acceptance

- STOP_CONFIRM deterministic fill/gap/expiry/cancel tests pass;
- ATR initial SL tests pass using closed-bar history only;
- ZRSI dynamic TP original/extend/lock/reversal/time-cap tests pass;
- same-bar ambiguity remains conservative;
- partial close volume/P&L tests pass;
- trailing/SL-tighten tests prove stops never widen;
- Task 009 manual simulation remains broker-locked/idempotent;
- Task 011 deterministic result hashing/restart persistence remains reproducible;
- Task 012 optimizer can exercise newly-supported canonical parameters without
  unlocking safety fields;
- all prior Python regression tests pass;
- C# IPC/Desktop regressions pass;
- Avalonia Release build passes;
- MetaEditor Bridge compile passes with 0 errors / 0 warnings;
- packaged Task 013 smoke passes;
- complete Windows x64 artifact `XAUPY-Task013-win-x64` is produced and
  independently inspected.
