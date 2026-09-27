from __future__ import annotations
import contextlib
import csv
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from xaupy_engine.history_archive import CandleArchive
from xaupy_engine.history_collect import main, write_json
from xaupy_engine.history_jobs import HistoryJobs


def candle(timestamp):
    return dict(time=timestamp, open=2000, high=2002, low=1999, close=2001,
                tick_volume=10, spread=20, real_volume=0)


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def test_paged_dedup_order_forming_exclusion_and_gap_report(self):
        archive = CandleArchive(self.temp.name, "XAUUSD")
        self.addCleanup(archive.close)
        archive.add("M1", [candle(300), candle(360)], current_bar_open=360)
        archive.add("M1", [candle(60), candle(120), candle(300)], current_bar_open=360)
        result = archive.export_csv("M1")
        self.assertEqual(3, result["rows"])
        self.assertEqual(1, result["gap_intervals"])
        self.assertEqual(180, result["maximum_gap_seconds"])
        with Path(result["path"]).open() as stream:
            self.assertEqual([60, 120, 300], [int(row["time"]) for row in csv.DictReader(stream)])

    def test_invalid_page_rolls_back_every_row(self):
        archive = CandleArchive(self.temp.name, "XAUUSD")
        self.addCleanup(archive.close)
        bad = candle(120); bad["high"] = float("nan")
        with self.assertRaises(ValueError):
            archive.add("M1", [candle(60), bad], current_bar_open=360)
        self.assertEqual(0, archive.summary("M1")["rows"])

    def test_archive_reopen_preserves_symbol_and_closed_rows(self):
        archive = CandleArchive(self.temp.name, "XAUUSD")
        archive.add("M1", [candle(60)], current_bar_open=120)
        archive.close()
        with self.assertRaises(ValueError): CandleArchive(self.temp.name, "EURUSD")
        archive = CandleArchive(self.temp.name, "XAUUSD")
        self.assertEqual(1, archive.summary("M1")["rows"])
        archive.close()

    def provider(self, maxbars=0):
        rows = [candle(i * 60) for i in range(1, 13)]
        def copy(symbol, timeframe, offset, count):
            available = len(rows) - offset
            if available <= 0 or count > available: return None
            return rows[available-count:available]
        fields = {name: 1 for name in ("digits", "point", "trade_tick_size", "trade_tick_value", "volume_min", "volume_max", "volume_step", "trade_contract_size")}
        return SimpleNamespace(initialize=lambda *a, **kw: True, shutdown=lambda: None,
            terminal_info=lambda: SimpleNamespace(maxbars=maxbars, connected=True),
            symbol_info=lambda s: SimpleNamespace(**fields),
            account_info=lambda: SimpleNamespace(server="TEST", trade_mode=0),
            copy_rates_from_pos=copy, last_error=lambda: (-1, "Test provider boundary"),
            TIMEFRAME_M1=1, __version__="test")

    def collect(self, provider):
        with patch.dict(sys.modules, {"MetaTrader5": provider}), patch("xaupy_engine.history_collect.time.sleep"), contextlib.redirect_stdout(io.StringIO()):
            main(["--terminal", "terminal64.exe", "--output", self.temp.name, "--timeframes", "M1", "--page-size", "4"])
        return json.loads((Path(self.temp.name) / "manifest.json").read_text())

    def test_collector_probes_short_provider_page_to_exhaustion(self):
        result = self.collect(self.provider())
        self.assertEqual(11, result["timeframes"]["M1"]["rows"])
        self.assertEqual(720, result["timeframes"]["M1"]["current_bar_open_excluded"])
        self.assertEqual("PROVIDER_BOUNDARY_OR_ERROR", result["timeframes"]["M1"]["status"])
        self.assertFalse(result["broker_execution_requested"])

    def test_collector_reports_terminal_limit_without_claiming_all_history(self):
        result = self.collect(self.provider(maxbars=7))
        self.assertEqual(6, result["timeframes"]["M1"]["rows"])
        self.assertEqual("TERMINAL_MAXBARS_REACHED", result["timeframes"]["M1"]["status"])

    def test_jobs_reject_relative_executable_and_unsafe_symbol(self):
        jobs = HistoryJobs(Path(self.temp.name))
        with self.assertRaises(ValueError): jobs.start("terminal64.exe", "XAUUSD")
        self.assertEqual("IDLE", jobs.status()["status"])

    def test_progress_replace_retries_windows_reader_sharing_violation(self):
        import os
        destination = Path(self.temp.name) / "progress.json"
        write_json(destination, {"rows": 1})
        original = os.replace
        attempts = []
        def replace(source, target):
            attempts.append(1)
            if len(attempts) == 1: raise PermissionError("WinError5 reader sharing")
            return original(source, target)
        with patch("xaupy_engine.history_collect.os.replace", side_effect=replace), patch("xaupy_engine.history_collect.time.sleep"):
            write_json(destination, {"rows": 2})
        self.assertEqual({"rows": 2}, json.loads(destination.read_text()))
        self.assertEqual(2, len(attempts))


if __name__ == "__main__": unittest.main()
