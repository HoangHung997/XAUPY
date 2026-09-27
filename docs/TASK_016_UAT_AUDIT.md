# XAUPY Task 016 — RC2 acceptance audit

Date: 2026-09-28. Candidate: **0.16.0-rc2**. Status: **ACTIVE — final release acceptance pending**.

This document records RC2 evidence separately from the accepted RC1 baseline. The original [RC1 release acceptance](TASK016_RELEASE_ACCEPTANCE.md), workflow run `36340716356`, artifact checksums, installer round trip and live MT5 captures remain historical evidence for source `a9137702661c810b301d388ce23230791dcd137c`. They do not certify the changed RC2 source or artifact. Strict 100% parity with the ten UI references is still unfulfilled; current visual evidence belongs in [UI_REFERENCE_PARITY_AUDIT.md](UI_REFERENCE_PARITY_AUDIT.md).

## Concrete changes from RC1

| Area | RC1 baseline | RC2 behavior |
| --- | --- | --- |
| Historical data | 256 closed bars per timeframe bootstrap the UI/strategy; bounded realtime caches | Separate official-MT5 reader pages all currently accessible closed candles into SQLite and ascending CSV without an application row cap |
| History operation | No packaged full-history download action | Tools → Xuất / Nhập dữ liệu launches an isolated collector; progress, output directory, coverage and provider limits are available through maintenance IPC |
| Tick observations | Quote and closed-bar snapshots | EA sends ordered `bridge_ticks` frames with stream ID, sequence and continuity information; same-millisecond source order is retained |
| RSI/Z mode | Closed-bar confirmation | Closed-bar remains default; explicit opt-in retains observed thresholds/extrema inside a candle and confirms only in a later permitted Trigger candle |
| Strategy editing | Mainly active-profile projection and file actions | Editable strategy controls, validation/persistence and draft/reconnect/external-change handling have dedicated interaction tests |
| Release packaging | RC1 ZIP and installer already verified in CI | Distinct RC2 filenames; official MetaTrader5/NumPy bundled and checked inside the executable; intrabar socket smoke added to the build |

Broker order placement, modification and closure remain hard-locked. The collector does not log in, switch accounts, change terminal settings or call order APIs. Existing active profiles are not automatically changed to tick mode. Synthetic protocol tests use isolated temporary state and ports.

## Historical acquisition evidence

The terminal initially reported Max bars 100,000. The first collection contains 598,630 closed candles; M1–M30 reached that configured cap. The user-authorized terminal setting was then changed to Unlimited; a fresh provider query reported **100,000,000** without restarting MT5. The following collection is the fixed research input:

`data/mt5-history/XAUUSD-20260928-unlimited/`

| Timeframe | Closed candles |
| --- | ---: |
| M1 | 100,062 |
| M3 | 100,000 |
| M5 | 100,012 |
| M15 | 100,000 |
| M30 | 100,083 |
| H1 | 53,325 |
| H2 | 29,244 |
| H4 | 16,068 |
| Total | **598,794** |

All eight timeframes ended with `PROVIDER_BOUNDARY_OR_ERROR` after retrying and shrinking the final request to one row. Additional bounded date-based probes before the oldest M1/M3/M5 data did not extend the archive; the provider returned only a boundary row. The result is therefore **history currently accessible from this terminal/provider**, not proof of all history held by the broker. MT5 was not restarted to force a different cache lifecycle.

`manifest.json` records the actual terminal limit, excluded forming-bar boundary, first/last timestamp, row count, provider error, CSV SHA-256 and gap coverage. Gap counts include market closures and possible provider gaps; they are not automatically labeled missing bars. Original MT5 timestamps are preserved without local-time conversion. Every timeframe fixes its current-bar cutoff before paging and deduplicates overlapping pages.

A separate read-only sample at `data/mt5-history/XAUUSD-20260928-ticks/` contains **10,150 real ticks** over approximately 30 minutes, with same-millisecond ordering preserved. Its manifest explicitly makes no live-stream continuity claim. Archive replay is research evidence; it does not alter the active profile or prove profitable execution. See [history/tick transport](MT5_HISTORY_AND_TICKS.md) and [intrabar signal semantics](INTRABAR_THRESHOLD_LATCH.md).

## Recorded local checks

| Check | Recorded result | Evidence / limitation |
| --- | --- | --- |
| Python combined suite | 324 tests PASS | `artifacts/rc2-final-python-tests.log`; full discovery in the isolated packaging environment, including direction-reset and storage-isolation regressions. Final CI must repeat against the release commit. |
| C# IPC contracts | 102 checks PASS | `artifacts/rc2-final-contract-tests.log` |
| Avalonia interaction tests | 51/51 PASS | `artifacts/rc2-final-interaction-tests.log`; repeated after UI source freeze, isolated Engine, no MT5 connection |
| Packaged intrabar socket smoke | 16 checks PASS | `scripts/smoke_intrabar_engine.py`; threshold retreat, later confirmation, duplicate sequence, gaps, stale market, wrong symbol and closed-bar mode |
| Packaged maintenance/config | PASS | Settings/restart, backup/recovery, diagnostics, process identity and profile tool checks |
| Packaged history provider | PASS | MetaTrader5 5.0.6231 and NumPy 2.5.3 import from the executable; NumPy is explicitly included because the native MT5 extension loads it dynamically |
| Packaged history download | PASS | Eight real MT5 timeframes completed while 75 heartbeats were served; highest observed response 0.9614 ms in this local run |
| EA compilation | 0 errors / 0 warnings | `artifacts/ea-intrabar/compile.log`, version property 1.016 |
| Final RC2 full build, installer, CI | Pending | RC1 installer/CI results are retained separately; no local installer execution is claimed for RC2 |
| New EA → RC2 Engine live acceptance | 19/19 checks PASS | `artifacts/live-bridge-rc2-ticks.json`; 13 actual read-only samples. This protocol probe explicitly does not certify Avalonia rendering. |
| RC2 Avalonia live/restart acceptance | Pending final evidence | Requires the actual RC2 Desktop/Engine state and fresh recovery evidence |
| RC2 ten-page visual audit | Pending final capture | Source/build/interaction checks do not establish pixel equivalence |

The packaged history acceptance used the same collector implementation before the subsequent telemetry, storage-isolation and strategy-regression Engine rebuilds. Dependency, maintenance and intrabar smokes were repeated on the latest runtime. Runtime files and their SHA-256 values are recorded in `artifacts/rc2-runtime/runtime-package-evidence.json`; collector details are in `artifacts/rc2-runtime/history-job-evidence.json`. These local runtime packages are test artifacts, not the final CI-delivered ZIP/installer.

### Test-journal isolation correction

The final visual review found rejected synthetic `place_order` / `trade_intent`
test messages in the user's journal. Legacy Python protocol tests supplied a
temporary settings directory but omitted the other store paths; EngineServer
therefore still wrote their diagnostic events to the normal user journal.
Packaged smoke and headless interaction tests already supplied all four isolated
paths. No broker order API was enabled or invoked, and the current test runs did
not change the user's persisted profile.

EngineServer now derives every unspecified store from an explicitly scoped
runtime directory. The regression emits a rejected command and proves that the
production sentinel journal and repositories are untouched. A subsequent full
324-test run left production rejection-event counts and profile SHA-256 unchanged
(`artifacts/rc2-test-isolation-evidence.json`). Existing journal entries remain
preserved as evidence; earlier Journal captures must not be described as a pure
record of live EA activity. Raw journal/profile content is not committed.

## Required final live evidence

The actual version-1.016 EA was attached for the read-only RC2 probe. Across 13
samples in 12 seconds, snapshots increased **36 → 49**, accepted tick frames
**1 → 14**, and received ticks **1 → 60**. The final tick sequence was 14 with
`complete=true`. All eight timeframes held 256 genuine closed bars; demo mode,
execution locks, fresh snapshots, valid quotes, ready strategy/history and tick
transport progression passed all 19 checks. The probe sent only `hello` and
`heartbeat`. These aggregate counts contain no account identity or balances;
the complete evidence remains local and is not included in Git.

Keep the current profile's `confirm_closed_bar=true` while verifying the new EA. An increasing `heartbeat.tick_transport.received_batches/received_ticks`, advancing stream sequence and current receipt age prove transport without opting into intrabar strategy mode. Invalid/stale/mismatched frames do not increment the summary; retransmissions are receipt counts, while strategy sequence handling stays idempotent.

The final probe must additionally establish stable Engine ownership/READY, actual quote and closed-bar history, snapshot progress, all execution locks and recovery after the supported Engine restart flow. A successful connection is not permission to mutate broker orders. Record the actual artifact/source identity and probe path here when complete; do not replace a missing live check with synthetic fixture results.

RC2 delivery should contain `XAUPY-0.16.0-rc2-win-x64.zip` and `XAUPY-0.16.0-rc2-Setup.exe`, a build manifest and checksums. Final CI/source/artifact identifiers, installer verification and consolidated test counts remain to be appended after completion. Calibration findings belong in their separate research report and are not a profitability claim or an instruction to activate a candidate profile.
