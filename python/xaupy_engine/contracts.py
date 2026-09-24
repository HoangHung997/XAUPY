from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Literal

ComponentState = Literal["starting", "ready", "degraded", "offline"]


@dataclass(frozen=True)
class Heartbeat:
    schema_version: int
    component: str
    state: ComponentState
    trading_enabled: bool

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"), sort_keys=True)

    @classmethod
    def from_json(cls, payload: str) -> "Heartbeat":
        data = json.loads(payload)
        return cls(**data)


def foundation_heartbeat() -> Heartbeat:
    return Heartbeat(
        schema_version=1,
        component="python-engine",
        state="ready",
        trading_enabled=False,
    )
