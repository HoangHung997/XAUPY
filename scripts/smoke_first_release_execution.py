"""Exercise the packaged broker protocol against an ISOLATED synthetic EA.

This is NOT broker/live acceptance. It launches its own process, random port and
empty temporary stores; never connects to an existing Engine or MT5 terminal.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
from uuid import uuid4

from _smoke_runtime import isolated_environment

IDENTITY = ('account_login', 'account_server', 'symbol', 'magic')
TIMEFRAMES = {'M1':60,'M3':180,'M5':300,'M15':900,'M30':1800,'H1':3600,'H2':7200,'H4':14400,'D1':86400}
checks = 0


def check(condition, label):
    global checks
    if not condition:
        raise AssertionError(label)
    checks += 1
    print('PASS:', label, flush=True)


class Peer:
    def __init__(self, port):
        self.socket = socket.create_connection(('127.0.0.1', port), timeout=5)
        self.socket.settimeout(15)
        self.stream = self.socket.makefile('rwb')

    def request(self, kind, payload=None, *, error=False):
        request_id = str(uuid4())
        envelope = dict(schema_version=1, type=kind, request_id=request_id,
                        sent_at_utc=datetime.now(timezone.utc).isoformat(), payload=payload or {})
        self.stream.write((json.dumps(envelope, separators=(',',':'))+'\n').encode())
        self.stream.flush()
        line = self.stream.readline()
        if not line:
            raise RuntimeError('Isolated Engine closed the connection')
        response = json.loads(line)
        expected = 'error' if error else 'config_active_ack' if kind=='config_active_get' else kind+'_ack'
        check(response['request_id']==request_id and response['type']==expected, kind+' correlated response')
        return response['payload']

    def close(self):
        self.stream.close()
        self.socket.close()


@contextmanager
def engine(executable, root):
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1',0))
        port=reservation.getsockname()[1]
    env=isolated_environment(root)
    instance=uuid4().hex
    env['XAUPY_INSTANCE_ID']=instance
    process=subprocess.Popen([executable,'--host','127.0.0.1','--port',str(port)],
                             env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    desktop=None
    try:
        until=time.monotonic()+30
        while time.monotonic()<until:
            if process.poll() is not None:
                out,err=process.communicate()
                raise RuntimeError('Isolated Engine exited: '+err.decode(errors='replace'))
            try:
                desktop=Peer(port)
                break
            except OSError:
                time.sleep(.1)
        if desktop is None:
            raise TimeoutError('Isolated Engine startup timeout')
        hello=desktop.request('hello',{'component':'first-release-isolated-smoke'})
        check(hello['engine_instance_id']==instance, 'process identity excludes existing user Engine')
        check(hello['execution_enabled'] is False, 'fresh process does not enable execution')
        yield desktop,port
    finally:
        if desktop:
            try:
                desktop.request('execution_mode_set',{'mode':'OFF'})
                desktop.request('shutdown',{'reason':'isolated-first-release-smoke'})
                process.wait(timeout=10)
            except (OSError,ValueError,AssertionError,subprocess.TimeoutExpired):
                pass
            desktop.close()
        if process.poll() is None:
            if os.name=='nt':
                subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,check=False)
            else:
                process.kill()
            process.wait(timeout=5)
        process.stdout.close();process.stderr.close()


def run(executable):
    with tempfile.TemporaryDirectory(prefix='xaupy-release-execution-') as temporary:
        root=Path(temporary)
        lost_id=None
        with engine(executable,root) as (desktop,port):
            profile=desktop.request('config_active_get')['profile']
            profile['profile']['name']='ISOLATED EXECUTION ACCEPTANCE - NOT A BROKER'
            profile['stop_loss'].update(mode='FIXED',fixed_price_units=3.,min_price_units=.5,max_price_units=20.)
            profile['take_profit'].update(mode='FIXED',fixed_price_units=6.)
            profile['risk'].update(sizing_mode='FIXED_LOT',fixed_lot=.02,max_lot=.1,max_open_positions=5,cooldown_minutes=0)
            profile['management'].update(breakeven_enabled=False,partial_close_enabled=False,trailing_enabled=False,sl_tighten_mode='OFF')
            profile['sessions'].update(timezone='BROKER',session1_enabled=False,session2_enabled=False,
                **{day:True for day in ('monday','tuesday','wednesday','thursday','friday','saturday','sunday')})
            profile['news']['enabled']=False
            check(desktop.request('config_active_set',{'profile':profile})['applied'], 'isolated profile applied')
            session=str(uuid4())
            start=int(time.time())
            clock=time.monotonic()
            snapshot=dict(execution_capabilities=dict(schema_version=1,trade_allowed=True,allow_buy=True,allow_sell=True,market_orders=True,stop_orders=True,limit_orders=True,server_sl=True,server_tp=True,specified_expiration=True,netting_symbol_exposed=False,margin_mode='HEDGING'),bridge_version='1.022',execution_capable=True,demo_once_capable=True,
                bridge_session_id=session,account_login=700001,account_server='ISOLATED-NO-BROKER',
                symbol='XAUUSD',magic=991188,account_trade_mode='DEMO',terminal_connected=True,
                server_time=start,tick_time_msc=start*1000,bid=4200.,ask=4200.2,balance=10000.,
                equity=10000.,margin_free=10000.,account_currency='USD',point=.01,tick_size=.01,
                tick_value=1.,tick_value_loss=1.,volume_min=.01,volume_max=100.,volume_step=.01,
                stops_level=10,freeze_level=0,positions=[],orders=[],deals=[],
                guardian={'execution_locked':True,'execution_ready':False,'reason':'USER_STOPPED','max_volume':.1},
                demo_once_guard=dict(history_complete=True,broker_day_start=start//86400*86400,
                    trades_today=0,consecutive_losses=0,last_exit_time=0,day_start_balance=10000.,daily_realized=0.),
                bars={tf:dict(time=(start//span-1)*span,open=4200.,high=4201.,low=4199.,close=4200.,tick_volume=1)
                      for tf,span in TIMEFRAMES.items()})
            identity={k:snapshot[k] for k in IDENTITY}
            ea=Peer(port)

            def hello():
                return dict(component='mt5-bridge',bridge_version='1.022',symbol='XAUUSD',
                    execution_capable=True,demo_once_capable=True,bridge_session_id=session)

            def refresh():
                now=start+int(time.monotonic()-clock)
                snapshot.update(server_time=now,tick_time_msc=now*1000)
                snapshot['demo_once_guard']['broker_day_start']=now//86400*86400
                return ea.request('bridge_snapshot',snapshot)

            def status():
                return desktop.request('execution_status')

            def action(kind,**kwargs):
                return desktop.request('execution_action',dict(intent_id=str(uuid4()),action=kind,
                    confirmed=True,confirmed_identity=identity,**kwargs))

            def dispatch(kind,**kwargs):
                refresh()
                accepted=action(kind,**kwargs)
                check(accepted['accepted'] and not accepted.get('broker_request_sent'),kind+' queues, not a fill')
                command=refresh()['execution_command']
                check(command and command['intent_id']==accepted['intent_id'],kind+' leaves owning EA socket')
                check(refresh()['execution_command'] is None,kind+' cannot dispatch twice')
                return command

            serial=1000
            def evidence(command,**override):
                nonlocal serial
                serial+=10
                entry=command['action']=='ENTRY'
                ispending=entry and command['order_type'] not in ('BUY','SELL')
                order=command.get('ticket',serial) if command['action'] in ('MODIFY_PENDING','CANCEL_PENDING') else serial
                result={k:command[k] for k in (*IDENTITY,'intent_id','bridge_session_id')}
                result.update(state='CONFIRMED',broker_verified=True,order_send_called=True,retcode=10009,
                    order_ticket=order,deal_ticket=0 if ispending else serial+1,
                    position_ticket=0 if ispending else command.get('ticket',serial+2),
                    filled_volume=0 if ispending else command.get('volume',.02),
                    fill_price=0 if ispending else snapshot['ask' if command.get('side')=='BUY' else 'bid'],
                    sl=command.get('sl',0),tp=command.get('tp',0),reason='ISOLATED_SYNTHETIC_RECEIPT',**{})
                result.update(override)
                check(ea.request('bridge_execution_result',result)['accepted'],command['action']+' reconciles synthetic evidence')
                refresh()
                item=desktop.request('execution_history',{'intent_id':command['intent_id']})['items']
                check(len(item)==1 and item[0]['state']=='CONFIRMED','exact intent lookup proves result')
                return result

            try:
                ea.request('bridge_hello',hello());refresh()
                check(desktop.request('execution_mode_set',dict(mode='MANUAL',confirmed=True,**identity))['accepted'], 'explicit account-bound manual mode')
                denied=desktop.request('execution_action',dict(intent_id=str(uuid4()),action='MARKET_SELL',confirmed=False))
                check(not denied['accepted'] and denied['code']=='USER_CONFIRMATION_REQUIRED','missing manual consent cannot queue')
                check(desktop.request('execution_history',{})['total']==0,'rejected consent left no trade intent')
                for side in ('BUY','SELL'):
                    command=dispatch('MARKET_'+side)
                    check(command['action']=='ENTRY' and command['side']==side,side+' uses real execution protocol, not simulator')
                    fake={k:command[k] for k in (*IDENTITY,'intent_id','bridge_session_id')}
                    fake.update(state='CONFIRMED',broker_verified=False,order_send_called=True,retcode=10009,
                        order_ticket=12,deal_ticket=13,position_ticket=14,filled_volume=.02,fill_price=4200.,sl=command['sl'],tp=command['tp'])
                    check(not ea.request('bridge_execution_result',fake)['accepted'],'unverified fill cannot become confirmed')
                    evidence(command)
                check(status()['entry_enabled'], 'post-trade snapshot releases entry gate')
                refresh()
                check(desktop.request('bridge_snapshot',snapshot,error=True)['code']=='BRIDGE_SNAPSHOT_INVALID','other socket cannot impersonate owning EA')
                command=dispatch('PLACE_PENDING',side='BUY',order_type='BUY_STOP',price=4203.,volume=.02)
                result=evidence(command)
                pending=dict(ticket=result['order_ticket'],symbol='XAUUSD',magic=991188,type='BUY_STOP',
                    price_open=4203.,sl=command['sl'],tp=command['tp'],volume_current=.02,volume_initial=.02,
                    expiration=snapshot['server_time']+300)
                snapshot['orders']=[pending]
                refresh()
                denied=action('MODIFY_PENDING',ticket=pending['ticket'],price=4204.)
                check(not denied['accepted'] and denied['code']=='PENDING_RISK_INCREASE','pending edit cannot silently increase initial risk')
                command=dispatch('MODIFY_PENDING',ticket=pending['ticket'],price=4204.,sl=pending['sl']+1,tp=4210.)
                evidence(command);pending.update(price_open=4204.,sl=command['sl'],tp=command['tp'])
                command=dispatch('CANCEL_PENDING',ticket=pending['ticket']);evidence(command)
                snapshot['orders']=[]
                position=dict(ticket=2001,symbol='XAUUSD',magic=991188,side='BUY',volume=.04,price_open=4197.,
                    sl=4194.,tp=4207.,profit=12.,swap=0.,time=snapshot['server_time']-60)
                snapshot['positions']=[position]
                command=dispatch('MOVE_SL_BE',ticket=position['ticket']);evidence(command)
                position['sl']=command['sl']
                command=dispatch('PARTIAL_CLOSE',ticket=position['ticket'],percent=50);evidence(command)
                position['volume']=.02
                refresh()
                trailing=action('START_TRAILING',ticket=position['ticket'])
                check(trailing['accepted'] and trailing['state']=='APPLIED_LOCAL','manual trailing activation is local, not claimed as a broker fill')
                # Cancel management before refreshing to keep this fixture focused
                # on explicit close; trailing calculations are separately tested.
                desktop.request('execution_mode_set',{'mode':'OFF'})
                snapshot['positions']=[];refresh()
                desktop.request('execution_mode_set',dict(mode='MANUAL',confirmed=True,**identity))
                snapshot['positions']=[{**position,'ticket':2002}]
                command=dispatch('CLOSE_POSITION',ticket=2002);evidence(command)
                snapshot['positions']=[];refresh()
                empty=action('CLOSE_ALL')
                check(not empty['accepted'] and empty['code']=='NO_TARGETS','empty bulk action does not report a broker success')
                # Frozen page membership remains stable while a new intent is queued.
                page=desktop.request('execution_history',{'limit':2})
                command=dispatch('MARKET_BUY')
                lost_id=command['intent_id']
                page2=desktop.request('execution_history',{'limit':2,'offset':2,'snapshot_time':page['snapshot_time']})
                check(page2['total']==page['total'],'ledger paging is stable across new actions')
                ea.close();ea=None
                time.sleep(.05)
                check(any(x['id']==lost_id and x['state']=='UNKNOWN' for x in status()['recent']), 'lost broker reply stays UNKNOWN')
                session=str(uuid4());snapshot['bridge_session_id']=session
                ea=Peer(port);ea.request('bridge_hello',hello())
                check(refresh()['execution_command'] is None,'new EA session cannot resend ambiguous operation')
                check(not status()['entry_enabled'],'unresolved operation blocks new entries')
            finally:
                if ea:ea.close()
        with engine(executable,root) as (desktop,port):
            item=desktop.request('execution_history',{'intent_id':lost_id})['items']
            check(len(item)==1 and item[0]['state']=='UNKNOWN','restart preserves ambiguous intent evidence')
            check(desktop.request('execution_status')['mode']=='OFF','restart does not silently reactivate trading')
    print(f'PASS: {checks} isolated packaged execution protocol checks. No MT5/broker was connected.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('engine_exe')
    run(str(Path(parser.parse_args().engine_exe).resolve()))
