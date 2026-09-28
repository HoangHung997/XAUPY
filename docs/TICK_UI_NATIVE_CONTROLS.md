# Tick display and native DEMO controls — 0.17.1-tickui

User-requested changes: keep the current quote, forming candle and oscillator
display responsive to observed ticks; control the DEMO acceptance run inside the
desktop application rather than using a separate authorization script.

## Data and display

- EA 1.018 defaults to a 250 ms collection interval. It still reads ordered
  CopyTicks records, including ticks coalesced by MT5's OnTick event. Existing EA
  input values must be checked when replacing the attached EA.
- Python processes every accepted tick in a batch, including same-millisecond
  observations. The screen receives the newest state at a 200 ms polling cadence;
  display refreshes may coalesce observations, while strategy evaluation does not.
- A light market_update response excludes bulk chart history and background
  journal/optimizer summaries. Full heartbeat/history refresh remains every two
  seconds. Losing the connection clears freshness rather than inventing prices.
- strategy.display exposes live RSI/Z, even when an oscillator is disabled as an
  entry filter. strategy.indicators and conditions retain decision evidence.
  Closed-bar confirmation therefore never becomes intrabar trading accidentally.
- The current candle is a separate observed-tick overlay. Its OHLC and volume
  cover only the received portion of the candle, not the broker's entire candle.
  It is never inserted into the engine's closed history or used to fill tick gaps.

## Native execution controls and remaining scope

The Orders page has explicit Start/Stop-wait controls with account/profile context,
lot cap and duration. Start requires a fresh capable DEMO session and confirmation
inside the app. Stop cancels an unused allowance; it does not close a position.
The old allowance was cancelled before the upgrade, without sending an order.

The Settings page removes the unusable real-account checkbox and instead states
the supported capability honestly. This revision does **not** implement or enable
real-money trading, general unlimited execution, or live manual BUY/SELL. Those
manual buttons retain their simulation label. The DEMO acceptance allowance is
still limited to one send and at most 0.01 lot. This is a partial fulfillment of
the requested user-controlled execution architecture, not a claim that REAL is
available. A periodic observer only reads the app's state; it is not another bot.

## Parameters prepared for DEMO comparison

No candidate from the previous 720 parameter experiments passed the held-out
checks. Research_M1_RSI7_Demo.json records the training-ranked M1 nominee:
RSI(7), buy/sell thresholds 40/60, reversal 3. Z is displayed but disabled as an
entry filter. Its validation and final-test mean price outcomes were -0.178536
and -0.218797 after historical spread (2,465 test events). It is not profitable
or validated merely because it ranks highest by the training lower bound.

The M1-only, MA-disabled profile is an explicit proxy for the single-timeframe
event study. Those framework choices were not optimized. Tick confirmation,
server SL/TP and actual broker costs differ from the study; whole-strategy profit
is unproven. This profile is offered only for DEMO comparison. The separate
RSI(14)+Z(20) AND comparator is not silently mixed into the chosen profile.

Raw ranking evidence remains local in artifacts/research-demo-comparison/.
See RSI_Z_CALIBRATION_20260928.md for data sizes, splits and limitations.

## Native checkpoint — 2026-09-28 09:32 ICT

- Clean source `4a51b28b0e7dec5c44ea9a07f0a81f8637ef503f` passed 386 Python
  tests, 148 IPC contract checks and 84 desktop interaction assertions. All
  packaged smoke checks passed; MetaEditor reported zero errors and warnings.
  [CI run 36369800086](https://github.com/HoangHung997/XAUPY/actions/runs/36369800086)
  independently passed for the same source.
- The local package was copied to `dist/XAUPY-verified-tickui-final-win-x64` and
  every file was verified against its manifest before launch. EA 1.018 is
  attached to the existing Bridge chart with the 250 ms input confirmed; its
  native JSON self-test passed 23 cases. Other EAs were not changed.
- Native review caught a clipped duration/lot input in the first build. Hiding
  its spinner buttons makes both values readable. Strategy summaries now
  correctly say MA is disabled for this preset. These are presentation fixes;
  they do not alter the strategy or entry guards.
- `Research_M1_RSI7_Demo.json` was applied through the native Strategy import
  and confirmation dialog. It survived the app restart. The active profile hash
  is `3f832ad47c84b8d66118ce89de75d119de754b98546182a1d436f4b3ca4d3386`.
- At 09:31:41 ICT the native Orders Start button and its confirmation authorized
  one DEMO entry, at most 0.01 lot, for 1,440 minutes. The app shows CHỜ TÍN HIỆU
  and enables Stop; IPC independently reports ARMED with budget unconsumed.
  Earlier strategy signals were excluded by the authorization baseline. No
  broker fill has been observed at this checkpoint. Sessions start at 07:00
  broker time, approximately 11:00 ICT with the observed offset.
- Twenty read-only live samples of the unchanged tick-processing implementation
  over 4.28 seconds showed 15 distinct tick times/quotes, changing RSI and Z,
  and an M1 forming-candle count rising from 332 to 362 observed ticks. All 21
  checks passed. The active mode was intrabar: enabled RSI decision values
  correctly changed with ticks; disabled Z stayed null in decision evidence
  while its display value changed. Closed-bar separation is covered by isolated
  tests, not claimed as a live test on this intrabar profile.
- The existing five-minute task observer was updated for this native attempt.
  It only reads the running app/EA evidence, never generates signals, rearms,
  changes settings or sends orders. It stops after a verified fill or an
  actionable failure. The application itself continuously processes ticks.

Local evidence: `artifacts/tickui-build-final.log`,
`artifacts/tickui-live-samples.json`, `artifacts/tickui-native-arm-status.json`
and `artifacts/tickui-native-final/`. Account identifiers and raw observations
remain local. Strict 100% visual parity and general user-controlled REAL
execution remain unfulfilled; this checkpoint does not certify either.
