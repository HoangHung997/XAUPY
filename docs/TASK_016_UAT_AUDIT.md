# XAUPY Task 016 — RC2 acceptance audit

Date: 2026-09-28. Candidate: **0.16.0-rc2**. Build/CI/installer and live acceptance of both the local build and the downloaded CI runtime: **PASS**. Task 016 remains **ACTIVE** because strict 100% UI parity has not been met.

The acceptance sections below retain the RC2 baseline at `7f968266`. A subsequent
UI refinement at `5dc7a6e` has its own CI/artifact, live-probe and native-capture
evidence at the end of this document, independently of the baseline.

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
| Python combined suite | 324 tests PASS | Local full build and both Linux/Windows CI jobs on source `7f968266a288a33ff0f30ac2b215004644a9dd95`, including direction-reset and storage-isolation regressions |
| C# IPC contracts | 102 checks PASS | `artifacts/rc2-final-contract-tests.log` |
| Avalonia interaction tests | 51/51 PASS | `artifacts/rc2-final-interaction-tests.log`; repeated after UI source freeze, isolated Engine, no MT5 connection |
| Packaged intrabar socket smoke | 16 checks PASS | `scripts/smoke_intrabar_engine.py`; threshold retreat, later confirmation, duplicate sequence, gaps, stale market, wrong symbol and closed-bar mode |
| Packaged maintenance/config | PASS | Settings/restart, backup/recovery, diagnostics, process identity and profile tool checks |
| Packaged history provider | PASS | MetaTrader5 5.0.6231 and NumPy 2.5.3 import from the executable; NumPy is explicitly included because the native MT5 extension loads it dynamically |
| Packaged history download | PASS | Eight real MT5 timeframes completed while 75 heartbeats were served; highest observed response 0.9614 ms in this local run |
| EA compilation | 0 errors / 0 warnings | `artifacts/ea-intrabar/compile.log`, version property 1.016 |
| Final RC2 full build, installer, CI | PASS | Clean local full build; GitHub run `36359181671`; installer install/hash/uninstall round trip on Windows CI. Installer not run locally. |
| Downloaded CI EA → RC2 Engine live acceptance | 19/19 checks PASS | `artifacts/live-bridge-rc2-ci.json`; 21 actual read-only samples in 20 seconds; deployed EA and running Engine match the CI manifest hashes. This protocol probe explicitly does not certify Avalonia rendering. |
| RC2 Avalonia live/restart acceptance | Local full-build PASS | Native Stop closed port 39421; Start created a new owned Engine and EA reconnected in approximately three seconds; stable probes before/after restart each pass 19/19 |
| RC2 ten-page visual audit | Local-build and downloaded-CI native captures | Ten native pages captured on each build, including `artifacts/ui-audit-rc2-ci/`. This does not establish exact pixel equivalence; see the separate visual audit. |

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

## Live acceptance evidence

The actual version-1.016 EA was attached for the read-only RC2 probe. Across 13
samples in 12 seconds, snapshots increased **36 → 49**, accepted tick frames
**1 → 14**, and received ticks **1 → 60**. The final tick sequence was 14 with
`complete=true`. All eight timeframes held 256 genuine closed bars; demo mode,
execution locks, fresh snapshots, valid quotes, ready strategy/history and tick
transport progression passed all 19 checks. The probe sent only `hello` and
`heartbeat`. These aggregate counts contain no account identity or balances;
the complete evidence remains local and is not included in Git.

Keep the current profile's `confirm_closed_bar=true` while verifying the new EA. An increasing `heartbeat.tick_transport.received_batches/received_ticks`, advancing stream sequence and current receipt age prove transport without opting into intrabar strategy mode. Invalid/stale/mismatched frames do not increment the summary; retransmissions are receipt counts, while strategy sequence handling stays idempotent.

Native acceptance supplements the protocol probe with observed Engine ownership/READY, UI state and the supported Stop/Start recovery flow. It retains actual quote/history, snapshot progress and execution-lock checks; no synthetic fixture is substituted for a missing live observation.

The clean local full build from source `7f968266a288a33ff0f30ac2b215004644a9dd95`
was then exercised in the native Desktop. The deployed EA was independently
compiled from identical MQL source. `artifacts/rc2-live-acceptance-summary.json`
records the following aggregate evidence:

- Before restart, `artifacts/live-bridge-rc2-release.json` passes 19/19 checks over
  16 samples; tick frames advance 10→25 and received ticks 65→160.
- Native Stop reaches STOPPED and closes port 39421. Start reaches READY with a
  new owned Engine process; the actual EA reconnects in approximately three seconds.
- The immediate startup probe is retained in
  `artifacts/live-bridge-rc2-restart-transition.json`; its expected initial
  unavailability fails the continuous-connected criterion rather than being hidden.
- After visible READY, `artifacts/live-bridge-rc2-restart-ready.json` passes 19/19
  checks over 16 samples; tick frames advance 45→60 and received ticks 254→317.
- Each stable probe retains 256 closed bars in all eight timeframes and verifies
  execution locks. These protocol checks are accompanied by actual native UI
  Stop/Start observations and the ten-page capture, not substituted for them.

The independently downloaded CI application was then launched from
`dist/XAUPY-verified-rc2-win-x64/`, with its exact compiled EA deployed to MT5.
`artifacts/live-bridge-rc2-ci.json` passes **19/19 checks across 21 samples in
20 seconds**: accepted tick frames advance **50→70** and received ticks
**232→429**. The probe remains read-only (`hello` and `heartbeat` only), checks
demo/execution locks, and observes fresh quotes, closed history and advancing
snapshots. Aggregate identity and counters are retained in
`artifacts/rc2-ci-live-summary.json`.

The deployed EA SHA-256 is
`3732657063009ab529054cc39da81059def557a6bee9641faf2caf6057acc04b` and the
running CI Engine SHA-256 is
`010f6c0683c8d8b34de7b5700f1227061c6a61d8bd4ef787c824680884b3b2ea`;
both match the independently verified CI manifest. Separate native observations
show Desktop READY and capture all ten pages in `artifacts/ui-audit-rc2-ci/`.
Stop/Start recovery evidence above belongs to the clean local build; the CI
probe and capture establish the final delivered runtime's connected operation.

## RC2 baseline CI and independently verified delivery — `7f968266`

- [GitHub run 36359181671](https://github.com/HoangHung997/XAUPY/actions/runs/36359181671)
  succeeds on source `7f968266a288a33ff0f30ac2b215004644a9dd95` for both validation
  and Windows packaging. The build manifest records `working_tree_modified=false`,
  `tests_executed=true` and `broker_execution_locked=true`.
- CI repeats 324 Python tests, 102 C# contracts, 51 desktop interaction assertions,
  all nine packaged smoke categories including 16 intrabar socket checks, the
  MetaTrader5/NumPy provider check and zero-error/zero-warning EA compilation.
- Windows CI installs the per-user installer, verifies every installed manifest
  hash, and uninstalls it successfully. No installer was executed on the user's PC.
- Downloaded artifact `10945071140` contains the ZIP, installer, checksums and
  standalone manifest. The outer artifact is 223,309,381 bytes with SHA-256
  `80e43e9253d05a0858b1103f452b3f9d29060820d68f6d2c3c0aaafff2d6b277`.
- Independent verification checks all **282 portable files / 281 manifest hashes**,
  the clean source identity, three x64 application tools, self-contained runtime,
  EX5 compile log, ten approved reference images and canonical execution locks.
  Extracted files are hashed again; the baseline retains closed-bar confirmation.
- CI portable ZIP SHA-256:
  `ebbd807f2977b2eb5d61d8936a01784f92666304e1c03fa8c4768653f455a30b`.
- CI installer SHA-256:
  `2f9463c035c03e40b59367fb9cc2ac66d6aa53c01600979296fffc6c5114b44a`.
- Verified CI pair: `dist/rc2-ci/XAUPY-0.16.0-rc2-win-x64.zip` and
  `dist/rc2-ci/XAUPY-0.16.0-rc2-Setup.exe`. Download metadata, complete CI log and
  verification result remain in `artifacts/ci-rc2-download/`.
- Verified extracted CI application: `dist/XAUPY-verified-rc2-win-x64/`.
  Its Engine provider check passes locally; the exact CI EA/Engine live probe
  passes 19/19 across 21 samples, with separate native Desktop READY and ten-page
  capture evidence recorded above.
- The independently built local ZIP remains separate at
  `dist/XAUPY-0.16.0-rc2-win-x64.zip` (SHA-256
  `012e9cbeef62011dd1b3611963aac6026a630cc7847f92cc4aac1cdb14667244`).
  The already verified RC1 files and their evidence are preserved.

Calibration findings belong in their separate research report and are not a
profitability claim or an instruction to activate a candidate profile. Final
documentation may be committed after the release source; the artifact's exact
source remains the commit recorded in its manifest.

## UI refinement CI and delivery — `5dc7a6e`

The next RC2 revision keeps the prior release evidence and files separate. It
adds a syntax-colored native JSON editor with line numbers, selection/undo,
search/format/fullscreen shortcuts; persisted Settings switches; the Monitoring
timeframe matrix and indicator gauges; and further layout/control corrections.
Conditions being warmed up or ready do not imply all entry conditions passed.
The JSON editor uses the TextBox's real text layout, not a screenshot overlay.

- [GitHub run 36361798910](https://github.com/HoangHung997/XAUPY/actions/runs/36361798910)
  succeeds on source `5dc7a6ea1f4cafe50e9316028a19c797830457b9` in validation
  and Windows packaging. Its manifest records clean source, executed tests and
  locked broker execution.
- Linux and Windows each pass **324 Python tests / 102 C# contract checks**.
  The Windows packaged runtime passes **76 desktop interaction assertions**,
  all nine packaged smoke categories including **16 intrabar socket checks**,
  the bundled provider check and EA compilation with zero errors/warnings.
- The additional desktop assertions exercise native JSON editing, selected-text
  replacement, undo, routed search/format/F11 shortcuts, synchronized gutter
  scrolling, Settings persistence across an isolated Engine restart, profile
  preservation and Monitoring matrix/gauge evidence. These tests use temporary
  stores and ports without a live MT5 connection.
- Windows CI installs the installer, verifies installed manifest hashes and
  uninstalls it. The installer is downloaded but not run on the user's PC.
- Artifact `10945744624` is **223,357,228 bytes**, expires
  `2026-10-12T00:24:06Z`, and has outer SHA-256
  `f001a440b12c089dc5abdf8de38211a9015aee778871a50175f4c2eb655e681c`.
- Independent inspection verifies **282 portable files / 281 manifest hashes**,
  source identity, x64 Desktop/Engine/config tools, self-contained runtime,
  compile log, ten reference images and baseline safety locks. Archive traversal,
  symlink and duplicate/case-collision checks pass; extracted/copied files are
  hashed again. `confirm_closed_bar=true` remains the baseline.
- Portable ZIP SHA-256:
  `9216a86e2bbc82bca52a31b0d914f0f312483a7c04745e05605110df9e0ad5f5`.
- Installer SHA-256:
  `18ccdd0f4a7f67bcf2eea4b85d1ec29ee26a755d41a0183f25be849a6307984d`.
- CI EA SHA-256:
  `6d990c7f0a885e711aa5a911ea3ee9cef36e229aa0f10215a85ab31386b39434`.
- CI Engine SHA-256:
  `584e1d41c445bcfd8242d5479ed470474f180070cb0a0bafc6805e530840d3c3`.
- CI Desktop SHA-256:
  `9bf079eedb10e0c88bda5721dad4fbbbaf9d8eb19477bedc821e4b65dc4267c4`.
- Verified pair and checksums: `dist/rc2-refined-ci/`. Verified extracted app:
  `dist/XAUPY-verified-rc2-refined-win-x64/`. Metadata, complete CI log,
  verification result and provider check: `artifacts/ci-rc2-refined-download/`.
  The extracted executable reports MetaTrader5 **5.0.6231** / NumPy **2.5.3**.

### Exact refined-CI live acceptance

The exact new CI EA was deployed with unchanged inputs/security, and Desktop was
launched from `dist/XAUPY-verified-rc2-refined-win-x64/` with the matching Engine.
`artifacts/live-bridge-rc2-refined-ci.json` passes **19/19 read-only checks across
21 samples in 20 seconds**. Accepted tick frames advance **32→53** and received
ticks **321→614**. The running Engine and installed EA match the manifest hashes
above; execution remains locked. The aggregate identity/counter evidence is
`artifacts/rc2-refined-ci-live-summary.json`.

All ten pages of this exact compiled Desktop were captured separately in
`artifacts/ui-audit-rc2-refined-ci/`, with visible local clocks 07:33:26–07:33:38
on 2026-09-28. Native visual assessment belongs to
[UI_REFERENCE_PARITY_AUDIT.md](UI_REFERENCE_PARITY_AUDIT.md); the read-only probe
does not itself prove rendering or pixel parity. These are new observations of
the refined artifact, while earlier 19/19 probes, Stop/Start recovery and native
captures retain their stated source/artifact scope. Strict 100% visual parity
is not certified; Task 016 remains ACTIVE.
