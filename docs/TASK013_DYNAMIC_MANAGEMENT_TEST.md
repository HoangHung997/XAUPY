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

## Local recovery validation — 2026-09-28

Recovered the in-progress implementation from remote
`origin/task/013-dynamic-trade-management` and added regression checks for:

- BUY/SELL intrabar stop entry cannot exit at the pre-entry open;
- signal-age expiry uses the configured Trigger timeframe;
- breakeven cannot cross the current executable market;
- partial close queues at bar close, fills once at the next open, and loses to a
  protective gap stop;
- opening exits exclude future bar extrema and report the opening timestamp;
- EITHER handles one unavailable indicator without requiring BOTH;
- an old favorable excursion cannot arm extension after price retreats;
- broker tick size, minimum stop distance, freeze zone, and invalid initial SL;
- a TP touched before new extension evidence retains the original target.

Focused commands: `python -m unittest discover -s python/tests -p
'test_task013_dynamic_management.py' -v` and the same command with
`test_task011_backtest.py`. Local passing checks do not replace the required
Windows packaged smoke, CI artifact, or demo acceptance.

Current local results: 29 focused Task 013 tests, 19 Task 011 backtest tests and
29 optimizer tests passed. The packaged Task 013 smoke also passed with the
corrected closed-bar extension fixture: price must close inside the near-TP zone,
and partial close executes on the following open. All smoke processes isolate
state/log/backtest/optimizer storage from the user's data. The combined local
regression run recorded 278 Python tests and 85 C# contract checks passing.
Final integrated CI run 36340716356 passes 283 Python tests, 90 C# checks,
20 desktop interaction checks and all packaged smokes. Artifact 10939305308
was downloaded and independently verified against its complete SHA-256 manifest.
