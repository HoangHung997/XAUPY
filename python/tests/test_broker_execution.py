from copy import deepcopy
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from uuid import uuid4

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from xaupy_engine.broker_execution import BrokerExecution, IDENTITY
from xaupy_engine.config_schema import default_profile
from xaupy_engine.settings import default_settings
from xaupy_engine.trade_plan import TradePlanError, plan_entry
from test_demo_once import NOW


class BrokerExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.profile=default_profile()
        self.profile['stop_loss'].update(mode='FIXED',fixed_price_units=3)
        self.profile['take_profit'].update(mode='FIXED',fixed_price_units=6)
        self.profile['risk'].update(fixed_lot=.01,sizing_mode='FIXED_LOT')
        self.settings=default_settings()
        self.snapshot=dict(execution_capable=True,terminal_connected=True,account_trade_mode='DEMO',
            account_login=123456,account_server='Test-Demo',symbol='XAUUSD',magic=991188,
            bridge_session_id=str(uuid4()),server_time=NOW,tick_time_msc=NOW*1000,
            bid=4200.,ask=4200.2,balance=10000.,point=.01,tick_size=.01,tick_value=1.,
            volume_min=.01,volume_max=100.,volume_step=.01,stops_level=10,freeze_level=0,positions=[],orders=[],
            guardian={'max_volume':.1},demo_once_guard={'broker_day_start':NOW//86400*86400,'trades_today':0,
            'consecutive_losses':0,'last_exit_time':0,'day_start_balance':10000.,'daily_realized':0.,'history_complete':True})
        self.signal=None
        self.strategy=SimpleNamespace(history={},status_payload=lambda **kwargs:{'last_signal':self.signal})
        self.bridge=SimpleNamespace(latest_fresh_snapshot=lambda:deepcopy(self.snapshot))
        self.service=BrokerExecution(Path(self.temp.name),self.bridge,self.strategy,self.settings)
        self.addCleanup(lambda:self.service.close())

    def enable(self,mode='MANUAL'):
        return self.service.set_mode({'mode':mode,'confirmed':True,**{k:self.snapshot[k] for k in IDENTITY}},self.profile)

    def test_user_startup_sync_choice_controls_restored_mode(self):
        self.enable('AUTO');self.settings['safety']['auto_start_trading']=True
        self.service.close()
        self.service=BrokerExecution(Path(self.temp.name),self.bridge,self.strategy,self.settings)
        self.assertEqual('STARTUP_BRIDGE_SYNC_PENDING',self.service.status()['reason'])
        self.snapshot['demo_once_guard']['history_complete']=False;self.service.on_snapshot()
        self.assertTrue(self.service.startup_sync_pending)
        self.snapshot['demo_once_guard']['history_complete']=True;self.service.on_snapshot()
        self.assertTrue(self.service.status()['trading_enabled'])
        self.settings['safety']['require_reconciliation']=False;self.service.close()
        self.service=BrokerExecution(Path(self.temp.name),self.bridge,self.strategy,self.settings)
        self.assertFalse(self.service.startup_sync_pending)
        self.assertTrue(self.service.status()['trading_enabled'])

    def entry(self,**changes):
        return dict(intent_id=str(uuid4()),action='MARKET_BUY',confirmed=True,**changes)

    def broker_result(self,command,**changes):
        return {**{k:command[k] for k in (*IDENTITY,'bridge_session_id','intent_id')},'state':'CONFIRMED',
                'broker_verified':True,'order_send_called':True,'retcode':10009,'order_ticket':501,'deal_ticket':502,'position_ticket':503,
                'filled_volume':command['volume'],'fill_price':command['price'],'sl':command['sl'],'tp':command['tp'],**changes}

    def test_off_is_user_choice_and_exact_account_confirmation_is_required(self):
        with self.assertRaisesRegex(TradePlanError,'USER_STOPPED'):
            self.service.submit(self.entry(),self.profile)

        with self.assertRaisesRegex(TradePlanError,'CONFIRMED_ACCOUNT_MISMATCH'):
            self.service.set_mode({'mode':'MANUAL','confirmed':True},self.profile)
        self.enable()
        self.snapshot['account_login']+=1
        with self.assertRaisesRegex(TradePlanError,'ACCOUNT_OR_SYMBOL_CHANGED'):
            self.service.submit(self.entry(),self.profile)

    def test_existing_position_risk_does_not_replace_new_entry_stop(self):
        before=plan_entry(self.profile,self.snapshot,{},'BUY')
        self.snapshot['positions']=[dict(side='SELL',price_open=4190.,sl=4192.,volume=.01)]
        after=plan_entry(self.profile,self.snapshot,{},'BUY')
        self.assertEqual(before['sl'],after['sl'])
        self.assertEqual(4197.2,after['sl'])
        self.assertEqual('BUY',after['side'])

    def test_real_profile_import_cannot_grant_local_account_permission(self):
        self.snapshot['account_trade_mode']='REAL'
        self.profile['execution'].update(demo_only=False,allow_real_account=True)
        with self.assertRaisesRegex(TradePlanError,'USER_REAL_PERMISSION_REQUIRED'):
            self.enable()
        self.settings['safety']['allow_real_account']=True
        self.enable()
        self.assertTrue(self.service.submit(self.entry(),self.profile)['accepted'])

    def test_intent_is_durable_idempotent_and_dispatched_once(self):
        self.enable()
        payload=self.entry()
        self.service.submit(payload,self.profile)
        self.assertEqual('QUEUED',self.service.submit(payload,self.profile)['state'])
        command=self.service.next_command(self.profile,self.snapshot['bridge_session_id'])
        self.assertIsNotNone(command)
        self.assertIsNone(self.service.next_command(self.profile,self.snapshot['bridge_session_id']))
        with self.assertRaisesRegex(TradePlanError,'INTENT_ID_CONFLICT'):
            self.service.submit({**payload,'action':'MARKET_SELL'},self.profile)
        self.service.close()
        self.service=BrokerExecution(Path(self.temp.name),self.bridge,self.strategy,self.settings)
        self.assertEqual('UNKNOWN',self.service.history()[0]['state'])
        self.enable()
        with self.assertRaisesRegex(TradePlanError,'RECONCILIATION_REQUIRED'):
            self.service.submit(self.entry(),self.profile)
        self.assertIsNone(self.service.next_command(self.profile,self.snapshot['bridge_session_id']))

    def test_broker_evidence_and_post_trade_snapshot_are_required(self):
        self.enable()
        self.service.submit(self.entry(),self.profile)
        command=self.service.next_command(self.profile,self.snapshot['bridge_session_id'])
        with self.assertRaisesRegex(TradePlanError,'BROKER_EVIDENCE_REQUIRED'):
            self.service.record_result(self.broker_result(command,broker_verified=False),self.snapshot['bridge_session_id'])
        with self.assertRaisesRegex(TradePlanError,'PROTECTION_EVIDENCE_MISMATCH'):
            self.service.record_result(self.broker_result(command,sl=command['sl']-1),self.snapshot['bridge_session_id'])
        result=self.broker_result(command)
        self.service.record_result(result,self.snapshot['bridge_session_id'])
        self.assertTrue(self.service.record_result(result,self.snapshot['bridge_session_id'])['accepted'])
        with self.assertRaisesRegex(TradePlanError,'AWAITING_POST_TRADE_SNAPSHOT'):
            self.service.submit(self.entry(),self.profile)
        self.service.on_snapshot()
        self.assertTrue(self.service.submit(self.entry(),self.profile)['accepted'])

    def test_stopping_cancels_queued_intent_and_profile_change_cannot_send_old_plan(self):
        self.enable()
        self.service.submit(self.entry(),self.profile)
        self.service.set_mode({'mode':'OFF'},self.profile)
        self.assertEqual('CANCELLED',self.service.history()[0]['state'])
        self.enable()
        self.service.submit(self.entry(),self.profile)
        self.profile['take_profit']['fixed_price_units']=7
        self.assertIsNone(self.service.next_command(self.profile,self.snapshot['bridge_session_id']))
        self.assertEqual('CANCELLED',self.service.history()[0]['state'])

    def test_reserved_entries_obey_max_positions(self):
        self.enable()
        self.service.submit(self.entry(),self.profile)
        with self.assertRaisesRegex(TradePlanError,'MAX_OPEN_POSITIONS'):
            self.service.submit(self.entry(),self.profile)

    def test_risk_sizing_rounds_down_and_manual_oversize_is_rejected(self):
        self.profile['risk'].update(sizing_mode='RISK_PERCENT',risk_percent=.15,max_lot=1)
        self.snapshot['guardian']['max_volume']=1
        plan=plan_entry(self.profile,self.snapshot,{},'BUY')
        self.assertEqual(.04,plan['volume'])
        with self.assertRaisesRegex(TradePlanError,'RISK_BUDGET_EXCEEDED'):
            plan_entry(self.profile,self.snapshot,{},'BUY',{'volume':.1})
        with self.assertRaisesRegex(TradePlanError,'REQUESTED_VOLUME_NOT_ALLOWED'):
            plan_entry(self.profile,self.snapshot,{},'BUY',{'volume':.015})

    def test_pending_and_custom_comment_reach_command(self):
        self.enable()
        self.profile['execution']['order_comment']='User strategy'
        queued=self.service.submit(dict(intent_id=str(uuid4()),confirmed=True,action='PLACE_PENDING',side='BUY',order_type='BUY_STOP',price=4201.),self.profile)
        self.assertEqual('BUY_STOP',queued['preview']['order_type'])
        self.assertEqual('User strategy',queued['preview']['comment'])
        self.assertGreater(queued['preview']['expiration'],NOW)

    def test_unowned_ticket_partial_remainder_and_stop_widening_rejected(self):
        self.enable()
        self.snapshot['positions']=[dict(ticket=10,magic=991188,symbol='XAUUSD',side='BUY',volume=.01,price_open=4198.,sl=4199.,tp=4206.)]
        def action(name,**kw):
            return self.service.submit(dict(intent_id=str(uuid4()),confirmed=True,action=name,ticket=10,**kw),self.profile)
        with self.assertRaisesRegex(TradePlanError,'VOLUME_BELOW_BROKER_MINIMUM'):
            action('PARTIAL_CLOSE',percent=50)
        with self.assertRaisesRegex(TradePlanError,'NEVER_WIDEN_SL'):
            action('MODIFY_POSITION',sl=4198.)
        self.snapshot['positions'][0]['magic']=42
        with self.assertRaisesRegex(TradePlanError,'OWNED_TICKET_NOT_FOUND'):
            action('CLOSE_POSITION')

    def test_pending_management_uses_broker_volume_current_and_expiration(self):
        self.enable()
        self.snapshot['orders']=[dict(ticket=700,magic=991188,symbol='XAUUSD',type='BUY_STOP',volume_current=.01,
            price_open=4202.,sl=4199.,tp=4208.,expiration=NOW+600)]
        result=self.service.submit(dict(intent_id=str(uuid4()),confirmed=True,action='MODIFY_PENDING',ticket=700,price=4203.,sl=4200.),self.profile)
        self.assertEqual(NOW+600,result['preview']['expiration'])
        self.assertEqual(.01,result['preview']['volume'])

    def test_desktop_null_optional_values_keep_existing_tp_when_moving_be(self):
        self.enable()
        self.snapshot['positions']=[dict(ticket=42,magic=991188,symbol='XAUUSD',side='BUY',volume=.02,price_open=4198.,sl=4195.,tp=4205.)]
        result=self.service.submit(dict(intent_id=str(uuid4()),confirmed=True,action='MOVE_SL_BE',ticket=42,sl=None,tp=None,percent=None,price=None),self.profile)
        self.assertEqual(4198.1,result['preview']['sl'])
        self.assertEqual(4205.,result['preview']['tp'])

    def test_uncertain_send_blocks_entries_after_reply_timeout(self):
        self.enable()
        self.service.submit(self.entry(),self.profile)
        self.service.next_command(self.profile,self.snapshot['bridge_session_id'])
        self.service.db.execute("UPDATE intents SET updated=0 WHERE state='DISPATCHED'")
        self.assertEqual('RECONCILIATION_REQUIRED',self.service.status()['reason'])
        self.assertEqual('UNKNOWN',self.service.history()[0]['state'])

    def test_new_signal_is_automatic_only_and_not_replayed_after_restart(self):
        from xaupy_engine.demo_once import profile_hash
        self.signal=dict(side='BUY',profile_hash=profile_hash(self.profile),bar_time=NOW-60,sequence=1)
        self.enable('AUTO')
        self.service.observe_signal(self.profile)
        self.assertEqual([],self.service.history())
        self.signal['sequence']=2
        self.service.observe_signal(self.profile)
        self.assertEqual(1,len(self.service.history()))
        self.service.observe_signal(self.profile)
        self.assertEqual(1,len(self.service.history()))

    def test_management_reuses_original_risk_after_break_even(self):
        self.enable('AUTO')
        self.profile['management'].update(partial_close_enabled=True,breakeven_enabled=False)
        position=dict(ticket=700,position_identifier=701,magic=991188,symbol='XAUUSD',side='BUY',volume=.04,price_open=4197.,sl=4197.1,tp=4205.)
        self.snapshot['positions']=[position]
        self.service.save_position_state(self.service.position_key(self.snapshot,700),{'initial_risk':3.,'original_tp':4203.})
        self.service.manage_positions(self.profile)
        self.assertEqual('PARTIAL_CLOSE',self.service.history()[0]['command']['action'])
        self.assertEqual(.02,self.service.history()[0]['command']['volume'])
        self.service.manage_positions(self.profile)
        self.assertEqual(1,len(self.service.history()))


if __name__=='__main__':
    unittest.main()
