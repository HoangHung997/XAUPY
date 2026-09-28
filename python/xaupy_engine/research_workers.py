"""Bounded process workers for independent research training/validation replays."""
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
import multiprocessing
import time

_engine = _dataset = None


class _Cancellation:
    def __init__(self, event):
        self.event=event;self.checked=0.;self.cancelled=False
    def is_set(self):
        now=time.monotonic()
        if now-self.checked>=.1:
            self.cancelled=self.event.is_set();self.checked=now
        return self.cancelled


def _initialize(profile, options, dataset, stop):
    from .optimizer import OptimizerEngine
    global _engine, _dataset
    _engine=OptimizerEngine(profile, **options)
    _engine._cancel_event=_Cancellation(stop)
    _dataset=dataset


def _evaluate(index, parameters, start, end):
    return _engine._evaluate_candidate(index, parameters, _dataset, start, end)


class ResearchWorkers:
    def __init__(self, engine, dataset, cancel_event):
        context=multiprocessing.get_context('spawn')
        self.stop=context.Event();self.cancel_event=cancel_event
        options={k:getattr(engine,k) for k in ('initial_balance','spread_pips','commission_per_lot','min_trades')}
        self.pool=ProcessPoolExecutor(max_workers=engine.max_workers,mp_context=context,
            initializer=_initialize,initargs=(engine.base_profile,options,dataset,self.stop))

    def evaluate(self, indices, patches, period, completed):
        from .optimizer import OptimizationCancelled
        pending={self.pool.submit(_evaluate,index,patches[index],*period):index for index in indices}
        result={}
        while pending:
            if self.cancel_event is not None and self.cancel_event.is_set():
                self.stop.set()
                for future in pending:future.cancel()
                raise OptimizationCancelled('research cancelled')
            finished,_=wait(tuple(pending),timeout=.1,return_when=FIRST_COMPLETED)
            for future in finished:
                index=pending.pop(future);result[index]=future.result()
                completed(len(pending))
        # Completion timing must never change deterministic ranks or the winner.
        return [result[index] for index in indices]

    def close(self):
        self.stop.set()
        self.pool.shutdown(wait=True,cancel_futures=True)
