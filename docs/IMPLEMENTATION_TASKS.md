# XAUPY — Implementation Tasks

## Execution rules

1. Work on one task only.
2. Do not start the next task until the current task is DONE.
3. DONE requires code + tests + GitHub CI evidence + required build artifact.
4. If user acceptance is required, mark READY_FOR_USER_TEST until evidence is supplied.
5. Product philosophy changes require an explicit spec update.

## Status legend

ACTIVE — only task currently being implemented.  
PLANNED — not started.  
BLOCKED — dependency/user decision prevents work.  
READY_FOR_USER_TEST — CI/build complete, awaiting manual acceptance.  
DONE — acceptance evidence complete.

## Task table

| ID | Status | Task | Dependency | Required evidence |
|---|---|---|---|---|
| XAUPY-001 | ACTIVE | Foundation, Avalonia shell, Python engine stub, CI Windows artifact | — | CI green + Windows zip artifact |
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

Status: ACTIVE

## Goal

Create a runnable, non-trading foundation that proves the selected stack can build and be delivered before broker/strategy implementation begins.

## Scope

- Avalonia 12 desktop project targeting .NET 10.
- Dark Control Center shell reflecting approved UI hierarchy.
- All ten top-level tabs visible and navigable as placeholders.
- Explicit foundation / no trading status.
- Minimal Python engine package with versioned heartbeat contract; no strategy/execution.
- GitHub Actions validation and Windows x64 self-contained publish.
- Root README/build instructions.

## Out of scope

MT5 connectivity, MQL5 EA, strategy calculations, order placement, trading, backtest/optimizer implementation and real profile editing.

## Acceptance criteria

- [ ] dotnet restore succeeds.
- [ ] dotnet build Release succeeds.
- [ ] Python unit tests pass.
- [ ] Windows self-contained publish succeeds.
- [ ] CI uploads XAUPY-Task001-win-x64.zip.
- [ ] Desktop shell opens with ten tab names.
- [ ] Shell states trading is disabled in Task 001.
- [ ] No code path sends broker/trading commands.
- [ ] Task docs record CI run/artifact before status change.

## Handoff after CI

When automated criteria pass, update status to READY_FOR_USER_TEST and provide the GitHub Actions artifact. Do not begin XAUPY-002 until user acceptance when manual test is requested.
