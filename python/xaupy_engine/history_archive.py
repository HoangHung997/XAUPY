"""Disk-backed closed-candle archive independent of the bounded realtime UI cache."""
from __future__ import annotations

import csv
import hashlib
import math
from pathlib import Path
import sqlite3
from typing import Any, Iterable

TIMEFRAME_SECONDS = {"M1": 60, "M3": 180, "M5": 300, "M15": 900, "M30": 1800,
                     "H1": 3600, "H2": 7200, "H4": 14400, "D1": 86400}
CANDLE_COLUMNS = ("time", "open", "high", "low", "close", "tick_volume", "spread", "real_volume")


class CandleArchive:
    def __init__(self, root: str | Path, symbol: str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        if not symbol or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-" for c in symbol):
            raise ValueError("Unsafe archive symbol")
        self.symbol = symbol
        self.path = self.root / "candles.sqlite"
        self.connection = sqlite3.connect(self.path)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("CREATE TABLE IF NOT EXISTS metadata (name TEXT PRIMARY KEY, value TEXT NOT NULL)")
        previous = self.connection.execute("SELECT value FROM metadata WHERE name='symbol'").fetchone()
        if previous and previous[0] != symbol:
            self.connection.close()
            raise ValueError("Archive belongs to a different symbol")
        self.connection.execute("INSERT OR IGNORE INTO metadata VALUES ('symbol', ?)", (symbol,))
        self.connection.execute("""CREATE TABLE IF NOT EXISTS candles (
            timeframe TEXT NOT NULL,time INTEGER NOT NULL,open REAL NOT NULL,high REAL NOT NULL,
            low REAL NOT NULL,close REAL NOT NULL,tick_volume INTEGER NOT NULL,spread INTEGER NOT NULL,
            real_volume INTEGER NOT NULL,PRIMARY KEY(timeframe,time)) WITHOUT ROWID""")
        self.connection.commit()

    def add(self, timeframe: str, rows: Iterable[dict[str, Any]], *, current_bar_open: int) -> int:
        if timeframe not in TIMEFRAME_SECONDS or type(current_bar_open) is not int or current_bar_open <= 0:
            raise ValueError("Invalid timeframe or current-bar boundary")
        accepted = []
        previous = 0
        for row in rows:
            timestamp = int(row["time"])
            values = [float(row[key]) for key in ("open", "high", "low", "close")]
            if timestamp <= previous or timestamp <= 0:
                raise ValueError("Page timestamps must be positive and increasing")
            previous = timestamp
            if timestamp >= current_bar_open:
                continue
            o, h, l, c = values
            if any(not math.isfinite(x) or x <= 0 for x in values) or l > min(o, c) or h < max(o, c) or l > h:
                raise ValueError("Invalid OHLC in provider history")
            volumes = [int(row.get(key, 0)) for key in ("tick_volume", "spread", "real_volume")]
            if any(x < 0 for x in volumes):
                raise ValueError("Negative candle volume or spread")
            accepted.append((timeframe, timestamp, *values, *volumes))
        before = self.connection.total_changes
        with self.connection:
            self.connection.executemany("INSERT OR IGNORE INTO candles VALUES (?,?,?,?,?,?,?,?,?)", accepted)
        return self.connection.total_changes - before

    def summary(self, timeframe: str) -> dict[str, Any]:
        count, earliest, latest = self.connection.execute(
            "SELECT COUNT(*),MIN(time),MAX(time) FROM candles WHERE timeframe=?", (timeframe,)).fetchone()
        return {"rows": count, "earliest_time": earliest, "latest_time": latest}

    def export_csv(self, timeframe: str) -> dict[str, Any]:
        path = self.root / f"{self.symbol}_{timeframe}.csv"
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(CANDLE_COLUMNS)
            writer.writerows(self.connection.execute(
                "SELECT time,open,high,low,close,tick_volume,spread,real_volume FROM candles WHERE timeframe=? ORDER BY time", (timeframe,)))
        return {**self.summary(timeframe), **self.coverage(timeframe), "path": str(path.resolve()), "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    def coverage(self, timeframe: str) -> dict[str, Any]:
        interval = TIMEFRAME_SECONDS[timeframe]
        gaps = maximum = 0
        previous = None
        for (timestamp,) in self.connection.execute("SELECT time FROM candles WHERE timeframe=? ORDER BY time", (timeframe,)):
            if previous is not None and timestamp - previous > interval:
                gaps += 1
                maximum = max(maximum, timestamp - previous)
            previous = timestamp
        return {"gap_intervals": gaps, "maximum_gap_seconds": maximum,
                "gap_note": "Intervals longer than the timeframe; includes market closures and possible provider gaps, not classified as missing bars."}

    def close(self) -> None:
        self.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.connection.close()
