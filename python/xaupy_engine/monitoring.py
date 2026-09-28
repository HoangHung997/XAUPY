"""Measured host telemetry and reference market clocks; no execution authority."""
from copy import deepcopy
from datetime import datetime,timezone,timedelta
import time
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError

from .config_schema import TIMEFRAME_OPTIONS
from .strategy_engine import StrategyEngine
from .demo_once import profile_hash


def market_sessions(utc=None):
    utc=utc or datetime.now(timezone.utc)
    result=[]
    for name,zone,start,end in [('Sydney','Australia/Sydney',8,17),('Tokyo','Asia/Tokyo',9,18),
                                ('London','Europe/London',8,17),('New York','America/New_York',8,17)]:
        try:
            local=utc.astimezone(ZoneInfo(zone))
            opening=local.replace(hour=start,minute=0,second=0,microsecond=0)
            closing=local.replace(hour=end,minute=0,second=0,microsecond=0)
            active=local.weekday()<5 and opening<=local<closing
            boundary=closing if active else opening
            while boundary<=local or boundary.weekday()>=5: boundary+=timedelta(days=1)
            result.append(dict(name=name,active=active,local_time=local.strftime('%H:%M'),
                minutes_to_change=int((boundary-local).total_seconds()/60),timezone=zone,
                basis='REFERENCE_FOREX_SESSION',available=True))
        except ZoneInfoNotFoundError:
            result.append(dict(name=name,available=False,reason='TIMEZONE_DATABASE_UNAVAILABLE'))
    return result


class MonitoringService:
    def __init__(self,root):
        self.root=root
        self._last=0
        self._cached={}
        self._scanners={}
        self._hash=None
        self._psutil=None
        try:
            import psutil
            self._psutil=psutil
            psutil.cpu_percent(None)
        except ImportError:
            pass

    def resources(self):
        if self._psutil is None:
            return {'available':False,'reason':'RESOURCE_PROVIDER_MISSING'}
        try:
            psutil=self._psutil
            memory=psutil.virtual_memory()
            disk=psutil.disk_usage(str(self.root))
            return dict(available=True,cpu_percent=psutil.cpu_percent(None),ram_percent=memory.percent,
                disk_percent=disk.percent,disk_free_bytes=disk.free,ram_total_bytes=memory.total,
                process_rss_bytes=psutil.Process().memory_info().rss,disk_path=str(self.root.anchor),
                sampled_utc=datetime.now(timezone.utc).isoformat())
        except (OSError,RuntimeError) as exc:
            return {'available':False,'reason':str(exc)}

    def scan(self,server,snapshot):
        digest=profile_hash(server.active_profile)
        if digest!=self._hash:
            self._scanners={}
            self._hash=digest
        rows=[]
        for tf in TIMEFRAME_OPTIONS:
            if tf not in self._scanners:
                cfg=deepcopy(server.active_profile)
                cfg['timeframes']={role:tf for role in ('direction','pullback','trigger')}
                cfg['mtf']=dict(pullback_timeframes='',trigger_timeframes='',logic='AND')
                # The matrix is explicitly closed-bar research; the active
                # strategy's tick decisions remain in its own three-role panel.
                cfg['trigger']['confirm_closed_bar']=True
                self._scanners[tf]=StrategyEngine(cfg)
            scanner=self._scanners[tf]
            if snapshot:
                bars=server.strategy.history.get(tf,[])
                latest=bars[-1].time if bars else None
                previous=scanner.history[tf][-1].time if scanner.history[tf] else None
                scanner.history={name:list(history) for name,history in server.strategy.history.items()}
                if latest!=previous: scanner._evaluate({tf})
            status=scanner.status_payload(market_connected=bool(snapshot))
            rows.append(dict(timeframe=tf,direction=status['direction'],state=status['state'],armed_side=status['armed_side'],
                indicators=status['indicators'],conditions=status['conditions'],reason=status['blocked_reason'],basis='CLOSED_BAR_SCAN'))
        return rows

    def payload(self,server):
        now=time.monotonic()
        if self._cached and now-self._last<1: return deepcopy(self._cached)
        self._last=now
        snapshot=server.bridge.latest_fresh_snapshot() or {}
        if hasattr(server,'library'): snapshot=server.library.merge_calendar(snapshot)
        native_logs=server.mt5_logs.poll(snapshot) if hasattr(server,'mt5_logs') else {'available':False}
        execution=server.execution.status()
        alerts=server.journal.query(levels=['WARN','ERROR'],date_scope='TODAY',limit=10)['events']
        guard=snapshot.get('demo_once_guard') or {}
        kpi={'profit_today':guard.get('daily_realized'),'trades_today':guard.get('trades_today'),
             'history_complete':guard.get('history_complete',False),'drawdown_scope':'OBSERVED_STRATEGY_EQUITY',
             'max_drawdown_pct':None,'observed_since':None}
        if guard.get('history_complete') and hasattr(server.execution,'meta'):
            key='equity:'+':'.join(str(snapshot.get(k,'')) for k in ('account_login','account_server','symbol','magic'))+':'+str(guard['broker_day_start'])
            equity=guard['day_start_balance']+guard['daily_realized']+sum(p.get('profit',0)+p.get('swap',0) for p in snapshot.get('positions',[]))
            previous=server.execution.meta(key,{'peak':equity,'max_drawdown_pct':0.,'observed_since':snapshot['server_time']})
            peak=max(previous['peak'],equity)
            drawdown=max(previous['max_drawdown_pct'],(peak-equity)/peak*100 if peak>0 else 0)
            state={**previous,'peak':peak,'max_drawdown_pct':drawdown}
            if server.execution.meta(key)!=state: server.execution._save_meta(key,state)
            kpi.update(max_drawdown_pct=drawdown,observed_since=state['observed_since'])
        self._cached=dict(available=bool(snapshot),resources=self.resources(),sessions=market_sessions(),
            calendar=snapshot.get('calendar',{'available':False,'reason':'WAITING_FOR_BRIDGE','events':[]}),
            symbol_sessions=snapshot.get('symbol_sessions',[]),broker_ping_ms=snapshot.get('broker_ping_ms'),
            snapshot_age_ms=server.bridge.status().age_ms,server_time=snapshot.get('server_time'),
            execution=execution,alerts=alerts,scanner=self.scan(server,snapshot),
            kpi=kpi,native_logs=native_logs)
        return deepcopy(self._cached)
