# XAUPY Task 012 — Optimizer + Walk-Forward

Status: DONE  
Dependency: XAUPY-011  
Visual source-of-truth: docs/ui-reference/Tab Tối Ưu.png

## 1. Goal

Implement deterministic parameter sweep and walk-forward validation on top of
the exact Task 011 `BacktestEngine`, persist reproducible optimization
evidence, and replace the Optimizer placeholder with the approved workspace.

Task 012 is research-only. It does not enable broker execution and does not
change strategy code.

## 2. UI source-of-truth

Follow docs/ui-reference/README.md and `Tab Tối Ưu.png`:

- common live XAUUSD / EA / account / connection sidebar on the left;
- Optimizer header with preset, start and stop actions;
- parameter-range grid;
- real optimization status/progress;
- computation-resource/status panel;
- Top 10 parameter setups;
- result heatmap;
- Walk-Forward Validation controls and aggregate results.

Mock profits, scores, progress, CPU/RAM usage, setup rows and heatmap cells in
the PNG are illustrative only.

### Documented parameter/resource departures

The approved mock uses generic Z-Score/Delta and ATR SL/TP multiplier rows.
Runtime Task 012 instead maps these rows to the **active canonical profile and
Task 011-supported semantics**:

- Trigger Delta shows RSI reversal delta when Trigger RSI is active, or Z-Score
  reversal delta when Trigger Z is active;
- MA Period uses the active SMA/EMA/SMMA/LWMA type label;
- SL row uses STRUCTURE lookback or FIXED distance;
- TP row uses FIXED distance or RR ratio;
- unsupported Task 011 modes remain disabled/rejected rather than being
  approximated.

The real UI also exposes initial balance, spread and commission assumptions in
the optimizer context strip because they are part of the reproducibility key.

Task 014 owns system diagnostics. Task 012 therefore reports only optimizer-owned
resources that are real and measurable inside the optimizer:

- configured worker slots;
- active/in-flight work;
- combinations completed/remaining;
- throughput;
- elapsed/ETA;
- Engine / dataset / Backtest / result-writer status.

It does **not** fabricate CPU %, RAM or Disk I/O. Those fields remain explicitly
unavailable until Task 014.

The mock's live MT5/Data Feed resource checks are replaced by historical Dataset,
Backtest Engine and Result Writer states for the optimizer itself. The common
left sidebar still shows live MT5/EA/Engine connectivity separately.

## 3. Reuse of Task 011

Every candidate and every train/test fold calls the exact Task 011
`BacktestEngine`.

There is no optimizer-specific strategy implementation.

The Task 011 model remains:

`M1_OHLC_PARITY_V1`

and all Task 011 execution limitations remain in force.

## 4. Optimizable canonical parameters

Task 012 accepts only an explicit allow-list of canonical config paths whose
Task 011 behavior is implemented:

- timeframes.direction
- timeframes.pullback
- timeframes.trigger
- direction.ma_period
- pullback.rsi_period
- pullback.rsi_buy_level
- pullback.rsi_sell_level
- trigger.rsi_period
- trigger.rsi_reversal_delta
- trigger.z_period
- trigger.z_reversal_delta
- stop_loss.fixed_price_units
- stop_loss.structure_lookback
- stop_loss.structure_buffer_price_units
- take_profit.fixed_price_units
- take_profit.rr_ratio
- management.breakeven_trigger_rr
- management.breakeven_offset_price_units
- risk.risk_percent
- risk.fixed_lot
- risk.max_trades_per_day
- risk.cooldown_minutes
- risk.max_consecutive_losses

A parameter is rejected when its owning feature/mode is inactive, for example:

- direction.ma_period when MA direction is disabled;
- RSI fields when that RSI stage is disabled;
- Z fields when Z is disabled;
- fixed SL distance when stop mode is not FIXED;
- structure SL fields when stop mode is not STRUCTURE;
- fixed TP when TP mode is not FIXED;
- RR ratio when TP mode is not RR;
- breakeven fields when breakeven is disabled;
- risk_percent outside RISK_PERCENT sizing;
- fixed_lot outside FIXED_LOT sizing.

Locked safety/execution fields are never optimizable.

## 5. Range contract

Each enabled parameter range is one of:

Enum:
{
  "path": "timeframes.direction",
  "values": ["M30", "H1"]
}

Numeric:
{
  "path": "direction.ma_period",
  "min": 30,
  "max": 70,
  "step": 20
}

Rules:

- paths are unique;
- values obey the canonical config schema;
- numeric steps are positive and expanded deterministically using decimal-safe
  arithmetic;
- each generated profile must pass canonical config validation;
- combinations are generated in canonical sorted-path/value order;
- maximum combinations per sweep/fold: 50,000;
- zero-range/no-parameter jobs are rejected.

## 6. Default UI sweep

The default Custom preset is intentionally bounded and uses the active profile
as its default values. Its default grid is approximately the approved mock
shape and targets a practical combination count rather than millions of runs.

The initial rows are:

- Direction TF
- Pullback TF
- Trigger TF
- Pullback RSI Buy
- Pullback RSI Sell
- Trigger RSI reversal delta
- Direction EMA period
- Structure SL lookback (when STRUCTURE) or Fixed SL distance (when FIXED)
- Fixed TP distance (when FIXED) or RR ratio (when RR)

If the active profile makes a row inapplicable, the UI disables/replaces it
rather than optimizing a parameter that has no effect.

## 7. Deterministic ranking

Task 012 objective id:

`ROBUST_SCORE_V1`

For candidates meeting the configured minimum trade count:

- compute real Task 011 metrics;
- compute deterministic trade-sample Sharpe from completed-trade net returns;
- calculate a documented balanced score from:
  - net profit percentage;
  - max drawdown percentage penalty;
  - capped profit factor;
  - win rate;
  - trade-sample Sharpe.

Candidates below minimum trades remain evidence but are ineligible for Top
ranking.

Ties are resolved deterministically by canonical parameter JSON, never by worker
completion order.

## 8. Worker model and cancellation

Optimization runs in a background job so Engine heartbeat/UI remain responsive.

A bounded deterministic worker pool evaluates candidates concurrently. Candidate
indices and final ordering are independent of completion order.

Stop is cooperative:

- heartbeat/status retain the latest terminal job after completion/cancel/fail
  until another job starts or Engine restarts, so UI cannot miss the terminal
  result id;
- no new candidates are scheduled after cancel;
- already-running candidates may finish;
- partial progress remains visible;
- a cancelled job is not presented as a completed optimization result.

## 9. Sweep persistence and reproducibility

Completed sweep results preserve:

- run id / timestamp;
- mode = SWEEP;
- model / objective ids;
- base normalized profile + profile hash;
- dataset file name + SHA-256 fingerprint;
- exact date range;
- spread / commission / initial balance;
- canonical range spec;
- combination count;
- minimum trade count;
- workers used;
- every candidate summary:
  parameters, eligibility, score, Sharpe, Task 011 metrics and result_hash;
- deterministic optimizer_hash excluding run id/timestamp/worker scheduling.

Repeating identical dataset/profile/ranges/date/cost assumptions must produce the
same optimizer_hash, ranking and candidate hashes regardless of worker count.

## 10. Heatmap

Heatmap data is derived only from persisted real candidate results.

The user chooses:

- X parameter;
- Y parameter;
- metric: net profit, score, win rate, profit factor, max drawdown or Sharpe.

When other parameters vary, each X/Y cell is the arithmetic mean of eligible
candidate metric values for that pair. Cell sample count is returned with each
value.

No synthetic interpolation is used.

To keep the Desktop heatmap bounded, Task 012 rejects X×Y grids larger than
2,500 cells and asks the user to narrow one or both axes. This does not change
the persisted sweep evidence or candidate ranking.

## 11. Walk-Forward Validation

Inputs:

- folds: 2..20;
- train ratio: 0.50..0.90;
- rolling: true/false;
- same canonical parameter ranges/objective/min-trades as sweep.

Dataset dates inside the requested range are sorted chronologically.

Plan:

1. initial training span = floor(total dates × train ratio);
2. the remaining out-of-sample dates are partitioned contiguously across folds;
3. every test fold starts strictly after its training end;
4. rolling=true uses a fixed-length trailing training window;
5. rolling=false uses an anchored expanding training window.

For each fold:

1. optimize candidates on the **train range only**;
2. choose the deterministic best eligible train candidate;
3. freeze those parameters;
4. evaluate exactly that frozen profile on the following test range;
5. never use test metrics to select or rank the candidate.

The persisted fold evidence contains train/test boundaries, best train params,
train score/hash/metrics, test hash/metrics and explicit
`selection_source = TRAIN_ONLY`.

Leakage guard fails the run if ranges overlap or test dates precede/equal train
end.

## 12. Walk-Forward aggregate metrics

Real out-of-sample fold results produce:

- average net profit;
- average net profit percentage;
- average trade-sample Sharpe;
- average win rate;
- average max drawdown;
- average profit factor where defined;
- positive-fold ratio;
- stability score 0..1 derived deterministically from positive-fold ratio and
  dispersion of out-of-sample net-return percentages.

The UI must label these as Walk-Forward/out-of-sample results.

## 13. Job/status IPC

Task 012 adds:

- optimizer_start → optimizer_start_ack
- walk_forward_start → walk_forward_start_ack
- optimizer_status → optimizer_status_ack
- optimizer_cancel → optimizer_cancel_ack
- optimizer_result_get → optimizer_result_get_ack
- optimizer_history_query → optimizer_history_query_ack
- optimizer_result_delete → optimizer_result_delete_ack
- optimizer_heatmap → optimizer_heatmap_ack

All responses keep:

- trading_enabled=false
- execution_enabled=false

No Task 012 request sends `trade_intent` or mutates MT5.

## 14. Journal evidence

Task 010 Journal records:

- OPTIMIZER_START;
- OPTIMIZER_COMPLETE / OPTIMIZER_CANCELLED / OPTIMIZER_FAILED;
- WALK_FORWARD_START / COMPLETE / FAILED;
- dataset fingerprint;
- base profile hash;
- range spec/combinations;
- deterministic optimizer hash;
- fold train/test boundaries and out-of-sample summary.

No mock optimization result is written.

## 15. Acceptance

- range/schema/relevance validation tests;
- combination-count/limit tests;
- deterministic grid ordering tests;
- same sweep hash/ranking with worker count 1 vs >1;
- minimum-trade eligibility tests;
- deterministic tie-break tests;
- heatmap aggregation tests with no interpolation;
- cooperative cancel/status tests;
- persisted sweep history/get/delete/restart tests;
- walk-forward fold-boundary tests;
- explicit train/test non-overlap leakage guards;
- proof that test metrics do not affect train candidate selection;
- rolling vs anchored plan tests;
- out-of-sample aggregate/stability tests;
- packaged optimizer/restart smoke;
- approved Optimizer UI hierarchy source test;
- C# optimizer status/result/heatmap contract tests;
- all Task 001–011 regressions pass;
- Avalonia Release 0 warnings / 0 errors;
- packaged Task 011/010/009/007/config regressions pass;
- MetaEditor Bridge compile 0 errors / 0 warnings;
- complete Windows x64 Task 012 artifact produced and independently inspected.


## 16. Automated evidence

- Final implementation CI source commit before ledger-only updates:
  `8e77001c38b513360c8150aa7ee385cf0805d693`
- Final successful branch run: `36207387702`
- Python regression/source/optimizer tests: 225/225 PASS
- C# IPC/Optimizer checks: 74/74 PASS
- Avalonia Release: 0 warnings / 0 errors
- Packaged Task012 optimizer/walk-forward reproducibility/restart smoke: PASS
- Packaged Task011/010/009/007/config regression smokes: PASS
- MetaEditor Bridge: 0 errors / 0 warnings
- Artifact id: `10894211806`
- Artifact: `XAUPY-Task012-win-x64`
- Artifact outer SHA-256:
  `9bfe2b9c956d414b8773688b89540c6722090765495eef968fec5f98e8677b6a`
- Direct build ZIP SHA-256:
  `d821d039b1c2a74deb7ec87fb1cbd8c401e35e2a717e2cc0e9e50f1ebc0a9b91`
- Independent artifact inspection: PASS


## Task 013 extension note

The Task 012 allow-list above is the completed Task 012 milestone boundary.
XAUPY-013 extends the same optimizer implementation to newly-supported
STOP_CONFIRM/ATR/ZRSI/management parameters, guarded by active-mode relevance.
It does not create a second optimizer or trading model. Locked execution/safety
fields remain excluded.
