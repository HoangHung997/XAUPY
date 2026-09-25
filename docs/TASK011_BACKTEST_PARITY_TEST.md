# XAUPY Task 011 — Backtest Parity Test

Status: implementation acceptance  
Visual source-of-truth: docs/ui-reference/Tab BackTest.png

## Automated acceptance

Task 011 is DONE only when all are green:

- JSON/CSV M1 dataset validation and SHA-256 fingerprint tests;
- M1 → M3/M5/M15/M30/H1/H2/H4 complete-bucket aggregation tests;
- gapped/incomplete higher-timeframe buckets are not fabricated;
- direct StrategyEngine replay parity test;
- next-M1-bar MARKET entry/no-lookahead test;
- deterministic SL-first rule when SL and TP are both touched in one M1 bar;
- fixed/structure SL and fixed/RR TP tests;
- fixed-lot/risk-percent sizing and broker volume-step tests;
- risk/session/cooldown/daily guard tests;
- MAE/MFE and drawdown tests;
- repeated run produces identical result_hash/trades/curves;
- persisted history/get/delete and restart replay;
- Task010 Journal BACKTEST_DATASET/BACKTEST_RUN evidence;
- approved Backtest UI hierarchy source test;
- C# Backtest parser/IPC contract tests;
- all Task001–010 regressions;
- Avalonia Release 0 warnings / 0 errors;
- packaged Task011 deterministic Backtest/restart smoke;
- packaged Task010/009/007/config regressions;
- locked MT5 Bridge MetaEditor compile 0 errors / 0 warnings;
- complete Windows x64 Task011 artifact.

## Manual UI smoke after delivery

1. Launch XAUPY.Desktop.exe from the full Task011 build.
2. Open **Backtest**.
3. Confirm the common XAUUSD/EA/account/system sidebar remains on the left.
4. Confirm right-side layout follows docs/ui-reference/Tab BackTest.png:
   - Backtest configuration;
   - six KPI cards;
   - Equity + Drawdown charts;
   - Backtest run history;
   - trade list + paging.
5. Confirm Model reads **M1 OHLC deterministic parity**, not Every tick.
6. Load a canonical M1 JSON/CSV dataset. Before running, KPI/chart/table values
   must remain empty/— rather than showing demo values from the PNG.
7. Run Backtest and confirm all KPI/chart/trade values appear from the real
   Engine result.
8. Run the same dataset/profile/range/cost assumptions again and confirm the
   result hash is identical.
9. Open a stored result from history and page through trades.
10. Export JSON result and CSV trades; compare run_id/result_hash/trade values
    to the UI.
11. Delete a stored result and confirm it disappears from history.
12. Change the active profile to an unsupported Task011 mode such as
    STOP_CONFIRM or ZRSI_DYNAMIC TP: Backtest must reject it explicitly.

## Hard boundary

- Backtest calls the same StrategyEngine as live logic;
- no Every-tick accuracy claim;
- no trade_intent;
- no MT5 broker mutation;
- demo/live execution settings remain locked;
- Task009 simulation safety remains unchanged.
