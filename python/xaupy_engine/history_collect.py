"""Read-only official MT5 history acquisition; never calls an order/login API.

Run with an isolated Python environment containing the official MetaTrader5 wheel.
The existing terminal/account stays untouched. No fixed archive row limit is used;
the terminal's Max bars setting and actual broker history determine coverage.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time

from .history_archive import CandleArchive, CANDLE_COLUMNS, TIMEFRAME_SECONDS


def write_json(path: Path, data: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    for attempt in range(10):
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            # Windows readers/antivirus may briefly deny replacement of an open
            # progress file. The prior complete JSON remains readable meanwhile.
            if attempt == 9:
                raise
            time.sleep(0.03 * (attempt + 1))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--terminal", required=True)
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--output", required=True)
    parser.add_argument("--page-size", type=int, default=5000)
    parser.add_argument("--timeframes", nargs="+", choices=tuple(TIMEFRAME_SECONDS), default=list(TIMEFRAME_SECONDS))
    args = parser.parse_args(argv)
    if not 1 <= args.page_size <= 50000:
        parser.error("page-size must be 1..50000 (transport batch only; no total archive cap)")
    import MetaTrader5 as mt5
    if not mt5.initialize(str(Path(args.terminal).resolve()), timeout=15000):
        raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")
    root = Path(args.output).resolve()
    archive = CandleArchive(root, args.symbol)
    started = datetime.now(timezone.utc).isoformat()
    terminal = mt5.terminal_info()
    symbol = mt5.symbol_info(args.symbol)
    account = mt5.account_info()
    if terminal is None or symbol is None:
        archive.close()
        mt5.shutdown()
        raise RuntimeError("MT5 terminal or symbol metadata unavailable")
    maxbars = int(terminal.maxbars)
    report = {"schema_version": 1, "source": "MetaQuotes official MetaTrader5 Python API",
              "symbol": args.symbol, "started_utc": started, "status": "RUNNING", "timeframes": {},
              "terminal_maxbars": maxbars, "terminal_connected": bool(terminal.connected),
              "provider_package": mt5.__version__, "broker_server": account.server if account else None,
              "account_mode": account.trade_mode if account else None, "columns": list(CANDLE_COLUMNS),
              "timestamp_semantics": "Original MT5 epoch timestamps preserved; no local-time conversion",
              "forming_bar_excluded": True, "broker_execution_requested": False,
              "symbol_metadata": {key: getattr(symbol, key) for key in ["digits", "point", "trade_tick_size", "trade_tick_value", "volume_min", "volume_max", "volume_step", "trade_contract_size", "trade_stops_level", "trade_freeze_level"]}}
    write_json(root / "progress.json", report)
    try:
        for timeframe in args.timeframes:
            tf = getattr(mt5, "TIMEFRAME_" + timeframe)
            current = mt5.copy_rates_from_pos(args.symbol, tf, 0, 1)
            if current is None or len(current) != 1:
                report["timeframes"][timeframe] = {"status": "ERROR", "provider_error": list(mt5.last_error())}
                write_json(root / "progress.json", report)
                continue
            boundary = int(current[0]["time"])
            offset = 1
            status = "AVAILABLE_HISTORY_EXHAUSTED"
            pages = 0
            last_error = None
            while True:
                remaining = maxbars - offset if maxbars > 0 else args.page_size
                if remaining <= 0:
                    status = "TERMINAL_MAXBARS_REACHED"
                    break
                count = min(args.page_size, remaining)
                rows = None
                # MT5 may need time to synchronize an uncached interval.
                for attempt in range(3):
                    rows = mt5.copy_rates_from_pos(args.symbol, tf, offset, count)
                    if rows is not None:
                        break
                    last_error = list(mt5.last_error())
                    time.sleep(0.3 * (attempt + 1))
                if rows is None:
                    # A page straddling the provider boundary can fail rather than
                    # return a partial page. Probe progressively smaller pages.
                    while count > 1 and rows is None:
                        count = max(1, count // 2)
                        rows = mt5.copy_rates_from_pos(args.symbol, tf, offset, count)
                    if rows is None:
                        last_error = list(mt5.last_error())
                        status = "PROVIDER_BOUNDARY_OR_ERROR"
                        break
                if len(rows) == 0:
                    break
                page = [{key: int(item[key]) if key in ("time", "tick_volume", "spread", "real_volume") else float(item[key])
                         for key in CANDLE_COLUMNS} for item in rows]
                archive.add(timeframe, page, current_bar_open=boundary)
                offset += len(rows)
                pages += 1
                report["timeframes"][timeframe] = {**archive.summary(timeframe), "status": "RUNNING", "pages": pages,
                                                    "next_position": offset, "current_bar_open_excluded": boundary}
                write_json(root / "progress.json", report)
                print(json.dumps({"timeframe": timeframe, **report["timeframes"][timeframe]}), flush=True)
            report["timeframes"][timeframe] = {**archive.export_csv(timeframe), "status": status, "pages": pages,
                                                "next_position": offset, "current_bar_open_excluded": boundary,
                                                "last_provider_error": last_error}
            write_json(root / "progress.json", report)
            print(json.dumps({"completed_timeframe": timeframe, **report["timeframes"][timeframe]}), flush=True)
        report["status"] = "COMPLETE_WITH_COVERAGE_LIMITS"
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        write_json(root / "manifest.json", report)
        write_json(root / "progress.json", report)
    except Exception as exc:
        report["status"] = "FAILED"
        report["error"] = str(exc)
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        write_json(root / "progress.json", report)
        raise
    finally:
        archive.close()
        mt5.shutdown()


if __name__ == "__main__":
    main()
