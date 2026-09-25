# XAUPY Task 006 — Full Configuration Tab Specification

Status: implementation task
Visual source-of-truth: docs/ui-reference/Tab Cấu Hình.png
Backend source-of-truth: python/xaupy_engine/config_schema.py

## 1. Goal

Implement a real Avalonia Configuration workspace for the complete canonical schema introduced in Task 004.

The UI must not hard-code a partial handpicked subset. It must build its field rows from the schema returned by Python Engine so every canonical field is represented.

Current canonical field count: 133.

## 2. Core UX

The Configuration tab contains:

- profile name/status;
- unsaved-changes indicator;
- validation state;
- exact total field count;
- search by path/description/.set key;
- quick Direction/Pullback/Trigger TF summary;
- grouped parameter sections;
- defaults/revert/validate/apply;
- JSON load/save;
- MT5 .set import/export;
- hard-safety visibility.

## 3. Schema-driven form

The editor receives config_schema_get from Python Engine.

For each field:

- bool → checkbox;
- enum → combo box;
- int/float/time/string → text editor;
- locked safety value → disabled editor + LOCKED marker.

The field row shows:

- canonical dotted path;
- optional description;
- canonical .set key;
- enum choice count or numeric min/max;
- locked value where applicable.

Grouping is derived from canonical paths. Required groups include profile, strategy, timeframes, direction, pullback, trigger, ADX, ATR, Open filter, entry, risk, SL, TP, dynamic TP, management, sessions/days, news, costs, execution, safety and logging.

## 4. Exact timeframes

Direction, Pullback and Trigger remain independent.

Exact options:

M1, M3, M5, M15, M30, H1, H2, H4

The UI must not reject unusual ordering such as:

M1 → H4 → M3

## 5. Draft and Active profile

Editing a control changes only the desktop draft and sets UNSAVED CHANGES.

Validate sends config_validate.

Apply sends config_active_set.

Python Engine is the authority:

- invalid config is rejected;
- valid config is normalized;
- active profile changes only after successful config_active_set;
- Overview receives the updated active summary through the supervisor.

Task 006 does not start trading or strategy execution.

## 6. Safety locks

The UI may display all canonical fields, but locked safety fields are disabled.

At minimum:

- execution.max_retry_count = 0
- execution.demo_only = true
- execution.allow_real_account = false
- safety.never_widen_sl = true
- safety.require_server_sl = true
- safety.block_on_stale_market_data = true

Python validation remains the final authority even if UI code is altered.

## 7. JSON profile operations

Open JSON:

- user chooses a file;
- JSON is sent to Python validation;
- only a valid normalized profile becomes the draft;
- loading does not automatically Apply.

Save JSON:

- draft must validate;
- normalized profile is written with indentation;
- saved file does not implicitly become active unless user also presses Apply.

## 8. MT5 .set operations

Task 006 uses the packaged tools/xaupy-config.exe from Task 004.

Import .set:

- current valid draft is used as base profile;
- known values are imported;
- unknown keys are reported;
- imported .set becomes remembered template;
- resulting profile is validated by Engine;
- import does not automatically Apply.

Export .set:

- draft must validate;
- if a .set was previously imported, export uses it as template to preserve unknown keys/comments/order/optimizer suffix;
- otherwise export creates canonical UTF-16 LE BOM .set.

## 9. Search/filter

Search is local UI filtering only.

Matching fields remain visible by canonical path, .set key, description or group.

Nonmatching groups are hidden.

Search never alters configuration values.

## 10. Persistence boundary

Task 006 active profile is in-memory inside Python Engine.

Explicit JSON/.set save is the persistent user artifact.

Automatic startup restore belongs to later startup/settings work.

## 11. Execution boundary

Task 006 must not add:

- OrderSend/CTrade;
- trade_intent;
- strategy state machine;
- live-account enablement;
- automatic broker retry.

EXECUTION LOCKED remains visible in the application.

## 12. Acceptance

- all 133 schema fields render;
- exact timeframe options preserved;
- search works structurally;
- safety fields disabled;
- validation and Apply use Engine;
- invalid safety unlock cannot become active;
- JSON profile load/save exists;
- .set import/export exists;
- Overview remains functional;
- all previous backend/MT5 tests remain green;
- Windows full build contains Desktop, Engine, config tool, profiles, MT5 Bridge, docs and the approved Configuration reference image.
