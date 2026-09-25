from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from typing import Any, Callable
from uuid import UUID, uuid4


JOURNAL_SCHEMA_VERSION = 1
JOURNAL_LEVELS = ("INFO", "WARN", "ERROR", "DEBUG")
JOURNAL_SOURCES = (
    "System",
    "MT5",
    "EA Bridge",
    "Python Engine",
    "Strategy",
    "Orders",
    "Alerts",
)
_TAG_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")


class JournalSchemaError(ValueError):
    """Raised when a structured journal event violates schema v1."""


def default_journal_directory() -> Path:
    override = os.environ.get("XAUPY_LOG_DIR")
    if override:
        return Path(override).expanduser()

    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            return Path(local) / "XAUPY" / "logs"
        return Path.home() / "AppData" / "Local" / "XAUPY" / "logs"

    state_home = os.environ.get("XDG_STATE_HOME")
    if state_home:
        return Path(state_home) / "xaupy" / "logs"
    return Path.home() / ".local" / "state" / "xaupy" / "logs"


class StructuredJournal:
    def __init__(
        self,
        root_dir: str | os.PathLike[str] | None = None,
        *,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.root_dir = (
            Path(root_dir).expanduser()
            if root_dir is not None
            else default_journal_directory()
        )
        self.root_dir.mkdir(parents=True, exist_ok=True)

        self.events_path = self.root_dir / "journal-v1.jsonl"
        self.bookmarks_path = self.root_dir / "bookmarks-v1.json"
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))
        self._events: list[dict[str, Any]] = []
        self._events_by_sequence: dict[int, dict[str, Any]] = {}
        self._bookmarks: set[int] = set()
        self._next_sequence = 1
        self.invalid_replay_lines = 0
        self.duplicate_replay_lines = 0

        self._load_bookmarks()
        self._replay_events()

    @property
    def latest_sequence(self) -> int:
        return self._events[-1]["sequence"] if self._events else 0

    @property
    def event_count(self) -> int:
        return len(self._events)

    def append(
        self,
        level: str,
        source: str,
        tag: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        correlation_id: str | None = None,
        symbol: str | None = None,
        profile_hash: str | None = None,
        timestamp_utc: str | None = None,
    ) -> dict[str, Any]:
        normalized_level = str(level).strip().upper()
        normalized_source = str(source).strip()
        normalized_tag = str(tag).strip().upper()

        if normalized_level not in JOURNAL_LEVELS:
            raise JournalSchemaError(f"unsupported journal level: {level!r}")
        if normalized_source not in JOURNAL_SOURCES:
            raise JournalSchemaError(f"unsupported journal source: {source!r}")
        if not _TAG_RE.fullmatch(normalized_tag):
            raise JournalSchemaError(f"invalid journal tag: {tag!r}")
        if not isinstance(message, str) or not message.strip():
            raise JournalSchemaError("journal message must be a non-empty string")

        if timestamp_utc is None:
            now = self._now_provider()
            if now.tzinfo is None:
                now = now.replace(tzinfo=timezone.utc)
            timestamp_utc = now.astimezone(timezone.utc).isoformat()
        else:
            timestamp_utc = self._normalize_timestamp(timestamp_utc)

        event = {
            "schema_version": JOURNAL_SCHEMA_VERSION,
            "sequence": self._next_sequence,
            "event_id": str(uuid4()),
            "timestamp_utc": timestamp_utc,
            "level": normalized_level,
            "source": normalized_source,
            "tag": normalized_tag,
            "message": message.strip(),
            "details": self._safe_json_object(details),
            "correlation_id": self._optional_string(correlation_id),
            "symbol": self._optional_string(symbol),
            "profile_hash": self._optional_string(profile_hash),
        }
        self.validate_event(event)

        encoded = json.dumps(
            event,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        with self.events_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded)
            handle.write("\n")
            handle.flush()

        stored = deepcopy(event)
        self._events.append(stored)
        self._events_by_sequence[event["sequence"]] = stored
        self._next_sequence += 1
        return self._public_event(stored)

    def query(
        self,
        *,
        levels: list[str] | tuple[str, ...] | None = None,
        sources: list[str] | tuple[str, ...] | None = None,
        search: str | None = None,
        date_scope: str = "TODAY",
        bookmarks_only: bool = False,
        limit: int = 500,
        before_sequence: int | None = None,
    ) -> dict[str, Any]:
        selected_levels = {
            str(level).strip().upper()
            for level in (levels or JOURNAL_LEVELS)
        }
        if not selected_levels.issubset(set(JOURNAL_LEVELS)):
            raise JournalSchemaError("journal query contains unsupported level")

        selected_sources = {
            str(source).strip()
            for source in (sources or JOURNAL_SOURCES)
        }
        if not selected_sources.issubset(set(JOURNAL_SOURCES)):
            raise JournalSchemaError("journal query contains unsupported source")

        scope = str(date_scope).strip().upper()
        if scope not in {"TODAY", "ALL"}:
            raise JournalSchemaError("date_scope must be TODAY or ALL")

        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 2000:
            raise JournalSchemaError("journal query limit must be 1..2000")

        needle = (search or "").strip().casefold()
        matched: list[dict[str, Any]] = []

        for event in reversed(self._events):
            sequence = int(event["sequence"])
            if before_sequence is not None and sequence >= before_sequence:
                continue
            if event["level"] not in selected_levels:
                continue
            if event["source"] not in selected_sources:
                continue
            if bookmarks_only and sequence not in self._bookmarks:
                continue
            if scope == "TODAY" and not self._is_today_local(event["timestamp_utc"]):
                continue
            if needle and needle not in self._search_haystack(event):
                continue

            matched.append(self._public_event(event))

        total_matched = len(matched)
        return {
            "schema_version": JOURNAL_SCHEMA_VERSION,
            "date_scope": scope,
            "total_matched": total_matched,
            "events": matched[:limit],
            "latest_sequence": self.latest_sequence,
            "invalid_replay_lines": self.invalid_replay_lines,
        }

    def summary(self, *, date_scope: str = "TODAY") -> dict[str, Any]:
        scope = str(date_scope).strip().upper()
        if scope not in {"TODAY", "ALL"}:
            raise JournalSchemaError("date_scope must be TODAY or ALL")

        events = [
            event
            for event in self._events
            if scope == "ALL" or self._is_today_local(event["timestamp_utc"])
        ]
        level_counts = {level: 0 for level in JOURNAL_LEVELS}
        source_counts = {source: 0 for source in JOURNAL_SOURCES}

        for event in events:
            level_counts[event["level"]] += 1
            source_counts[event["source"]] += 1

        recent_alerts = [
            self._public_event(event)
            for event in reversed(events)
            if event["source"] == "Alerts" or event["level"] in {"WARN", "ERROR"}
        ][:5]

        bookmarked = [
            self._public_event(event)
            for event in reversed(self._events)
            if int(event["sequence"]) in self._bookmarks
        ][:5]

        return {
            "schema_version": JOURNAL_SCHEMA_VERSION,
            "date_scope": scope,
            "total": len(events),
            "level_counts": level_counts,
            "source_counts": source_counts,
            "latest_sequence": self.latest_sequence,
            "recent_alerts": recent_alerts,
            "bookmarks": bookmarked,
            "invalid_replay_lines": self.invalid_replay_lines,
            "duplicate_replay_lines": self.duplicate_replay_lines,
        }

    def set_bookmark(self, sequence: int, bookmarked: bool) -> dict[str, Any]:
        if isinstance(sequence, bool) or not isinstance(sequence, int):
            raise JournalSchemaError("bookmark sequence must be an integer")

        event = self._events_by_sequence.get(sequence)
        if event is None:
            raise JournalSchemaError("journal event does not exist")

        if bookmarked:
            self._bookmarks.add(sequence)
        else:
            self._bookmarks.discard(sequence)

        self._save_bookmarks()
        return self._public_event(event)

    def get_event(self, sequence: int) -> dict[str, Any] | None:
        event = self._events_by_sequence.get(sequence)
        return self._public_event(event) if event is not None else None

    @staticmethod
    def validate_event(event: dict[str, Any]) -> None:
        if not isinstance(event, dict):
            raise JournalSchemaError("journal event must be an object")
        if event.get("schema_version") != JOURNAL_SCHEMA_VERSION:
            raise JournalSchemaError("unsupported journal schema_version")

        sequence = event.get("sequence")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
            raise JournalSchemaError("journal sequence must be a positive integer")

        event_id = event.get("event_id")
        if not isinstance(event_id, str):
            raise JournalSchemaError("journal event_id must be a UUID string")
        try:
            UUID(event_id)
        except ValueError as exc:
            raise JournalSchemaError("journal event_id must be a UUID") from exc

        StructuredJournal._normalize_timestamp(event.get("timestamp_utc"))

        if event.get("level") not in JOURNAL_LEVELS:
            raise JournalSchemaError("journal event has unsupported level")
        if event.get("source") not in JOURNAL_SOURCES:
            raise JournalSchemaError("journal event has unsupported source")

        tag = event.get("tag")
        if not isinstance(tag, str) or not _TAG_RE.fullmatch(tag):
            raise JournalSchemaError("journal event has invalid tag")

        message = event.get("message")
        if not isinstance(message, str) or not message.strip():
            raise JournalSchemaError("journal event message is required")

        if not isinstance(event.get("details"), dict):
            raise JournalSchemaError("journal event details must be an object")

        for key in ("correlation_id", "symbol", "profile_hash"):
            value = event.get(key)
            if value is not None and not isinstance(value, str):
                raise JournalSchemaError(f"journal event {key} must be string or null")

    def _replay_events(self) -> None:
        if not self.events_path.exists():
            return

        seen_sequences: set[int] = set()
        seen_ids: set[str] = set()

        with self.events_path.open("r", encoding="utf-8", errors="replace") as handle:
            for raw in handle:
                raw = raw.strip()
                if not raw:
                    continue

                try:
                    event = json.loads(raw)
                    self.validate_event(event)
                except (json.JSONDecodeError, JournalSchemaError, TypeError, ValueError):
                    self.invalid_replay_lines += 1
                    continue

                sequence = int(event["sequence"])
                event_id = str(event["event_id"])
                if sequence in seen_sequences or event_id in seen_ids:
                    self.duplicate_replay_lines += 1
                    continue

                seen_sequences.add(sequence)
                seen_ids.add(event_id)
                self._events.append(deepcopy(event))

        self._events.sort(key=lambda event: int(event["sequence"]))
        self._events_by_sequence = {
            int(event["sequence"]): event
            for event in self._events
        }
        self._next_sequence = (
            max(self._events_by_sequence) + 1
            if self._events_by_sequence
            else 1
        )

    def _load_bookmarks(self) -> None:
        if not self.bookmarks_path.exists():
            return

        try:
            payload = json.loads(self.bookmarks_path.read_text(encoding="utf-8"))
            values = payload.get("sequences", [])
            if not isinstance(values, list):
                return
            self._bookmarks = {
                int(value)
                for value in values
                if isinstance(value, int) and not isinstance(value, bool) and value > 0
            }
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            self._bookmarks = set()

    def _save_bookmarks(self) -> None:
        payload = {
            "schema_version": JOURNAL_SCHEMA_VERSION,
            "sequences": sorted(self._bookmarks),
        }
        temp = self.bookmarks_path.with_suffix(".json.tmp")
        temp.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        temp.replace(self.bookmarks_path)

    def _public_event(self, event: dict[str, Any]) -> dict[str, Any]:
        public = deepcopy(event)
        public["bookmarked"] = int(event["sequence"]) in self._bookmarks
        return public

    def _is_today_local(self, timestamp_utc: str) -> bool:
        event_time = datetime.fromisoformat(timestamp_utc.replace("Z", "+00:00"))
        local_event = event_time.astimezone()
        now = self._now_provider()
        if now.tzinfo is None:
            now = now.astimezone()
        else:
            now = now.astimezone()
        return local_event.date() == now.date()

    @staticmethod
    def _search_haystack(event: dict[str, Any]) -> str:
        detail_text = json.dumps(
            event.get("details", {}),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return " ".join(
            str(value)
            for value in (
                event.get("sequence"),
                event.get("level"),
                event.get("source"),
                event.get("tag"),
                event.get("message"),
                event.get("correlation_id") or "",
                event.get("symbol") or "",
                event.get("profile_hash") or "",
                detail_text,
            )
        ).casefold()

    @staticmethod
    def _safe_json_object(details: dict[str, Any] | None) -> dict[str, Any]:
        if details is None:
            return {}
        if not isinstance(details, dict):
            raise JournalSchemaError("journal details must be an object")
        encoded = json.dumps(details, ensure_ascii=False, default=str)
        decoded = json.loads(encoded)
        if not isinstance(decoded, dict):
            raise JournalSchemaError("journal details must serialize to an object")
        return decoded

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _normalize_timestamp(value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise JournalSchemaError("journal timestamp_utc is required")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise JournalSchemaError("journal timestamp_utc must be ISO-8601") from exc

        if parsed.tzinfo is None:
            raise JournalSchemaError("journal timestamp_utc must include timezone")
        return parsed.astimezone(timezone.utc).isoformat()
