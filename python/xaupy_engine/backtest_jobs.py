"""Bounded, cancellable replay jobs; no access to live strategy/bridge state."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Event, RLock
from typing import Any
from uuid import uuid4

from .backtest import BacktestCancelled, BacktestEngine, BacktestError, load_historical_dataset


class BacktestJobs:
    def __init__(self, repository, log):
        self.repository = repository
        self.log = log
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="xaupy-replay")
        self._lock = RLock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._cancel: dict[str, Event] = {}
        self._closed = False

    def start(self, profile: dict, request: dict) -> dict:
        path = request.get("path")
        if not isinstance(path, str) or not path.strip():
            raise BacktestError("path is required")
        # Freeze both profile and request before moving any work off the loop.
        frozen, parameters = deepcopy(profile), deepcopy(request)
        with self._lock:
            if self._closed:
                raise BacktestError("Backtest service is closing")
            if any(j["state"] in {"QUEUED", "RUNNING", "CANCELLING"} for j in self._jobs.values()):
                raise BacktestError("A backtest is already running")
            job_id = str(uuid4())
            self._cancel[job_id] = Event()
            self._jobs[job_id] = {"job_id": job_id, "state": "QUEUED", "completed_bars": 0, "total_bars": 0,
                                  "run_id": None, "errors": [], "profile_hash": None}
            self._pool.submit(self._run, job_id, frozen, parameters)
            # Retain enough recent completed jobs for clients without unbounded growth.
            for old_id in list(self._jobs)[:-20]:
                self._jobs.pop(old_id, None)
                self._cancel.pop(old_id, None)
            return self.status(job_id)

    def _update(self, job_id: str, **values):
        with self._lock:
            self._jobs[job_id].update(values)

    def _run(self, job_id: str, profile: dict, parameters: dict):
        cancel = self._cancel[job_id]
        try:
            if cancel.is_set():
                raise BacktestCancelled("Backtest cancelled")
            self._update(job_id, state="RUNNING")
            dataset = load_historical_dataset(parameters["path"])
            from .tick_backtest import TickDataset, TickBacktestEngine
            engine_type=TickBacktestEngine if isinstance(dataset,TickDataset) else BacktestEngine
            selected_model=parameters.get('model','AUTO')
            if selected_model not in ('AUTO','M1_OHLC','REAL_TICKS'): raise BacktestError('Unknown backtest model')
            if (selected_model=='REAL_TICKS' and not isinstance(dataset,TickDataset)) or (selected_model=='M1_OHLC' and isinstance(dataset,TickDataset)):
                raise BacktestError('Selected model does not match dataset. Observed ticks cannot be reconstructed from OHLC.')
            engine = engine_type(profile, initial_balance=float(parameters.get("initial_balance", 10000)),
                                    spread_pips=float(parameters.get("spread_pips", 20)),
                                    commission_per_lot=float(parameters.get("commission_per_lot", 7)))
            self.log("INFO", "Python Engine", "BACKTEST_RUN", "Backtest started in background",
                     details={"job_id": job_id, "dataset_fingerprint": dataset.fingerprint})
            result = engine.run(dataset, from_date=str(parameters.get("from_date", "")).strip(),
                                to_date=str(parameters.get("to_date", "")).strip(), cancel_check=cancel.is_set,
                                progress=lambda done, total: self._update(job_id, completed_bars=done, total_bars=total))
            # Commit cancellation and persistence under one lock, so a successful
            # cancel cannot race a job into publishing a result afterwards.
            with self._lock:
                if cancel.is_set():
                    raise BacktestCancelled("Backtest cancelled")
                stored = self.repository.save(result)
                self._jobs[job_id].update(state="COMPLETED", run_id=stored["run_id"], profile_hash=stored["engine_profile_hash"])
            self.log("INFO", "Python Engine", "BACKTEST_RUN", "Backtest completed",
                     details={"job_id": job_id, "run_id": stored["run_id"], "metrics": stored["metrics"],
                              "result_hash": stored["result_hash"], "profile_hash": stored["engine_profile_hash"],
                              "dataset_fingerprint": stored["dataset_fingerprint"],
                              "from_date": stored["from_date"], "to_date": stored["to_date"]},
                     profile_hash=stored["engine_profile_hash"])
        except BacktestCancelled:
            self._update(job_id, state="CANCELLED")
        except Exception as error:
            self._update(job_id, state="FAILED", errors=[str(error)])
            self.log("WARN", "Python Engine", "BACKTEST_RUN", f"Backtest failed: {error}", details={"job_id": job_id})

    def status(self, job_id: str) -> dict:
        with self._lock:
            if job_id not in self._jobs:
                raise BacktestError("Unknown backtest job")
            return deepcopy(self._jobs[job_id])

    def cancel(self, job_id: str) -> dict:
        with self._lock:
            job = self.status(job_id)
            if job["state"] in {"QUEUED", "RUNNING", "CANCELLING"}:
                self._cancel[job_id].set()
                self._jobs[job_id]["state"] = "CANCELLING"
            return self.status(job_id)

    def close(self):
        with self._lock:
            self._closed = True
            for event in self._cancel.values():
                event.set()
        self._pool.shutdown(wait=True, cancel_futures=True)
