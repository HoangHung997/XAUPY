"""Predeclared RSI/Z search with chronological selection and one held-out test.

Uses the same replay engines as the app. This is retrospective evidence; reusing
a dataset never makes its final segment a new independent forward observation.
"""
from copy import deepcopy
from datetime import date
import itertools

from .optimizer import (OptimizerError, OptimizationCancelled, _get_path,
    _optimizer_hash, apply_parameters, observation_times, OPTIMIZER_SCHEMA_VERSION,
    replay_engine, _candidate_summary)
from .backtest import BacktestCancelled, BACKTEST_MODEL
from .tick_backtest import TickDataset, TICK_BACKTEST_MODEL


def research_candidates(profile):
    """Search enabled indicators only; preserve sizing, exits, hours and permissions."""
    rsi = profile['pullback']['rsi_enabled'] or profile['trigger']['rsi_enabled']
    z = profile['pullback']['z_enabled'] or profile['trigger']['z_enabled']
    if not rsi and not z:
        raise OptimizerError('Enable RSI or Z in the active strategy before research')
    patches = []
    # Baseline plus 3 x 3 correlated families. Symmetric levels and identical
    # pullback/trigger periods avoid an accidental Cartesian explosion.
    for period_variant, strength in itertools.product(range(3), range(3)):
        patch = {}
        if rsi:
            for section in ('pullback', 'trigger'):
                if profile[section]['rsi_enabled']:
                    patch[f'{section}.rsi_period'] = (7, 14, 20)[period_variant]
            if profile['pullback']['rsi_enabled']:
                level = (60, 65, 70)[strength]
                patch.update({'pullback.rsi_buy_level':100-level, 'pullback.rsi_sell_level':level})
            if profile['trigger']['rsi_enabled']:
                patch['trigger.rsi_reversal_delta'] = (3., 5., 7.)[strength]
        if z:
            for section in ('pullback', 'trigger'):
                if profile[section]['z_enabled']:
                    patch[f'{section}.z_period'] = (20, 30, 50)[period_variant]
            if profile['pullback']['z_enabled']:
                level = (2., 2.5, 3.)[strength]
                patch.update({'pullback.z_buy_level':-level, 'pullback.z_sell_level':level})
            if profile['trigger']['z_enabled']:
                patch['trigger.z_reversal_delta'] = (.2, .3, .5)[strength]
        apply_parameters(profile, patch)
        patches.append(patch)
    paths = set().union(*patches)
    baseline = {p:_get_path(profile,p) for p in sorted(paths)}
    return [baseline] + [p for p in patches if p != baseline]


def research_segments(dataset, from_date, to_date):
    start, end = date.fromisoformat(from_date), date.fromisoformat(to_date)
    stamps={stamp//86400*86400 for stamp in observation_times(dataset)} if dataset.metadata.timezone_offset_minutes==0 else set(observation_times(dataset))
    days = sorted({dataset.local_date(t) for t in stamps if start <= dataset.local_date(t) <= end})
    if len(days) < 15:
        raise OptimizerError('Research needs at least 15 observed trading dates (60/20/20 split)')
    a, b = int(len(days)*.6), int(len(days)*.8)
    return {name:[str(items[0]),str(items[-1])] for name,items in
            (('train',days[:a]),('validation',days[a:b]),('test',days[b:]))}


def _rank(row, min_trades):
    m=row['metrics']
    valid=not row.get('rejection_reason') and m['total_trades']>=min_trades
    return (valid, m['net_profit']-.5*m['max_drawdown_usd'], -row['index'])


def _passes(row, min_trades):
    m=row['metrics']
    return (not row.get('rejection_reason') and m['total_trades']>=min_trades
            and m['net_profit']>0 and m['max_drawdown_pct']<=20)


def run_research(engine, dataset, *, from_date, to_date, cancel_event=None, progress=None):
    pool=None
    try:
        if engine.max_workers>1:
            from .research_workers import ResearchWorkers
            pool=ResearchWorkers(engine,dataset,cancel_event)
        return _run_research(engine,dataset,from_date=from_date,to_date=to_date,
            cancel_event=cancel_event,progress=progress,pool=pool)
    finally:
        if pool is not None:pool.close()


def _run_research(engine, dataset, *, from_date, to_date, cancel_event=None, progress=None, pool=None):
    engine._validate_dataset_range(dataset, from_date, to_date)
    engine._cancel_event=cancel_event
    segments=research_segments(dataset,from_date,to_date)
    patches=research_candidates(engine.base_profile)
    total=len(patches)+5  # three validation finalists, one test and one stress
    done=0
    def evaluate(index, phase, stress=False):
        nonlocal done
        if cancel_event is not None and cancel_event.is_set():
            raise OptimizationCancelled('research cancelled')
        if progress:progress(done,total,0,1,phase.upper())
        period=segments['test' if stress else phase]
        if stress:
            # Leave broker/risk limits intact. Exceeding a configured ceiling
            # is a failed stress case, never a reason to loosen that limit.
            profile=apply_parameters(engine.base_profile,patches[index])
            profile['costs']['max_slippage_points']*=2
            try:
                result=replay_engine(dataset)(profile,initial_balance=engine.initial_balance,
                    spread_pips=engine.spread_pips*1.5,
                    commission_per_lot=engine.commission_per_lot*1.5).run(dataset,
                    from_date=period[0],to_date=period[1],
                    cancel_check=cancel_event.is_set if cancel_event else None)
                row=_candidate_summary(index,patches[index],result,engine.min_trades)
            except BacktestCancelled as exc:
                raise OptimizationCancelled(str(exc)) from exc
            except ValueError as exc:
                row={'index':index,'metrics':{'total_trades':0,'net_profit':0,
                    'max_drawdown_usd':0,'max_drawdown_pct':0},'rejection_reason':str(exc)}
        else:
            row=engine._evaluate_candidate(index,patches[index],dataset,*period)
        done+=1
        if progress:progress(done,total,0,1,phase.upper(),)
        return row
    def phase(indices,name):
        nonlocal done
        if pool is None:return [evaluate(i,name) for i in indices]
        if progress:progress(done,total,0,min(len(indices),engine.max_workers),name.upper())
        def completed(inflight):
            nonlocal done
            done+=1
            if progress:progress(done,total,0,min(inflight,engine.max_workers),name.upper())
        return pool.evaluate(indices,patches,segments[name],completed)
    train=phase(list(range(len(patches))),'train')
    finalists=sorted(train,key=lambda r:_rank(r,engine.min_trades),reverse=True)[:3]
    validation=phase([r['index'] for r in finalists],'validation')
    winner=max(validation,key=lambda r:_rank(r,engine.min_trades))
    selected=winner['index']  # fixed before either held-out replay
    test=evaluate(selected,'test')
    stress=evaluate(selected,'cost_stress',True)
    stages={'train':train[selected], 'validation':winner,'test':test,'cost_stress':stress}
    qualified=all(_passes(r,engine.min_trades) for r in stages.values())
    reviewed=[]
    for rank,row in enumerate(sorted(validation,key=lambda r:_rank(r,engine.min_trades),reverse=True),1):
        item=deepcopy(row);item.update(rank=rank, research_selected=row['index']==selected,
            qualified=qualified and row['index']==selected)
        reviewed.append(item)
    result=dict(schema_version=OPTIMIZER_SCHEMA_VERSION,mode='RESEARCH',model='RSIZ_CHRONOLOGICAL_RESEARCH_V1',
        objective='NET_MINUS_HALF_DRAWDOWN_MIN_SAMPLE_V1',
        backtest_model=TICK_BACKTEST_MODEL if isinstance(dataset,TickDataset) else BACKTEST_MODEL,
        base_profile_hash=engine.base_profile_hash,base_profile=deepcopy(engine.base_profile),
        dataset_file_name=dataset.path.name,dataset_fingerprint=dataset.fingerprint,
        dataset_metadata=dataset.metadata.public(),from_date=from_date,to_date=to_date,
        initial_balance=engine.initial_balance,spread_pips=engine.spread_pips,
        commission_per_lot=engine.commission_per_lot,min_trades=engine.min_trades,
        parameter_ranges=[],combination_count=len(patches),evaluated_count=len(patches),
        eligible_count=sum(bool(r['eligible']) for r in reviewed),
        ineligible_count=sum(not r['eligible'] for r in reviewed),candidates=reviewed,
        research=dict(qualified=qualified,selected_index=selected,segments=segments,
            planned_parameters=patches,train_results=train,validation_results=validation,stages=stages,
            selection='Train top 3; validation winner fixed before one test and cost stress',
            qualification='Each stage: positive net, minimum trades, drawdown <=20%, no replay error',
            cost_stress='Commission x1.5, slippage x2; OHLC spread x1.5, observed tick spread unchanged',
            limitations='Retrospective reused data; no independent forward claim, no swap/liquidity/latency model. Not a global optimum.',
            execution_changed=False))
    result['optimizer_hash']=_optimizer_hash(result)
    result['workers_used']=engine.max_workers
    return result
