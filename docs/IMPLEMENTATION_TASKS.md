# XAUPY — Implementation Tasks

## Execution rules

1. Work on one task only.
2. Do not start the next task until the current task is DONE.
3. DONE requires code + tests + GitHub CI evidence + required build artifact.
4. Product philosophy changes require an explicit spec update.
5. User smoke testing may follow delivery when the task's purpose is to create the first runnable build, but no later task may start until the current task is fully closed.

## Status legend

ACTIVE — only task currently being implemented.  
PLANNED — not started.  
BLOCKED — dependency/user decision prevents work.  
READY_FOR_USER_TEST — CI/build complete, awaiting manual acceptance.  
DONE — implementation, automated evidence and required deliverable complete.

## Task table

| ID | Status | Task | Dependency | Required evidence |
|---|---|---|---|---|
| XAUPY-001 | DONE | Foundation, Avalonia shell, Python engine stub, CI Windows artifact | — | CI green + verified Windows zip artifact |
| XAUPY-002 | PLANNED | Versioned local IPC contract and process lifecycle | 001 | contract + reconnect/heartbeat tests |
| XAUPY-003 | PLANNED | MQL5 Bridge data channel + execution guardian | 002 | compile + CI/static + demo probe |
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

# XAUPY-001 — Foundation, Avalonia shell and CI build

Status: DONE

## Goal

Create a runnable, non-trading foundation that proves the selected stack can build and be delivered before broker/strategy implementation begins.

## Scope completed

- Avalonia 12 desktop project targeting .NET 10.
- Dark Control Center shell reflecting approved UI hierarchy.
- All ten top-level tabs visible and navigable as placeholders.
- Explicit foundation / no trading status.
- Minimal Python engine package with versioned heartbeat contract; no strategy/execution.
- GitHub Actions validation and Windows x64 self-contained publish.
- Root README/build instructions.

## Out of scope retained

MT5 connectivity, MQL5 EA, strategy calculations, order placement, trading, backtest/optimizer implementation and real profile editing.

## Acceptance criteria

- [x] dotnet restore succeeds.
- [x] dotnet build Release succeeds.
- [x] Python unit tests pass.
- [x] Windows self-contained publish succeeds.
- [x] CI uploads XAUPY-Task001-win-x64.zip.
- [x] Artifact independently unpacked and verified to contain XAUPY.Desktop.exe, XAUPY.Desktop.dll, deps/runtimeconfig, Python contract source and task/product docs.
- [x] Packaged Python unit tests pass after extracting the built artifact.
- [x] XAUPY.Desktop.exe verified as Windows PE32+ x86-64 GUI executable.
- [x] runtimeconfig verified as net10.0 self-contained runtime.
- [x] Shell states trading is disabled in Task 001.
- [x] No code path sends broker/trading commands.
- [x] Task docs record CI run/artifact evidence.

## Automated evidence

- Source commit: 536c4f54f7d47ebe74ee970922dbff13d1dc3926
- Branch: task/001-foundation-shell
- GitHub Actions run: 35992138266
- Validate source job: SUCCESS
- Windows x64 artifact job: SUCCESS
- Artifact: XAUPY-Task001-win-x64
- GitHub artifact id: 10804970735
- Outer GitHub artifact SHA-256: 298918bb070362e2027842c4d82c32e3b85ec2bcf0eda1b4f12141fadffed17c
- Direct inner build ZIP SHA-256: 18e9ad63bfb3154c0c47b641b7002382d18b8ebe72baee82022d2fa12177213d
- Artifact expiry: 2026-10-08
- Packaged Python tests: 3/3 PASS

## Delivery

The direct build ZIP is the user-test deliverable for Task 001. User smoke testing of launch/resize/navigation happens after delivery. XAUPY-002 remains PLANNED and has not started.
