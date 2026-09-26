# XAUPY Task 013 — Dynamic Management Acceptance

## Automated acceptance

The Task 013 CI gate must run the complete Python regression suite plus focused
coverage for:

- STOP_CONFIRM trigger price, gap fill, expiry, opposite-signal cancellation and
  direction-change cancellation;
- ATR stop warm-up and deterministic value;
- ZRSI_DYNAMIC original TP, extension decision, hard/emergency cap, original-TP
  SL lock, reversal exit and time exit;
- partial close volume-step/minimum handling and realized P/L;
- STRUCTURE/ATR trailing and STRUCTURE/ATR/ZRSI_ASSIST tightening;
- never-widen-SL invariants;
- conservative same-bar SL/target ordering;
- repeat-run deterministic result hash;
- Task 012 optimizer relevance for Task 013 parameters;
- Task 009 broker-simulation/idempotency regressions;
- locked MQL5 source and MetaEditor compilation.

The Windows job must also run `scripts/smoke_task013_management.py` against the
packaged `xaupy-engine.exe`.

## Manual smoke after delivery

1. Start the packaged Desktop/Engine with broker execution visibly locked.
2. Load a profile using STOP_CONFIRM + ATR SL + ZRSI_DYNAMIC TP.
3. Validate/apply the profile and confirm safety fields remain locked.
4. Run the supplied deterministic Backtest fixture through the packaged Engine.
5. Confirm the result records pending-stop entry evidence, original/final SL/TP
   management evidence and no claim of live broker execution.
6. Open Orders & Positions and confirm manual controls remain SIMULATION ONLY.
7. Confirm no action can silently enable real-account execution.

## Hard boundary

Task 013 acceptance is research/state/broker simulation only.

- no live `trade_intent`;
- no MT5 broker mutation;
- no automatic retry;
- real account remains disabled;
- server SL remains mandatory;
- stale data remains blocking;
- stop widening remains forbidden.
