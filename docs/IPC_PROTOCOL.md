# XAUPY IPC Protocol v1

Status: Task XAUPY-002
Transport: TCP loopback
Default endpoint: 127.0.0.1:39421
Framing: UTF-8 JSON Lines, one JSON object per line
Trading: disabled in Task 002

## 1. Purpose

IPC v1 is the local control channel between XAUPY.Desktop and the Python Engine. Task 002 deliberately does not connect to MT5 and does not define broker execution messages.

The protocol is designed so later tasks can add market data, strategy state and trade intents without replacing the transport or lifecycle model.

## 2. Security boundary

The Python Engine must bind to loopback only. A non-loopback host is rejected by the engine.

The default endpoint is 127.0.0.1:39421. The port may be overridden for testing or local development. Remote network control is outside scope and must not be enabled accidentally.

## 3. Envelope

Every message uses the same envelope with these fields:

- schema_version: required integer. Task 002 accepts exactly 1.
- type: required non-empty string.
- request_id: required UUID string.
- sent_at_utc: required ISO-8601 UTC timestamp.
- payload: required JSON object.

Responses copy the request_id of the request they answer.

## 4. Message types in Task 002

hello: Desktop to Engine. Response hello_ack.

heartbeat: Desktop to Engine every two seconds. Response heartbeat_ack. Task 002 treats a missing or invalid response as a broken connection and begins reconnect handling.

shutdown: Desktop to Engine when Desktop owns the process. Response shutdown_ack, then the engine exits cleanly.

error: returned for unsupported messages or protocol errors that can still be framed safely.

Task 002 does not accept order, position, strategy or broker commands.

## 5. Lifecycle

Packaged Windows build layout:

XAUPY.Desktop.exe
engine/xaupy-engine.exe

Normal flow:

1. Desktop starts.
2. Desktop launches engine/xaupy-engine.exe with localhost and port arguments.
3. Desktop retries loopback connection while the one-file engine starts.
4. Desktop sends hello.
5. Engine returns hello_ack.
6. Desktop enters READY and sends heartbeat periodically.
7. If the connection breaks, Desktop enters RECONNECTING and retries.
8. If the owned Engine process exits unexpectedly, Desktop restarts it with bounded retries.
9. User Stop Engine sends shutdown when possible and terminates an unresponsive owned process if required.
10. Closing Desktop terminates the owned Engine process so no orphan remains.

## 6. Fail-safe state

Task 002 has no trading functionality. Every hello and heartbeat response reports trading_enabled=false. The Desktop displays NO TRADING — IPC ONLY.

Any future trading message family must be introduced in a later task with explicit protocol documentation and safety tests.

## 7. Compatibility rules

- Unknown schema_version is rejected.
- New optional payload fields may be ignored by an older peer.
- Envelope fields may not silently change meaning.
- Breaking envelope changes require a new schema_version.
- request_id is the correlation key and is reserved for idempotency and reconciliation in later execution tasks.
- JSON Lines framing remains deterministic: exactly one JSON object per line.

## 8. Task 002 test evidence required

- Python envelope validation tests.
- Python hello/heartbeat integration test.
- Disconnect then reconnect test.
- Shutdown lifecycle test.
- C# envelope serialization/correlation self-tests.
- Windows PyInstaller engine executable smoke test.
- Avalonia Release build.
- Windows x64 self-contained Desktop build containing engine/xaupy-engine.exe.
