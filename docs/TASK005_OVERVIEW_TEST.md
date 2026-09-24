# XAUPY Task 005 — Overview Smoke Test

Use the full Task 005 build only.

## Without MT5

1. Extract the ZIP.
2. Run XAUPY.Desktop.exe.
3. Wait for Python Engine READY.
4. Expected:
   - header shows ENGINE READY;
   - MT5 shows WAITING;
   - account/price values show —;
   - strategy card shows canonical profile M30/M5/M1;
   - strategy state says CHƯA CHẠY;
   - EXECUTION LOCKED stays visible.
5. Click every left navigation item.
6. Only Tổng quan shows the Overview dashboard.
7. Other tabs show an explicit not-yet-implemented placeholder.

## With MT5 demo

1. Follow docs/TASK003_MT5_DEMO_TEST.md to attach XAUPY_Bridge_EA.ex5 to XAUUSD.
2. Expected within a few seconds:
   - MT5 CONNECTED;
   - symbol, BID, ASK and spread update;
   - balance/equity/free margin show real demo values;
   - account mode shows DEMO;
   - quote chart begins collecting real BID values;
   - positions/orders counters reflect Bridge snapshot;
   - quick log records MT5 Bridge connection and first market snapshot.
3. Detach the Bridge EA.
4. After stale timeout:
   - MT5 returns to WAITING;
   - live quote/account values clear;
   - chart clears;
   - quick log records unavailable/stale transition.

Task 005 must not place, modify or close any order.
