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
| XAUPY-004 | ACTIVE | Canonical configuration/profile model + .set import/export | 002 | schema/validation + .set round-trip/property + packaged tool + Windows build |
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

# XAUPY-003

Status: DONE. Evidence preserved in git history.

# XAUPY-004 — Canonical configuration/profile model + MT5 .set

Status: ACTIVE

## Goal

Establish one versioned Python-owned configuration model so every strategy parameter can be changed by profile rather than source edits, while preserving MT5 .set compatibility and maintaining hard safety locks.

## Scope

- canonical schema_version=1;
- more than 100 typed parameters;
- exact independent Direction/Pullback/Trigger timeframe enum:
  M1/M3/M5/M15/M30/H1/H2/H4;
- no hardcoded timeframe-order restriction;
- MA/Open/Z/RSI/ADX/ATR parameters;
- entry, risk, SL, TP/dynamic TP, management;
- sessions/weekdays/news/cost filters;
- execution identity and mandatory safety values;
- JSON profile normalization/validation;
- atomic JSON save/load;
- MT5 .set parser/import/export;
- known legacy aliases;
- unknown key/comment/order/encoding/line-ending preservation;
- MT5 optimizer suffix preservation;
- packaged xaupy-config.exe;
- Engine IPC schema/default/validate endpoints;
- generated baseline JSON/.set profiles in full artifact;
- regression compile of Task 003 MT5 Bridge for complete build.

## Explicitly out of scope

- full Avalonia configuration editor (Task 006);
- strategy calculations (Task 007);
- order execution;
- live-account enablement;
- optimizer/backtest.

## Hard safety values

The validator must reject changes that would:

- enable real-account execution;
- disable demo-only mode;
- enable blind broker retries;
- allow widening SL;
- remove required server SL;
- permit operation on stale market data.

## Acceptance criteria

- [ ] exact timeframe option test passes.
- [ ] unusual timeframe order remains valid.
- [ ] default profile validates.
- [ ] field catalog contains at least 100 parameters.
- [ ] safety unlock attempts are rejected.
- [ ] random numeric property tests pass.
- [ ] canonical JSON save/load round-trip passes.
- [ ] canonical profile → .set → profile is lossless.
- [ ] UTF-16 LE BOM .set support passes.
- [ ] UTF-8 BOM and CP1252 detection passes.
- [ ] template export preserves unknown keys/comments/order/optimizer suffix.
- [ ] template export does not append missing fields unless explicitly requested.
- [ ] Engine IPC config schema/default/validation tests pass.
- [ ] existing bridge/lifecycle tests remain green.
- [ ] Avalonia/.NET build succeeds with 0 warnings/0 errors.
- [ ] packaged xaupy-engine.exe Task 004 smoke test passes.
- [ ] packaged xaupy-config.exe defaults/validate/export/import smoke test passes.
- [ ] Task 003 MQL5 Bridge still compiles 0 errors/0 warnings and EX5 is included.
- [ ] Windows full artifact contains Desktop, Engine, config tool, baseline JSON/.set, MQ5/EX5 and docs.
- [ ] GitHub CI green and uploads XAUPY-Task004-win-x64.

## Required artifact

XAUPY-Task004-win-x64.zip

XAUPY-005/006/007 remain PLANNED until this task is complete.
