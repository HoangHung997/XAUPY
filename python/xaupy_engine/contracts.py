from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from typing import Any
from uuid import UUID, uuid4

PROTOCOL_VERSION = 1


class ProtocolError(ValueError):
    """Raised when an IPC envelope violates protocol v1."""


@dataclass(frozen=True)
class Envelope:
    schema_version: int
    type: str
    request_id: str
    sent_at_utc: str
    payload: dict[str, Any]

    @classmethod
    def create(
        cls,
        message_type: str,
        payload: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> "Envelope":
        if not message_type or not message_type.strip():
            raise ProtocolError("message type is required")

        return cls(
            schema_version=PROTOCOL_VERSION,
            type=message_type,
            request_id=request_id or str(uuid4()),
            sent_at_utc=datetime.now(timezone.utc).isoformat(),
            payload=payload or {},
        )

    @classmethod
    def response(
        cls,
        message_type: str,
        request_id: str,
        payload: dict[str, Any] | None = None,
    ) -> "Envelope":
        return cls.create(message_type, payload, request_id=request_id)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, separators=(",", ":"), sort_keys=True)

    @classmethod
    def from_json(cls, value: str) -> "Envelope":
        try:
            raw = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ProtocolError(f"invalid JSON: {exc.msg}") from exc

        if not isinstance(raw, dict):
            raise ProtocolError("envelope must be a JSON object")

        required = {"schema_version", "type", "request_id", "sent_at_utc", "payload"}
        missing = required.difference(raw)
        if missing:
            raise ProtocolError(f"missing envelope fields: {sorted(missing)}")

        envelope = cls(
            schema_version=raw["schema_version"],
            type=raw["type"],
            request_id=raw["request_id"],
            sent_at_utc=raw["sent_at_utc"],
            payload=raw["payload"],
        )
        envelope.validate()
        return envelope

    def validate(self) -> None:
        if self.schema_version != PROTOCOL_VERSION:
            raise ProtocolError(
                f"unsupported schema_version={self.schema_version}; expected {PROTOCOL_VERSION}"
            )

        if not isinstance(self.type, str) or not self.type.strip():
            raise ProtocolError("type must be a non-empty string")

        if not isinstance(self.request_id, str):
            raise ProtocolError("request_id must be a string")

        try:
            UUID(self.request_id)
        except (ValueError, AttributeError) as exc:
            raise ProtocolError("request_id must be a UUID") from exc

        if not isinstance(self.sent_at_utc, str):
            raise ProtocolError("sent_at_utc must be a string")

        try:
            datetime.fromisoformat(self.sent_at_utc.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ProtocolError("sent_at_utc must be ISO-8601") from exc

        if not isinstance(self.payload, dict):
            raise ProtocolError("payload must be a JSON object")
