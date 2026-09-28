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

Build/native deployment evidence will be appended after validation.
