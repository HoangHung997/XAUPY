from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .config_schema import (
    default_profile,
    schema_payload,
    validate_profile,
)
from .mt5_set import SetDocument, export_set_document, import_set_document
from .profile_io import load_profile, save_profile


def _write_json(value: object, path: str | None) -> None:
    payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="xaupy-config",
        description="XAUPY canonical profile and MT5 .set conversion tool",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    schema = sub.add_parser("schema", help="Show canonical configuration schema")
    schema.add_argument("--out")

    defaults = sub.add_parser("defaults", help="Write canonical default profile")
    defaults.add_argument("--out")

    validate = sub.add_parser("validate", help="Validate a profile JSON")
    validate.add_argument("profile")

    import_set = sub.add_parser("import-set", help="Import known values from MT5 .set")
    import_set.add_argument("set_file")
    import_set.add_argument("--base-profile")
    import_set.add_argument("--out", required=True)
    import_set.add_argument("--report")

    export_set = sub.add_parser("export-set", help="Export profile to MT5 .set")
    export_set.add_argument("profile")
    export_set.add_argument("--template")
    export_set.add_argument("--append-missing", action="store_true")
    export_set.add_argument("--out", required=True)

    roundtrip = sub.add_parser(
        "roundtrip-set",
        help="Parse and re-write an MT5 .set without changing unknown keys/comments/order",
    )
    roundtrip.add_argument("set_file")
    roundtrip.add_argument("--out", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "schema":
        _write_json(schema_payload(), args.out)
        return 0

    if args.command == "defaults":
        _write_json(default_profile(), args.out)
        return 0

    if args.command == "validate":
        data = json.loads(Path(args.profile).read_text(encoding="utf-8"))
        errors = validate_profile(data)
        if errors:
            for error in errors:
                print(f"ERROR: {error}", file=sys.stderr)
            return 2
        print("VALID")
        return 0

    if args.command == "import-set":
        document = SetDocument.read(args.set_file)
        base = load_profile(args.base_profile) if args.base_profile else None
        result = import_set_document(document, base)
        errors = validate_profile(result.profile)
        if errors:
            for error in errors:
                print(f"ERROR: {error}", file=sys.stderr)
            return 2

        save_profile(result.profile, args.out)
        report = {
            "encoding": document.encoding,
            "bom": document.bom,
            "newline": "CRLF" if document.newline == "\r\n" else "LF",
            "imported_count": len(result.imported_keys),
            "imported_keys": list(result.imported_keys),
            "unknown_count": len(result.unknown_keys),
            "unknown_keys": list(result.unknown_keys),
        }
        if args.report:
            _write_json(report, args.report)
        else:
            print(json.dumps(report, ensure_ascii=False))
        return 0

    if args.command == "export-set":
        profile = load_profile(args.profile)
        template = SetDocument.read(args.template) if args.template else None
        document = export_set_document(
            profile,
            template,
            append_missing=args.append_missing,
        )
        document.write(args.out)
        return 0

    if args.command == "roundtrip-set":
        document = SetDocument.read(args.set_file)
        document.write(args.out)
        return 0

    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
