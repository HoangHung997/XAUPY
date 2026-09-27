# MT5 history and observed ticks

Tools → Xuất / Nhập dữ liệu → **Tải lịch sử MT5** starts a separate read-only collector process. Choose the installed `terminal64.exe` and symbol. **Tiến độ** shows progress, output directory, provider errors and coverage. The collector uses the official MetaTrader5 Python package bundled in Windows releases. It never calls login, account switching, order or terminal-settings APIs. The existing terminal session supplies the account and symbol.

The collector pages 5,000 candles at a time across M1/M3/M5/M15/M30/H1/H2/H4 into SQLite and exports one ascending CSV per timeframe. The 256-bar realtime UI bootstrap and 4,096-bar strategy working window are independent of this disk archive. There is no application row cap. MT5's configured Max bars and actual terminal/broker availability bound the result. Failed full pages are retried and reduced down to a one-row boundary probe; the report distinguishes a configured cap from a provider boundary/error. Neither means that all history ever held by the broker was obtained.

Each timeframe captures its current bar open before paging and excludes that bar and newer bars throughout acquisition. Overlapping page timestamps are deduplicated. CSV columns: `time,open,high,low,close,tick_volume,spread,real_volume`. MT5 epoch values are preserved without local-time conversion. `manifest.json` includes counts, first/last timestamp, excluded forming-bar boundary, SHA-256, provider error and gap counts. A gap is an interval greater than the nominal timeframe; closures and missing provider data are not automatically classified. Historical gaps must be considered before calibration/backtesting.

Downloads are stored below the user's XAUPY state directory in `market-history/<job>`. Closing Engine stops its owned collector, retaining already committed pages. Development entry point: `scripts/collect_mt5_history.py --terminal <absolute path> --output <directory>`. The isolated process prevents terminal history synchronization from blocking the IPC heartbeat.

## Ordered realtime ticks

After the normal closed-bar snapshot, EA sends a separate `bridge_ticks` envelope:

```json
{"symbol":"XAUUSD","server_time":1790561000,"tick_batch":{"stream_id":"unique stream","sequence":1,"complete":false,"gap_reason":"STREAM_BASELINE","ticks":[{"time_msc":1790560999123,"bid":2000.1,"ask":2000.3,"last":0,"flags":6}]}}
```

`CopyTicks(COPY_TICKS_ALL)` supplies at most 1,000 observations per frame. The cursor is the last millisecond plus the number of observations already emitted within that millisecond; equal-timestamp ticks retain source order. New streams/reconnects, copy errors, long synchronization, cursor gaps and excessive same-millisecond batches explicitly lose continuity. Python baselines the next stream instead of replaying historical entry signals. Only a fresh matching-symbol EA snapshot admits tick analysis. Sequence duplicates are idempotent; sequence gaps clear threshold/extreme state. Zero quotes can represent an empty book and never form an indicator entry.

Heartbeat `tick_transport` reports accepted frame/tick receipt counts, latest stream/sequence, continuity flag, gap reason and receipt age independently of closed-bar/intrabar strategy mode. Invalid, stale and mismatched-symbol frames do not increment these counters. Transport retransmissions count as receipts; strategy sequence handling remains idempotent. No raw tick array is retained in this summary.

EA's `OnTick` callback does not promise every tick. CopyTicks may itself block while MT5 synchronizes; a call taking over two seconds is marked incomplete and discarded, and Python rejects ticks when its preceding snapshot is stale. This cannot guarantee an uninterrupted stream under all terminal/network conditions. Bulk candle download remains outside EA. The strategy uses actual observed tick paths when intrabar mode is enabled and filters closed bars at each tick's time. Default closed-bar confirmation remains enabled. Broker execution remains hard-locked in both modes.

Official references: [CopyTicks](https://www.mql5.com/en/docs/series/copyticks), [copy_rates_from_pos](https://www.mql5.com/en/docs/python_metatrader5/mt5copyratesfrompos_py), [copy_rates_range](https://www.mql5.com/en/docs/python_metatrader5/mt5copyratesrange_py).
