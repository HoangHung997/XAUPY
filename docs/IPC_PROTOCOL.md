# XAUPY IPC Protocol v1

Status: extended by Task XAUPY-004
Transport: TCP loopback
Default endpoint: 127.0.0.1:39421
Framing: UTF-8 JSON Lines, one JSON object per line
Trading/execution: disabled

## 1. Purpose

IPC v1 is the local control channel shared by XAUPY.Desktop, Python Engine and MT5 Bridge EA.

Task 002 established Desktop ↔ Python lifecycle.
Task 003 added MT5 Bridge → Python data snapshots.
Task 004 adds canonical configuration schema/defaults/validation messages.

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

heartbeat_ack includes MT5 bridge health from Task 003.

## 5. MT5 Bridge messages

bridge_hello → bridge_hello_ack

bridge_snapshot → bridge_snapshot_ack

bridge_heartbeat → bridge_heartbeat_ack

Task 004 keeps all Task 003 execution locks:

- trading_enabled=false
- execution_enabled=false
- bridge snapshot requires execution_locked=true
- bridge snapshot requires execution_ready=false
- trade_intent remains unsupported

## 6. Configuration messages

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

## 7. MT5 .set file conversion

File conversion itself is implemented in the Python config backend and packaged xaupy-config.exe, rather than transmitting arbitrary file paths over IPC.

This keeps IPC messages data-oriented and allows the future Avalonia UI to choose files locally, parse them through the Engine/backend and present a preview.

## 8. Compatibility

- Unknown schema_version is rejected.
- New optional payload fields may be ignored by an older peer.
- Envelope meaning may not silently change.
- Breaking envelope changes require a new schema_version.
- request_id remains correlation/idempotency key.
- Exactly one JSON object per line.
