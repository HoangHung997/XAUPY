"""Observed bid/ask replay using the production entry and management policies.

Signals and management intentions execute on the next supplied quote. No OHLC
path is invented; server SL/TP are evaluated before newly dispatched changes.
"""
from __future__ import annotations
from copy import deepcopy
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from .backtest import (BacktestEngine, BacktestError, BacktestCancelled, HistoricalDataset,
                       BacktestState, OpenPosition, build_close_schedule)
from .strategy_engine import Bar, StrategyEngine
from .trade_plan import entry_guard, plan_entry, TradePlanError, grid, session_allowed, weekend_close_due
from .position_management import position_decision
from .broker_execution import BrokerExecution
from .tick_tape import TickTape

TICK_BACKTEST_MODEL = 'OBSERVED_BID_ASK_NEXT_TICK_V1'


@dataclass(frozen=True)
class TickDataset(HistoricalDataset):
    ticks: tuple[dict, ...] | TickTape
    context: dict

    @property
    def first_time(self): return self.ticks[0]['time_msc']//1000
    @property
    def last_time(self): return self.ticks[-1]['time_msc']//1000

    def inspect_payload(self):
        return {**super().inspect_payload(),'timeframe':'TICKS + M1','input_model':'REAL_TICKS',
                'tick_count':len(self.ticks),'continuous_ticks':sum(t['continuous'] for t in self.ticks)}


def tick_dataset(base: HistoricalDataset, payload: dict) -> TickDataset:
    ticks=payload.get('ticks')
    if not isinstance(ticks,(list,TickTape)) or not ticks: raise BacktestError('Observed tick dataset needs nonempty ticks')
    normalized=[]
    previous=0
    for index,row in enumerate(ticks if not isinstance(ticks,TickTape) else ()):
        if not isinstance(row,dict): raise BacktestError(f'Invalid tick {index}')
        stamp,bid,ask=row.get('time_msc'),row.get('bid'),row.get('ask')
        if type(stamp) is not int or stamp<=0 or stamp<previous: raise BacktestError('Tick timestamps must be positive and nondecreasing')
        if any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in (bid,ask)) or ask<bid:
            raise BacktestError('Tick bid/ask must be finite positive ordered quotes')
        continuous=row.get('continuous',True)
        if type(continuous) is not bool: raise BacktestError('Tick continuity must be boolean')
        normalized.append(dict(time_msc=stamp,bid=float(bid),ask=float(ask),continuous=continuous))
        previous=stamp
    context=payload.get('tick_context',{})
    if not isinstance(context,dict): raise BacktestError('tick_context must be an object')
    if base.metadata.timezone_offset_minutes!=0:
        raise BacktestError('Tick archive epochs must preserve broker calendar with zero additional timezone offset')
    quotes=ticks.seal() if isinstance(ticks,TickTape) else tuple(normalized)
    return TickDataset(base.path,base.fingerprint,base.metadata,base.bars,quotes,deepcopy(context))


class TickBacktestEngine(BacktestEngine):
    def _validate_profile_support(self):
        # Profile schema already validates all enum values. Tick availability,
        # historical calendar and Friday session are checked against the dataset.
        pass

    def _snapshot(self,state,dataset,tick,pending):
        now=tick['time_msc']//1000
        self._ensure_day_state(state,dataset,now)
        key=self._day_key(dataset,now)
        metadata=dataset.metadata
        snapshot=dict(server_time=now,tick_time_msc=tick['time_msc'],bid=tick['bid'],ask=tick['ask'],
            symbol=metadata.symbol,magic=self.profile['execution']['magic'],terminal_connected=True,
            balance=state.balance,point=metadata.point_size,tick_size=metadata.tick_size,tick_value=metadata.tick_value,
            volume_min=metadata.volume_min,volume_max=metadata.volume_max,volume_step=metadata.volume_step,
            stops_level=metadata.stops_level_points,freeze_level=metadata.freeze_level_points,
            positions=[self._position(p) for p in state.positions],
            orders=[dict(type=p['plan']['order_type'],volume_current=p['plan']['volume'],price_open=p['plan']['price'],sl=p['plan']['sl']) for p in pending],
            demo_once_guard=dict(history_complete=True,broker_day_start=now//86400*86400,
                trades_today=state.trades_by_day.get(key,0),consecutive_losses=state.consecutive_losses_by_day.get(key,0),
                last_exit_time=state.last_exit_time or 0,day_start_balance=state.day_start_balance[key],daily_realized=state.pnl_by_day[key]))
        if 'server_utc_offset_seconds' in dataset.context:
            snapshot['server_utc_offset_seconds']=dataset.context['server_utc_offset_seconds']
        if self.profile['sessions']['weekend_close_enabled']:
            seconds=dataset.context.get('friday_session_end_seconds')
            if type(seconds) is not int or not 0<seconds<=172800: raise BacktestError('Actual Friday session end required in tick_context')
            weekday=datetime.fromtimestamp(now,timezone.utc).weekday()
            snapshot['weekend_session_end']=now//86400*86400+(4-weekday)*86400+seconds
        if self.profile['news']['enabled']:
            calendar=dataset.context.get('calendar',{})
            if not (type(calendar.get('coverage_start')) is int and type(calendar.get('coverage_end')) is int and
                    calendar['coverage_start']<=now<=calendar['coverage_end'] and isinstance(calendar.get('events'),list)):
                raise BacktestError('Historical news coverage required for every replayed tick')
            snapshot['calendar']={**calendar,'available':True,'as_of':now}
        return snapshot

    def _position(self,p):
        return dict(ticket=p.trade_id,position_identifier=p.trade_id,side=p.side,price_open=p.entry_price,
                    sl=p.sl,tp=p.tp,volume=p.volume,symbol=self.profile['strategy']['symbol'],magic=self.profile['execution']['magic'])

    def _fill(self,state,strategy,dataset,tick,planned,signal,management):
        side=planned['side']; buy=side=='BUY'
        slip=self.profile['costs']['max_slippage_points']*dataset.metadata.point_size
        price=grid(tick['ask' if buy else 'bid']+(slip if buy else -slip),dataset.metadata.tick_size,up=buy)
        risk=(price-planned['sl']) if buy else (planned['sl']-price)
        cash=risk/dataset.metadata.tick_size*dataset.metadata.tick_value*planned['volume']+self.commission_per_lot*planned['volume']
        if risk<=0 or risk>self.profile['stop_loss']['max_price_units']+1e-9 or cash>planned['max_loss_money']+1e-9:
            self._skip(state,'FILL_RISK_BUDGET');return
        quote=tick['bid' if buy else 'ask']; gap=dataset.metadata.stops_level_points*dataset.metadata.point_size
        if (quote-planned['sl'] if buy else planned['sl']-quote)<max(gap,dataset.metadata.tick_size)-1e-9:
            self._skip(state,'FILL_INVALID_SL');return
        if planned['tp'] and (planned['tp']-quote if buy else quote-planned['tp'])<max(gap,dataset.metadata.tick_size)-1e-9:
            self._skip(state,'FILL_INVALID_TP');return
        now=tick['time_msc']//1000
        position=OpenPosition(trade_id=state.next_trade_id,signal_sequence=signal['sequence'],signal_time=signal['bar_time'],
            side=side,entry_time=now,entry_price=price,volume=planned['volume'],sl=planned['sl'],tp=planned['tp'],
            original_sl=planned['sl'],original_risk=risk,profile_hash=strategy.profile_hash,dataset_fingerprint=dataset.fingerprint,
            initial_volume=planned['volume'],original_tp=planned['original_tp'],hard_tp=planned['tp'],
            entry_mode='STOP_CONFIRM' if planned['order_type']!=side else 'MARKET',
            pending_trigger_price=planned['price'] if planned['order_type']!=side else None)
        metrics=(signal.get('indicators') or {}).get('trigger',{})
        management[position.trade_id]=dict(initial_risk=risk,original_tp=planned['original_tp'],entry_rsi=metrics.get('rsi'),entry_z=metrics.get('z'))
        state.next_trade_id+=1;state.positions.append(position)
        key=self._day_key(dataset,now);state.trades_by_day[key]=state.trades_by_day.get(key,0)+1
        entry_fee=self.commission_per_lot*planned['volume']/2
        state.balance-=entry_fee;state.pnl_by_day[key]-=entry_fee
        position.realized_commission=entry_fee;position.realized_net=-entry_fee
        position.management_events.append(dict(event='OBSERVED_TICK_FILL',time_msc=tick['time_msc'],signal_time_msc=signal.get('tick_time_msc'),slippage_assumed_price_units=slip))

    def _close_position(self,*args,**kwargs):
        # The configured fee is round trip; half was charged on entry.
        commission=self.commission_per_lot;self.commission_per_lot=commission/2
        try:super()._close_position(*args,**kwargs)
        finally:self.commission_per_lot=commission

    def _apply_partial_close(self,*args,**kwargs):
        commission=self.commission_per_lot;self.commission_per_lot=commission/2
        try:super()._apply_partial_close(*args,**kwargs)
        finally:self.commission_per_lot=commission

    def _exit_quote(self,position,tick,dataset):
        slip=self.profile['costs']['max_slippage_points']*dataset.metadata.point_size
        return grid(tick['bid']-slip if position.side=='BUY' else tick['ask']+slip,dataset.metadata.tick_size,up=position.side=='SELL')

    def _protect(self,state,dataset,tick):
        for p in list(state.positions):
            quote=tick['bid' if p.side=='BUY' else 'ask'];sign=1 if p.side=='BUY' else -1
            gain=sign*(quote-p.entry_price)
            p.mfe_price_units=max(p.mfe_price_units,gain);p.mae_price_units=max(p.mae_price_units,-gain)
            reason='SL' if sign*(quote-p.sl)<=0 else 'TP' if p.tp and sign*(quote-p.tp)>=0 else None
            if reason:
                price=self._exit_quote(p,tick,dataset) if reason=='SL' else p.tp
                self._close_position(state,dataset,p,exit_time=tick['time_msc']//1000,exit_price=price,reason=reason)

    def run(self,dataset,*,from_date,to_date,cancel_check=None,progress=None):
        if not isinstance(dataset,TickDataset): raise BacktestError('REAL_TICKS requires an observed tick dataset')
        if dataset.metadata.symbol!=self.profile['strategy']['symbol']: raise BacktestError('Dataset/profile symbol mismatch')
        if self.commission_per_lot>self.profile['costs']['max_commission_per_lot']: raise BacktestError('Historical commission exceeds configured ceiling')
        start,end=self._parse_date(from_date,'from_date'),self._parse_date(to_date,'to_date')
        if end<start: raise BacktestError('Invalid date range')
        if isinstance(dataset.ticks,TickTape):
            from datetime import timedelta
            start_ms=int(datetime.combine(start,datetime.min.time(),timezone.utc).timestamp()*1000)
            end_ms=int(datetime.combine(end+timedelta(days=1),datetime.min.time(),timezone.utc).timestamp()*1000)
            ticks=dataset.ticks.between(start_ms,end_ms)
        else:ticks=[t for t in dataset.ticks if start<=dataset.local_date(t['time_msc']//1000)<=end]
        if not ticks: raise BacktestError('No observed ticks in selected dates')
        strategy=StrategyEngine(self.profile)
        schedule=build_close_schedule(dataset.bars,cancel_check=cancel_check)
        closing=sorted(schedule);closed_index=0
        # Seed only closed indicator history before the first requested quote.
        # Re-evaluating every old setup cannot influence this run (setup is reset
        # below), and becomes quadratic with a large archive.
        warmup={tf:deque(maxlen=strategy.max_history) for tf in strategy.history}
        while closed_index<len(closing) and closing[closed_index]<=ticks[0]['time_msc']//1000:
            if cancel_check and closed_index%1024==0 and cancel_check():raise BacktestCancelled('Backtest cancelled')
            for tf,bar in schedule[closing[closed_index]].items():warmup[tf].append(bar)
            closed_index+=1
        strategy.history={tf:list(bars) for tf,bars in warmup.items()}
        state=BacktestState(balance=self.initial_balance,peak_equity=self.initial_balance)
        management={};queued=[];pending=[];last_signal=0;gaps=0
        for index,tick in enumerate(ticks):
            if cancel_check and cancel_check(): raise BacktestCancelled('Backtest cancelled')
            if progress and index%128==0:progress(index,len(ticks))
            now=tick['time_msc']//1000
            while closed_index<len(closing) and closing[closed_index]<=now:
                strategy.ingest_snapshot({'symbol':dataset.metadata.symbol,'bars':{tf:vars(bar) for tf,bar in schedule[closing[closed_index]].items()}})
                closed_index+=1
            if index==0:
                strategy.reset_setup('TICK_REPLAY_START')
                last_signal=strategy.signal_sequence
            snapshot=self._snapshot(state,dataset,tick,pending)
            self._protect(state,dataset,tick)
            # Deliver only intents created by an earlier observed quote.
            delivering=queued;queued=[]
            for intent in delivering:
                action=intent['action']
                if action=='ENTRY':
                    if not tick['continuous'] or tick['time_msc']-intent['time_msc']>5000:
                        self._skip(state,'ENTRY_TICK_GAP_OR_EXPIRED');continue
                    try:
                        snapshot=self._snapshot(state,dataset,tick,pending);entry_guard(snapshot,self.profile)
                        plan=intent['plan']
                        if plan['order_type']!=plan['side']:
                            distance=(plan['price']-tick['ask']) if plan['side']=='BUY' else (tick['bid']-plan['price'])
                            minimum=max(dataset.metadata.tick_size,dataset.metadata.stops_level_points*dataset.metadata.point_size)
                            if distance<minimum-1e-9:
                                self._skip(state,'PENDING_INVALID_DISTANCE_ON_DELIVERY');continue
                            pending.append(intent)
                            state.pending_entry_events.append(dict(event='PLACED',time=now,side=plan['side'],price=plan['price']))
                        else:self._fill(state,strategy,dataset,tick,plan,intent['signal'],management)
                    except TradePlanError as exc:
                        self._skip(state,str(exc));continue
                    continue
                position=next((p for p in state.positions if p.trade_id==intent['ticket']),None)
                if position is None:continue
                if not tick['continuous'] or tick['time_msc']-intent['time_msc']>5000:
                    self._skip(state,'MANAGEMENT_TICK_GAP_OR_EXPIRED');continue
                if action=='CLOSE_POSITION':
                    self._close_position(state,dataset,position,exit_time=now,exit_price=self._exit_quote(position,tick,dataset),reason=intent['reason'])
                elif action=='MODIFY_POSITION':
                    try:
                        BrokerExecution._validate_stop_change(self._position(position),intent,self._snapshot(state,dataset,tick,pending))
                        position.sl=intent['sl'];position.tp=intent['tp'];position.sl_tighten_updates+=1
                        position.breakeven_applied |= (position.sl>=position.entry_price if position.side=='BUY' else position.sl<=position.entry_price)
                    except TradePlanError as exc:
                        self._skip(state,str(exc));continue
                elif action=='PARTIAL_CLOSE':
                    slip=self.profile['costs']['max_slippage_points']*dataset.metadata.point_size
                    bid=tick['bid']+(-slip if position.side=='BUY' else slip)
                    self._apply_partial_close(state,dataset,position,Bar(now,bid,bid,bid,bid),tick['ask']-tick['bid'])
                    management[position.trade_id]['partial_intent']=True
                    if not position.partial_close_applied:
                        self._skip(state,'PARTIAL_REMAINDER_BELOW_MINIMUM');continue
                position.management_events.append(dict(event=action,time_msc=tick['time_msc'],reason=intent.get('reason')))
            for intent in list(pending):
                plan=intent['plan'];snapshot=self._snapshot(state,dataset,tick,pending)
                if now>=plan['expiration'] or not session_allowed(snapshot,self.profile['sessions']) or weekend_close_due(snapshot,self.profile['sessions']):
                    pending.remove(intent);self._skip(state,'PENDING_EXPIRED_OR_SESSION');continue
                buy=plan['side']=='BUY';touch=tick['ask']>=plan['price'] if buy else tick['bid']<=plan['price']
                if touch:
                    pending.remove(intent)
                    self._fill(state,strategy,dataset,tick,plan,intent['signal'],management)
            if not tick['continuous']:gaps+=1
            status=strategy.ingest_tick_batch({'symbol':dataset.metadata.symbol,'tick_batch':{
                'stream_id':'historical-observed','sequence':index+1,'complete':tick['continuous'],'ticks':[tick]}})
            display=status.get('display') or {}
            metrics=display.get('indicators',{}).get('trigger',{}) if display.get('continuous') else {}
            snapshot=self._snapshot(state,dataset,tick,pending)
            for position in state.positions:
                updated,decision=position_decision(self.profile,snapshot,strategy.history,self._position(position),management[position.trade_id],metrics)
                management[position.trade_id]=updated
                position.dynamic_extended=bool(updated.get('extended'))
                position.dynamic_extension_time=updated.get('extension_time')
                if decision:queued.append({**decision,'ticket':position.trade_id,'time_msc':tick['time_msc']})
            if self.profile['entry']['cancel_on_opposite_setup'] and status.get('armed_side'):
                for intent in list(pending):
                    if intent['plan']['side']!=status['armed_side']:
                        pending.remove(intent);self._skip(state,'PENDING_OPPOSITE_SETUP')
            sequence=status['signal_sequence']
            if sequence>last_signal:
                last_signal=sequence;signal=deepcopy(status['last_signal'])
                try:
                    entry_guard(snapshot,self.profile)
                    plan=plan_entry(self.profile,snapshot,strategy.history,signal['side'])
                    queued.append(dict(action='ENTRY',plan=plan,signal=signal,time_msc=tick['time_msc']))
                except TradePlanError as exc:self._skip(state,str(exc))
            # Sample every quote; one row per second retains its worst drawdown.
            previous_dd=state.drawdown_curve[-1].copy() if state.drawdown_curve and state.drawdown_curve[-1]['time']==now else None
            self._append_curve_point(state,dataset,Bar(now-60,tick['bid'],tick['bid'],tick['bid'],tick['bid']),tick['ask']-tick['bid'],replace_same_time=True)
            if previous_dd and previous_dd['drawdown_usd']>state.drawdown_curve[-1]['drawdown_usd']:state.drawdown_curve[-1]=previous_dd
        final=ticks[-1]
        for p in list(state.positions):self._close_position(state,dataset,p,exit_time=final['time_msc']//1000,exit_price=self._exit_quote(p,final,dataset),reason='END_OF_DATA')
        previous_dd=state.drawdown_curve[-1].copy()
        self._append_curve_point(state,dataset,Bar(final['time_msc']//1000-60,final['bid'],final['bid'],final['bid'],final['bid']),final['ask']-final['bid'],replace_same_time=True)
        if previous_dd['drawdown_usd']>state.drawdown_curve[-1]['drawdown_usd']:state.drawdown_curve[-1]=previous_dd
        if queued:self._skip(state,'UNEXECUTED_INTENT_AT_END')
        if pending:self._skip(state,'PENDING_END_OF_DATA')
        result=self._result_payload(state,strategy,dataset,start_date=start,end_date=end)
        result.update(model=TICK_BACKTEST_MODEL,execution_revision='SHARED_LIVE_ENTRY_AND_POSITION_POLICY_V1',
            tick_count=len(ticks),discontinuous_ticks=gaps,spread_model='OBSERVED_BID_ASK',
            fill_model='Next observed quote; configured adverse slippage; TP at limit, SL at observed quote plus adverse slippage; no liquidity/latency guarantee',
            swap_model='Not included; review overnight exposure',broker_execution_requested=False)
        result.pop('result_hash',None)
        result['result_hash']=hashlib.sha256(json.dumps(result,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        if progress:progress(len(ticks),len(ticks))
        return result
