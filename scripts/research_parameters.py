"""Offline, reproducible whole-strategy comparison. Never connects to MT5 or IPC.

Selection uses chronological training then validation. Previously examined
history is explicitly reused evidence, not a new unseen forward test.
"""
from concurrent.futures import ProcessPoolExecutor
from copy import deepcopy
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from xaupy_engine.backtest import BacktestEngine, load_historical_dataset
from xaupy_engine.config_schema import default_profile

OUT = ROOT / "artifacts/parameter-remediation-20260928"
SOURCE = ROOT / "data/mt5-history/XAUUSD-20260928-unlimited"


def candidates():
    for family, period, level, zperiod, zlevel in (
        ("RSI", 7, 60, 20, 2.5), ("RSI", 14, 65, 20, 2.5),
        ("Z", 14, 65, 20, 2.5), ("Z", 14, 65, 30, 2),
        ("AND", 7, 60, 20, 2.5), ("AND", 14, 65, 20, 2),
        ("OR", 7, 60, 20, 2.5), ("OR", 14, 65, 30, 2),
    ):
        for sl in (3, 5):
            p = default_profile()
            label = f"{family}-r{period}-{level}-z{zperiod}-{zlevel}-sl{sl}"
            p["profile"].update(name=label, notes="Offline M1 closed-bar candidate; requires independent forward validation; no automatic live application.")
            p["timeframes"] = dict(direction="M1", pullback="M1", trigger="M1")
            p["direction"]["ma_enabled"] = False
            for section in ("pullback", "trigger"):
                p[section].update(rsi_enabled=family != "Z", z_enabled=family != "RSI", rsi_period=period, z_period=zperiod, logic="OR" if family == "OR" else "AND")
            p["pullback"].update(rsi_buy_level=100-level, rsi_sell_level=level, z_buy_level=-zlevel, z_sell_level=zlevel)
            p["trigger"].update(rsi_reversal_delta=3, z_reversal_delta=.3, confirm_closed_bar=True)
            p["stop_loss"].update(mode="FIXED", fixed_price_units=sl)
            p["take_profit"].update(mode="FIXED", fixed_price_units=sl*2)
            p["risk"].update(sizing_mode="FIXED_LOT", fixed_lot=.01, max_lot=.01, max_open_positions=1)
            p["costs"].update(max_spread_price_units=1, max_commission_per_lot=7, max_slippage_points=20, min_net_rr=1.2)
            yield label, p


def run_job(job):
    label, profile, segment, start, end, spread = job
    path = OUT / f"{label}-{segment}.json"
    begun = time.perf_counter()
    dataset = load_historical_dataset(OUT / "dataset.json")
    result = BacktestEngine(profile, initial_balance=1000, spread_pips=spread, commission_per_lot=7).run(dataset, from_date=start, to_date=end)
    path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return {"candidate": label, "segment": segment, "metrics": result["metrics"], "result_hash": result["result_hash"], "seconds": round(time.perf_counter()-begun, 2), "path": str(path)}


def rank(row):
    m = row["metrics"]
    if m["total_trades"] < 30:
        return -1e12
    return m["net_profit"] - .5 * m["max_drawdown_usd"]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = list(csv.DictReader((SOURCE / "XAUUSD_M1.csv").open(encoding="utf-8-sig")))
    manifest = json.loads((SOURCE / "manifest.json").read_text(encoding="utf-8-sig"))
    meta = manifest["symbol_metadata"]
    dates = sorted({datetime.fromtimestamp(int(r["time"]), timezone.utc).date().isoformat() for r in rows})
    a, b = int(len(dates)*.6), int(len(dates)*.8)
    segments = {"train": [dates[0], dates[a-1]], "validation": [dates[a], dates[b-1]], "test": [dates[b], dates[-1]]}
    dataset = dict(schema_version=1, timeframe="M1", symbol="XAUUSD", point_size=meta["point"], tick_size=meta["trade_tick_size"], tick_value=meta["trade_tick_value"], volume_min=meta["volume_min"], volume_max=meta["volume_max"], volume_step=meta["volume_step"], timezone_offset_minutes=0, bars=[dict(time=int(r["time"]), **{k:float(r[k]) for k in ("open","high","low","close","tick_volume")}) for r in rows])
    (OUT / "dataset.json").write_text(json.dumps(dataset), encoding="utf-8")
    profiles = dict(candidates())
    protocol = {"source_sha256": hashlib.sha256((SOURCE / "XAUUSD_M1.csv").read_bytes()).hexdigest(), "bars":len(rows), "segments":segments, "profiles":profiles, "selection_metric":"net_profit - 0.5 * max_drawdown_usd, >=30 trades", "spread_points":40, "commission_per_lot_round_trip":7, "account_balance":1000, "workers":2, "timestamp_semantics":"Original archive epochs unchanged, zero additional offset; session windows evaluated on source calendar", "previously_examined_history":True, "scope":"16 predeclared M1 CLOSED-BAR configurations, fixed 0.01 lot. Not a proof of global optimum or intrabar profitability."}
    (OUT / "protocol.json").write_text(json.dumps(protocol, ensure_ascii=False, indent=2), encoding="utf-8")
    results = []
    def collect(pool, jobs):
        found=[]
        for row in pool.map(run_job, jobs):
            found.append(row); results.append(row)
            (OUT / "progress.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
            print(json.dumps(row), flush=True)
        return found
    with ProcessPoolExecutor(max_workers=2) as pool:
        train = collect(pool, [(k,p,"train",*segments["train"],40) for k,p in profiles.items()])
        finalists = sorted(train, key=rank, reverse=True)[:3]
        validation = collect(pool, [(r["candidate"],profiles[r["candidate"]],"validation",*segments["validation"],40) for r in finalists])
        winner = max(validation, key=rank)["candidate"]
        tests = collect(pool, [(winner,profiles[winner],"test",*segments["test"],40), (winner,profiles[winner],"test-stress",*segments["test"],70)])
        full = collect(pool, [(winner,profiles[winner],"full",dates[0],dates[-1],40)])
    selected = deepcopy(profiles[winner])
    qualified = all(r["metrics"]["net_profit"]>0 and r["metrics"]["total_trades"]>=30 for r in [next(r for r in train if r["candidate"]==winner), next(r for r in validation if r["candidate"]==winner), *tests])
    selected["profile"]["notes"] = ("Passed retrospective train/validation/test/stress screens; still requires independent forward validation. " if qualified else "Best relative validation score among three train finalists; failed at least one profitability/sample screen. Research only. ") + "CLOSED-BAR model; not evidence for observed intrabar mode."
    (OUT / "selected-profile.json").write_text(json.dumps(selected, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "summary.json").write_text(json.dumps(dict(winner=winner, qualified=qualified, protocol=protocol, results=results), ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
