"""Tick-observed position policy. Returns intentions; never talks to a broker."""
from copy import deepcopy
from .strategy_engine import _atr
from .trade_plan import TradePlanError, closed_history, grid, weekend_close_due


def _combine(values, mode):
    return bool(values) and (all(values) if mode == 'BOTH' else any(values))


def stop_candidate(mode, profile, snapshot, history, position, *, trailing=False):
    cfg, management = profile['stop_loss'], profile['management']
    buy = position['side'] == 'BUY'
    now = int(snapshot['server_time'])
    close = snapshot['bid' if buy else 'ask']
    if mode == 'STRUCTURE':
        count = management['trailing_structure_lookback'] if trailing else cfg['structure_lookback']
        bars = closed_history(history, cfg['structure_timeframe'], now, count)[-count:]
        return (min(b.low for b in bars)-cfg['structure_buffer_price_units'] if buy
                else max(b.high for b in bars)+cfg['structure_buffer_price_units']+snapshot['ask']-snapshot['bid'])
    if mode == 'ATR':
        bars = closed_history(history, cfg['atr_timeframe'], now, cfg['atr_period']+1)
        atr = _atr(bars,cfg['atr_period'])
        multiple = management['trailing_atr_multiplier'] if trailing else cfg['atr_multiplier']
        return close + (-1 if buy else 1)*atr*multiple if atr else None
    return None


def position_decision(profile, snapshot, history, position, state, metrics, *, automatic=True):
    """Persist peaks/initial risk separately from broker-confirmed management steps."""
    state = deepcopy(state)
    buy = position['side']=='BUY'
    sign = 1 if buy else -1
    close = snapshot['bid' if buy else 'ask']
    gain = sign*(close-position['price_open'])
    management, dynamic = profile['management'], profile['take_profit']['dynamic']
    if automatic and weekend_close_due(snapshot,profile['sessions']):
        return state, {'action':'CLOSE_POSITION','reason':'WEEKEND_CLOSE'}
    risk = state.get('initial_risk',0)
    candidates = []
    if automatic and risk > 0:
        if management['partial_close_enabled'] and not state.get('partial_intent') and gain >= risk*management['partial_close_at_rr']:
            return state, {'action':'PARTIAL_CLOSE','percent':management['partial_close_percent'],'reason':'PARTIAL_RR'}
        if management['breakeven_enabled'] and gain >= risk*management['breakeven_trigger_rr']:
            candidates.append((position['price_open']+sign*management['breakeven_offset_price_units'],snapshot['tick_size']))
        if profile['take_profit']['mode']=='ZRSI_DYNAMIC' and state.get('original_tp'):
            target=state['original_tp']
            remaining=sign*(target-close)
            values=[]
            for name in ('z','rsi'):
                if dynamic['extend_use_'+name]:
                    initial,current=state.get('entry_'+name),metrics.get(name)
                    values.append(initial is not None and current is not None and sign*(current-initial)>0)
            if not state.get('extended') and remaining <= dynamic['near_tp_distance']:
                if _combine(values,dynamic['extend_logic']):
                    state.update(extended=True,extension_time=snapshot['server_time'])
                elif remaining <= 0:
                    return state, {'action':'CLOSE_POSITION','reason':'ORIGINAL_TP'}
            if state.get('extended'):
                reversals=[]
                for name in ('z','rsi'):
                    if not dynamic['extend_use_'+name]:
                        continue
                    current=metrics.get(name)
                    if current is None:
                        reversals.append(False)
                        continue
                    previous=state.get('peak_'+name,current)
                    peak=max(previous,current) if buy else min(previous,current)
                    state['peak_'+name]=peak
                    reversals.append(sign*(peak-current)>=dynamic['exit_'+name+'_reverse_delta'])
                if _combine(reversals,dynamic['extend_logic']):
                    return state, {'action':'CLOSE_POSITION','reason':'ZRSI_REVERSAL'}
                if snapshot['server_time']-state['extension_time']>=dynamic['max_extension_minutes']*60:
                    return state, {'action':'CLOSE_POSITION','reason':'EXTENSION_TIMEOUT'}
                if -remaining>=dynamic['max_extension_price_units']:
                    return state, {'action':'CLOSE_POSITION','reason':'MAX_EXTENSION'}
                if dynamic['lock_sl_at_original_tp']:
                    candidates.append((target+sign*dynamic['lock_profit_buffer'],snapshot['tick_size']))
        mode=management['sl_tighten_mode']
        if mode=='ZRSI_ASSIST' and state.get('extended'):
            candidates.append((state['original_tp']+sign*dynamic['lock_profit_buffer'],snapshot['tick_size']))
        elif mode in {'STRUCTURE','ATR'}:
            try:
                candidate=stop_candidate(mode,profile,snapshot,history,position)
                if candidate is not None: candidates.append((candidate,snapshot['tick_size']))
            except TradePlanError:
                pass  # Incomplete bar history cannot create a new stop.
    if (automatic and management['trailing_enabled']) or state.get('manual_trailing'):
        try:
            candidate=stop_candidate(management['trailing_mode'],profile,snapshot,history,position,trailing=True)
            if candidate is not None: candidates.append((candidate,max(snapshot['tick_size'],management['trailing_step_price_units'])))
        except TradePlanError:
            pass
    old=position.get('sl',0)
    gap=max(snapshot.get('stops_level',0),snapshot.get('freeze_level',0))*snapshot['point']
    valid=[]
    for candidate, step in candidates:
        if candidate<=0: continue
        candidate=grid(candidate,snapshot['tick_size'],up=not buy)
        if sign*(close-candidate)<max(gap,snapshot['tick_size'])-1e-9: continue
        if old and sign*(candidate-old)<step-1e-9: continue
        valid.append(candidate)
    if valid:
        return state, {'action':'MODIFY_POSITION','sl':max(valid) if buy else min(valid),'tp':position.get('tp',0),'reason':'TIGHTEN_SL'}
    return state, None
