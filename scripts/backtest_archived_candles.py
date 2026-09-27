"""Run the canonical CLOSED-BAR backtest against an acquired M1 archive."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from xaupy_engine.backtest import BacktestEngine, DatasetMetadata, HistoricalDataset
from xaupy_engine.calibration import read_candles
from xaupy_engine.config_schema import default_profile


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--spread-points", type=float, default=35.0)
    parser.add_argument("--commission-per-lot", type=float, default=0.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads((args.directory / "manifest.json").read_text(encoding="utf-8"))
    meta = manifest["symbol_metadata"]
    source = args.directory / f"{manifest['symbol']}_M1.csv"
    bars, _ = read_candles(source)
    dataset = HistoricalDataset(source.resolve(), hashlib.sha256(source.read_bytes()).hexdigest(),
        DatasetMetadata(symbol=manifest["symbol"], point_size=meta["point"],
                        tick_size=meta["trade_tick_size"], tick_value=meta["trade_tick_value"],
                        volume_min=meta["volume_min"], volume_max=meta["volume_max"],
                        volume_step=meta["volume_step"], timezone_offset_minutes=0), tuple(bars))
    profile = (json.loads(args.profile.read_text(encoding="utf-8-sig"))
               if args.profile else default_profile())
    started = time.monotonic()
    engine = BacktestEngine(profile, initial_balance=10000.0,
                            spread_pips=args.spread_points, commission_per_lot=args.commission_per_lot)
    first, last = dataset.local_date(bars[0].time).isoformat(), dataset.local_date(bars[-1].time).isoformat()
    print(f"Canonical closed-bar backtest: {len(bars)} M1 bars, {first} to {last}", flush=True)
    result = engine.run(dataset, from_date=first, to_date=last)
    result["research_evidence"] = {
        "elapsed_seconds": time.monotonic() - started,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_manifest": str((args.directory / "manifest.json").resolve()),
        "note": "Canonical closed-bar strategy only; this does not validate intrabar tick execution. "
                "Constant spread assumption; commission is only included if provided. Raw MT5 calendar timestamps retained.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(result.get("metrics", result.get("summary", {}))), flush=True)
    print(f"Finished in {time.monotonic()-started:.1f}s: {args.output}", flush=True)


if __name__ == "__main__":
    main()
