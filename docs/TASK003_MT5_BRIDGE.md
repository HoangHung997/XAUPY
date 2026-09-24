# XAUPY Task 003 — MT5 Bridge Data Channel & Execution Guardian

Status: ACTIVE during implementation.

## Goal

Add the real MT5-side bridge without enabling trading.

The EA sends MT5/account/symbol/bar/guardian snapshots to the already-packaged Python Engine over the Task 002 localhost IPC channel. The Python Engine exposes bridge health to Avalonia.

## Task 003 safety boundary

Task 003 is intentionally **data-only**.

The MQL5 bridge contains a hard constant:

TASK003_EXECUTION_LOCKED = true

There is no OrderSend, OrderSendAsync or CTrade execution path in the EA.

The guardian still computes and reports the safety state that later execution tasks will depend on:

- terminal connection;
- terminal/MQL trade permission;
- account trade mode;
- demo-only status;
- configured max lot;
- max daily loss;
- own open positions/orders;
- strategy magic;
- broker min/max/step volume;
- stop/freeze levels.

This lets the application validate the broker environment before order execution is implemented.

## Data snapshot

Each bridge_snapshot includes:

- symbol and magic;
- terminal connected state;
- account trade mode/login/currency;
- balance/equity/free margin;
- bid/ask/spread;
- digits/point;
- broker volume min/max/step;
- tick size/tick value;
- stops/freeze level;
- own position/order count;
- guardian state;
- latest closed bar for M1, M3, M5, M15, M30, H1, H2, H4.

## IPC lifecycle

1. Avalonia launches the packaged Python Engine.
2. MT5 EA connects to 127.0.0.1:39421.
3. EA sends bridge_hello.
4. Engine replies bridge_hello_ack.
5. EA sends bridge_snapshot every configured timer interval.
6. Engine validates execution_locked=true and execution_ready=false.
7. Desktop heartbeat receives bridge state and shows CONNECTED/WAITING.
8. If snapshots stop, Engine marks the bridge stale/disconnected.

## MT5 network permission

MetaTrader 5 requires the socket destination to be explicitly allowed in:

Tools → Options → Expert Advisors → Allow WebRequest for listed URL

Add:

http://127.0.0.1:39421

The bridge itself rejects non-loopback host configuration.

## Build output

The full Task 003 Windows build must contain:

- XAUPY.Desktop.exe
- engine/xaupy-engine.exe
- mt5/XAUPY_Bridge_EA.mq5
- mt5/XAUPY_Bridge_EA.ex5
- mt5/XAUPY_Bridge_EA.compile.log
- docs/TASK003_MT5_DEMO_TEST.md

## Manual demo acceptance after delivery

The user test happens only after CI has produced the complete build. No real account should be used for Task 003.
