from __future__ import annotations

import json
from pathlib import Path
import tempfile
from typing import Any

from .config_schema import normalized_profile, validate_profile


def load_profile(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("profile JSON root must be an object")
    errors = validate_profile(data)
    if errors:
        raise ValueError("invalid profile: " + "; ".join(errors))
    return normalized_profile(data)


def save_profile(profile: dict[str, Any], path: str | Path) -> None:
    normalized = normalized_profile(profile)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    payload = json.dumps(normalized, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        delete=False,
        dir=destination.parent,
        prefix=destination.name + ".",
        suffix=".tmp",
    ) as handle:
        handle.write(payload)
        temp_path = Path(handle.name)

    temp_path.replace(destination)
