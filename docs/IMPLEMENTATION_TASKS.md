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
| XAUPY-005 | ACTIVE | Overview tab implementation | 002,004 | UI/reference structure + real overview projection + Windows build |
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

# XAUPY-003

Status: DONE. Evidence preserved in git history.

# XAUPY-004

Status: DONE. Evidence preserved in git history.

# XAUPY-005 — Overview tab implementation

Status: ACTIVE

## Goal

Implement the approved Avalonia Overview dashboard using real read-only MT5 Bridge/config/Engine data, with no fake strategy/trading results.

## Visual source-of-truth

docs/ui-reference/Tab Tổng Quan.png

The implementation follows the reference information hierarchy rather than literal mock trading numbers.

## Scope

- quote headline: symbol, BID, ASK, spread;
- account headline: balance, equity, free margin, currency/mode;
- persistent Guardian/EXECUTION LOCKED state;
- Desktop / Python Engine / MT5 Bridge system status;
- live BID-history lightweight chart using actual Bridge snapshots;
- canonical baseline profile summary:
  Direction TF / Pullback TF / Trigger TF / MA / TP / SL / risk limits;
- explicit Strategy Engine not-running state until Task 007;
- real current position/order counts;
- honest empty state instead of fabricated trade history;
- quick local lifecycle event log;
- navigation hides Overview when unfinished tabs are selected and shows explicit placeholders;
- full Windows artifact retains Engine/config tool/profiles/MT5 Bridge.

## Data changes

Python BridgeRegistry exposes overview_payload().

Desktop heartbeat contains overview projection.

Avalonia IPC layer parses:

- OverviewSnapshot;
- ConfigurationSummary loaded from Task 004 config_defaults_get.

Stale MT5 data must never remain presented as live.

## Explicitly out of scope

- strategy state machine;
- synthetic BUY/SELL signal;
- order execution;
- ticket-level order history;
- full Configuration editor;
- persistent structured trading journal;
- full candlestick/indicator chart.

## Acceptance criteria

- [ ] UI reference image exists and structural UI test passes.
- [ ] Overview contains price, system, account, chart, strategy, orders and quick-log groups.
- [ ] other tabs show explicit placeholders instead of Overview data.
- [ ] Overview Bridge projection tests pass.
- [ ] stale Bridge clears live overview values.
- [ ] packaged Engine Overview smoke test passes.
- [ ] C# OverviewSnapshot parser checks pass.
- [ ] canonical M30/M5/M1 config summary is loaded through config_defaults_get.
- [ ] Python regression tests all pass.
- [ ] C# IPC self-tests all pass.
- [ ] Avalonia Release build passes with 0 warnings / 0 errors.
- [ ] Task 003 MT5 Bridge regression compiles 0 errors / 0 warnings.
- [ ] Windows full artifact contains Desktop, Engine, config tool, profiles, MQ5/EX5, Task005 docs and Overview UI reference.
- [ ] GitHub CI green and uploads XAUPY-Task005-win-x64.

## Required artifact

XAUPY-Task005-win-x64.zip

XAUPY-006 and XAUPY-007 remain PLANNED until Task 005 is complete.
