"""Control/observe the explicitly authorized, bounded DEMO entry acceptance.

The watcher is read-only. Only the separate `arm` operation changes authorization;
it never manufactures a strategy signal and never sends an MT5 order itself.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import socket
import sys
import time
from uuid import uuid4

MAX_FRAME = 1024 * 1024
FINISHED = {"FILLED", "REJECTED", "UNKNOWN", "CANCELLED", "SUSPENDED", "EXPIRED"}


class Client:
    def __init__(self, port: int):
        self.socket = socket.create_connection(("127.0.0.1", port), timeout=5)
        self.stream = self.socket.makefile("rwb")
        self.request("hello", {"component": "demo-once-observer"})

    def close(self):
        self.stream.close()
        self.socket.close()

    def request(self, kind: str, payload: dict | None = None) -> dict:
        identifier = str(uuid4())
        envelope = {"schema_version": 1, "type": kind, "request_id": identifier,
                    "sent_at_utc": datetime.now(timezone.utc).isoformat(), "payload": payload or {}}
        self.stream.write((json.dumps(envelope, allow_nan=False) + "\n").encode())
        self.stream.flush()
        raw = self.stream.readline(MAX_FRAME + 1)
        if len(raw) > MAX_FRAME or not raw.endswith(b"\n"):
            raise RuntimeError("Incomplete or oversized IPC reply")
        reply = json.loads(raw)
        if reply.get("request_id") != identifier or reply.get("type") != kind + "_ack":
            raise RuntimeError(f"IPC reply rejected: {reply.get('payload', {})}")
        result = reply["payload"]
        if result.get("execution_enabled") is not False or result.get("trading_enabled") is not False:
            raise RuntimeError("General execution lock unexpectedly changed")
        return result


def compact(client: Client) -> dict:
    status = client.request("demo_once_status")
    heartbeat = client.request("heartbeat")
    strategy = heartbeat.get("strategy") or {}
    bridge = heartbeat.get("bridge") or {}
    return {"observed_utc": datetime.now(timezone.utc).isoformat(),
            "demo_once": status.get("demo_once"),
            "bridge": {key: bridge.get(key) for key in
                       ("connected", "terminal_connected", "account_trade_mode", "age_ms", "symbol")},
            "strategy": {key: strategy.get(key) for key in
                         ("state", "ready", "signal_sequence", "last_signal", "decision_trace")},
            "tick_transport": heartbeat.get("tick_transport")}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("status", "arm", "cancel", "watch"))
    parser.add_argument("--port", type=int, default=39421)
    parser.add_argument("--attempt-id")
    parser.add_argument("--confirm-demo-one-order", action="store_true")
    parser.add_argument("--max-volume", type=float, default=0.01)
    parser.add_argument("--lifetime", type=int, default=86400)
    parser.add_argument("--duration", type=int, default=50)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or not 1 <= args.duration <= 300:
        parser.error("port must be 1..65535 and watch duration 1..300 seconds")
    if not 0 < args.max_volume <= 0.01 or not 1 <= args.lifetime <= 86400:
        parser.error("DEMO limit must be <=0.01 lot with a lifetime <=86400 seconds")
    client = Client(args.port)
    evidence = []
    try:
        if args.operation == "arm":
            if not args.confirm_demo_one_order or not args.attempt_id:
                parser.error("arm requires --confirm-demo-one-order and a stable --attempt-id")
            reply = client.request("demo_once_status")
            context = reply.get("demo_once_context") or {}
            if context.get("account_trade_mode") != "DEMO" or context.get("demo_once_capable") is not True:
                raise RuntimeError("Connected capable DEMO Bridge is required; nothing was armed")
            payload = {key: context.get(key) for key in
                       ("account_login", "account_server", "symbol", "magic", "profile_hash")}
            payload.update(attempt_id=args.attempt_id, confirmed=True, max_volume=args.max_volume,
                           duration_seconds=args.lifetime)
            result = client.request("demo_once_arm", payload)
            evidence.append(result)
            print(json.dumps(result.get("demo_once"), ensure_ascii=False))
            return 0 if result.get("accepted") else 2
        if args.operation == "cancel":
            if not args.attempt_id:
                parser.error("cancel requires --attempt-id")
            result = client.request("demo_once_cancel", {"attempt_id": args.attempt_id})
            evidence.append(result)
            print(json.dumps(result.get("demo_once"), ensure_ascii=False))
            return 0 if result.get("accepted") else 2
        deadline = time.monotonic() + (args.duration if args.operation == "watch" else 0)
        previous = None
        while True:
            result = compact(client)
            evidence.append(result)
            state = result.get("demo_once") or {}
            key = (state.get("state"), state.get("reason"), state.get("code"),
                   state.get("order_ticket"), state.get("deal_ticket"),
                   result["strategy"].get("state"))
            if key != previous or args.operation == "status":
                print(json.dumps(result, ensure_ascii=False), flush=True)
                previous = key
            if state.get("state") in FINISHED or time.monotonic() >= deadline:
                return 0
            time.sleep(min(2, max(0, deadline - time.monotonic())))
    finally:
        client.close()
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"error": str(exc), "broker_request_sent_by_observer": False}), file=sys.stderr)
        sys.exit(2)
