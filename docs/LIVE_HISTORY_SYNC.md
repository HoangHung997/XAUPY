# MT5 closed-history synchronization

The bridge can now warm the Python strategy and Avalonia chart from genuine MT5
history at connection time. It does not wait for hundreds of future candles and
does not generate synthetic market prices.

## Wire contract

`bridge_snapshot` retains its existing protocol version, `bars` latest-bar map,
and execution locks. It optionally adds:

- `server_time`: integer MT5 broker timestamp;
- `tick_time_msc`: optional original `MqlTick.time_msc`, distinct from snapshot
  receipt time; absent/zero remains unknown. The overview exposes this as
  `tick_time_msc` and C# as nullable `OverviewSnapshot.TickTimeMsc`. A fresh IPC
  snapshot may still carry Friday's last quote while the market is closed;
- `bar_history`: a map from M1/M3/M5/M15/M30/H1/H2/H4 to arrays of up to 256 closed
  OHLC bars with the existing `time/open/high/low/close/tick_volume` fields.

The EA captures each latest bar and history array from the same `CopyRates`
result, beginning at shift 1. Arrays preserve the broker's timestamps and run
oldest to newest. The forming candle is excluded. History is transmitted on the
first snapshot after connection/reconnection and every 60 seconds; incomplete
MT5 data is retried at the next refresh. Legacy snapshots without either field
remain accepted.

The EA bounds each outgoing envelope to 1 MiB and handles partial socket sends.
Python already uses the same 1 MiB input limit. History is separately bounded to
eight timeframes and 256 rows per timeframe, so ordinary chart heartbeats remain
bounded as well.

The EA reads only bytes reported available by `SocketIsReadable`, accumulates
them until the newline delimiter, and decodes UTF-8 only after the full frame is
available. The entire read has one timeout and a 1 MiB bound; partial JSON is
never validated as a complete acknowledgement. Repeated socket errors are
logged at most every ten seconds, with configuration guidance for error 4014.
The availability check follows the documented
[MQL5 socket reading contract](https://www.mql5.com/en/docs/network/socketisreadable).

## Validation and strategy timing

Python rejects the entire history snapshot if the shape, OHLC, ordering, count,
or timestamp is invalid. Each history bar must have fully closed by the supplied
MT5 server time and must not be newer than the latest closed bar for its
timeframe. The last history row and latest row must agree when their timestamps
match. A rejected snapshot leaves previously accepted market state intact.

Initial history, an older backfill, or a gap recovery seeds indicator history
and resets the actionable setup once. Historical bars are never replayed through
entry generation. Only the current closed snapshot is evaluated after seeding;
old setups cannot produce a historical entry. Repeated history refreshes preserve
the current setup. A strategy symbol change clears history from the former
symbol.

The bridge registry retains and merges real bars between history refreshes,
capping the chart projection at 256 rows per timeframe. The heartbeat exposes
`overview.bar_history`; C# parses it as `OverviewSnapshot.BarHistory`. Older
clients continue using `overview.bars` unchanged. Disconnected/stale overview
responses expose no active market history.

## Validation performed

On 2026-09-28, ten focused history tests passed, including a real local socket
exchange carrying all 8 × 256 bars (larger than 64 KiB), indicator warm-up,
no historical entries, reconnect recovery, malformed/future/oversize rejection,
legacy compatibility, and symbol isolation. The complete Python regression
suite passed 278 tests; C# IPC contract tests passed 85 checks, including history
parsing and a warm-up heartbeat without indicator objects.

All packaged Task 007/009/010/011/012/013 and config CLI smokes passed with
isolated state/log/backtest/optimizer directories. Restart tests intentionally
reuse their own temporary paths. They cannot write their test profiles into the
user's saved runtime profile.

MetaEditor compiled the framed-reader EA with 0 errors / 0 warnings. The live
read-only MT5 demo probe `artifacts/live-framed-reader.json` passed 11 samples
(snapshot counters 203→214, maximum reported age 952 ms, 256 bars per timeframe).
A stronger probe records the original tick timestamp, monotonic sample/snapshot
progress and all Engine/Strategy/EA execution locks. Its first run,
`artifacts/live-framed-reader-tick-locks.json`, passed all transport/history/lock
checks but failed tick metadata checks because the currently running Engine
returned a null tick timestamp. After repackaging, `artifacts/live-final.json`
passed all 16 checks across 11 samples, including the original tick timestamp.
The native Avalonia Stop/Start controls were exercised: quote/account values
cleared on STOPPED, then the EA reconnected automatically and all 8 × 256 bars
returned. `artifacts/live-after-ui-restart.json` also passed all 16 checks.
Old last-session prices are valid evidence while the market is closed. Avalonia
labels them “Giá gần nhất” and exposes the last tick time in its tooltip;
connection freshness is measured independently. No broker action was requested.

Quote age compares `tick_time_msc` with the EA's existing `server_time` field,
which uses [TimeTradeServer](https://www.mql5.com/en/docs/dateandtime/timetradeserver).
Both values share the broker clock; Desktop must not subtract its UTC/local clock
from a broker timestamp or relabel that timestamp as local time. Missing or
inconsistent server-clock metadata leaves freshness unknown.

History synchronization does not enable broker execution, trading
intents, real-account permission, or automatic retries. Profiles requiring more
history than MT5 has supplied continue to show warm-up honestly.
