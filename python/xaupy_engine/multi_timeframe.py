"""Additional independent setup/reversal confirmations, never extra orders."""
from copy import deepcopy


class MultiTimeframeConfirmation:
    def __init__(self,owner):
        from .strategy_engine import StrategyEngine
        self.owner=owner;self.engines={};self.consumed={};self.sequence=0;self.rows=[]
        cfg=owner.profile.get('mtf',{})
        self.logic=cfg.get('logic','AND')
        pullback=[s for s in cfg.get('pullback_timeframes','').split(',') if s]
        trigger=[s for s in cfg.get('trigger_timeframes','').split(',') if s]
        if not pullback and not trigger:return
        for p in pullback or [owner.profile['timeframes']['pullback']]:
            for t in trigger or [owner.profile['timeframes']['trigger']]:
                if (p,t)==(owner.profile['timeframes']['pullback'],owner.profile['timeframes']['trigger']):continue
                profile=deepcopy(owner.profile);profile['mtf']=dict(pullback_timeframes='',trigger_timeframes='',logic='AND')
                profile['timeframes'].update(pullback=p,trigger=t)
                self.engines[p+'/'+t]=StrategyEngine(profile,max_history=owner.max_history)

    def reset(self,reason):
        self.consumed={};self.rows=[];self.sequence=0
        for engine in self.engines.values():engine.reset_setup(reason)

    def snapshot(self,payload):
        for engine in self.engines.values():engine.ingest_snapshot(payload)

    def tick(self,timestamp,bid,ask,continuous):
        self.sequence+=1
        for engine in self.engines.values():
            if self.sequence==1:
                # Replay may seed closed history directly before the first tick.
                engine.history={tf:list(bars) for tf,bars in self.owner.history.items()}
            engine.ingest_tick_batch(dict(symbol=self.owner.profile['strategy']['symbol'],tick_batch=dict(
                stream_id='mtf-observed',sequence=self.sequence,complete=continuous,
                ticks=[dict(time_msc=timestamp,bid=bid,ask=ask)])))

    def permits(self,side,observed_at):
        from .strategy_engine import HISTORY_TIMEFRAME_SECONDS
        self.rows=[]
        for key,engine in self.engines.items():
            signal=engine.last_signal or {};timeframe=engine.profile['timeframes']['trigger']
            period=HISTORY_TIMEFRAME_SECONDS[timeframe]
            when=signal.get('tick_time_msc',0)/1000 if 'tick_time_msc' in signal else signal.get('bar_time',0)+period
            passed=(signal.get('side')==side and engine.state=='TRIGGERED_'+side and
                signal.get('sequence',0)>self.consumed.get(key,0) and 0<=observed_at-when<=period*self.owner.profile['entry']['max_signal_age_bars'])
            self.rows.append(dict(pair=key,state=engine.state,side=signal.get('side'),signal_sequence=signal.get('sequence'),
                observed_at=when,passed=passed,reason=engine.blocked_reason))
        values=[row['passed'] for row in self.rows]
        return not values or (all(values) if self.logic=='AND' else any(values))

    def consume(self):
        for row in self.rows:
            if row['passed']:self.consumed[row['pair']]=row['signal_sequence']

    def status(self):
        return dict(enabled=bool(self.engines),logic=self.logic,pairs=list(self.engines),confirmations=deepcopy(self.rows),
            semantics='Primary signal plus independent additional pair confirmations; current side, bounded age, each consumed once')
