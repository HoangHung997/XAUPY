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

Status: DONE

## Goal

Establish one versioned Python-owned configuration model so every strategy parameter can be changed by profile rather than source edits, while preserving MT5 .set compatibility and maintaining hard safety locks.

## Scope completed

- canonical schema_version=1;
- 133 typed parameters;
- exact independent Direction/Pullback/Trigger timeframe enum:
  M1/M3/M5/M15/M30/H1/H2/H4;
- no timeframe-order restriction;
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

## Explicitly out of scope retained

- full Avalonia configuration editor (Task 006);
- strategy calculations (Task 007);
- order execution;
- live-account enablement;
- optimizer/backtest.

## Hard safety values

The validator rejects changes that would:

- enable real-account execution;
- disable demo-only mode;
- enable blind broker retries;
- allow widening SL;
- remove required server SL;
- permit operation on stale market data.

## Acceptance criteria

- [x] exact timeframe option test passes.
- [x] unusual timeframe order remains valid.
- [x] default profile validates.
- [x] field catalog contains 133 parameters.
- [x] safety unlock attempts are rejected.
- [x] 500-case random numeric property test passes.
- [x] canonical JSON save/load round-trip passes.
- [x] canonical profile → .set → profile is lossless.
- [x] UTF-16 LE BOM .set support passes.
- [x] UTF-8 BOM and CP1252 detection passes.
- [x] template export preserves unknown keys/comments/order/optimizer suffix.
- [x] template export does not append missing fields unless explicitly requested.
- [x] Engine IPC config schema/default/validation tests pass.
- [x] existing bridge/lifecycle tests remain green.
- [x] Avalonia/.NET build succeeds with 0 warnings/0 errors.
- [x] packaged xaupy-engine.exe Task 004 smoke test passes.
- [x] packaged xaupy-config.exe defaults/validate/export/import smoke test passes.
- [x] Task 003 MQL5 Bridge still compiles 0 errors/0 warnings and EX5 is included.
- [x] Windows full artifact contains Desktop, Engine, config tool, baseline JSON/.set, MQ5/EX5 and docs.
- [x] GitHub CI green and uploads XAUPY-Task004-win-x64.
- [x] downloaded artifact independently inspected before delivery.

## Automated evidence

- Final source commit: 715ae9fd73d8c97845b2f0c01a20575b497316b9
- Branch: task/004-config-profile-set
- GitHub Actions final run: 36014253927
- Validate config backend job: SUCCESS
- Windows x64 full config build job: SUCCESS
- Python tests: 46/46 PASS
- C# IPC contract checks: 7/7 PASS
- Avalonia/.NET build: SUCCESS, 0 warnings, 0 errors
- Canonical field count: 133
- Exact timeframe options: M1, M3, M5, M15, M30, H1, H2, H4
- Packaged Engine Task 004 config smoke test: PASS
- Packaged xaupy-config defaults/validate/export/import smoke test: PASS
- MetaEditor regression compile: Result: 0 errors, 0 warnings, 1733 ms elapsed
- GitHub artifact: XAUPY-Task004-win-x64
- GitHub artifact id: 10814635399
- Outer GitHub artifact SHA-256: 4ba076479dbd9ded60040b069d9429e9cf95f4d3dec4387c0c41a54310d5bf0d
- Direct full-build ZIP SHA-256: f4e465bd404786705d44acc3cdee33ad24462a382e7b2382d0b66ace91385212
- Artifact expiry: 2026-10-08
- Independent artifact inspection: 240 files
- XAUPY.Desktop.exe: present, PE32+ Windows x86-64
- engine/xaupy-engine.exe: present, PE32+ Windows x86-64
- tools/xaupy-config.exe: present, PE32+ Windows x86-64
- profiles/Baseline_M30_M5_M1.json: present and valid
- profiles/Baseline_M30_M5_M1.set: present, UTF-16 LE BOM
- profiles/config-schema-v1.json: present, field_count=133
- mt5/XAUPY_Bridge_EA.mq5/.ex5/compile.log: present
- Desktop runtime: net10.0 self-contained, Microsoft.NETCore.App 10.0.12 included

## Build/fix history

The first Task 004 CI run exposed duplicated legacy .set aliases for Open filter/reference fields. The aliases were made unambiguous and the complete test/build pipeline was re-run.

The final source commit above is the one that passed all 46 Python tests and produced the verified full build.

## Delivery

The Task 004 Windows x64 full build is ready for manual smoke testing using docs/TASK004_CONFIG_TEST.md.

XAUPY-005, XAUPY-006 and XAUPY-007 remain PLANNED and have not started.
