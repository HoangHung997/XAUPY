# XAUPY Canonical Configuration & Profile Specification

Version: 1
Task: XAUPY-004
Canonical owner: Python Engine
UI consumer: Avalonia Control Center
MT5 compatibility: import/export .set

## 1. Purpose

XAUPY strategy behavior must be changed through configuration, not source edits.

Task 004 establishes one canonical versioned profile model for:

- strategy direction/pullback/trigger;
- all three independent timeframes;
- MA/Open/Z/RSI/ADX/ATR settings;
- entry mode;
- stop loss;
- take profit including future ZRSI dynamic TP parameters;
- trade management;
- risk and daily limits;
- sessions/weekdays/news;
- cost filters;
- execution identity;
- logging;
- hard safety values.

The full Avalonia parameter editor is Task 006. Task 004 is the backend contract it will use.

## 2. Timeframes

The three independent selectors are:

- timeframes.direction
- timeframes.pullback
- timeframes.trigger

Each accepts exactly:

M1, M3, M5, M15, M30, H1, H2, H4

There is deliberately no validation rule requiring Direction > Pullback > Trigger.

Examples that must validate:

- M30 → M5 → M1
- H1 → M15 → M3
- H4 → M30 → M5
- M15 → M3 → M1
- M5 → M5 → M1
- M1 → H4 → M3

The application may later warn about unusual ordering but may not silently change or reject it.

## 3. Baseline profile

Initial research baseline:

- symbol XAUUSD;
- Direction M30;
- Pullback M5;
- Trigger M1;
- Direction EMA50 / close;
- Pullback RSI14 40/60;
- Trigger RSI14 reversal delta 3;
- Pullback Z disabled by default;
- Trigger Z disabled by default;
- ADX hard filter disabled;
- ATR hard filter disabled;
- Open hard filter disabled;
- Market entry;
- Structure SL;
- Fixed TP 7 price units;
- risk 0.5%;
- max lot 0.10;
- max trades/day 8.

These are defaults, not hard-coded strategy rules.

## 4. Schema

The Python module xaupy_engine.config_schema owns the field catalog.

Every field has:

- dotted canonical path;
- scalar type;
- default;
- canonical MT5 .set key;
- optional legacy aliases;
- enum values where applicable;
- min/max where applicable;
- description;
- optional locked safety value.

The field list is exposed over IPC by config_schema_get.

## 5. Hard safety values in Task 004

The following are intentionally locked even though they appear in the canonical profile:

- execution.max_retry_count = 0
- execution.demo_only = true
- execution.allow_real_account = false
- safety.never_widen_sl = true
- safety.require_server_sl = true
- safety.block_on_stale_market_data = true

Importing a .set or JSON file cannot unlock these values.

This follows the product rule that technical/broker safety boundaries may be mandatory even while strategy parameters remain configurable.

## 6. MT5 .set compatibility

XAUPY supports two workflows.

### New canonical export

Without a template, export creates UTF-16 LE with BOM and writes every canonical XAUPY key.

### Template-preserving export

With an existing .set as template:

- comments remain in place;
- unknown keys remain untouched;
- line order remains unchanged;
- file encoding/BOM remains unchanged;
- CRLF/LF style remains unchanged;
- MT5 optimizer suffixes such as value||start||step||stop||Y remain unchanged;
- known values are updated in place;
- missing canonical keys are NOT appended unless append-missing is explicitly requested.

### Import

Known canonical keys and registered legacy aliases update the canonical profile.

Unknown keys remain part of the SetDocument and are reported, not deleted.

Invalid known values do not corrupt the profile; the existing/default canonical value remains and the key is reported as unimported/unknown.

## 7. Canonical JSON

Profile JSON is UTF-8.

Root:

- schema_version = 1
- profile
- strategy
- timeframes
- direction
- pullback
- trigger
- filters
- entry
- risk
- stop_loss
- take_profit
- management
- sessions
- news
- costs
- execution
- safety
- logging

Profile save uses atomic temporary-file replacement.

## 8. IPC messages

Task 004 adds:

config_schema_get → config_schema_ack

config_defaults_get → config_defaults_ack

config_validate → config_validate_ack

config_validate never enables execution and returns:

- valid
- errors
- normalized profile when valid

## 9. Command-line tool

The Windows full build contains:

tools/xaupy-config.exe

Commands:

- schema
- defaults
- validate
- import-set
- export-set
- roundtrip-set

This tool is a backend/diagnostic utility. The normal end-user configuration UI remains Task 006.

## 10. Compatibility policy

Profile schema changes that break meaning require a schema_version change and migration logic.

Adding aliases does not require a schema version bump.

Unknown .set keys must never be discarded merely because XAUPY does not understand them.
