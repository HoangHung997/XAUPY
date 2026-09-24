from .contracts import foundation_heartbeat


def main() -> int:
    print(foundation_heartbeat().to_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
