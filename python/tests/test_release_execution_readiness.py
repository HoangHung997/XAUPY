"""First-release regression: quote clock and permission UI share real send gates.

All snapshots are generated fixtures; no terminal, user state or broker is used.
"""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from xaupy_engine.bridge_state import BridgeRegistry
from xaupy_engine.broker_execution import BrokerExecution, IDENTITY
from xaupy_engine.config_schema import default_profile
from xaupy_engine.settings import default_settings
from xaupy_engine.trade_plan import TradePlanError
from test_bridge_state import snapshot as minimal_snapshot
import test_broker_execution as fixtures


class QuoteClockTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.clock = patch('xaupy_engine.bridge_state.time.monotonic', side_effect=lambda: self.now)
        self.clock.start(); self.addCleanup(self.clock.stop)
        self.registry = BridgeRegistry()
        self.session = str(uuid4())
        self.base = minimal_snapshot()
        self.base.update(server_time=1800000000, tick_time_msc=1800000000250,
                         account_login=123, account_server='Test-Demo', magic=991188,
                         bridge_session_id=self.session, point=.01)
        self.registry.record_snapshot(self.base)

    def frame(self, sequence=1, server=1800000003, stamp=1800000003250, **kw):
        batch = dict(stream_id='stream', sequence=sequence, complete=True,
                     ticks=[dict(time_msc=stamp, bid=4300., ask=4300.2, last=0., flags=6)])
        batch.update(kw)
        return dict(symbol='XAUUSD', server_time=server, tick_batch=batch)

    def test_new_tick_compared_to_its_frame_clock_not_old_account_clock(self):
        self.now += 3
        self.assertTrue(self.registry.record_execution_ticks(self.frame(), self.session))
        value = self.registry.execution_snapshot()
        self.assertEqual('TICK_BATCH', value['quote_source'])
        self.assertEqual(4300., value['bid'])
        self.assertEqual(-250, value['quote_age_ms'])
        self.assertEqual(1800000003, value['server_time'])
        self.assertEqual(3000, value['snapshot_age_ms'])
        self.assertNotIn('bars', value)
        self.assertEqual(4281.1, self.registry.latest_fresh_snapshot()['bid'])

    def test_ticks_and_heartbeat_cannot_refresh_old_account_state(self):
        self.now += 4
        self.registry.record_execution_ticks(self.frame(server=1800000004, stamp=1800000004000), self.session)
        self.now += 1.1
        self.registry.record_heartbeat({})
        self.assertIsNone(self.registry.execution_snapshot())
        self.assertFalse(self.registry.record_execution_ticks(self.frame(sequence=2), self.session))

    def test_duplicate_packet_does_not_rejuvenate_quote_or_clock(self):
        self.now += 1
        frame = self.frame(server=1800000001, stamp=1800000001000)
        self.registry.record_execution_ticks(frame, self.session)
        self.now += 2.5
        before = self.registry.execution_snapshot()
        self.assertFalse(self.registry.record_execution_ticks(frame, self.session))
        self.assertEqual(before, self.registry.execution_snapshot())
        self.assertEqual(2500, before['quote_age_ms'])

    def test_empty_packet_updates_clock_not_price(self):
        self.now += 3
        self.registry.record_execution_ticks(self.frame(ticks=[]), self.session)
        value = self.registry.execution_snapshot()
        self.assertEqual('SNAPSHOT', value['quote_source'])
        self.assertGreater(value['quote_age_ms'], 2000)

    def test_foreign_session_and_symbol_cannot_replace_quote(self):
        self.assertFalse(self.registry.record_execution_ticks(self.frame(), str(uuid4())))
        frame = self.frame(); frame['symbol']='EURUSD'
        self.assertFalse(self.registry.record_execution_ticks(frame, self.session))
        self.assertEqual('SNAPSHOT', self.registry.execution_snapshot()['quote_source'])

    def test_identity_change_discards_quote_overlay(self):
        self.registry.record_execution_ticks(self.frame(server=1800000000, stamp=1800000000400), self.session)
        for field, value in [('account_login',124), ('account_server','Other-Demo'),
                             ('magic',991189), ('bridge_session_id',str(uuid4()))]:
            with self.subTest(field=field):
                changed = {**self.base, field:value}
                self.registry.record_snapshot(changed)
                self.assertEqual('SNAPSHOT', self.registry.execution_snapshot()['quote_source'])

    def test_retired_stream_and_out_of_order_packets_are_not_reaccepted(self):
        self.registry.record_execution_ticks(self.frame(2), self.session)
        self.assertFalse(self.registry.record_execution_ticks(self.frame(1), self.session))
        self.registry.record_execution_ticks(self.frame(1, stream_id='new'), self.session)
        self.assertFalse(self.registry.record_execution_ticks(self.frame(3), self.session))

    def test_price_older_than_snapshot_never_replaces_snapshot(self):
        self.registry.record_execution_ticks(self.frame(server=1800000000, stamp=1800000000100), self.session)
        self.assertEqual('SNAPSHOT', self.registry.execution_snapshot()['quote_source'])

    def test_invalid_nonfinite_transport_rejected(self):
        frame=self.frame(); frame['tick_batch']['ticks'][0]['bid']=float('nan')
        with self.assertRaises(ValueError):
            self.registry.record_execution_ticks(frame,self.session)

    def test_unknown_server_clock_remains_unknown(self):
        self.registry.record_snapshot({**self.base,'server_time':None})
        value=self.registry.execution_snapshot()
        self.assertIsNone(value['quote_age_ms'])
        self.assertEqual('INVALID_CLOCK',value['quote_source'])


class ReadinessTests(fixtures.BrokerExecutionTests):
    # Reuse fixture without counting inherited tests a second time.
    def test_fresh_quote_guard_is_identical_for_status_and_submit(self):
        self.enable()
        self.snapshot['tick_time_msc']-=2001
        value=self.service.status()
        self.assertEqual('FRESH_QUOTE_REQUIRED',value['reason'])
        self.assertFalse(value['entry_enabled'])
        self.assertFalse(value['execution_enabled'])
        with self.assertRaisesRegex(TradePlanError,'FRESH_QUOTE_REQUIRED'):
            self.service.submit(self.entry(),self.profile)
        self.snapshot['tick_time_msc']+=2001
        value=self.service.status()
        self.assertTrue(value['entry_enabled'])
        self.assertEqual('',value['reason'])

    def test_old_attempt_error_is_separate_from_current_readiness(self):
        self.enable(); self.service.last_blocker='FRESH_QUOTE_REQUIRED'
        value=self.service.status()
        self.assertEqual('',value['reason'])
        self.assertEqual('FRESH_QUOTE_REQUIRED',value['last_attempt_reason'])
        self.assertTrue(value['entry_enabled'])

    def test_day_loss_blocks_entry_but_does_not_prevent_protective_management(self):
        self.enable()
        self.snapshot['demo_once_guard']['daily_realized']=-10000
        value=self.service.status()
        self.assertFalse(value['entry_enabled'])
        self.assertTrue(value['management_enabled'])
        self.assertEqual('DAILY_LOSS_LIMIT',value['entry_reason'])

    def test_permissions_do_not_enable_mode(self):
        self.settings['safety']['allow_real_account']=True
        self.strategy.profile=self.profile
        value=self.service.status()
        self.assertTrue(value['permissions']['local_allow_real'])
        self.assertFalse(value['permissions']['effective_allow_real'])
        self.assertFalse(value['execution_enabled'])
        self.assertEqual('OFF',value['mode'])

    def test_fresh_display_cannot_override_account_clock_by_itself(self):
        self.enable()
        self.strategy.status_payload=lambda **kw: {'display':{'available':True,'bid':5000,'ask':5001,'tick_time_msc':(self.snapshot['server_time']+30)*1000}}
        value=self.service._snapshot()
        self.assertEqual(4200.,value['bid'])
        self.assertEqual(self.snapshot['tick_time_msc'],value['tick_time_msc'])

    def test_empty_batch_is_not_reported_as_success(self):
        self.enable()
        result=self.service.submit(dict(intent_id=str(uuid4()),action='CLOSE_ALL',confirmed=True),self.profile)
        self.assertFalse(result['accepted']); self.assertEqual('NO_TARGETS',result['code'])
        self.assertEqual('REJECTED',self.service.history()[0]['state'])

    def test_live_permission_revocation_is_reflected_in_status(self):
        self.snapshot['account_trade_mode']='REAL'
        self.settings['safety']['allow_real_account']=True
        self.profile['execution'].update(allow_real_account=True,demo_only=False)
        self.strategy.profile=self.profile
        self.enable()
        self.settings['safety']['allow_real_account']=False
        value=self.service.status()
        self.assertEqual('USER_REAL_PERMISSION_REQUIRED',value['reason'])
        self.assertFalse(value['permissions']['effective_allow_real'])
        self.assertFalse(value['entry_enabled'])

# Only run new tests here; base regressions remain in test_broker_execution.
for name in list(fixtures.BrokerExecutionTests.__dict__):
    if name.startswith('test_') and name not in ReadinessTests.__dict__:
        setattr(ReadinessTests, name, None)


class RiskProjectionTests(unittest.TestCase):
    def test_locked_profit_is_not_reported_as_open_loss_risk(self):
        for side,stop in [('BUY',4201.),('SELL',4199.)]:
            data=minimal_snapshot()
            data.update(tick_size=.01,tick_value=1.,tick_value_loss=1.,equity=1000,
                        positions=[dict(side=side,sl=stop,price_open=4200.,volume=.1)])
            bridge=BridgeRegistry();bridge.record_snapshot(data)
            view=bridge.orders_positions_payload()
            self.assertEqual(0,view['risk_usd']);self.assertTrue(view['risk_complete'])

    def test_invalid_tick_metadata_is_incomplete_not_infinite_risk(self):
        data=minimal_snapshot()
        data.update(tick_size=.01,tick_value=float('inf'),equity=1000,
                    positions=[dict(side='BUY',sl=4190.,price_open=4200.,volume=.1)])
        bridge=BridgeRegistry();bridge.record_snapshot(data)
        self.assertFalse(bridge.orders_positions_payload()['risk_complete'])
        self.assertIsNone(bridge.orders_positions_payload()['risk_usd'])


if __name__=='__main__': unittest.main()
