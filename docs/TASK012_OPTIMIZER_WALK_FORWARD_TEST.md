# XAUPY Task 012 — Optimizer + Walk-Forward Test

Status: implementation acceptance  
Visual source-of-truth: docs/ui-reference/Tab Tối Ưu.png

## Automated acceptance

Task 012 is DONE only when all are green:

- canonical optimizer range allow-list/relevance/schema tests;
- deterministic decimal range expansion and combination limit tests;
- same sweep hash/ranking with worker count 1 vs >1;
- minimum-trade eligibility and deterministic tie-break tests;
- heatmap aggregation from real candidates only, with null missing cells;
- cooperative background cancel/status tests;
- optimizer persistence/history/get/delete/restart;
- heartbeat responsiveness while optimization runs;
- walk-forward rolling and anchored fold-plan tests;
- strict train/test non-overlap leakage guards;
- selection_source=TRAIN_ONLY for every fold;
- proof that TEST preference cannot alter TRAIN selection;
- out-of-sample aggregate/stability tests;
- Task010 optimizer journal evidence;
- approved Optimizer UI source hierarchy test;
- C# status/result/heatmap/walk-forward contract checks;
- all Task001–011 regressions;
- Avalonia Release 0 warnings / 0 errors;
- packaged Task012 optimizer + walk-forward + restart smoke;
- packaged Task011/010/009/007/config regressions;
- locked MT5 Bridge MetaEditor compile 0 errors / 0 warnings;
- complete Windows x64 Task012 artifact.

## Manual Optimizer smoke after delivery

1. Launch XAUPY.Desktop.exe from the full Task012 build.
2. Open **Tối ưu** and confirm the live XAUUSD/system sidebar remains on the left.
3. Confirm the right-side layout follows docs/ui-reference/Tab Tối Ưu.png:
   - Parameter Sweep header/actions;
   - parameter range grid;
   - real status/progress/resources;
   - Top 10 setups;
   - Heatmap;
   - Walk-Forward Validation.
4. Before a real run, Top 10/heatmap/WF metrics must remain empty/—, not mock values.
5. Load the same canonical M1 JSON/CSV dataset used by Task011.
6. Confirm active-profile defaults populate the optimizer range rows; inapplicable
   Task011 modes are disabled instead of silently optimized.
7. Start a bounded sweep. Verify heartbeat/UI remain responsive and progress,
   completed work, workers, throughput and ETA advance from backend status.
8. Stop a running sweep. It must finish as CANCELLED/STOPPING and must not appear
   as a completed persisted result.
9. Run an identical sweep twice, including with a different worker count; compare
   optimizer_hash, ranking and candidate result hashes — they must match.
10. Open Top setup details and confirm metrics/parameters are real persisted values.
11. Change Heatmap axes/metric; missing cells must remain blank/— and never be
    synthetically interpolated.
12. Run Walk-Forward. Every fold must state TRAIN_ONLY and train_to < test_from.
13. Confirm Walk-Forward summary is labelled out-of-sample and shows stability,
    positive-fold ratio, average P/L/Sharpe/winrate/DD from real TEST folds.
14. Save/load a preset and verify ranges/cost assumptions restore without changing
    locked safety fields.
15. Confirm CPU/RAM/Disk values are not fabricated; UI explicitly points those
    diagnostics to Task014.

## Hard boundary

- Optimizer candidates use Task011 BacktestEngine only;
- no optimizer-specific strategy implementation;
- no trade_intent;
- no MT5 broker mutation;
- locked execution/risk safety fields cannot be optimized;
- test folds never participate in parameter selection;
- no profitability claim is implied by ranking or walk-forward output.
