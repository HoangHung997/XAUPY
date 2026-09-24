# XAUPY IPC Protocol v1

Status: extended by Task XAUPY-003
Transport: TCP loopback
Default endpoint: 127.0.0.1:39421
Framing: UTF-8 JSON Lines, one JSON object per line
Trading/execution: disabled in Task 003

## 1. Purpose

IPC v1 is the local control channel shared by XAUPY.Desktop, the Python Engine and the MT5 Bridge EA.

Task 002 established Desktop ↔ Python lifecycle.
Task 003 adds MT5 Bridge → Python data snapshots while preserving the same versioned envelope.

## 2. Security boundary

The Python Engine binds loopback only.
The MQL5 Bridge also rejects non-loopback host configuration.

Default endpoint:

127.0.0.1:39421

Remote network control is outside scope.

## 3. Envelope

Every message uses:

- schema_version: required integer, currently 1;
- type: required non-empty string;
- request_id: required UUID string;
- sent_at_utc: required ISO-8601 UTC timestamp;
- payload: required JSON object.

Responses copy request_id from the request.

## 4. Desktop lifecycle messages

hello → hello_ack

heartbeat → heartbeat_ack

shutdown → shutdown_ack

error is returned for unsupported or invalid framed requests.

Desktop heartbeat payload now also contains a bridge object:

- connected
- age_ms
- symbol
- terminal_connected
- account_trade_mode
- execution_ready
- execution_locked
- guardian_reason
- snapshots_total

## 5. MT5 Bridge messages

### bridge_hello

EA → Engine after socket connect.

Required payload includes:

- bridge_version
- component
- symbol
- magic
- execution_locked=true

Response:

bridge_hello_ack

The response always reports:

- trading_enabled=false
- execution_enabled=false
- guardian_reason=TASK003_EXECUTION_LOCKED

### bridge_snapshot

EA → Engine on timer.

Required snapshot includes:

- symbol
- terminal_connected
- account_trade_mode
- bid
- ask
- guardian
- bars

The guardian object must contain:

- execution_locked=true
- execution_ready=false

bars must include all required timeframe keys:

M1, M3, M5, M15, M30, H1, H2, H4

Response:

bridge_snapshot_ack

Task 003 response includes command=null. Python does not send trading commands in this task.

### bridge_heartbeat

Reserved lightweight EA heartbeat. Response bridge_heartbeat_ack.

## 6. Stale handling

The Engine records the monotonic arrival time of Bridge messages.

If the last Bridge activity becomes older than the configured stale threshold, Desktop heartbeat reports bridge.connected=false.

This status does not stop or restart the Python Engine itself.

## 7. Execution lock

Task 003 explicitly rejects any bridge snapshot claiming:

execution_locked=false

or:

execution_ready=true

Messages such as trade_intent remain unsupported.

Actual order execution must be introduced by a later task with additional protocol messages, idempotency, reconciliation and broker-side safety tests.

## 8. Compatibility rules

- Unknown schema_version is rejected.
- Optional payload fields may be ignored by an older peer.
- Envelope field meaning may not silently change.
- Breaking envelope changes require a new schema_version.
- request_id remains the correlation/idempotency key.
- Exactly one JSON object is framed per line.

## 9. Task 003 build evidence

Required:

- Python protocol/bridge tests.
- C# Desktop/IPC Release build.
- MQL5 source safety tests.
- MetaEditor real compile: 0 errors.
- Compiled XAUPY_Bridge_EA.ex5.
- Packaged Python Engine bridge smoke test.
- Windows x64 full build containing Desktop, Engine, .mq5, .ex5 and docs.
