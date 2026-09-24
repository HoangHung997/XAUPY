from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config_schema import (
    FIELDS,
    default_profile,
    field_for_set_key,
    format_set_value,
    get_path,
    update_profile_value,
    validate_profile,
)


@dataclass
class SetLine:
    raw: str
    key: str | None = None
    value: str | None = None
    suffix: str = ""

    @classmethod
    def parse(cls, raw: str) -> "SetLine":
        stripped = raw.lstrip()
        if not stripped or stripped.startswith(";") or stripped.startswith("#") or "=" not in raw:
            return cls(raw=raw)

        key_part, rest = raw.split("=", 1)
        key = key_part.strip()
        if not key:
            return cls(raw=raw)

        if "||" in rest:
            value, suffix_tail = rest.split("||", 1)
            suffix = "||" + suffix_tail
        else:
            value = rest
            suffix = ""

        return cls(raw=raw, key=key, value=value, suffix=suffix)

    def render(self) -> str:
        if self.key is None:
            return self.raw
        return f"{self.key}={self.value or ''}{self.suffix}"


@dataclass
class SetDocument:
    lines: list[SetLine]
    encoding: str = "utf-8"
    bom: bool = False
    newline: str = "\r\n"
    trailing_newline: bool = True

    @classmethod
    def from_text(
        cls,
        text: str,
        *,
        encoding: str = "utf-8",
        bom: bool = False,
    ) -> "SetDocument":
        newline = "\r\n" if "\r\n" in text else "\n"
        trailing = text.endswith("\r\n") or text.endswith("\n")
        raw_lines = text.splitlines()
        return cls(
            lines=[SetLine.parse(line) for line in raw_lines],
            encoding=encoding,
            bom=bom,
            newline=newline,
            trailing_newline=trailing,
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> "SetDocument":
        if data.startswith(b"\xff\xfe"):
            return cls.from_text(data[2:].decode("utf-16-le"), encoding="utf-16-le", bom=True)
        if data.startswith(b"\xfe\xff"):
            return cls.from_text(data[2:].decode("utf-16-be"), encoding="utf-16-be", bom=True)
        if data.startswith(b"\xef\xbb\xbf"):
            return cls.from_text(data[3:].decode("utf-8"), encoding="utf-8", bom=True)

        if len(data) >= 4 and data[1:2] == b"\x00" and data[3:4] == b"\x00":
            return cls.from_text(data.decode("utf-16-le"), encoding="utf-16-le", bom=False)

        try:
            return cls.from_text(data.decode("utf-8"), encoding="utf-8", bom=False)
        except UnicodeDecodeError:
            return cls.from_text(data.decode("cp1252"), encoding="cp1252", bom=False)

    @classmethod
    def read(cls, path: str | Path) -> "SetDocument":
        return cls.from_bytes(Path(path).read_bytes())

    def to_text(self) -> str:
        text = self.newline.join(line.render() for line in self.lines)
        if self.trailing_newline:
            text += self.newline
        return text

    def to_bytes(self) -> bytes:
        text = self.to_text()
        if self.encoding == "utf-16-le":
            body = text.encode("utf-16-le")
            return (b"\xff\xfe" + body) if self.bom else body
        if self.encoding == "utf-16-be":
            body = text.encode("utf-16-be")
            return (b"\xfe\xff" + body) if self.bom else body
        if self.encoding == "utf-8":
            body = text.encode("utf-8")
            return (b"\xef\xbb\xbf" + body) if self.bom else body
        return text.encode(self.encoding)

    def write(self, path: str | Path) -> None:
        Path(path).write_bytes(self.to_bytes())

    def assignment_keys(self) -> list[str]:
        return [line.key for line in self.lines if line.key is not None]


@dataclass(frozen=True)
class ImportResult:
    profile: dict[str, Any]
    imported_keys: tuple[str, ...]
    unknown_keys: tuple[str, ...]


def import_set_document(
    document: SetDocument,
    base_profile: dict[str, Any] | None = None,
) -> ImportResult:
    profile = default_profile() if base_profile is None else _deepcopy_profile(base_profile)
    imported: list[str] = []
    unknown: list[str] = []

    for line in document.lines:
        if line.key is None:
            continue

        field = field_for_set_key(line.key)
        if field is None:
            unknown.append(line.key)
            continue

        try:
            update_profile_value(profile, field, (line.value or "").strip())
        except (TypeError, ValueError):
            unknown.append(line.key)
            continue

        imported.append(line.key)

    return ImportResult(
        profile=profile,
        imported_keys=tuple(imported),
        unknown_keys=tuple(unknown),
    )


def export_set_document(
    profile: dict[str, Any],
    template: SetDocument | None = None,
    *,
    append_missing: bool = False,
) -> SetDocument:
    errors = validate_profile(profile)
    if errors:
        raise ValueError("invalid profile: " + "; ".join(errors))

    if template is None:
        lines = [
            SetLine.parse("; XAUPY canonical profile export"),
            SetLine.parse("; Generated by XAUPY configuration backend"),
        ]
        for field in FIELDS:
            value = format_set_value(field, get_path(profile, field.path))
            lines.append(SetLine.parse(f"{field.set_key}={value}"))
        return SetDocument(lines=lines, encoding="utf-16-le", bom=True, newline="\r\n", trailing_newline=True)

    document = SetDocument(
        lines=[SetLine(raw=line.raw, key=line.key, value=line.value, suffix=line.suffix) for line in template.lines],
        encoding=template.encoding,
        bom=template.bom,
        newline=template.newline,
        trailing_newline=template.trailing_newline,
    )

    represented_paths: set[str] = set()

    for line in document.lines:
        if line.key is None:
            continue
        field = field_for_set_key(line.key)
        if field is None:
            continue

        line.value = format_set_value(field, get_path(profile, field.path))
        represented_paths.add(field.path)

    if append_missing:
        document.lines.append(SetLine.parse("; XAUPY canonical fields appended below"))
        for field in FIELDS:
            if field.path in represented_paths:
                continue
            value = format_set_value(field, get_path(profile, field.path))
            document.lines.append(SetLine.parse(f"{field.set_key}={value}"))

    return document


def _deepcopy_profile(profile: dict[str, Any]) -> dict[str, Any]:
    import copy
    return copy.deepcopy(profile)
