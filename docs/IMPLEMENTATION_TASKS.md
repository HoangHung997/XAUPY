# XAUPY — Implementation Tasks

## Execution rules

1. Work on one task only.
2. Do not start the next task until the current task is DONE.
3. DONE requires code + tests + GitHub CI evidence + required build artifact.
4. Product philosophy changes require an explicit spec update.
5. User smoke testing may follow delivery, but the current task must have a complete downloadable build before asking the user to test.

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

Automated evidence is preserved in git history.

# XAUPY-002 — Versioned local IPC and process lifecycle

Status: DONE

## Goal

Turn the Task 001 shell into a real two-process desktop foundation: Avalonia owns a packaged Python Engine process, communicates with it over a versioned loopback-only protocol, monitors heartbeat health, reconnects after connection loss and shuts it down cleanly. Trading remains impossible.

## Scope completed

- Protocol v1 envelope and documentation.
- TCP loopback transport at 127.0.0.1 with configurable port.
- JSON Lines framing.
- hello / hello_ack.
- heartbeat / heartbeat_ack.
- shutdown / shutdown_ack.
- error envelope for unsupported messages.
- UUID request_id correlation.
- Python asyncio Engine server.
- C# protocol client and Python Engine process supervisor.
- bounded restart behavior for an unexpectedly exited owned Engine.
- Avalonia UI live Engine connection state and last heartbeat.
- packaged xaupy-engine.exe so the user does not need to install Python.
- GitHub CI source tests and packaged executable smoke test.
- Windows x64 self-contained full build artifact.

## Explicitly out of scope retained

MT5 connection, MQL5 Bridge, ticks/bars/account data, strategy calculations, trade intents/order execution, configuration editor, backtest and optimization.

## Acceptance criteria

- [x] Python protocol unit tests pass.
- [x] Python server hello/heartbeat integration passes.
- [x] Disconnect/reconnect integration passes.
- [x] Shutdown lifecycle integration passes.
- [x] Non-loopback bind is rejected.
- [x] Unsupported trading/order message returns an error and trading remains disabled.
- [x] C# protocol serialization/correlation self-tests pass.
- [x] Avalonia Desktop Release build passes with 0 warnings and 0 errors.
- [x] Windows xaupy-engine.exe is built by PyInstaller.
- [x] Built xaupy-engine.exe passes hello + heartbeat + shutdown smoke test.
- [x] Windows Desktop self-contained publish contains engine/xaupy-engine.exe.
- [x] Desktop shows Python Engine lifecycle status and manual Start/Stop controls.
- [x] Task 002 exposes no MT5, broker or order execution path.
- [x] GitHub CI is green and uploads XAUPY-Task002-win-x64.

## Automated evidence

- Source commit: 4a0409d0885f8dabff0a1248929260589039c9a3
- Branch: task/002-ipc-lifecycle
- GitHub Actions run: 36006314803
- Validate IPC source job: SUCCESS
- Windows x64 full build job: SUCCESS
- Python tests: 10/10 PASS
- C# IPC contract checks: 7/7 PASS
- Avalonia/.NET build: SUCCESS, 0 warnings, 0 errors
- Packaged Engine smoke test: PASS
- GitHub artifact: XAUPY-Task002-win-x64
- GitHub artifact id: 10811230332
- Outer GitHub artifact SHA-256: 029419da9770a95a85f10444f589183c9783556303a677a0a3e517075838c49d
- Direct full-build ZIP SHA-256: d123dbe0ecf124db00066afc453cfca7caaba70d600adeb27249f8dd29c121c1
- Artifact expiry: 2026-10-08
- Independent artifact inspection: 230 files; XAUPY.Desktop.exe present; engine/xaupy-engine.exe present; IPC/task/product docs present
- XAUPY.Desktop.exe: Windows PE32+ x86-64
- xaupy-engine.exe: Windows PE32+ x86-64
- Desktop runtime: net10.0 self-contained, Microsoft.NETCore.App 10.0.12 included

## Delivery

The direct Task 002 Windows x64 full-build ZIP is the user-test deliverable. Manual smoke testing now checks that the Desktop starts the bundled Engine, reaches READY, shows heartbeat updates, Stop Engine reaches STOPPED, and Start Engine returns to READY.

XAUPY-003 remains PLANNED and has not started.
