"""Exercise the same research implementation exposed in the app; read only live state."""
import argparse
import json
from pathlib import Path
import time
from xaupy_engine.backtest import load_historical_dataset
from xaupy_engine.optimizer import OptimizerEngine
from xaupy_engine.parameter_research import run_research
from xaupy_engine.settings import _atomic_json

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--dataset',required=True)
    parser.add_argument('--state',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--workers',type=int,default=1)
    args=parser.parse_args()
    output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
    profile=json.loads(Path(args.state).read_text(encoding='utf-8'))['profile']
    _atomic_json(output/'profile-used.json',profile)
    started=time.monotonic()
    _atomic_json(output/'progress.json',dict(status='LOADING',started_utc=time.time()))
    data=load_historical_dataset(args.dataset)
    engine=OptimizerEngine(profile,initial_balance=10000,spread_pips=40,commission_per_lot=7,min_trades=20,max_workers=args.workers)
    def progress(done,total,fold,inflight,phase):
        state=dict(status='RUNNING',completed=done,total=total,phase=phase,seconds=round(time.monotonic()-started,1))
        _atomic_json(output/'progress.json',state);print(json.dumps(state),flush=True)
    result=run_research(engine,data,from_date=data.local_date(data.first_time).isoformat(),to_date=data.local_date(data.last_time).isoformat(),progress=progress)
    _atomic_json(output/'result.json',result)
    _atomic_json(output/'progress.json',dict(status='COMPLETE',qualified=result['research']['qualified'],seconds=round(time.monotonic()-started,1)))
    print(json.dumps(result['research']['stages']),flush=True)

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    main()
