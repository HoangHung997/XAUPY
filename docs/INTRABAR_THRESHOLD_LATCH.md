# Observed-tick RSI/Z threshold latching

This extension produces strategy evidence only. Broker trading and execution remain locked.

`trigger.confirm_closed_bar=true` retains the established closed-bar pipeline and is the default. Setting it to `false` opts into actual observed tick batches. No active user profile is changed automatically. The canonical schema remains 133 parameters; old complete profiles remain valid.

## Signal semantics

- Direction, MA and optional ADX/ATR/Open gates use only bars already closed at the tick timestamp.
- Pullback and Trigger RSI/Z use their independent configured periods/timeframes. Their forming value is computed from the preceding closed closes plus the current valid Bid. A tick is never appended as another closed candle. Wilder RSI advances once from the closed-bar state for every observation.
- Each enabled Pullback threshold is latched for its permitted side within the current Pullback candle. AND may collect its conditions at different observations in that candle; OR needs any enabled condition. Partial AND observations are not combined across different Pullback candles or direction changes.
- An armed setup retains its observed Trigger peak for SELL or trough for BUY even when the indicator retreats before the candle closes. Trigger AND/OR and reversal deltas remain independently configurable.
- Confirmation is allowed only from a later Trigger candle, never on the candle that armed the setup. For example, SELL Z=2.5 followed by Z=2.2 in the next candle satisfies a configured 0.3 reversal. A numerical tolerance of 1e-12 prevents binary floating-point roundoff from rejecting equality; a genuinely smaller move does not pass. RSI follows the same rule.
- `entry.max_signal_age_bars` also bounds the number of following Trigger candles in which an intrabar setup may confirm. A value of 1 allows only the next Trigger candle. The default 2 permits the next two candles. A setup beyond that limit expires and its latched extrema are cleared.
- A setup emits at most one signal. It must leave the raw Pullback zone before another setup can start. Changes of profile/direction, filtering, missing just-closed history, transport discontinuity or a skipped Trigger candle invalidate the current latch.

## Tick contract and failure behavior

The optional `bridge_ticks` payload is `{symbol, server_time, tick_batch}`. `tick_batch` contains a nonempty `stream_id`, positive `sequence`, boolean `complete`, and at most 1000 `ticks`. The wire validator requires integer `time_msc` and `flags`, plus finite nonnegative `bid`, `ask`, and `last`; optional volume fields may also be archived. Strategy calculations use Bid, and do not treat Last or volume as an indicator observation. Equal-millisecond observations retain their supplied order. A repeated sequence is ignored. Negative, nonfinite, reversed-time and reversed-quote data are rejected before changing strategy state. Records with a zero quote retain transport ordering but do not supply an indicator observation.

The entire first packet of a stream and every incomplete/gapped packet are baseline evidence, never replayed as historical signals. Resetting strategy after stale data also clears stream continuity, so the next packet establishes another baseline. Runtime latches are not persisted or restored.

The EA must send fresh closed-bar snapshots before its corresponding tick packet. At a timeframe rollover, the strategy waits for the just-observed candle to appear in closed history. Missing history invalidates the setup and reports `CLOSED_BAR_PENDING`; later arrival cannot resurrect its old peak. For batches spanning a rollover, every indicator lookup filters history at the individual event timestamp, excluding later closes even when present in the packet's snapshot.

Optional `strategy.intrabar` status exposes the observation mode, stream/sequence, last tick time, observed count, current candle times, individual threshold latches, setup latches, current-bar min/max values, retained setup extrema and reason. A tick signal includes observation timestamp, stream/sequence and the latch/reversal evidence. These are observations received by the engine, not a guarantee that every market tick was captured.

## Historical validation boundary

The existing M1 OHLC BacktestEngine explicitly rejects `confirm_closed_bar=false`: OHLC does not establish intrabar indicator observation order. It does not silently approximate real ticks. Any separate high/low event study must label its approximation and cannot claim tick parity or profitability.

`scripts/replay_intrabar_ticks.py --history-dir <MT5 CSV directory> --ticks <tick-batches.jsonl> --out <evidence.json>` replays genuine archived observations in memory. `--profile` optionally selects a research profile; the selected profile is copied and only that in-memory copy enables tick mode. Historical bars seed warm-up and are released at their actual close time. Same-millisecond ordering is preserved. The output states explicitly that live continuity, account mutations, broker execution and profitability are not claimed.

The regression suite covers intra-candle retreat and later confirmation, symmetric BUY, RSI, independent AND observations, exact numerical boundaries, expiry, missing closes, idempotency, reconnect/gaps, profile resets, immutable closed history and no future-bar use. Closed-prefix caching plus one-step Wilder calculations avoids repeatedly traversing all historical prices for each tick.
