# XAUPY — Implementation Tasks

## Execution rules

1. Work on one task only.
2. Do not start the next task until the current task is DONE.
3. DONE requires code + tests + GitHub CI evidence + required build artifact.
4. Product philosophy changes require an explicit spec update.
5. User smoke testing follows delivery only after the current task has a complete downloadable build.

## Status legend

ACTIVE — only task currently being implemented.  
PLANNED — not started.  
BLOCKED — dependency/user decision prevents work.  
READY_FOR_USER_TEST — CI/build complete, awaiting requested manual acceptance.  
DONE — implementation, automated evidence and required deliverable complete.

## Task table

| ID | Status | Task | Dependency | Required evidence |
|---|---|---|---|---|
| XAUPY-001 | DONE | Foundation, Avalonia shell, Python engine stub, CI Windows artifact | — | CI green + verified Windows zip artifact |
| XAUPY-002 | DONE | Versioned local IPC contract and process lifecycle | 001 | contract + reconnect/heartbeat tests + verified Windows build |
| XAUPY-003 | DONE | MQL5 Bridge data channel + execution guardian | 002 | MetaEditor compile + CI/static + bridge probe + verified Windows build |
| XAUPY-004 | DONE | Canonical configuration/profile model + .set import/export | 002 | schema/validation + .set round-trip/property + packaged tool + verified Windows build |
| XAUPY-005 | DONE | Overview tab implementation | 002,004 | UI/reference structure + real overview projection + verified Windows build |
| XAUPY-006 | DONE | Full Configuration tab | 004 | schema-driven 133-field editor + validation/profile/.set tests + verified Windows build |
| XAUPY-007 | DONE | Strategy engine Direction → Pullback → Trigger | 002,004 | deterministic state tests + verified Windows build |
| XAUPY-008 | DONE | Strategy + Monitoring realtime tabs | 005,007 | projection tests + verified Windows build |
| XAUPY-009 | ACTIVE | Orders & Positions + guarded manual actions | 003,005 | execution simulation |
| XAUPY-010 | PLANNED | Structured logging + Journal tab | 002,003 | schema/replay tests |
| XAUPY-011 | PLANNED | Backtest engine parity | 007,010 | deterministic replay |
| XAUPY-012 | PLANNED | Optimizer + walk-forward | 011 | reproducibility/leakage guards |
| XAUPY-013 | PLANNED | Dynamic TP/SL + stop-confirm entry | 003,007,011 | state/broker simulation |
| XAUPY-014 | PLANNED | Tools tab + diagnostics | 003,004,010 | diagnostics tests |
| XAUPY-015 | PLANNED | Settings, backup, startup, fail-safe UX | 002,003,004 | restart/recovery tests |
| XAUPY-016 | PLANNED | Installer, release workflow, demo acceptance | all prior | release + acceptance |

# XAUPY-001

Status: DONE. Evidence preserved in git history.

# XAUPY-002

Status: DONE. Evidence preserved in git history.

# XAUPY-003

Status: DONE. Evidence preserved in git history.

# XAUPY-004

Status: DONE. Evidence preserved in git history.

# XAUPY-005 — Overview tab implementation

Status: DONE

## Goal

Implement the approved Avalonia Overview dashboard using real read-only MT5 Bridge/config/Engine data, with no fake strategy/trading results.

## Visual source-of-truth

docs/ui-reference/Tab Tổng Quan.png

The implementation follows the reference information hierarchy rather than literal mock trading numbers.

## Scope completed

- XAUUSD symbol, BID, ASK and spread headline;
- account balance, equity, free margin, currency and MT5 account mode;
- persistent Guardian / EXECUTION LOCKED state;
- Desktop / Python Engine / MT5 Bridge system status;
- live BID-history lightweight chart fed only by actual Bridge snapshots;
- canonical profile summary:
  Direction TF / Pullback TF / Trigger TF / MA / TP / SL / risk limits;
- explicit Strategy Engine CHƯA CHẠY until Task 007 exists;
- real current position/order counts from Bridge snapshot;
- honest empty/detail-unavailable state instead of fabricated recent trades;
- quick local lifecycle event log;
- unfinished tabs are hidden behind explicit placeholders instead of reusing Overview;
- full Windows build retains Python Engine, config tool, profiles and MT5 Bridge.

## Data changes

Python BridgeRegistry exposes overview_payload().

Desktop heartbeat now includes an overview projection.

Avalonia IPC layer parses:

- OverviewSnapshot;
- ConfigurationSummary from Task 004 config_defaults_get.

If MT5 Bridge becomes stale, Overview clears live quote/account/chart data rather than presenting stale values as current.

## Explicitly out of scope retained

- strategy state machine;
- synthetic BUY/SELL signal;
- order execution;
- ticket-level order history;
- full Configuration editor;
- persistent structured trading journal;
- full candlestick/indicator chart.

## Acceptance criteria

- [x] UI reference image exists and structural UI test passes.
- [x] Overview contains price, system, account, chart, strategy, orders and quick-log groups.
- [x] other tabs show explicit placeholders instead of Overview data.
- [x] Overview Bridge projection tests pass.
- [x] stale Bridge clears live overview values.
- [x] packaged Engine Overview smoke test passes.
- [x] C# OverviewSnapshot parser checks pass.
- [x] canonical M30/M5/M1 config summary is loaded through config_defaults_get.
- [x] Python regression tests all pass.
- [x] C# IPC/Overview self-tests all pass.
- [x] Avalonia Release build passes with 0 warnings / 0 errors.
- [x] Task 003 MT5 Bridge regression compiles 0 errors / 0 warnings.
- [x] Windows full artifact contains Desktop, Engine, config tool, profiles, MQ5/EX5, Task005 docs and Overview UI reference.
- [x] GitHub CI green and uploads XAUPY-Task005-win-x64.
- [x] downloaded GitHub artifact independently inspected before delivery.

## Automated evidence

- Final source commit: 4460f3e82ff3b8dc6a3856657c28d430a59e162e
- Branch: task/005-overview-tab
- GitHub Actions final run: 36016882252
- Validate overview UI job: SUCCESS
- Windows x64 full overview build job: SUCCESS
- Python tests: 55/55 PASS
- C# IPC + Overview parser checks: 17/17 PASS
- Avalonia/.NET build: SUCCESS, 0 warnings, 0 errors
- Packaged Task 005 Python Engine overview/config/bridge smoke test: PASS
- Packaged xaupy-config smoke test: PASS
- MetaEditor regression compile: Result: 0 errors, 0 warnings, 1973 ms elapsed
- GitHub artifact: XAUPY-Task005-win-x64
- GitHub artifact id: 10815770184
- GitHub outer artifact SHA-256: 883d9a2df5235c83bcbb389d13da777d2bffe9cb16178eb4df240d99d8ed0de4
- Direct full-build ZIP SHA-256: 9ed0fda3e5a0d6297bc248a0eb45ee350311f6559ac66061bba6c47dd4d8f30f
- Artifact expiry: 2026-10-08
- Independent artifact inspection: 242 files
- XAUPY.Desktop.exe: present, PE32+ Windows x86-64
- engine/xaupy-engine.exe: present, PE32+ Windows x86-64
- tools/xaupy-config.exe: present, PE32+ Windows x86-64
- profiles/Baseline_M30_M5_M1.json: present, Direction=M30 Pullback=M5 Trigger=M1
- profiles/config-schema-v1.json: present, field_count=133
- exact timeframe options: M1, M3, M5, M15, M30, H1, H2, H4
- mt5/XAUPY_Bridge_EA.mq5/.ex5/compile.log: present
- docs/ui-reference/Tab Tổng Quan.png: present in artifact, 1,740,817 bytes
- Desktop runtime: net10.0 self-contained, Microsoft.NETCore.App 10.0.12 included

## Build/fix history

The first Task 005 CI run exposed a real Avalonia generated-name collision: the helper method name EngineStateText conflicted with the XAML control named EngineStateText.

The helper was renamed to GetEngineStateLabel and the complete CI/build pipeline was re-run. The final source commit above is the one that passed all tests and produced the verified full artifact.

## Delivery

The Task 005 Windows x64 full build is ready for manual smoke testing using docs/TASK005_OVERVIEW_TEST.md.

At Task 005 delivery, XAUPY-007 was still PLANNED.


# XAUPY-006 — Full Configuration tab

Status: DONE

## Goal

Implement the approved full Avalonia configuration workspace using the Task 004 canonical schema as the only field source.

## Visual source-of-truth

docs/ui-reference/Tab Cấu Hình.png

## Scope

- schema-driven rendering of all 133 canonical fields;
- grouped field cards and parameter search;
- bool/enum/string/time/int/float editors;
- disabled controls for locked safety values;
- exact independent Direction/Pullback/Trigger timeframe options;
- Defaults, Revert Active, Validate and Apply Active;
- active-profile get/set IPC owned by Python Engine;
- JSON open/save;
- MT5 .set import/export via packaged xaupy-config.exe;
- template preservation after .set import;
- Overview active-profile summary updates after Apply;
- full Task 003/004/005 regression coverage;
- complete Windows x64 build artifact.

## Explicitly out of scope

- strategy state machine;
- trade execution;
- live-account enablement;
- automatic startup persistence;
- backtest/optimizer;
- finished Strategy/Monitoring tabs.

## Hard safety

UI disables locked fields, but Python remains final authority.

The active profile cannot:

- enable real account;
- disable demo-only;
- enable broker retry;
- permit widening SL;
- remove required server SL;
- permit stale-market operation.

## Acceptance criteria

- [x] Configuration reference image exists.
- [x] all 133 canonical fields render from schema.
- [x] search/filter structure is present.
- [x] exact TF options remain M1/M3/M5/M15/M30/H1/H2/H4.
- [x] unusual timeframe ordering can validate/apply.
- [x] active profile get/set protocol tests pass.
- [x] invalid safety unlock cannot replace active profile.
- [x] JSON load/save actions exist.
- [x] .set import/export actions exist.
- [x] locked fields are disabled in UI.
- [x] Overview remains functional and receives active summary.
- [x] Python regression tests pass.
- [x] C# IPC/config parser tests pass.
- [x] Avalonia Release build succeeds with 0 warnings / 0 errors.
- [x] packaged Engine Task 006 active config smoke test passes.
- [x] packaged xaupy-config smoke test passes.
- [x] MT5 Bridge regression compiles 0 errors / 0 warnings.
- [x] Windows full artifact includes Desktop, Engine, config tool, profiles, MQ5/EX5, docs and both Overview/Configuration UI references.
- [x] GitHub CI green and uploads XAUPY-Task006-win-x64.

## Required artifact

XAUPY-Task006-win-x64.zip

## Automated evidence

- Final CI source commit: 0404b6f94ea4098650a3cebc7a9921b3e97491f7
- Branch: task/006-configuration-tab
- GitHub Actions final run: 36081310157
- Validate configuration UI job: SUCCESS
- Windows x64 full configuration build job: SUCCESS
- Python tests: 66/66 PASS
- C# IPC/config self-tests: 23/23 PASS
- Avalonia/.NET build: SUCCESS, 0 warnings, 0 errors
- Packaged Task 006 Python Engine active config/validation/safety smoke test: PASS
- Packaged xaupy-config defaults/validate/export/import smoke test: PASS
- MetaEditor MT5 Bridge regression: Result: 0 errors, 0 warnings, 2398 ms elapsed
- GitHub artifact: XAUPY-Task006-win-x64
- GitHub artifact id: 10841319551
- GitHub outer artifact SHA-256: 62b8253333b8e0f6a49c060d80547fc37af4fbfa2b65df23c4d4da1b2913dc53
- Direct full-build ZIP SHA-256: cd0dca3c972ab78f980b7460d642e4c9b8c7b4e955fbff215f92c151ae801881
- Artifact expiry: 2026-10-09
- Independent artifact inspection: 245 files
- XAUPY.Desktop.exe: present, PE32+ Windows x86-64
- engine/xaupy-engine.exe: present, PE32+ Windows x86-64
- tools/xaupy-config.exe: present, PE32+ Windows x86-64
- profiles/config-schema-v1.json: field_count=133
- Exact timeframe options: M1, M3, M5, M15, M30, H1, H2, H4
- profiles/Baseline_M30_M5_M1.json: Direction=M30, Pullback=M5, Trigger=M1
- Locked safety verified in packaged baseline: allow_real_account=false, demo_only=true, max_retry_count=0, never_widen_sl=true, require_server_sl=true, block_on_stale_market_data=true
- mt5/XAUPY_Bridge_EA.mq5/.ex5/compile.log: present
- docs/ui-reference/Tab Tổng Quan.png and Tab Cấu Hình.png: both present in ZIP with UTF-8 filenames
- Desktop runtime: net10.0 self-contained, Microsoft.NETCore.App 10.0.12 included

## Build/fix history

Task 006 CI found and resolved two implementation-quality issues before completion:

1. the Task 005 placeholder regression test still expected the old Task 005 wording after Configuration became a real tab;
2. Avalonia 12 reported obsolete TextBox.Watermark usage. Both XAML and code-behind were migrated to PlaceholderText.

The final run above is clean with 0 Avalonia/.NET warnings and 0 errors.

## Delivery

The full Task 006 Windows x64 build is ready for manual testing using docs/TASK006_CONFIGURATION_TEST.md.

At Task 006 delivery, XAUPY-007 was still PLANNED.


# XAUPY-007 — Strategy engine Direction → Pullback → Trigger

Status: DONE

## Goal

Implement the canonical deterministic Python strategy state machine on top of the
Task 003 closed-bar Bridge data and Task 004 active profile.

## Scope in implementation

- accumulate real closed bars independently for all 8 supported timeframes;
- Direction MA state using configured type/source/period;
- Pullback RSI/Z with configured AND/OR logic;
- Trigger RSI/Z reversal from armed extreme;
- optional ADX/ATR/Open research filters;
- explicit warm-up, wait, armed, triggered, stale and blocked states;
- profile hash and decision evidence projection;
- profile-change and reconnect reset rules;
- read-only strategy state in heartbeat and bridge_snapshot_ack;
- deterministic unit/IPC/package tests;
- full previous-task regression and Windows x64 build.

## Hard boundary

- no trade_intent;
- no broker execution;
- no live-account enablement;
- trading_enabled=false;
- execution_enabled=false;
- Task 003 MQL5 guardian remains locked.

## Acceptance criteria

- [x] indicator calculations are deterministic.
- [x] BUY Direction → Pullback → Trigger state test passes.
- [x] SELL state test passes symmetrically.
- [x] arming bar cannot trigger immediately.
- [x] duplicate/out-of-order bar handling is deterministic.
- [x] independent Direction/Pullback/Trigger TF behavior is tested.
- [x] profile change resets setup without inventing history.
- [x] stale/disconnected market projection is blocked.
- [x] reconnect resets setup.
- [x] heartbeat/Bridge IPC projection tests pass.
- [x] all previous Python regression tests pass.
- [x] existing C# IPC self-tests pass.
- [x] Avalonia Release build passes.
- [x] Task 003 MT5 Bridge still compiles 0 errors / 0 warnings.
- [x] packaged Task 007 Engine smoke test passes.
- [x] GitHub CI green.
- [x] XAUPY-Task007-win-x64 artifact is produced and independently inspected.

## Required artifact

XAUPY-Task007-win-x64.zip

## Evidence

- Final CI source commit: 00624e2d09771c9c23c41f2cee21b24c3a88ca3f
- Branch: task/007-strategy-engine
- GitHub Actions final run: 36084243977
- Validate deterministic strategy engine job: SUCCESS
- Windows x64 full strategy build job: SUCCESS
- Python tests: 78/78 PASS
- C# IPC regression self-tests: 23/23 PASS
- Avalonia/.NET Release build: SUCCESS, 0 warnings, 0 errors
- Packaged Task 007 Python Engine deterministic strategy/safety smoke: PASS
- Packaged xaupy-config regression smoke: PASS
- MetaEditor locked Bridge regression: Result: 0 errors, 0 warnings, 2185 ms elapsed
- GitHub artifact: XAUPY-Task007-win-x64
- GitHub artifact id: 10843277438
- Artifact size: 101031427 bytes
- Artifact outer SHA-256: da319de8a0800acd90ccf7e3a54c11a3b5fe7701c288f9b5f43522f8e4995c8e
- Direct full-build ZIP SHA-256: fa0fe51abc0733ac0530aa839a7100d46ccf43448dc374fedaf7f645e2e676fe
- Artifact expiry: 2026-10-09T02:00:44Z
- Independent artifact inspection: 249 entries
- XAUPY.Desktop.exe: present, PE32+ Windows x86-64
- engine/xaupy-engine.exe: present, PE32+ Windows x86-64
- tools/xaupy-config.exe: present, PE32+ Windows x86-64
- profiles/Baseline_M30_M5_M1.json: Direction=M30, Pullback=M5, Trigger=M1
- profiles/config-schema-v1.json: field_count=133; exact TF options M1/M3/M5/M15/M30/H1/H2/H4
- locked packaged safety verified: allow_real_account=false, demo_only=true, max_retry_count=0, never_widen_sl=true, require_server_sl=true, block_on_stale_market_data=true
- mt5/XAUPY_Bridge_EA.mq5/.ex5/compile.log: present
- Task 007 strategy/acceptance docs: present
- approved Overview/Configuration/Strategy/Monitoring UI reference PNGs: present with UTF-8 filenames

## Delivery

The complete Task 007 Windows x64 build is ready. The realtime Strategy and
Monitoring UI remains correctly deferred to XAUPY-008.


# XAUPY-008 — Strategy + Monitoring realtime tabs

Status: DONE

## Goal

Replace the two approved placeholders with real Avalonia Strategy and Monitoring
surfaces driven by Task 007 strategy state and Task 003/005 market data.

## Scope in implementation

- typed StrategySnapshot IPC projection;
- nested strategy execution-safety guard;
- Strategy dashboard for Direction/Pullback/Trigger, indicators, warm-up and signal evidence;
- Monitoring dashboard for real quotes, active closed bars, indicator/condition state and connectivity;
- session-local quote chart advances only on new real snapshot timestamps;
- explicit unavailable states for later-task Session/News/CPU/RAM backends;
- Overview strategy card uses real strategy projection;
- previous Overview/Configuration behavior preserved.

## Hard boundary

- no broker/manual actions;
- no synthetic market history;
- no fake Session/News/resource status;
- trading_enabled=false;
- execution_enabled=false.

## Acceptance criteria

- [x] approved Strategy and Monitoring references exist.
- [x] both tabs are real hosted controls, not placeholders.
- [x] StrategySnapshot parser and C# contract tests pass.
- [x] Strategy dashboard uses realtime Engine projection.
- [x] Monitoring chart advances only from new real snapshot timestamps.
- [x] active role bars come from Overview.Bars.
- [x] unavailable later-task backends are explicit.
- [x] nested strategy execution enable is rejected.
- [x] all Python regressions pass.
- [x] C# IPC self-tests pass.
- [x] Avalonia Release build passes with 0 warnings / 0 errors.
- [x] packaged Engine Task 007 strategy/safety smoke remains green.
- [x] packaged config smoke remains green.
- [x] MT5 Bridge compiles 0 errors / 0 warnings.
- [x] GitHub CI green.
- [x] XAUPY-Task008-win-x64 artifact is produced and independently inspected.

## Required artifact

XAUPY-Task008-win-x64.zip

## Evidence

- Final implementation CI source commit: 030c651ef47f9912caf931d87785e2fe44e6dc5e
- Branch: task/008-strategy-monitoring-tabs
- GitHub Actions final successful run: 36085413233
- Validate strategy monitoring projection and UI job: SUCCESS
- Windows x64 full Task 008 UI build job: SUCCESS
- Python tests: 87/87 PASS
- C# IPC regression self-tests: 33/33 PASS
- Avalonia/.NET Release build: SUCCESS, 0 warnings, 0 errors
- Packaged Task 007 Python Engine deterministic strategy/safety smoke: PASS
- Packaged xaupy-config regression smoke: PASS
- MetaEditor locked Bridge regression: Result: 0 errors, 0 warnings, 2366 ms elapsed
- GitHub artifact: XAUPY-Task008-win-x64
- GitHub artifact id: 10842524822
- Artifact size: 101059848 bytes
- Artifact outer SHA-256: d0ef14a4abae9a028c38c4b3f5a849a7dd4986beace009a21c3552012f347933
- Direct full-build ZIP size: 101283314 bytes
- Direct full-build ZIP SHA-256: 887fd5bcee5825ebb9f7a30c82d14bb75fd850194bb67bebc3840499718cee89
- Artifact expiry: 2026-10-09T02:16:47Z
- Independent artifact inspection: 251 entries
- XAUPY.Desktop.exe: present, Windows PE
- engine/xaupy-engine.exe: present, Windows PE
- tools/xaupy-config.exe: present, Windows PE
- profiles/Baseline_M30_M5_M1.json: Direction=M30, Pullback=M5, Trigger=M1
- profiles/config-schema-v1.json: field_count=133; exact TF options M1/M3/M5/M15/M30/H1/H2/H4
- packaged safety verified: execution.allow_real_account=false, execution.demo_only=true, execution.max_retry_count=0, safety.never_widen_sl=true, safety.require_server_sl=true, safety.block_on_stale_market_data=true
- mt5/XAUPY_Bridge_EA.mq5/.ex5/compile.log: present
- docs/STRATEGY_MONITORING_UI_SPEC.md and docs/TASK008_STRATEGY_MONITORING_TEST.md: present
- approved Strategy and Monitoring reference PNGs: present with UTF-8 filenames

## Delivery

The complete Task 008 Windows x64 build is ready. XAUPY-009 is the next planned
task and remains unstarted.
