"""Regression gate for RC1 P1 repairs using the *packaged* Engine protocol.

Synthetic EA on a random loopback port, temporary runtime. Never connects to an
existing Engine, MT5 terminal or broker and never calls any broker API.
"""
from copy import deepcopy
from pathlib import Path
import argparse
import tempfile
import time
from uuid import uuid4

import smoke_first_release_execution as wire


def run(executable):
    with tempfile.TemporaryDirectory(prefix='xaupy-rc2-repair-smoke-') as temporary:
        root = Path(temporary)
        with wire.engine(executable, root) as (desktop, port):
            profile = desktop.request('config_active_get')['profile']
            profile['stop_loss'].update(mode='FIXED', fixed_price_units=3.)
            profile['take_profit'].update(mode='FIXED', fixed_price_units=6.)
            profile['risk'].update(sizing_mode='FIXED_LOT', fixed_lot=.01, max_lot=.1,
                                   max_open_positions=4, cooldown_minutes=0)
            profile['management'].update(partial_close_enabled=True, partial_close_percent=50,
                partial_close_at_rr=1., breakeven_enabled=True, breakeven_trigger_rr=1.,
                breakeven_offset_price_units=.1, trailing_enabled=False, sl_tighten_mode='OFF')
            profile['sessions'].update(session1_enabled=False, session2_enabled=False,
                weekend_close_enabled=False, **{day:True for day in
                    ('monday','tuesday','wednesday','thursday','friday','saturday','sunday')})
            profile['news']['enabled'] = False
            wire.check(desktop.request('config_active_set', {'profile':profile})['applied'], 'RC2 isolated test profile')
            session = str(uuid4())
            now = int(time.time())
            caps = dict(schema_version=1, trade_allowed=True, allow_buy=True, allow_sell=True,
                market_orders=True, stop_orders=True, limit_orders=True, server_sl=True, server_tp=True,
                specified_expiration=True, netting_symbol_exposed=False, margin_mode='HEDGING')
            position = dict(ticket=700, position_identifier=701, magic=991188, symbol='XAUUSD', side='BUY',
                volume=.01, price_open=4197., price_current=4200., sl=4194., tp=4210., initial_sl=4194.,
                initial_tp=4210., profit=3., swap=0., time=now-300)
            snapshot = dict(bridge_version='1.022',execution_capable=True,execution_capabilities=caps,
                bridge_session_id=session,account_login=700101,account_server='ISOLATED-RC2-NO-BROKER',
                symbol='XAUUSD',magic=991188,account_trade_mode='DEMO',terminal_connected=True,
                server_time=now,tick_time_msc=now*1000,server_utc_offset_seconds=0,
                bid=4200.,ask=4200.2,balance=10000.,equity=10003.,margin_free=9990.,account_currency='USD',
                point=.01,tick_size=.01,tick_value=1.,tick_value_loss=1.,volume_min=.01,volume_max=100.,
                volume_step=.01,stops_level=10,freeze_level=0,positions=[position],orders=[],deals=[],
                guardian=dict(execution_locked=True,execution_ready=False,reason='USER_STOPPED',max_volume=.1),
                demo_once_guard=dict(history_complete=True,broker_day_start=now//86400*86400,
                    trades_today=1,consecutive_losses=0,last_exit_time=0,day_start_balance=10000.,daily_realized=0.),
                bars={tf:dict(time=(now//span-1)*span,open=4200.,high=4201.,low=4199.,close=4200.,tick_volume=1)
                      for tf,span in wire.TIMEFRAMES.items()})
            identity = {key:snapshot[key] for key in wire.IDENTITY}
            ea = wire.Peer(port)
            try:
                ea.request('bridge_hello',dict(component='mt5-bridge',bridge_version='1.022',symbol='XAUUSD',
                    execution_capable=True,bridge_session_id=session))
                def refresh():
                    now = int(time.time())
                    snapshot.update(server_time=now,tick_time_msc=now*1000)
                    snapshot['demo_once_guard']['broker_day_start'] = now//86400*86400
                    return ea.request('bridge_snapshot',snapshot)
                refresh()
                wire.check(desktop.request('execution_mode_set',dict(mode='AUTO',confirmed=True,**identity))['accepted'],
                           'explicit synthetic account AUTO for management regression')
                command = refresh()['execution_command']
                wire.check(command and command['action']=='MODIFY_POSITION' and abs(command['sl']-4197.1)<1e-8,
                           'impossible 0.005 lot partial still dispatches eligible BE at 4197.1')
                wire.check(refresh()['execution_command'] is None,'protective intent dispatched only once')
                status = desktop.request('execution_status')
                wire.check(status['management_warnings'].get('700')=='VOLUME_BELOW_BROKER_MINIMUM',
                           'partial skip visible through actual packaged status')
                receipt = {key:command[key] for key in (*wire.IDENTITY,'intent_id','bridge_session_id')}
                receipt.update(state='CONFIRMED',broker_verified=True,order_send_called=True,retcode=10009,
                    order_ticket=0,deal_ticket=0,position_ticket=700,filled_volume=0,fill_price=0,
                    sl=command['sl'],tp=command['tp'],reason='ISOLATED-BE-RECEIPT')
                wire.check(ea.request('bridge_execution_result',receipt)['accepted'],'synthetic BE receipt reconciled')
                position['sl']=command['sl']; refresh()
                events = desktop.request('execution_history',{'limit':100})['items']
                wire.check(len(events)==1 and events[0]['state']=='CONFIRMED',
                           'no invalid partial or repeated BE intent after confirmation')
                desktop.request('execution_mode_set',{'mode':'OFF'})
                # A saved REAL preference is just fixture data here. We never
                # attach a REAL terminal. Ensure restoring it cannot grant it.
                settings=desktop.request('settings_get')['settings']
                settings['safety']['allow_real_account']=True
                wire.check(desktop.request('settings_set',{'settings':settings})['ok'],'test-only saved permission')
                refresh()
                wire.check(desktop.request('execution_mode_set',dict(mode='AUTO',confirmed=True,**identity))['accepted'],
                           'synthetic AUTO state before backup')
                backup=desktop.request('backup_create')['backup']['id']
                settings=desktop.request('settings_get')['settings']; settings['safety']['allow_real_account']=False
                revoked=desktop.request('settings_set',{'settings':settings})
                wire.check(revoked['ok'] and revoked['execution']['mode']=='OFF' and not revoked['trading_enabled'],
                           'revoking REAL persists OFF immediately in ACK')
                before=desktop.request('config_active_get')['profile']
                wire.check(not desktop.request('backup_restore',{'backup_id':backup})['ok'],
                           'unreviewed restore rejected by packaged API')
                preview=desktop.request('backup_restore_preview',{'backup_id':backup})['preview']
                wire.check(not preview['after']['settings']['safety']['allow_real_account'] and
                           preview['after']['profile']['execution']['demo_only'],
                           'preview cannot restore previously revoked REAL grant')
                reply=desktop.request('backup_restore',{'backup_id':backup,'confirmed':True,'preview_hash':preview['preview_hash']})
                wire.check(reply['ok'] and reply['execution']['mode']=='OFF' and not reply['execution_enabled'],
                           'confirmed restore keeps execution OFF')
                wire.check(not reply['settings']['safety']['allow_real_account'] and
                           not reply['settings']['safety']['auto_start_trading'],
                           'restore does not increase REAL or automatic-start permission')
                wire.check(desktop.request('config_active_get')['profile']['execution']['demo_only'],
                           'profile remains DEMO restricted after restore')
                refresh()
                wire.check(desktop.request('execution_mode_set',dict(mode='MANUAL',confirmed=True,**identity))['accepted'],
                           'new mode requires explicit synthetic account review')
                caps['specified_expiration']=False;refresh()
                denied=desktop.request('execution_action',dict(intent_id=str(uuid4()),action='PLACE_PENDING',
                    confirmed=True,side='BUY',order_type='BUY_STOP',price=4202.))
                wire.check(not denied['accepted'] and denied['code']=='BROKER_EXPIRATION_NOT_SUPPORTED',
                           'unsupported pending expiry rejected before queue')
                wire.check(len(desktop.request('execution_history',{'limit':100})['items'])==1,
                           'repair acceptance created no ENTRY intents')
            finally:
                desktop.request('execution_mode_set',{'mode':'OFF'})
                ea.close()
        with wire.engine(executable,root) as (desktop,_):
            status=desktop.request('execution_status')
            wire.check(status['mode']=='OFF' and not status['trading_enabled'],'restart stays OFF after restore')
            settings=desktop.request('settings_get')['settings']
            wire.check(not settings['safety']['allow_real_account'],'revoked REAL remains revoked after restart')
    print(f'PASS: {wire.checks} RC2 packaged repair checks. Synthetic EA only; no MT5/broker/API connection.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('engine_executable')
    run(str(Path(parser.parse_args().engine_executable).resolve()))
