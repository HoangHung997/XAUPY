# XAUPY Task 010 — Structured Logging + Journal

Status: ACTIVE  
Dependency: XAUPY-002, XAUPY-003  
Visual source-of-truth: docs/ui-reference/Tab Nhật Kí.png

## Goal

Add a persistent structured evidence journal and replace the Journal placeholder
with the approved N30 Journal UI.

The journal is operational evidence, not a performance claim. It must preserve
enough context to reconstruct system/strategy/manual-action decisions across an
Engine restart.

## Structured event schema v1

Every event contains:

- schema_version = 1;
- sequence: monotonically increasing integer;
- event_id: UUID;
- timestamp_utc: ISO-8601 UTC;
- level: INFO / WARN / ERROR / DEBUG;
- source: MT5 / EA Bridge / Python Engine / Strategy / Orders / Alerts;
- tag: normalized event category;
- message: human-readable summary;
- details: JSON object with structured evidence;
- correlation_id: request/intent id when available;
- symbol and profile_hash when available;
- bookmarked: journal bookmark state.

The append-only persistence format is UTF-8 JSON Lines. Bookmark state is stored
separately so the original evidence record is never rewritten.

## Required evidence coverage

Task 010 records, where available:

- Engine start/stop and IPC hello/connection lifecycle;
- Bridge hello/snapshot invalid/reconnect/stale transitions;
- market snapshot receipt without fabricating values;
- profile/config apply success or rejection;
- Direction/Pullback/Trigger state transitions;
- decision trace with indicator/condition evidence when enabled;
- Task 009 manual-action simulation accepted/rejected results;
- safety warnings/errors and stale-data conditions;
- order/position/deal state counts;
- request/intent correlation identifiers.

Requested versus actual broker fill, actual broker mutations and MAE/MFE remain
unavailable until a real broker execution path exists; Task 010 must not invent
them.

## Persistence and replay

- default runtime directory:
  - Windows: %LOCALAPPDATA%/XAUPY/logs
  - other OS: XDG_STATE_HOME/xaupy/logs or ~/.local/state/xaupy/logs
- XAUPY_LOG_DIR overrides the directory for tests/portable deployments;
- journal-v1.jsonl is append-only and is the replay authority;
- when logging.csv_enabled=true, journal-v1.csv is maintained as a best-effort
  convenience mirror;
- bookmarks-v1.json persists bookmark sequence ids;
- replay reconstructs valid events in sequence order;
- malformed/corrupt lines are counted and ignored rather than preventing Engine
  startup;
- sequence continues after restart;
- duplicate persisted sequence/event_id is ignored on replay;
- query order is newest first;
- query supports source, severity, text, date scope and bookmark filters.

## IPC

Heartbeat adds a compact journal summary only.

Desktop uses:

- journal_query -> journal_query_ack
- journal_bookmark_set -> journal_bookmark_set_ack

Queries return real persisted events; no mock entries are generated.

## UI

The Avalonia Journal tab follows docs/ui-reference/Tab Nhật Kí.png:

- page title/subtitle;
- source tabs: Tất cả, MT5, EA Bridge, Python Engine, Strategy, Orders, Alerts;
- level checkboxes: INFO, WARN, ERROR, DEBUG;
- search box and date scope;
- bookmark/export/refresh actions;
- main log table: #, Thời gian, Mức độ, Nguồn, Thông điệp, Tag;
- selected-event detail panel;
- right summary with INFO/WARN/ERROR/DEBUG counts;
- recent alerts;
- persisted bookmarks.

The mock numbers/messages in the PNG are reference-only and are never hard-coded
as runtime results.

## Safety

Task 010 does not enable broker execution. It preserves all Task 009 locks:

- execution.demo_only=true
- execution.allow_real_account=false
- execution.max_retry_count=0
- safety.never_widen_sl=true
- safety.require_server_sl=true
- safety.block_on_stale_market_data=true
- trading_enabled=false
- execution_enabled=false
- MT5 Bridge contains no OrderSend/CTrade mutation path.

## Acceptance

- structured schema validation tests;
- append/query/filter tests;
- corrupt-line recovery tests;
- restart replay/sequence continuation tests;
- bookmark persistence/replay tests;
- optional CSV mirror tests;
- deterministic query tests;
- Engine IPC journal query/bookmark tests;
- strategy/manual-action/bridge event evidence tests;
- approved Journal UI hierarchy source test;
- C# journal parser checks;
- all previous regressions pass;
- Avalonia Release 0 warnings / 0 errors;
- packaged Task 010 replay smoke passes across two Engine launches;
- packaged Task 009 and Task 007 safety regression smokes pass;
- packaged config smoke passes;
- MetaEditor compile 0 errors / 0 warnings;
- complete Windows x64 artifact produced and independently inspected.
