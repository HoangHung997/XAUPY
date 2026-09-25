# XAUPY Task 007 — Strategy Engine Acceptance

Task 007 is a backend milestone. The finished Strategy and Monitoring screens are
Task 008, so the Task 007 acceptance gate is automated and package-based rather
than a visual trading-signal test.

## Automated acceptance

The Task 007 CI must run:

1. all Python regression tests;
2. deterministic strategy indicator/state tests;
3. Engine IPC strategy/reconnect tests;
4. existing C# IPC contract self-tests;
5. Avalonia Release build;
6. packaged xaupy-engine Task 007 smoke test;
7. packaged xaupy-config regression smoke test;
8. MetaEditor compile of the existing locked MT5 Bridge with 0 errors / 0 warnings;
9. Windows x64 full-build assembly and artifact upload.

## Safety expectation

The packaged smoke test applies a short-period test profile, feeds deterministic
closed-bar Bridge snapshots and verifies an ARMED_BUY → TRIGGERED_BUY sequence.

It also verifies that:

- trading_enabled=false;
- execution_enabled=false;
- no broker command is returned.

The synthetic deterministic series exists only inside automated tests. It is not
shown as live market data and is not evidence of trading performance.

## Optional user regression smoke after download

The complete Task 007 ZIP may be opened like Task 006:

1. run XAUPY.Desktop.exe;
2. verify Python Engine reaches READY;
3. verify existing Tổng quan and Cấu hình tabs still work;
4. optionally attach the Task 003 Bridge on a demo MT5 account and verify MT5
   CONNECTED / EXECUTION LOCKED behavior remains unchanged.

The dedicated realtime Strategy/Monitoring presentation is intentionally deferred
to XAUPY-008.
