# XAUPY Task 008 — Strategy + Monitoring Realtime UI Specification

Status: DONE
Dependencies: XAUPY-005, XAUPY-007
Visual source-of-truth:
- docs/ui-reference/Tab Chiến Lược.png
- docs/ui-reference/Tab Giám Sát.png

## 1. Goal

Replace the Strategy and Monitoring placeholders with real Avalonia surfaces
driven by the Task 007 Python strategy projection and Task 003/005 market data.

Task 008 is presentation/projection work. It does not add broker execution.

## 2. Strategy tab

The Strategy tab must present the approved information hierarchy without copying
mock trading outcomes from the reference image.

It displays:

- strategy state and blocked reason;
- active profile and profile hash;
- Direction / Pullback / Trigger timeframes;
- current direction and armed side;
- MA, Pullback RSI/Z and Trigger RSI/Z values;
- optional ADX / ATR / Open-reference values when the backend produces them;
- Pullback and Trigger condition evidence;
- warm-up reasons and observed bar counts;
- last strategy reset/data error;
- last signal evidence and signal sequence.

The tab is read-only in Task 008. Canonical parameter editing remains owned by the
Task 006 Configuration tab so there is only one configuration authority.

## 3. Monitoring tab

The Monitoring tab displays only observed runtime data:

- current real BID/ASK from Overview;
- MT5 Bridge connectivity and snapshot age;
- current strategy state/direction;
- a session-local quote chart accumulated only when the Bridge snapshot timestamp
  changes;
- the current closed market bar for each active Direction/Pullback/Trigger
  timeframe;
- current MA/RSI/ADX/ATR values when available;
- condition state for the three active strategy timeframes;
- terminal/account mode and Bridge snapshot count;
- explicit alerts for stale Bridge, offline terminal, warm-up and strategy data
  errors.

The chart is not historical backfill. On a fresh Desktop session it starts empty
and grows only from real heartbeat snapshots received during that session.

## 4. Explicit unavailable states

The approved Monitoring mockup contains areas whose backend belongs to later
tasks. Task 008 must not fabricate those values.

Therefore:

- Session/News panel explicitly says realtime session/news backend is unavailable;
- CPU/RAM diagnostics explicitly says it belongs to XAUPY-014;
- order/manual execution controls are not enabled;
- execution remains visibly LOCKED.

## 5. Desktop IPC projection

EngineProcessSupervisor carries a typed StrategySnapshot parsed from the
heartbeat strategy object.

The Desktop must treat any nested strategy projection reporting
trading_enabled=true or execution_enabled=true as a protocol/safety failure.

When Engine/Bridge reconnects or becomes unavailable, stale strategy data is
cleared/projected as STALE instead of remaining visually live.

## 6. Overview integration

The existing Overview strategy card must stop saying the Task 007 backend does
not exist. It now displays the real strategy state and active strategy
timeframes from the heartbeat projection.

## 7. Acceptance

- both approved reference PNGs exist and remain packaged;
- Strategy and Monitoring are real hosted controls, not placeholders;
- strategy projection parser tests pass;
- Strategy tab required realtime controls are data-driven;
- Monitoring quote chart only advances on a new real snapshot timestamp;
- active closed bars are read from Overview.Bars without synthetic backfill;
- later-task data is explicitly unavailable instead of mocked;
- nested strategy execution enable is rejected;
- all previous Python tests pass;
- C# IPC contract tests pass;
- Avalonia Release build passes with 0 warnings / 0 errors;
- packaged Task 007 Engine strategy smoke still passes unchanged;
- Task 003 MT5 Bridge still compiles 0 errors / 0 warnings;
- a complete Windows x64 Task 008 artifact is produced and independently inspected.
