"""Durable intent lifecycle. Only the owning MT5 EA may execute queued commands."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import time
from uuid import UUID, uuid4, uuid5

from .demo_once import profile_hash
from .trade_plan import TradePlanError, entry_guard, grid, number, plan_entry, volume_on_grid, pending_cancellation_reason
from .position_management import position_decision


IDENTITY = ('account_login','account_server','symbol','magic')
TERMINAL_STATES = {'CONFIRMED','REJECTED','CANCELLED','EXPIRED','APPLIED_LOCAL','BATCH_PARTIAL'}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


class BrokerExecution:
    def __init__(self, root: Path, bridge, strategy, settings):
        self.bridge, self.strategy, self.settings = bridge, strategy, settings
        self._profile = getattr(strategy, 'profile', None)
        self.db = sqlite3.connect(Path(root)/'execution-v1.sqlite3', isolation_level=None)
        try:
            self.db.row_factory = sqlite3.Row
            self.db.execute('PRAGMA journal_mode=WAL')
            self.db.execute('PRAGMA synchronous=FULL')
            self.db.executescript('''
                CREATE TABLE IF NOT EXISTS intents (
                    id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, state TEXT NOT NULL,
                    command TEXT NOT NULL, result TEXT, created REAL NOT NULL, updated REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS execution_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS position_state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            ''')
            self.db.execute("UPDATE intents SET state='UNKNOWN', updated=? WHERE state='DISPATCHED'", (time.time(),))
            self.db.execute("UPDATE intents SET state='CANCELLED', updated=? WHERE state='QUEUED'", (time.time(),))
            self.policy = self.meta('policy', {'mode':'OFF'})
            # Startup behavior is the user's explicit local setting, never an import.
            if not settings['safety']['auto_start_trading']:
                self.policy['mode'] = 'OFF'
            self.startup_sync_pending=(self.policy['mode']!='OFF' and settings['safety']['require_reconciliation'])
            self.last_blocker = ''
            self.awaiting_snapshot = False
            self.closed = False
            self.management_warnings = {}
            self._save_meta('policy', self.policy)
        except BaseException:
            self.db.close()
            raise

    def close(self):
        if not self.closed:
            self.closed = True
            self.db.close()

    def meta(self, key, default=None):
        row = self.db.execute('SELECT value FROM execution_meta WHERE key=?', (key,)).fetchone()
        return json.loads(row['value']) if row else deepcopy(default)

    def _save_meta(self, key, value):
        self.db.execute('INSERT OR REPLACE INTO execution_meta VALUES (?,?)', (key,canonical(value)))

    def status(self):
        # Lost replies must be reconciled even when the socket itself survives.
        self.db.execute("UPDATE intents SET state='UNKNOWN',updated=? WHERE state='DISPATCHED' AND updated<?", (time.time(),time.time()-15))
        counts = {r['state']:r['n'] for r in self.db.execute('SELECT state,COUNT(*) n FROM intents GROUP BY state')}
        fresh = (self.bridge.execution_snapshot() if hasattr(self.bridge, 'execution_snapshot')
                 else self.bridge.latest_fresh_snapshot())
        profile = getattr(self.strategy, 'profile', None) or self._profile
        reason = ''
        entry_reason = ''
        if self.policy['mode'] == 'OFF':
            reason = 'USER_STOPPED'
        else:
            try:
                self._snapshot()
                if any((fresh or {}).get(k) != self.policy.get(k) for k in IDENTITY):
                    raise TradePlanError('ACCOUNT_OR_SYMBOL_CHANGED')
                if profile:
                    self._account_permission(fresh, profile)
                elif fresh.get('account_trade_mode') == 'REAL':
                    raise TradePlanError('USER_REAL_PERMISSION_REQUIRED')
                if self.startup_sync_pending:
                    raise TradePlanError('STARTUP_BRIDGE_SYNC_PENDING')
            except TradePlanError as exc:
                reason = str(exc)
        enabled = self.policy['mode'] != 'OFF' and not reason
        if enabled:
            if counts.get('UNKNOWN', 0) or counts.get('DISPATCHED', 0):
                entry_reason = 'RECONCILIATION_REQUIRED'
            elif self.awaiting_snapshot:
                entry_reason = 'AWAITING_POST_TRADE_SNAPSHOT'
            elif profile:
                try:
                    entry_guard(getattr(self, 'snapshot_transform', lambda v: v)(deepcopy(fresh)), profile,
                                reserved_entries=sum(json.loads(r['command']).get('action') == 'ENTRY'
                                    for r in self.db.execute("SELECT command FROM intents WHERE state='QUEUED'")))
                    if fresh['ask']-fresh['bid'] > profile['costs']['max_spread_price_units']+1e-12:
                        raise TradePlanError('SPREAD_LIMIT')
                    if not profile['strategy']['allow_buy'] and not profile['strategy']['allow_sell']:
                        raise TradePlanError('SIDE_DISABLED')
                except TradePlanError as exc:
                    entry_reason = str(exc)
        entry_enabled = enabled and not entry_reason
        cfg = (profile or {}).get('execution', {})
        permission = bool(self.settings['safety']['allow_real_account'])
        today={}
        if fresh and fresh.get('server_utc_offset_seconds') is not None:
            start=fresh['server_time']//86400*86400-fresh['server_utc_offset_seconds']
            today={r['state']:r['n'] for r in self.db.execute("SELECT state,COUNT(*) n FROM intents WHERE created>=? AND json_extract(command,'$.account_login')=? AND json_extract(command,'$.account_server')=? GROUP BY state",
                   (start,fresh.get('account_login'),fresh.get('account_server')))}
        return {'mode':self.policy['mode'], 'identity':{k:self.policy.get(k) for k in IDENTITY},
                'reason':reason or entry_reason, 'last_attempt_reason':self.last_blocker,
                'entry_reason':reason or entry_reason, 'management_reason':reason,
                'entry_enabled':entry_enabled, 'management_enabled':enabled,
                'allow_buy':(profile or {}).get('strategy',{}).get('allow_buy',False),
                'allow_sell':(profile or {}).get('strategy',{}).get('allow_sell',False),
                'profile_hash':profile_hash(profile) if profile else None,
                'quote_age_ms':(fresh or {}).get('quote_age_ms'),
                'snapshot_age_ms':(fresh or {}).get('snapshot_age_ms'),
                'quote_source':(fresh or {}).get('quote_source'),
                'permissions':{'local_allow_real':permission,
                    'profile_allow_real':cfg.get('allow_real_account') is True,
                    'profile_demo_only':cfg.get('demo_only',True),
                    'effective_allow_real':permission and cfg.get('allow_real_account') is True and cfg.get('demo_only') is False},
                'counts':counts, 'available':True,
                'counts_today':today,
                'execution_enabled':enabled,
                'trading_enabled':self.policy['mode']=='AUTO' and entry_enabled,
                'management_warnings':self.management_warnings,
                'recent':self.history(limit=20)}

    def history(self, limit=100, offset=0, intent_id=None):
        self._refresh_batches()
        if intent_id is not None:
            rows = self.db.execute('SELECT * FROM intents WHERE id=?', (str(intent_id),)).fetchall()
            return [dict(id=r['id'], state=r['state'], command=json.loads(r['command']),
                         result=json.loads(r['result']) if r['result'] else None,
                         created=r['created'], updated=r['updated']) for r in rows]
        return [dict(id=r['id'], state=r['state'], command=json.loads(r['command']),
                     result=json.loads(r['result']) if r['result'] else None, created=r['created'], updated=r['updated'])
                for r in self.db.execute('SELECT * FROM intents ORDER BY created DESC LIMIT ? OFFSET ?', (min(max(int(limit),1),500),max(int(offset),0)))]

    def query_history(self, payload):
        """Freeze membership while paging; results keep their own updated times."""
        limit, offset = payload.get('limit', 100), payload.get('offset', 0)
        if type(limit) is not int or not 1 <= limit <= 500 or type(offset) is not int or offset < 0:
            raise TradePlanError('INVALID_HISTORY_PAGE')
        cutoff = payload.get('snapshot_time')
        cutoff = time.time() if cutoff is None else number(cutoff, 'snapshot_time', positive=True)
        self._refresh_batches()
        intent_id = payload.get('intent_id')
        where, args = 'created<=?', [cutoff]
        if intent_id is not None:
            try:
                intent_id = str(UUID(intent_id))
            except (ValueError, TypeError, AttributeError):
                raise TradePlanError('INVALID_INTENT_ID')
            where += ' AND id=?'; args.append(intent_id)
        total = self.db.execute('SELECT COUNT(*) FROM intents WHERE '+where, args).fetchone()[0]
        rows = self.db.execute('SELECT * FROM intents WHERE '+where+' ORDER BY created DESC,id DESC LIMIT ? OFFSET ?',
                               [*args, limit, offset]).fetchall()
        items = [dict(id=r['id'],state=r['state'],command=json.loads(r['command']),
                      result=json.loads(r['result']) if r['result'] else None,created=r['created'],updated=r['updated']) for r in rows]
        return {'accepted':True, 'items':items, 'total':total, 'has_more':offset+len(items)<total,
                'snapshot_time':cutoff, 'offset':offset}

    def _refresh_batches(self):
        for row in self.db.execute("SELECT * FROM intents WHERE state='BATCH_QUEUED'").fetchall():
            result=json.loads(row['result'])
            states=[]
            for item in result['items']:
                child=self.db.execute('SELECT state,result FROM intents WHERE id=?',(item.get('intent_id'),)).fetchone()
                state=child['state'] if child else 'REJECTED'
                states.append(state)
                item.update(state=state,broker_result=json.loads(child['result']) if child and child['result'] else None)
            if any(s not in TERMINAL_STATES for s in states):
                continue
            success=[s in {'CONFIRMED','APPLIED_LOCAL'} for s in states]
            state=('APPLIED_LOCAL' if all(s=='APPLIED_LOCAL' for s in states) else 'CONFIRMED') if all(success) else 'BATCH_PARTIAL' if any(success) else 'REJECTED'
            result.update(state=state,accepted=all(success),code=state)
            self.db.execute('UPDATE intents SET state=?,result=?,updated=? WHERE id=?',(state,canonical(result),time.time(),row['id']))

    def set_mode(self, payload, profile):
        self._profile = profile
        mode = payload.get('mode')
        if mode not in {'OFF','MANUAL','AUTO'}:
            raise TradePlanError('INVALID_EXECUTION_MODE')
        if mode == 'OFF':
            self.policy['mode']='OFF'
            self.db.execute("UPDATE intents SET state='CANCELLED',updated=? WHERE state='QUEUED'", (time.time(),))
        else:
            snapshot = self._snapshot()
            if payload.get('confirmed') is not True:
                raise TradePlanError('USER_CONFIRMATION_REQUIRED')
            if any(payload.get(k)!=snapshot.get(k) for k in IDENTITY):
                raise TradePlanError('CONFIRMED_ACCOUNT_MISMATCH')
            self._account_permission(snapshot, profile)
            self.policy = {'mode':mode, **{k:snapshot[k] for k in IDENTITY}, 'confirmed_at':time.time()}
            # Do not trade the signal that was already visible before activation.
            self._save_meta('last_signal', self._signal_key(profile))
        self.last_blocker=''
        self.startup_sync_pending=False  # the user has just reviewed this fresh account
        self._save_meta('policy',self.policy)
        return self.status()

    def _snapshot(self):
        snapshot = (self.bridge.execution_snapshot() if hasattr(self.bridge, 'execution_snapshot')
                    else self.bridge.latest_fresh_snapshot())
        if not snapshot or snapshot.get('terminal_connected') is not True:
            raise TradePlanError('MARKET_DATA_STALE')
        if snapshot.get('execution_capable') is not True:
            raise TradePlanError('BRIDGE_UPGRADE_REQUIRED')
        if type(snapshot.get('account_login')) is not int or snapshot['account_login']<=0:
            raise TradePlanError('ACCOUNT_IDENTITY_REQUIRED')
        # The bridge owns the quote/clock pair. Strategy display values must
        # never be spliced into an older account snapshot's clock.
        server_time = snapshot.get('server_time')
        if type(server_time) is not int or server_time <= 0:
            raise TradePlanError('BROKER_CLOCK_REQUIRED')
        clock = snapshot.get('execution_clock_msc', server_time * 1000)
        stamp = snapshot.get('tick_time_msc', 0)
        if type(stamp) is not int or stamp <= 0:
            raise TradePlanError('FRESH_QUOTE_REQUIRED')
        snapshot['quote_age_ms'] = clock - stamp
        if snapshot['quote_age_ms'] > 2000 or snapshot['quote_age_ms'] < -1000:
            raise TradePlanError('FRESH_QUOTE_REQUIRED')
        bid = number(snapshot.get('bid'), 'bid', positive=True)
        if number(snapshot.get('ask'), 'ask', positive=True) < bid:
            raise TradePlanError('INVALID_SPREAD')
        return getattr(self,'snapshot_transform',lambda value:value)(snapshot)

    def _account_permission(self, snapshot, profile):
        if snapshot.get('symbol')!=profile['strategy']['symbol'] or snapshot.get('magic')!=profile['execution']['magic']:
            raise TradePlanError('PROFILE_BRIDGE_IDENTITY_MISMATCH')
        mode = snapshot.get('account_trade_mode')
        if mode=='REAL':
            if (not self.settings['safety']['allow_real_account'] or profile['execution']['demo_only']
                    or not profile['execution']['allow_real_account']):
                raise TradePlanError('USER_REAL_PERMISSION_REQUIRED')
        elif mode not in {'DEMO','CONTEST'}:
            raise TradePlanError('UNKNOWN_ACCOUNT_MODE')

    def _permission(self, profile, *, entry=False):
        snapshot = self._snapshot()
        if self.policy['mode']=='OFF':
            raise TradePlanError('USER_STOPPED')
        if any(self.policy.get(k)!=snapshot.get(k) for k in IDENTITY):
            raise TradePlanError('ACCOUNT_OR_SYMBOL_CHANGED')
        self._account_permission(snapshot,profile)
        if self.startup_sync_pending:
            raise TradePlanError('STARTUP_BRIDGE_SYNC_PENDING')
        if entry and self.db.execute("SELECT 1 FROM intents WHERE state IN ('UNKNOWN','DISPATCHED') LIMIT 1").fetchone():
            raise TradePlanError('RECONCILIATION_REQUIRED')
        if entry and self.awaiting_snapshot:
            raise TradePlanError('AWAITING_POST_TRADE_SNAPSHOT')
        return snapshot

    def _envelope(self, plan, profile, snapshot, intent_id):
        return {**plan, 'intent_id':intent_id, **{k:snapshot[k] for k in IDENTITY},
                'bridge_session_id':snapshot['bridge_session_id'], 'profile_hash':profile_hash(profile),
                'account_trade_mode':snapshot['account_trade_mode'], 'allow_real_account':self.settings['safety']['allow_real_account'] and profile['execution']['allow_real_account'] and not profile['execution']['demo_only'],
                'issued_server_time':snapshot['server_time'], 'expires_server_time':snapshot['server_time']+5,
                'max_positions':profile['risk']['max_open_positions'], 'max_volume':profile['risk']['max_lot'],
                'max_daily_loss_pct':profile['risk']['max_daily_loss_pct'],
                'never_widen_sl':profile['safety']['never_widen_sl'], 'require_server_sl':profile['safety']['require_server_sl']}

    def _queue(self, intent_id, fingerprint, command):
        now = time.time()
        local=command['action']=='MANAGEMENT_ENABLED'
        state='APPLIED_LOCAL' if local else 'QUEUED'
        result={'accepted':True,'intent_id':intent_id,'state':state,'code':'TRAILING_ENABLED' if local else 'QUEUED_FOR_BROKER',
                'broker_request_sent':False,'broker_verified':False,'preview':command}
        self.db.execute('INSERT INTO intents VALUES (?,?,?,?,?,?,?)', (intent_id,fingerprint,state,canonical(command),canonical(result) if local else None,now,now))
        return result

    def submit(self, payload, profile, *, automatic=False):
        self._profile = profile
        if not isinstance(payload,dict):
            raise TradePlanError('INVALID_PAYLOAD')
        try:
            intent_id = str(UUID(payload.get('intent_id','')))
        except (ValueError,TypeError,AttributeError):
            raise TradePlanError('INVALID_INTENT_ID')
        fingerprint=hashlib.sha256(canonical(payload).encode()).hexdigest()
        existing=self.db.execute('SELECT * FROM intents WHERE id=?',(intent_id,)).fetchone()
        if existing:
            if existing['fingerprint']!=fingerprint:
                raise TradePlanError('INTENT_ID_CONFLICT')
            return {'accepted':existing['state'] not in {'REJECTED','CANCELLED','EXPIRED'},'intent_id':intent_id,
                    'state':existing['state'],'code':existing['state'],'result':json.loads(existing['result']) if existing['result'] else None}
        if payload.get('confirmed') is not True:
            raise TradePlanError('USER_CONFIRMATION_REQUIRED')
        action=payload.get('action','')
        entry=action in {'MARKET_BUY','MARKET_SELL','PLACE_PENDING'}
        snapshot=self._permission(profile,entry=entry)
        expected_hash = payload.get('confirmed_profile_hash')
        if expected_hash is not None and expected_hash != profile_hash(profile):
            raise TradePlanError('CONFIRMED_PROFILE_CHANGED')
        reviewed = payload.get('confirmed_identity')
        if reviewed is not None and (not isinstance(reviewed, dict) or any(reviewed.get(k) != snapshot.get(k) for k in IDENTITY)):
            raise TradePlanError('CONFIRMED_ACCOUNT_MISMATCH')
        if automatic and self.policy['mode']!='AUTO':
            raise TradePlanError('AUTOMATIC_TRADING_NOT_SELECTED')
        if action in {'CLOSE_ALL','CLOSE_PROFIT','CLOSE_LOSS','CANCEL_ALL_PENDING','PARTIAL_ALL','BE_ALL','TRAIL_ALL'}:
            items=snapshot.get('orders' if action=='CANCEL_ALL_PENDING' else 'positions',[])
            child_action={'CANCEL_ALL_PENDING':'CANCEL_PENDING','PARTIAL_ALL':'PARTIAL_CLOSE','BE_ALL':'MOVE_SL_BE','TRAIL_ALL':'START_TRAILING'}.get(action,'CLOSE_POSITION')
            results=[]
            for item in items:
                pnl=item.get('profit',0)+item.get('swap',0)
                if action=='CLOSE_PROFIT' and pnl<=0 or action=='CLOSE_LOSS' and pnl>=0:
                    continue
                child={**payload,'action':child_action,'ticket':item['ticket'],'intent_id':str(uuid5(UUID(intent_id),str(item['ticket'])))}
                try:
                    results.append(self.submit(child,profile,automatic=automatic))
                except TradePlanError as exc:
                    results.append({'accepted':False,'ticket':item['ticket'],'code':str(exc)})
            # Parent intent is persisted too: duplicate batch cannot act on tickets
            # that arrived after the first click.
            now=time.time()
            batch_state = 'BATCH_QUEUED' if results else 'REJECTED'
            result={'accepted':bool(results) and any(r['accepted'] for r in results),'all_accepted':bool(results) and all(r['accepted'] for r in results),'intent_id':intent_id,
                    'state':batch_state,'code':'BATCH_QUEUED' if results else 'NO_TARGETS','items':results}
            self.db.execute('INSERT INTO intents VALUES (?,?,?,?,?,?,?)',(intent_id,fingerprint,batch_state,canonical({'action':'BATCH'}),canonical(result),now,now))
            return result
        if entry:
            reserved=self.db.execute("SELECT command FROM intents WHERE state='QUEUED'").fetchall()
            entry_guard(snapshot,profile,reserved_entries=sum(json.loads(r['command']).get('action')=='ENTRY' for r in reserved))
            side=payload.get('side') if action=='PLACE_PENDING' else action.split('_')[1]
            overrides={k:payload[k] for k in ('volume','sl_points','tp_points','price','order_type') if payload.get(k) is not None}
            if action!='PLACE_PENDING' and not automatic:
                overrides['order_type']=side
            if action=='PLACE_PENDING' and payload.get('order_type') not in {'BUY_STOP','SELL_STOP','BUY_LIMIT','SELL_LIMIT'}:
                raise TradePlanError('INVALID_PENDING_TYPE')
            signal = self.strategy.status_payload(market_connected=True).get('last_signal') if automatic else None
            planning_snapshot=deepcopy(snapshot)
            planning_snapshot['orders']=list(planning_snapshot.get('orders',[]))
            for reserved_row in reserved:
                reserved_plan=json.loads(reserved_row['command'])
                if reserved_plan.get('action')=='ENTRY' and all(reserved_plan.get(k)==snapshot.get(k) for k in IDENTITY):
                    planning_snapshot['orders'].append({'side':reserved_plan['side'],'price_open':reserved_plan['price'],
                        'sl':reserved_plan['sl'],'volume_current':reserved_plan['volume']})
            plan=plan_entry(profile,planning_snapshot,self.strategy.history,side,overrides,signal=signal)
            metrics=self.strategy.status_payload(market_connected=True).get('display',{}).get('indicators',{}).get('trigger',{})
            plan.update(entry_rsi=metrics.get('rsi'),entry_z=metrics.get('z'))
        else:
            plan=self._management_action(action,payload,profile,snapshot)
        command=self._envelope(plan,profile,snapshot,intent_id)
        command['automatic']=automatic
        return self._queue(intent_id,fingerprint,command)

    def _management_action(self, action, payload, profile, snapshot):
        def value(key,default):
            return default if payload.get(key) is None else payload[key]
        ticket=payload.get('ticket')
        if type(ticket) is not int or ticket<=0:
            raise TradePlanError('INVALID_TICKET')
        pending=action in {'MODIFY_PENDING','CANCEL_PENDING'}
        collection=snapshot.get('orders' if pending else 'positions',[])
        item=next((p for p in collection if p['ticket']==ticket and p['symbol']==snapshot['symbol'] and p.get('magic')==snapshot['magic']),None)
        if item is None:
            raise TradePlanError('OWNED_TICKET_NOT_FOUND')
        plan={'action':action,'ticket':ticket,'volume':item.get('volume',item.get('volume_current',0)),
              'position_identifier':item.get('position_identifier',ticket),'side':item.get('side',''), 'sl':item.get('sl',0),'tp':item.get('tp',0),
              'max_deviation_points':profile['costs']['max_slippage_points'],'comment':profile['execution']['order_comment'][:31]}
        if action=='PARTIAL_CLOSE':
            percent=number(value('percent',50),'percent',positive=True)
            if percent>=100:
                raise TradePlanError('PARTIAL_PERCENT_MUST_BE_BELOW_100')
            plan['volume']=volume_on_grid(item['volume']*percent/100,snapshot)
            if item['volume']-plan['volume'] < snapshot['volume_min']-1e-9:
                raise TradePlanError('PARTIAL_REMAINDER_BELOW_MINIMUM')
        elif action in {'MOVE_SL_BE','MODIFY_POSITION'}:
            buy=item['side']=='BUY'
            raw=(item['price_open']+(1 if buy else -1)*profile['management']['breakeven_offset_price_units'] if action=='MOVE_SL_BE' else value('sl',item.get('sl',0)))
            plan.update(action='MODIFY_POSITION',sl=grid(number(raw,'sl',positive=True),snapshot['tick_size'],up=not buy),tp=number(value('tp',item.get('tp',0)),'tp'))
            self._validate_stop_change(item,plan,snapshot)
        elif action=='MODIFY_PENDING':
            for key in ('price','sl','tp'):
                raw=number(value(key,item.get('price_open' if key=='price' else key,0)),key,positive=key!='tp')
                plan[key]=grid(raw,snapshot['tick_size']) if raw else 0
            plan['expiration']=int(value('expiration',item.get('expiration',0)))
            kind = str(item.get('order_type', item.get('type', ''))).replace(' ', '_')
            buy = kind.startswith('BUY')
            if kind not in {'BUY_STOP','SELL_STOP','BUY_LIMIT','SELL_LIMIT'}:
                raise TradePlanError('INVALID_PENDING_TYPE')
            old_price = number(item.get('price_open'), 'old_pending_price', positive=True)
            old_sl = number(item.get('sl'), 'old_pending_sl', positive=True)
            sign = 1 if buy else -1
            if sign*(plan['sl']-old_sl)<-1e-9:
                raise TradePlanError('NEVER_WIDEN_SL')
            if sign*(plan['price']-plan['sl'])>sign*(old_price-old_sl)+1e-9:
                raise TradePlanError('PENDING_RISK_INCREASE')
            reference = snapshot['ask' if buy else 'bid']
            gap = max(snapshot.get('stops_level',0),snapshot.get('freeze_level',0))*snapshot['point']
            gap = max(gap, snapshot['tick_size'])
            separation = (plan['price']-reference) if kind.endswith('STOP') else (reference-plan['price'])
            if sign*separation < gap-1e-9 or sign*(plan['price']-plan['sl']) < gap-1e-9:
                raise TradePlanError('STOP_OR_FREEZE_LEVEL')
            if plan['tp'] and sign*(plan['tp']-plan['price']) < gap-1e-9:
                raise TradePlanError('INVALID_SERVER_TP')
            if plan['expiration'] and plan['expiration'] <= snapshot['server_time']:
                raise TradePlanError('PENDING_EXPIRED')
        elif action=='START_TRAILING':
            key=self.position_key(snapshot,ticket)
            state=self.position_state(key) or {}
            state['manual_trailing']=True
            self.save_position_state(key,state)
            plan.update(action='MANAGEMENT_ENABLED')
        elif action not in {'CLOSE_POSITION','CANCEL_PENDING'}:
            raise TradePlanError('UNSUPPORTED_ACTION')
        return plan

    @staticmethod
    def _validate_stop_change(item,plan,snapshot):
        buy=item['side']=='BUY'
        old=item.get('sl',0)
        if old and (plan['sl']<old-1e-10 if buy else plan['sl']>old+1e-10):
            raise TradePlanError('NEVER_WIDEN_SL')
        close=snapshot['bid' if buy else 'ask']
        gap=max(snapshot.get('stops_level',0),snapshot.get('freeze_level',0))*snapshot['point']
        if (close-plan['sl'] if buy else plan['sl']-close) < max(gap, snapshot['tick_size'])-1e-10:
            raise TradePlanError('STOP_OR_FREEZE_LEVEL')
        if plan.get('tp') and (plan['tp']-close if buy else close-plan['tp']) < max(gap, snapshot['tick_size'])-1e-10:
            raise TradePlanError('INVALID_SERVER_TP')

    @staticmethod
    def position_key(snapshot,ticket):
        return canonical([snapshot[k] for k in IDENTITY]+[ticket])

    def position_state(self,key):
        row=self.db.execute('SELECT value FROM position_state WHERE key=?',(key,)).fetchone()
        return json.loads(row['value']) if row else None

    def save_position_state(self,key,value):
        self.db.execute('INSERT OR REPLACE INTO position_state VALUES (?,?)',(key,canonical(value)))

    def _signal_key(self,profile):
        signal=self.strategy.status_payload(market_connected=True).get('last_signal') or {}
        return [profile_hash(profile),signal.get('tick_stream_id'),signal.get('tick_time_msc'),signal.get('bar_time'),signal.get('sequence'),signal.get('side')]

    def observe_signal(self,profile):
        if self.policy['mode']!='AUTO':
            return
        key=self._signal_key(profile)
        if key==self.meta('last_signal') or key[-1] not in {'BUY','SELL'}:
            return
        # A rejected signal is recorded too; never replay an old setup later.
        self._save_meta('last_signal',key)
        signal=self.strategy.status_payload(market_connected=True).get('last_signal') or {}
        try:
            snapshot=self._permission(profile,entry=True)
            if signal.get('profile_hash')!=profile_hash(profile):
                raise TradePlanError('SIGNAL_PROFILE_MISMATCH')
            if signal.get('tick_time_msc') and abs(snapshot['server_time']*1000-signal['tick_time_msc'])>2000:
                raise TradePlanError('SIGNAL_EXPIRED')
            from .strategy_engine import HISTORY_TIMEFRAME_SECONDS
            if snapshot['server_time']-signal.get('bar_time',0)>HISTORY_TIMEFRAME_SECONDS[profile['timeframes']['trigger']]*profile['entry']['max_signal_age_bars']:
                raise TradePlanError('SIGNAL_EXPIRED')
            result=self.submit({'intent_id':str(uuid4()),'action':'MARKET_'+signal['side'],'confirmed':True},profile,automatic=True)
            self.last_blocker='' if result['accepted'] else result.get('code','')
        except TradePlanError as exc:
            self.last_blocker=str(exc)

    def manage_positions(self,profile):
        if self.policy['mode']=='OFF':
            return
        try:
            snapshot=self._permission(profile)
        except TradePlanError:
            return
        if self.awaiting_snapshot:
            return
        automatic=self.policy['mode']=='AUTO'
        projection=self.strategy.status_payload(market_connected=True)
        display=projection.get('display') or {}
        metrics=display.get('indicators',{}).get('trigger',{}) if display.get('continuous') else {}
        outstanding=[json.loads(r['command']) for r in self.db.execute("SELECT command FROM intents WHERE state IN ('QUEUED','DISPATCHED','UNKNOWN')")]
        for position in snapshot.get('positions',[]):
            if position.get('symbol')!=snapshot['symbol'] or position.get('magic')!=snapshot['magic']:
                continue
            ticket=position['ticket']
            if any(c.get('ticket')==ticket for c in outstanding):
                continue
            key=self.position_key(snapshot,ticket)
            previous=self.position_state(key) or {}
            state=deepcopy(previous)
            if not state.get('entry_intent') and position.get('entry_order'):
                for row in self.db.execute("SELECT command,result FROM intents WHERE state='CONFIRMED' AND result IS NOT NULL"):
                    result=json.loads(row['result'])
                    command=json.loads(row['command'])
                    if command['action']=='ENTRY' and result.get('order_ticket')==position['entry_order'] and all(command.get(k)==snapshot.get(k) for k in IDENTITY):
                        state.update(initial_risk=abs(position['price_open']-command['sl']),original_tp=command['original_tp'],
                                     entry_rsi=command.get('entry_rsi'),entry_z=command.get('entry_z'),entry_intent=command['intent_id'])
                        break
            # Recover initial protection from the broker, never from a moved SL.
            if not state.get('initial_risk') and position.get('initial_sl'):
                sign=1 if position['side']=='BUY' else -1
                initial=sign*(position['price_open']-position['initial_sl'])
                if initial>0:
                    state.update(initial_risk=initial,original_tp=position.get('initial_tp'))
            try:
                state,action=position_decision(profile,snapshot,self.strategy.history,position,state,metrics,automatic=automatic)
                if state!=previous:
                    self.save_position_state(key,state)
                if action:
                    from uuid import NAMESPACE_URL
                    step=action['reason']+':'+str(action.get('sl',''))
                    intent_id=str(uuid5(NAMESPACE_URL,key+':'+step))
                    result=self.submit({'intent_id':intent_id,'confirmed':True,'ticket':ticket,**action},profile)
                    if action['action']=='PARTIAL_CLOSE' and result['accepted']:
                        state['partial_intent']=intent_id
                        self.save_position_state(key,state)
            except TradePlanError as exc:
                self.management_warnings[str(ticket)]=str(exc)

        # Strategy-owned pending orders are cancelled when their entry window ends.
        if automatic:
            from .trade_plan import session_allowed, weekend_close_due
            from uuid import NAMESPACE_URL
            for pending in snapshot.get('orders',[]):
                if any(c.get('ticket')==pending['ticket'] for c in outstanding): continue
                kind = pending.get('order_type',pending.get('type',''))
                side = 'BUY' if kind.startswith('BUY') else 'SELL' if kind.startswith('SELL') else ''
                try:
                    cancel = pending_cancellation_reason(profile,snapshot,projection,side,int(pending.get('expiration',0)))
                    if cancel:
                        key=self.position_key(snapshot,pending['ticket'])+':CANCEL_PENDING'
                        self.submit({'intent_id':str(uuid5(NAMESPACE_URL,key)),'confirmed':True,'ticket':pending['ticket'],'action':'CANCEL_PENDING'},profile)
                except TradePlanError as exc:
                    self.management_warnings[str(pending['ticket'])]=str(exc)

    def next_command(self,profile,session):
        try:
            snapshot=self._permission(profile)
        except TradePlanError as exc:
            self.last_blocker=str(exc)
            return None
        if snapshot.get('bridge_session_id')!=session:
            return None
        if self.db.execute("SELECT 1 FROM intents WHERE state='DISPATCHED' LIMIT 1").fetchone():
            return None
        for row in self.db.execute("SELECT * FROM intents WHERE state='QUEUED' ORDER BY created").fetchall():
            command=json.loads(row['command'])
            reason=None
            if time.time()-row['created']>(5 if command['action']=='ENTRY' else 60):
                reason='EXPIRED'
            elif command['profile_hash']!=profile_hash(profile) or command['bridge_session_id']!=session:
                reason='CANCELLED'
            if reason:
                self.db.execute('UPDATE intents SET state=?,updated=? WHERE id=?',(reason,time.time(),row['id']))
                continue
            if command['action']=='ENTRY':
                try:
                    self._permission(profile,entry=True)
                    entry_guard(snapshot,profile)
                except TradePlanError as exc:
                    self.db.execute("UPDATE intents SET state='REJECTED',result=?,updated=? WHERE id=?",
                        (canonical({'reason':str(exc),'order_send_called':False}),time.time(),row['id']))
                    continue
            command.update(issued_server_time=snapshot['server_time'],expires_server_time=snapshot['server_time']+5)
            # Persist before bytes can leave Python. Lost reply means UNKNOWN,
            # never an automatic resend of the financial operation.
            self.db.execute("UPDATE intents SET state='DISPATCHED',command=?,updated=? WHERE id=?",(canonical(command),time.time(),row['id']))
            return command
        return None

    def disconnected(self):
        if not self.closed:
            self.db.execute("UPDATE intents SET state='UNKNOWN',updated=? WHERE state='DISPATCHED'",(time.time(),))

    def on_snapshot(self):
        self.awaiting_snapshot = False
        snapshot=self.bridge.latest_fresh_snapshot() or {}
        if (snapshot.get('demo_once_guard',{}).get('history_complete') is True
                and all(snapshot.get(k)==self.policy.get(k) for k in IDENTITY)):
            self.startup_sync_pending=False

    def record_result(self,payload,current_session):
        row=self.db.execute('SELECT * FROM intents WHERE id=?',(payload.get('intent_id'),)).fetchone()
        snapshot=self.bridge.latest_fresh_snapshot() or {}
        if not row or snapshot.get('bridge_session_id')!=current_session:
            raise TradePlanError('UNKNOWN_INTENT_OR_SESSION')
        command=json.loads(row['command'])
        if any(payload.get(k)!=command.get(k) or snapshot.get(k)!=command.get(k) for k in IDENTITY):
            raise TradePlanError('RESULT_IDENTITY_MISMATCH')
        if payload.get('bridge_session_id')!=command['bridge_session_id']:
            raise TradePlanError('RESULT_ORIGINAL_SESSION_MISMATCH')
        if payload.get('state') not in {'CONFIRMED','REJECTED','UNKNOWN'}:
            raise TradePlanError('INVALID_RESULT_STATE')
        if row['state'] in TERMINAL_STATES:
            if row['result']!=canonical(payload):
                raise TradePlanError('CONFLICTING_FINAL_RESULT')
            return {'accepted':True,'state':row['state']}
        if row['state'] not in {'DISPATCHED','UNKNOWN'}:
            raise TradePlanError('RESULT_BEFORE_DISPATCH')
        for key in ('retcode','order_ticket','deal_ticket','position_ticket'):
            if type(payload.get(key)) is not int or payload[key]<0:
                raise TradePlanError('INVALID_RESULT_'+key.upper())
        if type(payload.get('order_send_called')) is not bool:
            raise TradePlanError('INVALID_RESULT_SEND_FLAG')
        if payload['state']=='CONFIRMED':
            if not payload['order_send_called'] or payload.get('broker_verified') is not True or payload['retcode'] not in {10008,10009,10010,10025}:
                raise TradePlanError('BROKER_EVIDENCE_REQUIRED')
            action=command['action']
            if action in {'ENTRY','CLOSE_POSITION','PARTIAL_CLOSE'} and (action!='ENTRY' or command['order_type'] in {'BUY','SELL'}):
                if payload['order_ticket']<=0 or payload['deal_ticket']<=0 or number(payload.get('filled_volume'),'filled_volume',positive=True)>command['volume']+1e-9:
                    raise TradePlanError('FILL_EVIDENCE_REQUIRED')
                number(payload.get('fill_price'),'fill_price',positive=True)
            if action in {'CLOSE_POSITION','PARTIAL_CLOSE','MODIFY_POSITION'} and payload['position_ticket']!=command['ticket']:
                raise TradePlanError('POSITION_EVIDENCE_MISMATCH')
            if action in {'CANCEL_PENDING','MODIFY_PENDING'} and payload['order_ticket']!=command['ticket']:
                raise TradePlanError('ORDER_EVIDENCE_MISMATCH')
            if action=='ENTRY' and payload['order_ticket']<=0:
                raise TradePlanError('ORDER_EVIDENCE_REQUIRED')
            if action in {'ENTRY','MODIFY_POSITION','MODIFY_PENDING'}:
                sl=number(payload.get('sl'),'sl',positive=True)
                tp=number(payload.get('tp'),'tp')
                tolerance=number(snapshot.get('tick_size'),'tick_size',positive=True)/2+1e-10
                if abs(sl-command['sl'])>tolerance or abs(tp-command['tp'])>tolerance:
                    raise TradePlanError('PROTECTION_EVIDENCE_MISMATCH')
                if action=='ENTRY' and command['order_type'] in {'BUY','SELL'} and (sl>=payload['fill_price'] if command['side']=='BUY' else sl<=payload['fill_price']):
                    raise TradePlanError('PROTECTION_EVIDENCE_MISMATCH')
        self.db.execute('UPDATE intents SET state=?,result=?,updated=? WHERE id=?',(payload['state'],canonical(payload),time.time(),row['id']))
        if payload['state']=='CONFIRMED' and command['action']=='ENTRY' and payload.get('position_ticket',0)>0 and payload.get('fill_price',0)>0:
            key=self.position_key(command,payload['position_ticket'])
            initial=abs(payload.get('fill_price',command['price'])-command['sl'])
            self.save_position_state(key,{'initial_risk':initial,'original_tp':command['original_tp'],
                'entry_rsi':command.get('entry_rsi'),'entry_z':command.get('entry_z'),'entry_intent':command['intent_id']})
        elif payload['state']=='CONFIRMED' and command['action']=='PARTIAL_CLOSE':
            key=self.position_key(command,command['ticket'])
            state=self.position_state(key) or {}
            state.update(partial_intent=command['intent_id'],partial_confirmed=True)
            self.save_position_state(key,state)
        self.awaiting_snapshot = payload['order_send_called']
        return {'accepted':True,'state':payload['state']}


class UnavailableBrokerExecution:
    """Preserve unreadable evidence and keep monitoring available."""
    policy={'mode':'OFF'}
    def __init__(self, error): self.error=str(error)
    def status(self):
        return {'mode':'OFF','reason':'EXECUTION_STORAGE_UNAVAILABLE','detail':self.error,'available':False,
                'execution_enabled':False,'trading_enabled':False,'counts':{},'recent':[]}
    def set_mode(self,payload,profile):
        if payload.get('mode')=='OFF': return self.status()
        raise TradePlanError('EXECUTION_STORAGE_UNAVAILABLE')
    def submit(self,*args,**kwargs): raise TradePlanError('EXECUTION_STORAGE_UNAVAILABLE')
    def record_result(self,*args,**kwargs): raise TradePlanError('EXECUTION_STORAGE_UNAVAILABLE')
    def history(self,*args,**kwargs): return []
    def query_history(self,payload): raise TradePlanError('EXECUTION_STORAGE_UNAVAILABLE')
    def close(self): pass
    def disconnected(self): pass
    def on_snapshot(self): pass
    def observe_signal(self,*args): pass
    def manage_positions(self,*args): pass
    def next_command(self,*args): return None
