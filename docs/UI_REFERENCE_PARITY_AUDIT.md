# UI reference audit — 2026-09-28

## Current 1.0 development review — 16:40 local

Reviewed all ten `artifacts/release-v1-ui-packaged` captures against all ten
reference PNGs. This package is from the first full 1.0-dev build and predates
the latest layout corrections. **Exact visual parity is still not certified.**

The source now removes misleading permanent-lock/simulation messages, follows
actual user execution mode, translates generated settings, and places research
actions inside the Optimizer header. Chart PNG/fullscreen controls use vector
icons, D1 is visible, and archive/RSI/Z legends occupy separate lines. The Orders
tables reserve less empty height so the new execution row does not hide history.
Dialog zoom accounts for margins, preventing horizontal clipping at 100%.

Native package acceptance opened all 100,537 real M1 bars through the file picker,
edited the chart RSI period, exported PNG, and opened/closed fullscreen. The PNG
`artifacts/release-v1-native-packaged/chart-export-before-layout-fix.png` records
the legend overlap found in this run. A fresh capture must verify the correction.

Earlier missing-feature descriptions in this document are historical. The current
code adds native telemetry, nine independent timeframe rows, broker calendar,
full broker history, tick replay, profile defaults/versioning and data bundles.
See [the feature matrix](RELEASE_V1_FEATURE_MATRIX.csv) for acceptance boundaries.
Reference credentials, notifications and some illustrative preferences still
differ from the implemented controls; account values and trade results remain
actual data. A build or a mock result cannot establish visual or broker acceptance.

## Evidence and verification

- Reviewed all ten approved PNGs in `docs/ui-reference/`.
- Compared two captures of all ten real Avalonia screens at 1672 × 941: `artifacts/ui-audit-initial/` and `artifacts/ui-audit-second/`.
- Reviewed all ten packaged captures from source `71902a8` at 1672 × 941 in `artifacts/ui-audit-final/`, against all ten approved references. Live MT5 data, connection states, history-backed candles and the six sidebar account rows are visible in that evidence.
- That packaged review found overlapping chart time labels, long Monitoring table cells, a clipped Strategy timeframe label, clipped Backtest footer buttons and a crowded Journal source badge. Subsequent source changes fix those defects, add actual EMA legends and make the Strategy direction arrow follow the received direction.
- Reviewed all ten post-polish packaged captures in `artifacts/ui-audit-polished/` at 1672 × 941, captured on 2026-09-28 at 01:23:02–01:23:14 local time. These captures contain the polish changes made after `71902a8`, before their final commit. The corrected chart axes, EMA legends, BUY arrow, wrapped Monitoring cells, complete Backtest footer buttons and separated Journal badge are visible. The shorter Overview configuration panel and single-line quick log also fit above the footer. No further blocking overlap or inaccessible primary control was found in this ten-page review.
- Reviewed the actual downloaded CI build from source `a913770`, successful workflow run `36340716356`: all ten captures in `artifacts/ui-audit-ci/`, at 1672 × 941 on 2026-09-28 at 01:34:44–01:34:56 local time. Its layout matches the post-polish captures with no observed layout regression. Differences are runtime values, timestamps, journal contents, the hovered window-close control and the packaged Python version. This verifies the shipped CI layout against the tested local layout; it does not certify equivalence to every demo pixel.
- Desktop Debug build passed with zero warnings/errors; 66 existing UI-source checks passed after updating assertions for real dashboard hosts, the candlestick control and translated safety labels.
- A headless Avalonia interaction probe passed 12 runtime assertions: real Monitoring chips and keyboard activation, selection persistence across heartbeats, indicator and chart-type toggles, comparison selection/clearing, rendering and Strategy action recovery when the engine is unavailable. The rendering fixture is test-only; it is never loaded into the application.
- Source checks verify control/data contracts, not pixel equivalence.

## RC2 reference remediation — 2026-09-28

The user's renewed request requires a direct comparison to the approved images, not merely a comparison to the preceding application build. The implementation remains **not certified as a 100% pixel match**.

- Reviewed all ten actual native captures in `artifacts/ui-audit-rc2-final/` at 1672 × 941 (06:22:10–06:22:22 local), against the approved reference geometry. These captures show the revised Configuration grid, the restored Optimizer results row, larger Tools/Settings typography and native vector card icons, live MT5 candles, and the first functional Strategy editor. They precede the final Journal sizing changes, the final Strategy compaction and three text-clipping fixes. The subsequent polished native capture below validates those edits together.
- Reviewed all ten subsequent native captures in `artifacts/ui-audit-rc2-polished/` at 1672 × 941 (06:26:37–06:26:49 local). Journal now shows the approved three-panel rail and larger divided rows; Overview state text, Monitoring execution note and Tools file information fit. Strategy’s core lower panels are visible. This review found two small remaining input/text width issues: the Strategy expiry spinner (subsequently widened from 80 to 110 px by the integration pass) and Journal alert time/level cells (subsequently given narrower cell padding). Those two localized changes follow the capture; no other blocking overlap was identified in the ten-screen review.
- Configuration now places risk/direction, pullback/trigger, timeframes/sessions and SL/TP/management/news/validation in the reference's four main rows. All 133 canonical fields remain accessible; additional fields follow below the primary cards. The first page no longer consists of long independent parameter columns. Timeframe chips edit their actual selectors. SL/TP captions use readable Vietnamese labels while retaining their canonical enum values.
- Optimizer places Top 10, Heatmap and Walk-Forward together directly below the range/progress panels. Dataset, dates, costs and worker options remain accessible in an expansion below the main results row. Real worker metrics remain distinct from unavailable CPU/RAM/Disk utilization.
- Overview quick configuration includes the actual Pullback AND/OR setting. It reads the active profile, preserves local edits across heartbeats, patches only changed values and rejects a concurrent change to the same value. Full Configuration and Strategy drafts block conflicting quick application.
- Strategy now has real editable indicator/timeframe/filter/SL-TP controls, applies validated changes through the existing configuration API and retains drafts on conflicts. Its last compaction is owned and verified by the integration pass; the old description of this page as a read-only projection no longer applies.
- Backtest's main configuration row, result toolbar, KPI cards, chart row and result tables were resized to the approved composition. Additional dataset/balance details remain in an expansion. Charts show axes, time labels, filled areas and actual final/maximum-drawdown callouts from received results. Balance/Equity/Both controls change the rendered series and retain their selection when new results arrive.
- Monitoring's alert table now spans the full dashboard below both the sidebar and main panels, matching the reference arrangement. This tab uses a 275 px compact sidebar with all four cards visible; leaving the tab restores the ordinary 288 px rail. The controller continues updating the relocated alert text. The resource rings use the reference's three colors and unknown telemetry remains unknown. The execution note and Overview's long state text were corrected to fit their cards.
- Journal's right rail now uses three principal panels: Summary at 188 px, Alerts at 313 px and Bookmarks filling the remaining height. Replay/status details remain accessible inside a drawer in Bookmarks. Log text is 14 px, row dividers are visible, and recent-alert messages wrap to two lines. The revised three-panel layout is visible in the polished native capture; the subsequent alert-cell padding fix is noted above.
- Tools and Settings received larger labels and native vector section icons. Tools file-info spacing was corrected after the native capture exposed a clipped final line. The implementation keeps actual JSON and available actions.
- Verification during this pass: desktop Release build had zero warnings/errors; 52 targeted UI-source checks passed; 16 headless chart/toolbar interaction assertions passed; all 133 schema editors loaded cleanly. A separate isolated-engine MainWindow probe passed 13 assertions: 8 for actual AND/OR loading/application, heartbeat draft preservation and concurrent-profile conflict protection, plus 5 for full-width Monitoring alerts, preserved controller updates after relocation, a sidebar that fits without scrolling, and restored layout after navigation. The resulting full-window render is `artifacts/quicklogic-tests/monitoring-fullwidth-test.png`. Twelve relevant Monitoring source checks passed after this final layout change. Test fixtures and test profile changes are confined to ignored `artifacts/` locations and a separate loopback port; they are never substituted into the live app.

## Changes made

- Restored the reference canvas proportions, full-width navigation selection, vector navigation icons, dark blue gradients and larger type.
- Matched the shared quote / EA / account / connection rail and retained neutral or waiting states where the corresponding data is unavailable.
- Replaced visible decorative quote columns with OHLC candles in Overview, Monitoring and Orders. Candles, volume and EMA curves are calculated only from closed bars supplied by the bridge. The chart consumes the genuine `bar_history` bootstrap and recent bar updates.
- Wired chart timeframe chips, EMA visibility and candle/closing-price display. Comparison offers other received timeframes of the same symbol, normalized to the first visible price and clearly labeled. Unavailable comparison series cannot be selected, and new snapshots retain the user's selected timeframe.
- Wired Strategy save/export to the current validated profile and load to JSON validation, a parameter summary and an explicit apply action. The separate default-profile action remains unavailable because there is no separate backend operation; active configuration is already persisted for restart recovery.
- Reworked Configuration into the approved four-row primary card layout with all canonical parameters retained. Category navigation scrolls to the actual group, and full parameter paths/ranges remain available in tooltips.
- Kept table headers and data rows on the same proportional column definitions; stretched journal rows to the table width.
- Kept the reference heights for empty order tables and fixed optimizer controls spilling into the neighboring panel.
- Bound strategy indicator mirrors and state dots to actual snapshots; removed permanently positive connection/condition signals.
- Bound the direction arrow and its color to BUY / SELL / BOTH / neutral state. The arrow no longer remains red and downward beside a BUY label.
- Fixed loading a profile being incorrectly marked as edited by deferred control events, and synchronized both visible profile labels.
- The footer labels local time as “Giờ máy”; it does not present the computer clock as MT5 server time.

## Remaining differences from the demo

The UI is **not certified as a 100% pixel match**. Fonts, some spacing and some component shapes still differ. The application must not manufacture the account values, trades, chart history or test results in the approved images.

| Area | Remaining difference |
| --- | --- |
| Overview | Quick configuration has the real timeframes, BUY/SELL and Pullback logic controls. The demo's single session-filter checkbox has no equivalent canonical field; the actual per-session settings remain in Configuration. The run/stop control and some small icon treatments differ from the illustration. |
| Configuration | The primary cards follow the reference arrangement; 133 canonical fields require supplementary groups below them. Native selectors, checkbox details and some dense labels are not pixel-identical to the illustrative parameter controls. |
| Strategy | The formerly read-only filters are editable and apply through the validated configuration API. The exact set of canonical fields differs from the demo; supplementary controls remain expandable. The separate default-profile action is still unavailable. |
| Market charts | Real candles, volume, EMA values and date ranges differ from the illustrative data. Comparison is restricted to received timeframes of the current symbol; arbitrary-symbol comparison and the demo's capture/fullscreen toolbar icons are not implemented. |
| Monitoring | The alert strip now spans under the sidebar. Only the active three timeframe roles have evaluated strategy evidence; the reference's independent seven-timeframe condition matrix, news calendar, CPU/RAM/Disk utilization and some execution counters are not available. These missing values are not simulated. |
| Orders | Empty strategy-owned positions/deals stay empty. The explicit guarded simulation controls and safety/status row add content that the demo lacks. Broker-order functionality is not implied by matching the visual buttons. |
| Backtest / Optimization | Real dataset selection and M1 OHLC model semantics differ from the demo's Every Tick example. Charts/results remain empty until a real run completes. Data/cost controls use a supplementary expansion; unavailable utilization is not replaced with illustrative percentages. |
| Journal | The revised card heights and larger log rows follow the reference more closely. Messages, counts and categories are real; source icons and some badge/detail styling still differ. The revised layout is visible in the polished native capture; the subsequent alert-cell padding fix is noted above. |
| Tools | The three-column tool/editor/help structure, type and vector icons follow the reference. The subsequent native JSON presenter adds token colors, line numbers, search and expansion. Canonical content replaces the illustrative sample; small style differences remain. |
| Settings | The card arrangement and icons follow the reference. Connection through the running MT5 terminal, actual recovery controls and available settings replace the demo's credential/login form and unsupported preferences. |
| Global layout | Small border, gradient, icon, font and spacing differences remain; Monitoring now has its own compact sidebar proportions; small differences from other tab-specific reference dimensions remain. The reviewed canvas is 1672 × 941. Smaller viewports require additional scrolling. |

The remaining feature and visual differences must stay visible in the handover; a successful build or source test is not evidence that the stricter user requirement of exact visual parity has been met.

## Additional reference corrections after the first RC2 artifact

The native review continued after `7f96826`. The subsequent implementation uses the
reference's 272 px Strategy sidebar and 8 px gutter, larger stage selectors and
gradient panels, vector filter icons and a divided current-configuration table.
Order summary cards now use the reference's 106 px height and 48 px icons. All
three order tables share proportional header/body columns; the former fixed body
widths could diverge from the header on resizing. The obsolete reconnect warning
is cleared when a fresh connected DEMO snapshot arrives. Strategy warm-up
readiness no longer labels all entry conditions as passed.

Overview quick configuration has three divided columns with consistent icons.
Monitoring has divided timeframe rows and metric-driven native gauges; extra
configured M3/H2 roles can scroll, and unevaluated roles retain unknown values.
Global status dots are drawn circles. Configuration, Backtest, Optimizer and
Journal received further corrections to toolbar proportions, column alignment,
icons, progress styling and clipped labels.

Tools now colors JSON in the native editable text presenter, with synchronized
line numbers, search, formatting and editor expansion. Selection, caret, undo
and IME remain owned by the native TextBox. Settings uses real persisted switches
and folder actions, with all principal cards and the save row visible at the
reviewed canvas. Thus the earlier remaining-differences entry about the
single-color editor is superseded; the remaining unsupported demo capabilities
and strict pixel-equivalence limitation still apply.

The first actual ten-page capture of this follow-up is
`artifacts/ui-audit-rc2-refined/` (07:02:21–07:02:33 local, 28 September), running
the newly compiled Desktop against the already verified unchanged RC2 Engine and
real MT5. It exposed three small final adjustments: Strategy footer clearance,
the last Orders summary caption and the Settings retention-value spinner.
These adjustments require a subsequent capture; this intermediate evidence is
not a claim that the first RC2 ZIP contains the follow-up changes.

The next ten-page native capture, `artifacts/ui-audit-rc2-refined-final/`
(07:07:12–07:07:25 local), verifies the complete Strategy expiry field above the
footer, the full Orders summary caption and the visible Settings retention value
and actual connected account identifier. The Orders manual rail subsequently
receives a small spacing correction so its simulation-confirmation checkbox fits
at the same canvas. Local verification passes 324 Python tests, 102 C# contracts
and 76 isolated Avalonia interaction checks. Newly added checks exercise native
JSON editing, selection, undo, keyboard shortcuts, line-number scroll alignment,
persisted Settings switches, nine-timeframe Monitoring scrolling and the two
corrected state-label behaviors. No broker trade or production-profile change
is made by these tests.

## Final local release review — source `7f96826`

Independently reviewed all ten native screens of the clean local Release build in `artifacts/ui-audit-rc2-release/`, each at 1672 × 941, against the approved references and the preceding RC2 captures. The application clocks show 2026-09-28, 06:37:15–06:37:27 in Asia/Saigon: Overview 06:37:15, Configuration 06:37:16, Strategy 06:37:18, Monitoring 06:37:19, Orders 06:37:20, Backtest 06:37:22, Optimization 06:37:23, Journal 06:37:24, Tools 06:37:26 and Settings 06:37:27.

- No critical clipping, overlapping content or hidden primary action was observed in these ten captured states. This finding is limited to the captured canvas and states; it does not establish every viewport or interaction state.
- Monitoring's alert strip visibly spans below both the compact sidebar and the main panels, with all four sidebar cards visible. Strategy's expiry value `2` is readable after the final width correction, and its core lower panels fit. Journal alert rows show the full time and `WARN` level after the cell-padding correction. Tools shows the complete final file-information line. Configuration Apply, Backtest/Optimization actions and Settings footer buttons are visible.
- These captures validate the post-polish Strategy and Journal corrections that were still pending screenshot confirmation in the earlier RC2 section. They are captures of the local clean Release build, not execution evidence from a downloaded CI artifact. Successful CI run `36359181671` for the same source is separate build evidence.
- **Exact 100% visual parity is not certified.** At source `7f96826`, supplementary canonical configuration groups, the then single-color Tools JSON editor, native control/icon/font/spacing differences and unsupported demo telemetry remained. The subsequent editor improvement is documented separately above. Real account values, chart series, events and empty results correctly differ from the illustration. Successful checks and CI do not prove pixel equivalence.
- Final CI artifact verification: independently reviewed all ten actual compiled-artifact captures in `artifacts/ui-audit-rc2-ci/` from successful run `36359181671`, source `7f96826`, at 1672 × 941 on 2026-09-28 (visible application clocks 06:44:20–06:44:32, Asia/Saigon). No layout regression or new critical clipping was observed against the local Release captures; differences are live prices/indicators, clocks, latency, journal contents and the bundled Python version (3.13.15). The full-width Monitoring alerts, readable Strategy expiry and complete Journal alert cells remain intact. This confirms the running CI artifact's layout, not 100% equivalence to the demo.

## Refined CI runtime review — source `5dc7a6e`

The final delivered revision comes from successful [CI run 36361798910](https://github.com/HoangHung997/XAUPY/actions/runs/36361798910), source `5dc7a6ea1f4cafe50e9316028a19c797830457b9`. Its downloaded Desktop and matching Engine ran from `dist/XAUPY-verified-rc2-refined-win-x64/` with the exact CI EA reattached to MT5. All ten native captures in `artifacts/ui-audit-rc2-refined-ci/` were visually reviewed at 1672 × 941. Visible application clocks span 07:33:26–07:33:38 on 2026-09-28, Asia/Saigon. These supersede the intermediate preview captures for the delivered layout.

- No critical clipping or hidden primary action was observed in these captured states. Configuration Apply, Backtest controls, Optimizer Start/Walk-Forward controls, Journal details and Settings Save remain visible. This statement is limited to the captured canvas and states.
- Strategy displays the complete expiry input and value `2`, and its lower condition panels fit above the footer. Waiting for a setup correctly displays `ĐANG CHỜ` rather than implying that all conditions passed.
- Orders displays the full last summary caption, aligned table headers and the manual simulation confirmation text above the footer. Eighteen separate local layout assertions also verified the rail's extent/viewport and Strategy expiry bounds at this canvas; these are supplemental layout evidence, not part of the CI's 76 interaction checks.
- Monitoring retains the full-width alert strip, divided timeframe matrix and gauges. Unavailable metrics remain unknown. The raw strategy state wraps inside its small gauge card; this is a remaining presentation difference, not hidden actionable content.
- Tools shows syntax-colored editable JSON, its line-number gutter, search/format/expand toolbar, complete file details and quick actions. Settings displays the connected account identifier and retention value `30` without the previous clipping. Account data and raw screenshots remain local.
- The comparison page at `http://127.0.0.1:8765/`, generated in `artifacts/ui-comparison-report/index.html`, now embeds these exact CI captures beside all ten approved reference PNGs and supports an adjustable overlay. Its header identifies source `5dc7a6e`.
- Separate read-only live evidence passes 19/19 checks across 21 samples in 20 seconds; tick frames advance 32→53 and ticks 321→614. `artifacts/rc2-refined-ci-live-summary.json` records that deployed EA and running Engine match the CI manifest. A native observation also confirms Desktop READY with updating MT5 data. Broker execution stays locked.

**Strict 100% parity remains unfulfilled.** Native font/icon/control rendering, supplementary canonical settings and unsupported illustrated capabilities still differ as detailed above. Live values and empty result sets also legitimately differ from the sample data. The completed build, 324 Python tests, 102 C# contracts, 76 interaction checks and successful MT5 connection establish their respective scopes; they do not certify pixel equivalence. Task 016 therefore remains ACTIVE.
