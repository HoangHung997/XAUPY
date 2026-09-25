# XAUPY IPC Protocol v1

Status: extended by Task XAUPY-010
Transport: TCP loopback
Default endpoint: 127.0.0.1:39421
Framing: UTF-8 JSON Lines, one JSON object per line
Trading/execution: disabled

## 1. Purpose

IPC v1 is the local control channel shared by XAUPY.Desktop, Python Engine and MT5 Bridge EA.

Task 002 established Desktop ↔ Python lifecycle.
Task 003 added MT5 Bridge → Python data snapshots.
Task 004 adds canonical configuration schema/defaults/validation messages.
Task 006 adds active-profile get/set lifecycle for the Avalonia Configuration editor.
Task 007 adds read-only deterministic strategy state projected from real closed-bar Bridge data.
Task 009 adds strategy-owned ticket/order/deal projection plus guarded manual-action simulation.
Task 010 adds persistent structured journal summary/query/bookmark messages.

## 2. Security boundary

Python Engine binds loopback only.

MT5 Bridge rejects non-loopback host configuration.

Default endpoint:

127.0.0.1:39421

Remote control is outside scope.

## 3. Envelope

Every message has:

- schema_version: integer, currently 1;
- type: non-empty string;
- request_id: UUID;
- sent_at_utc: ISO-8601 UTC timestamp;
- payload: JSON object.

Responses copy request_id from their request.

## 4. Desktop lifecycle

hello → hello_ack

heartbeat → heartbeat_ack

shutdown → shutdown_ack

heartbeat_ack includes MT5 bridge health from Task 003, Overview projection from
Task 005, Task 007 strategy projection, Task 009 orders_positions projection,
and a compact Task 010 journal_summary.

The strategy object includes read-only state such as state, blocked_reason,
profile_hash, exact strategy timeframes, direction, armed_side, signal_sequence,
last_signal, warmup_reasons, bars_seen, indicators and condition evidence.

When Bridge/terminal data is stale or unavailable, strategy.available=false and
strategy.state=STALE.

## 5. MT5 Bridge messages

bridge_hello → bridge_hello_ack

bridge_snapshot → bridge_snapshot_ack

bridge_heartbeat → bridge_heartbeat_ack

Task 007 keeps all Task 003 execution locks:

- trading_enabled=false
- execution_enabled=false
- bridge snapshot requires execution_locked=true
- bridge snapshot requires execution_ready=false
- trade_intent remains unsupported

Task 007 bridge_snapshot_ack also includes the current read-only strategy
projection. Strategy evaluation only advances from newer closed-bar timestamps.
A terminal reconnect resets the armed setup before resumed data is evaluated.

### Task 009 read-only order book

bridge_snapshot may additionally include strategy-owned arrays filtered by the
configured symbol and magic number:

- positions;
- pending orders;
- recent realized deals;
- account leverage and strategy-owned daily realized P/L.

heartbeat_ack exposes these as orders_positions together with deterministic KPI
fields (open P/L, realized P/L, exposure, current SL-based risk) and broker
metadata. If Bridge data becomes stale, orders_positions.available=false and all
ticket rows are cleared.

### Task 009 guarded manual simulation

Desktop may send:

manual_action_simulate → manual_action_simulate_ack

The request contains a unique intent_id, an action name, explicit confirmation
and any action-specific fields such as ticket, volume, SL/TP points or partial
percentage.

Supported Task 009 actions are MARKET_BUY, MARKET_SELL, CLOSE_POSITION,
PARTIAL_CLOSE, MOVE_SL_BE, START_TRAILING, MODIFY_PENDING, CANCEL_PENDING,
CLOSE_ALL, CLOSE_PROFIT, CLOSE_LOSS and CANCEL_ALL_PENDING.

The Python Engine validates fresh market data, DEMO account mode, locked safety
profile, strategy ownership, broker volume constraints, max open positions,
server-SL requirements and never-widen-SL. Duplicate intent_id with identical
content is idempotent; reuse with different content is rejected.

Task 009 is simulation-only. Every ack keeps:

- simulated=true;
- broker_mutated=false;
- trading_enabled=false;
- execution_enabled=false.

No automatic retry is performed. trade_intent remains unsupported and the MQL5
Bridge still contains no broker mutation path.

## 6. Task 010 structured journal messages

The Engine persists journal schema v1 as append-only UTF-8 JSON Lines and keeps
bookmark state separately. Desktop does not receive the full journal on every
heartbeat.

### heartbeat journal_summary

heartbeat_ack adds journal_summary:

- schema_version;
- date_scope;
- total;
- level_counts for INFO/WARN/ERROR/DEBUG;
- source_counts for System/MT5/EA Bridge/Python Engine/Strategy/Orders/Alerts;
- latest_sequence;
- recent_alerts;
- bookmarks;
- invalid_replay_lines;
- duplicate_replay_lines.

### journal_query

Request:

{
  "levels": ["INFO", "WARN", "ERROR", "DEBUG"],
  "sources": ["Strategy", "Orders"],
  "search": "optional text",
  "date_scope": "TODAY",
  "bookmarks_only": false,
  "limit": 500,
  "before_sequence": null
}

Response:

journal_query_ack

with ok, journal and summary. journal.events contains persisted structured
records with sequence, event_id, timestamp_utc, level, source, tag, message,
details, correlation_id, symbol, profile_hash and bookmarked.

Filtering is deterministic. Empty level/source arrays mean match no events.
TODAY uses the Engine machine local calendar day; ALL ignores the date filter.

### journal_bookmark_set

Request:

{
  "sequence": 42,
  "bookmarked": true
}

Response:

journal_bookmark_set_ack

with ok, the updated event and current summary.

Journal IPC never changes trading state. All responses keep
trading_enabled=false and execution_enabled=false.



## 7. Configuration messages

### config_schema_get

Request payload may be empty.

Response:

config_schema_ack

Payload includes config_schema:

- schema_version
- timeframe_options
- field_count
- fields

timeframe_options is exactly:

M1, M3, M5, M15, M30, H1, H2, H4

Each field describes its canonical dotted path, type, default, .set key, aliases, enum values, bounds and any locked safety value.

### config_defaults_get

Returns config_defaults_ack with the complete canonical default profile.

### config_active_get

Returns config_active_ack with the current normalized in-memory active profile.

### config_active_set

Request payload:

{
  "profile": { ... }
}

Python validates and normalizes before replacing the active profile.

Response config_active_set_ack contains:

- applied
- errors
- normalized profile when applied
- trading_enabled=false
- execution_enabled=false

Invalid profiles do not replace the previous active profile.

When a valid active profile changes in Task 007, the Strategy Engine receives the
same normalized profile, resets its current setup and keeps accumulated raw
closed-bar history.

The active profile is in-memory for Task 006. Explicit JSON/.set save is the persistence path; automatic startup restore belongs to later settings/startup work.

### config_validate

Request payload:

{
  "profile": { ... }
}

Response:

config_validate_ack

with:

- valid
- errors
- normalized profile when valid
- trading_enabled=false
- execution_enabled=false

A profile attempting to set execution.allow_real_account=true, execution.demo_only=false, max retry > 0 or disable mandatory safety values is rejected.

## 8. MT5 .set file conversion

File conversion itself is implemented in the Python config backend and packaged xaupy-config.exe, rather than transmitting arbitrary file paths over IPC.

This keeps IPC messages data-oriented and allows the future Avalonia UI to choose files locally, parse them through the Engine/backend and present a preview.

## 9. Compatibility

- Unknown schema_version is rejected.
- New optional payload fields may be ignored by an older peer.
- Envelope meaning may not silently change.
- Breaking envelope changes require a new schema_version.
- request_id remains correlation/idempotency key.
- Exactly one JSON object per line.
