# XAUPY Task 009 — Orders & Positions Test

Status: implementation acceptance
Visual source-of-truth: docs/ui-reference/Tab Lệnh & Vị thế.png

## Automated acceptance

Task 009 is accepted automatically only when all of the following are green:

- all Python regression tests;
- Task 009 order-book projection tests;
- stale-data ticket clearing;
- guarded manual simulation tests;
- confirmation/DEMO/ownership/lot/SL/max-position guards;
- idempotent intent replay and intent-id conflict tests;
- trade_intent remains unsupported;
- C# OrdersPositionsSnapshot / ManualActionResult contract checks;
- Avalonia Release build with 0 warnings and 0 errors;
- MQL5 bridge source safety checks;
- MetaEditor compile with 0 errors and 0 warnings;
- packaged Task 009 Engine smoke test;
- packaged config regression smoke;
- complete win-x64 self-contained artifact.

## Manual UI smoke after delivery

Use a DEMO MT5 account only.

1. Launch XAUPY.Desktop.exe from the complete Task 009 build.
2. Confirm Engine and MT5 Bridge become connected.
3. Open **Lệnh & Vị thế**.
4. Confirm the layout follows the approved Task 009 reference image:
   - five KPI cards;
   - open positions table;
   - pending orders table;
   - guarded bulk controls;
   - deals table;
   - right quote/chart/manual-order rail.
5. Confirm ticket rows correspond to the connected MT5 DEMO account and are not
   mock/example values.
6. Stop or disconnect MT5 and verify live ticket rows/quotes clear rather than
   remaining visually live.
7. Reconnect and verify current owned tickets repopulate.
8. Try a BUY/SELL preview without checking confirmation: it must be rejected.
9. Check confirmation and use a valid lot + SL: the result must explicitly say
   **SIMULATED** and must not create an MT5 trade.
10. Test Close / 1/2 / BE / TS / pending Sửa-Hủy previews. They must never claim
    broker execution and must never mutate MT5 in Task 009.
11. Verify REAL account mode, if accidentally connected, blocks manual
    simulations.

## Hard expected boundary

- no OrderSend;
- no OrderSendAsync;
- no CTrade;
- broker execution locked;
- demo-only profile locked;
- retry count remains zero;
- server SL remains mandatory;
- stale data blocks actions;
- never-widen-SL remains mandatory.
