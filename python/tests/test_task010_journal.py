from __future__ import annotations

from datetime import datetime, timezone
import json
import pathlib
import sys
import tempfile
import unittest
from uuid import uuid4

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xaupy_engine.journal import (
    JOURNAL_SCHEMA_VERSION,
    JournalSchemaError,
    StructuredJournal,
)


FIXED_NOW = datetime(2026, 9, 25, 4, 20, 0, tzinfo=timezone.utc)


class StructuredJournalTests(unittest.TestCase):
    def make_store(self, root):
        return StructuredJournal(root, now_provider=lambda: FIXED_NOW)

    def test_append_produces_schema_v1_and_monotonic_sequence(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self.make_store(tmp)
            first = store.append(
                "INFO",
                "Python Engine",
                "SYSTEM",
                "Engine started",
                details={"pid": 123},
            )
            second = store.append(
                "DEBUG",
                "Strategy",
                "DECISION_TRACE",
                "WAIT_PULLBACK_BUY",
                details={"direction": "BUY"},
                correlation_id=str(uuid4()),
                symbol="XAUUSD",
                profile_hash="abc123",
            )

            self.assertEqual(JOURNAL_SCHEMA_VERSION, first["schema_version"])
            self.assertEqual(1, first["sequence"])
            self.assertEqual(2, second["sequence"])
            self.assertFalse(first["bookmarked"])
            self.assertEqual(2, store.event_count)

            lines = pathlib.Path(tmp, "journal-v1.jsonl").read_text(
                encoding="utf-8"
            ).splitlines()
            self.assertEqual(2, len(lines))
            self.assertEqual(1, json.loads(lines[0])["sequence"])
            self.assertEqual(2, json.loads(lines[1])["sequence"])

    def test_schema_rejects_invalid_level_source_tag_and_details(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self.make_store(tmp)
            for kwargs in (
                {"level": "TRACE", "source": "System", "tag": "SYSTEM", "message": "x"},
                {"level": "INFO", "source": "Unknown", "tag": "SYSTEM", "message": "x"},
                {"level": "INFO", "source": "System", "tag": "bad tag", "message": "x"},
                {"level": "INFO", "source": "System", "tag": "SYSTEM", "message": "",},
            ):
                with self.subTest(kwargs=kwargs):
                    with self.assertRaises(JournalSchemaError):
                        store.append(**kwargs)

            with self.assertRaises(JournalSchemaError):
                store.append(
                    "INFO",
                    "System",
                    "SYSTEM",
                    "bad details",
                    details=["not", "object"],
                )

    def test_query_filters_level_source_search_bookmark_and_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self.make_store(tmp)
            one = store.append(
                "INFO",
                "MT5",
                "CONNECTION",
                "Connected to terminal",
                details={"ping_ms": 28},
                symbol="XAUUSD",
            )
            two = store.append(
                "WARN",
                "Alerts",
                "RISK",
                "Volatility high",
                details={"atr": 2.18, "threshold": 2.0},
                symbol="XAUUSD",
            )
            store.append(
                "DEBUG",
                "Strategy",
                "INDICATOR",
                "EMA cache updated",
                details={"ema50": 4295.10},
                symbol="XAUUSD",
            )
            store.set_bookmark(two["sequence"], True)

            warn = store.query(
                levels=["WARN"],
                sources=["Alerts"],
                search="2.18",
                date_scope="ALL",
            )
            self.assertEqual(1, warn["total_matched"])
            self.assertEqual(two["sequence"], warn["events"][0]["sequence"])

            bookmarks = store.query(
                date_scope="ALL",
                bookmarks_only=True,
            )
            self.assertEqual(1, bookmarks["total_matched"])
            self.assertTrue(bookmarks["events"][0]["bookmarked"])

            limited = store.query(date_scope="ALL", limit=2)
            self.assertEqual(3, limited["total_matched"])
            self.assertEqual(2, len(limited["events"]))
            self.assertGreater(
                limited["events"][0]["sequence"],
                limited["events"][1]["sequence"],
            )
            self.assertEqual(one["sequence"], 1)

    def test_today_scope_uses_local_day_and_summary_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self.make_store(tmp)
            store.append(
                "INFO",
                "System",
                "SYSTEM",
                "today",
                timestamp_utc="2026-09-25T04:00:00+00:00",
            )
            store.append(
                "ERROR",
                "Alerts",
                "DATA",
                "today error",
                timestamp_utc="2026-09-25T03:00:00+00:00",
            )
            store.append(
                "WARN",
                "MT5",
                "CONNECTION",
                "old",
                timestamp_utc="2026-09-23T03:00:00+00:00",
            )

            today = store.query(date_scope="TODAY")
            self.assertEqual(2, today["total_matched"])

            summary = store.summary(date_scope="TODAY")
            self.assertEqual(2, summary["total"])
            self.assertEqual(1, summary["level_counts"]["INFO"])
            self.assertEqual(1, summary["level_counts"]["ERROR"])
            self.assertEqual(1, summary["source_counts"]["Alerts"])
            self.assertEqual(1, len(summary["recent_alerts"]))

    def test_restart_replay_continues_sequence_and_preserves_bookmark(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = self.make_store(tmp)
            e1 = first.append("INFO", "System", "SYSTEM", "boot 1")
            e2 = first.append("WARN", "EA Bridge", "CONNECTION", "reconnect")
            first.set_bookmark(e2["sequence"], True)

            second = self.make_store(tmp)
            self.assertEqual(2, second.event_count)
            self.assertEqual(2, second.latest_sequence)
            replayed = second.get_event(e2["sequence"])
            self.assertIsNotNone(replayed)
            self.assertTrue(replayed["bookmarked"])

            e3 = second.append("INFO", "System", "SYSTEM", "boot 2")
            self.assertEqual(3, e3["sequence"])
            self.assertEqual(e1["event_id"], second.get_event(1)["event_id"])

    def test_corrupt_and_duplicate_lines_do_not_block_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self.make_store(tmp)
            good = store.append("INFO", "System", "SYSTEM", "valid")
            path = pathlib.Path(tmp, "journal-v1.jsonl")

            duplicate = {
                key: value
                for key, value in good.items()
                if key != "bookmarked"
            }
            with path.open("a", encoding="utf-8") as handle:
                handle.write("{not-json}\n")
                handle.write(json.dumps(duplicate) + "\n")
                handle.write(
                    json.dumps(
                        {
                            **duplicate,
                            "sequence": 999,
                            "event_id": "not-a-uuid",
                        }
                    )
                    + "\n"
                )

            replay = self.make_store(tmp)
            self.assertEqual(1, replay.event_count)
            self.assertEqual(2, replay.invalid_replay_lines)
            self.assertEqual(1, replay.duplicate_replay_lines)
            next_event = replay.append("INFO", "System", "SYSTEM", "next")
            self.assertEqual(2, next_event["sequence"])

    def test_bookmark_unknown_sequence_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self.make_store(tmp)
            with self.assertRaises(JournalSchemaError):
                store.set_bookmark(99, True)

    def test_query_rejects_unsupported_filters(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self.make_store(tmp)
            store.append("INFO", "System", "SYSTEM", "valid")

            with self.assertRaises(JournalSchemaError):
                store.query(levels=["TRACE"], date_scope="ALL")
            with self.assertRaises(JournalSchemaError):
                store.query(sources=["Unknown"], date_scope="ALL")
            with self.assertRaises(JournalSchemaError):
                store.query(date_scope="WEEK")
            with self.assertRaises(JournalSchemaError):
                store.query(date_scope="ALL", limit=0)


if __name__ == "__main__":
    unittest.main()
