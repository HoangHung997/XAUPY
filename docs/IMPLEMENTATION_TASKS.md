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
| XAUPY-004 | PLANNED | Canonical configuration/profile model + .set import/export | 002 | round-trip/property tests |
| XAUPY-005 | PLANNED | Overview tab implementation | 002,004 | UI build + reference review |
| XAUPY-006 | PLANNED | Full Configuration tab | 004 | validation/profile tests |
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

# XAUPY-003 — MQL5 Bridge data channel and execution guardian

Status: DONE

## Goal

Connect real MT5 terminal data to the packaged Python Engine through the existing localhost IPC channel while keeping every order-execution path hard-locked.

## Scope completed

- MQL5 Expert Advisor XAUPY_Bridge_EA.
- loopback-only Socket connection.
- bridge_hello and bridge_snapshot protocol.
- account/symbol/broker-rule snapshots.
- latest closed bar for M1/M3/M5/M15/M30/H1/H2/H4.
- own position/order counts for configured magic.
- guardian report for demo status, terminal permissions, max lot, max daily loss and max own positions.
- Engine bridge registry and stale detection.
- Desktop bridge CONNECTED/WAITING projection.
- real MetaEditor compile in GitHub Actions.
- packaged .mq5 and .ex5 in Windows full build.
- packaged Python Engine bridge/data/lock smoke test.

## Hard safety boundary

Task 003 is data-only.

- TASK003_EXECUTION_LOCKED=true in EA.
- guardian.execution_locked is required true.
- guardian.execution_ready is required false.
- Engine rejects snapshots violating either condition.
- trade_intent remains unsupported.
- EA source contains no OrderSend, OrderSendAsync, CTrade or Trade.mqh execution path.
- Real-account use is not required for acceptance.

## Acceptance criteria

- [x] Existing Task 002 protocol/lifecycle tests still pass.
- [x] Bridge registry validation tests pass.
- [x] bridge_hello and bridge_snapshot integration tests pass.
- [x] all 8 required timeframe keys are enforced.
- [x] stale bridge becomes disconnected.
- [x] trade_intent remains rejected.
- [x] MQL5 source static execution-lock tests pass.
- [x] Avalonia/.NET Release build succeeds with 0 warnings and 0 errors.
- [x] real MetaEditor compiles XAUPY_Bridge_EA.mq5 with 0 errors and 0 warnings.
- [x] CI produces XAUPY_Bridge_EA.ex5.
- [x] packaged xaupy-engine.exe passes Task 003 bridge smoke test.
- [x] Windows x64 self-contained build contains Desktop, Engine, MQ5, EX5, compile log and docs.
- [x] GitHub CI is green and uploads XAUPY-Task003-win-x64.
- [x] downloaded artifact independently inspected before delivery.

## Automated evidence

- Final source commit: cba989f89ebe19b75d829de3cb6d30a83c46f7ff
- Branch: task/003-mt5-bridge-guardian
- GitHub Actions final run: 36010613291
- Validate bridge source job: SUCCESS
- Windows x64 + MetaEditor build job: SUCCESS
- Python tests: 23/23 PASS
- C# IPC contract checks: 7/7 PASS
- Avalonia/.NET build: SUCCESS, 0 warnings, 0 errors
- Packaged Python Engine Task 003 bridge smoke test: PASS
- MetaEditor compile: Result: 0 errors, 0 warnings, 2379 ms elapsed
- GitHub artifact: XAUPY-Task003-win-x64
- GitHub artifact id: 10812636924
- Outer GitHub artifact SHA-256: b8bdc40ccf78ad16613847871386194dae7aaf5ddf4d28d6c5b87fa6ba5a9582
- Direct full-build ZIP SHA-256: c2d2a7b9e2d4898d44d93a8e293fb44cdaf33c9b6e343ea282d5db56adc26668
- Artifact expiry: 2026-10-08
- Independent artifact inspection: 235 files
- XAUPY.Desktop.exe present and verified PE32+ x86-64
- engine/xaupy-engine.exe present and verified PE32+ x86-64
- mt5/XAUPY_Bridge_EA.mq5 present
- mt5/XAUPY_Bridge_EA.ex5 present
- mt5/XAUPY_Bridge_EA.compile.log present and confirms 0 errors / 0 warnings
- docs/TASK003_MT5_DEMO_TEST.md present
- Desktop runtime: net10.0 self-contained, Microsoft.NETCore.App 10.0.12 included

## Build/fix history

CI exposed two real MQL5 issues during Task 003 and both were corrected before completion:

1. malformed JSON quote construction in the first EA source revision;
2. invalid MQL5 Market version formatting that produced one compiler warning.

The final source commit above is the one that compiled with 0 errors and 0 warnings.

## Delivery

The Task 003 full Windows x64 build is ready for manual demo testing with docs/TASK003_MT5_DEMO_TEST.md.

XAUPY-004 remains PLANNED and has not started.
