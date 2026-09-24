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
| XAUPY-003 | ACTIVE | MQL5 Bridge data channel + execution guardian | 002 | MetaEditor compile + CI/static + bridge probe + Windows build |
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

Status: ACTIVE

## Goal

Connect real MT5 terminal data to the packaged Python Engine through the existing localhost IPC channel while keeping every order-execution path hard-locked.

## Scope

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
- simulated bridge smoke test against packaged xaupy-engine.exe.

## Hard safety boundary

Task 003 is data-only.

- TASK003_EXECUTION_LOCKED=true in EA.
- guardian.execution_locked must be true.
- guardian.execution_ready must be false.
- Engine rejects snapshots that violate either condition.
- trade_intent remains unsupported.
- EA source contains no OrderSend, OrderSendAsync or CTrade path.
- Real-account use is not required for acceptance.

## Acceptance criteria

- [ ] Existing Task 002 protocol/lifecycle tests still pass.
- [ ] Bridge registry validation tests pass.
- [ ] bridge_hello and bridge_snapshot integration tests pass.
- [ ] all 8 required timeframe keys are enforced.
- [ ] stale bridge becomes disconnected.
- [ ] trade_intent remains rejected.
- [ ] MQL5 source static execution-lock tests pass.
- [ ] Avalonia/.NET Release build succeeds.
- [ ] real MetaEditor compiles XAUPY_Bridge_EA.mq5 with 0 errors.
- [ ] CI produces XAUPY_Bridge_EA.ex5.
- [ ] packaged xaupy-engine.exe passes Task 003 bridge smoke test.
- [ ] Windows x64 self-contained build contains Desktop, Engine, MQ5, EX5 and docs.
- [ ] GitHub CI is green and uploads XAUPY-Task003-win-x64.

## Required artifact

XAUPY-Task003-win-x64.zip

## User smoke test after delivery

Use docs/TASK003_MT5_DEMO_TEST.md against a demo MT5 account.

XAUPY-004 and XAUPY-009 remain PLANNED until Task 003 is complete.
