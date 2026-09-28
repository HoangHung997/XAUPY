"""Read-only acceptance of the shared historical tick path; no live changes."""
import argparse
import json
from pathlib import Path
import time
from xaupy_engine.backtest import load_historical_dataset
from xaupy_engine.tick_backtest import TickBacktestEngine

parser=argparse.ArgumentParser()
parser.add_argument('--dataset',required=True)
parser.add_argument('--state',required=True)
parser.add_argument('--output',required=True)
args=parser.parse_args()
profile=json.loads(Path(args.state).read_text(encoding='utf-8'))['profile']
data=load_historical_dataset(args.dataset)
started=time.monotonic();last=started
def progress(done,total):
    global last
    now=time.monotonic()
    if now-last>=15 or done==total:
        print(json.dumps(dict(completed=done,total=total,elapsed_seconds=round(now-started,1))),flush=True);last=now
result=TickBacktestEngine(profile,initial_balance=10000,spread_pips=0,commission_per_lot=7).run(data,
    from_date=data.local_date(data.first_time).isoformat(),to_date=data.local_date(data.last_time).isoformat(),progress=progress)
Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(metrics=result['metrics'],skipped_signals=result['skipped_signals'],seconds=time.monotonic()-started)),flush=True)
