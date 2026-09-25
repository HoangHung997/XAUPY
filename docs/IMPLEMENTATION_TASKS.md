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
| XAUPY-006 | ACTIVE | Full Configuration tab | 004 | schema-driven 133-field editor + validation/profile/.set tests + Windows build |
| XAUPY-007 | PLANNED | Strategy engine Direction → Pullback → Trigger | 002,004 | deterministic state tests |
| XAUPY-008 | PLANNED | Strategy + Monitoring realtime tabs | 005,007 | projection tests + build |
| XAUPY-009 | PLANNED | Orders & Positions + guarded manual actions | 003,005 | execution simulation |
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

XAUPY-007 remains PLANNED and has not started.


# XAUPY-006 — Full Configuration tab

Status: ACTIVE

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

- [ ] Configuration reference image exists.
- [ ] all 133 canonical fields render from schema.
- [ ] search/filter structure is present.
- [ ] exact TF options remain M1/M3/M5/M15/M30/H1/H2/H4.
- [ ] unusual timeframe ordering can validate/apply.
- [ ] active profile get/set protocol tests pass.
- [ ] invalid safety unlock cannot replace active profile.
- [ ] JSON load/save actions exist.
- [ ] .set import/export actions exist.
- [ ] locked fields are disabled in UI.
- [ ] Overview remains functional and receives active summary.
- [ ] Python regression tests pass.
- [ ] C# IPC/config parser tests pass.
- [ ] Avalonia Release build succeeds with 0 warnings / 0 errors.
- [ ] packaged Engine Task 006 active config smoke test passes.
- [ ] packaged xaupy-config smoke test passes.
- [ ] MT5 Bridge regression compiles 0 errors / 0 warnings.
- [ ] Windows full artifact includes Desktop, Engine, config tool, profiles, MQ5/EX5, docs and both Overview/Configuration UI references.
- [ ] GitHub CI green and uploads XAUPY-Task006-win-x64.

## Required artifact

XAUPY-Task006-win-x64.zip

XAUPY-007 remains PLANNED until Task 006 is complete.
