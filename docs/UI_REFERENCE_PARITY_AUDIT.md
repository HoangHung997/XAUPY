# UI reference audit — 2026-09-28

## Evidence and verification

- Reviewed all ten approved PNGs in `docs/ui-reference/`.
- Compared two captures of all ten real Avalonia screens at 1672 × 941: `artifacts/ui-audit-initial/` and `artifacts/ui-audit-second/`.
- The second capture prompted final fixes to sidebar status columns, the six account rows, monitoring alert space, profile-load state and profile labels. A final capture of the packaged build is required to verify those last fixes visually.
- Desktop Debug build passed with zero warnings/errors; 66 existing UI-source checks passed after updating assertions for real dashboard hosts, the candlestick control and translated safety labels.
- A headless Avalonia interaction probe passed 12 runtime assertions: real Monitoring chips and keyboard activation, selection persistence across heartbeats, indicator and chart-type toggles, comparison selection/clearing, rendering and Strategy action recovery when the engine is unavailable. The rendering fixture is test-only; it is never loaded into the application.
- Source checks verify control/data contracts, not pixel equivalence.

## Changes made

- Restored the reference canvas proportions, full-width navigation selection, vector navigation icons, dark blue gradients and larger type.
- Matched the shared quote / EA / account / connection rail and retained neutral or waiting states where the corresponding data is unavailable.
- Replaced visible decorative quote columns with OHLC candles in Overview, Monitoring and Orders. Candles, volume and EMA curves are calculated only from closed bars supplied by the bridge. The chart consumes the genuine `bar_history` bootstrap and recent bar updates.
- Wired chart timeframe chips, EMA visibility and candle/closing-price display. Comparison offers other received timeframes of the same symbol, normalized to the first visible price and clearly labeled. Unavailable comparison series cannot be selected, and new snapshots retain the user's selected timeframe.
- Wired Strategy save/export to the current validated profile and load to JSON validation, a parameter summary and an explicit apply action. The separate default-profile action remains unavailable because there is no separate backend operation; active configuration is already persisted for restart recovery.
- Reworked Configuration into compact paired cards with all canonical parameters retained. Category navigation scrolls to the actual group, and full parameter paths/ranges remain available in tooltips.
- Kept table headers and data rows on the same proportional column definitions; stretched journal rows to the table width.
- Kept the reference heights for empty order tables and fixed optimizer controls spilling into the neighboring panel.
- Bound strategy indicator mirrors and state dots to actual snapshots; removed permanently positive connection/condition signals.
- Fixed loading a profile being incorrectly marked as edited by deferred control events, and synchronized both visible profile labels.
- The footer labels local time as “Giờ máy”; it does not present the computer clock as MT5 server time.

## Remaining differences from the demo

The UI is **not certified as a 100% pixel match**. Fonts, some spacing and some component shapes still differ. The application must not manufacture the account values, trades, chart history or test results in the approved images.

| Area | Remaining difference |
| --- | --- |
| Configuration | The current strategy has 133 canonical fields. Its compact cards retain those real fields and scrolling; the demo's different illustrative parameter set is not substituted. |
| Strategy | The page is primarily a projection of the active configuration. Save, load and export work; a separate default-profile operation is unavailable. Detailed editing remains in Configuration. |
| Market charts | Actual series differ from the illustrative chart. Comparison is restricted to received timeframes of the current symbol; an arbitrary-symbol comparison feed is not implemented. |
| Monitoring | News-calendar data, broker-day drawdown and some monitoring resource metrics remain unavailable in this view. They show waiting/empty states. |
| Orders | Empty positions/deals stay empty. Broker actions remain explicitly restricted to the supported guarded simulation flow. |
| Backtest / Optimization | Empty charts and results remain empty until a real run completes. Some data-selection controls are additional to the demo because a valid dataset is required. |
| Global layout | At smaller viewport sizes, dense canonical content uses scrolling; the audit canvas is 1672 × 941. |

The missing interactions and remaining visual differences must stay visible in the handover; a successful build or source test is not evidence that the stricter user requirement of exact visual parity has been met.
