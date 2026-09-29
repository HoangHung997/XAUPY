"""Regressions for the reproduced RC1 blockers. All accounts are dictionaries.

No MT5 provider, broker socket, or production state is used by these tests.
"""
from copy import deepcopy
import asyncio
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from uuid import uuid4

sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parent)]
import test_broker_execution as broker_fixtures
from xaupy_engine.broker_execution import IDENTITY, BrokerExecution
from xaupy_engine.contracts import Envelope
from xaupy_engine.position_management import position_decision
from xaupy_engine.server import EngineServer
from xaupy_engine.settings import SettingsStore
from xaupy_engine.strategy_engine import Bar
from xaupy_engine.trade_plan import partial_close_volume, TradePlanError


class CombinedManagementRepairTests(unittest.TestCase):
    def setUp(self):
        self.case = broker_fixtures.BrokerExecutionTests(methodName='runTest')
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.profile = self.case.profile
        self.profile['management'].update(partial_close_enabled=True,
            partial_close_percent=50, partial_close_at_rr=1., breakeven_enabled=True,
            breakeven_trigger_rr=1., breakeven_offset_price_units=.1,
            trailing_enabled=False, sl_tighten_mode='OFF')
        self.case.enable('AUTO')
        self.position = dict(ticket=700, position_identifier=701, magic=991188,
            symbol='XAUUSD', side='BUY', volume=.01, price_open=4197., sl=4194., tp=4220.)
        self.case.snapshot['positions'] = [self.position]
        self.state = dict(initial_risk=3., original_tp=4203., entry_rsi=30., entry_z=-2.)
        self.key = self.case.service.position_key(self.case.snapshot, 700)
        self.case.service.save_position_state(self.key, self.state)

    def test_impossible_partial_does_not_starve_break_even_on_buy_or_sell(self):
        for side in ('BUY', 'SELL'):
            with self.subTest(side=side):
                position = dict(self.position)
                if side == 'SELL':
                    position.update(side='SELL', price_open=4203.2, sl=4206.2)
                state, decision = position_decision(self.profile, self.case.snapshot,
                    {}, position, self.state, {})
                self.assertEqual('MODIFY_POSITION', decision['action'])
                self.assertAlmostEqual(4197.1 if side == 'BUY' else 4203.1, decision['sl'])
                self.assertEqual('VOLUME_BELOW_BROKER_MINIMUM', state['partial_skip_reason'])
                self.assertNotIn('partial_intent', state)
                self.assertNotIn('partial_skip_reason', self.state, 'pure input must not mutate')

    def test_actual_service_queues_one_protective_action_and_bounded_skip_warning(self):
        for _ in range(20):
            self.case.service.manage_positions(self.profile)
        actions = self.case.service.history()
        self.assertEqual(1, len(actions))
        self.assertEqual('MODIFY_POSITION', actions[0]['command']['action'])
        self.assertAlmostEqual(4197.1, actions[0]['command']['sl'])
        self.assertEqual('VOLUME_BELOW_BROKER_MINIMUM',
            self.case.service.position_state(self.key)['partial_skip_reason'])
        self.assertIn('700', self.case.service.management_warnings)
        self.assertLessEqual(len(self.case.service.management_warnings), 1)

    def test_impossible_partial_does_not_starve_dynamic_exit_or_latch(self):
        self.profile['take_profit']['mode'] = 'ZRSI_DYNAMIC'
        snapshot = dict(self.case.snapshot, bid=4203., ask=4203.2)
        state, action = position_decision(self.profile, snapshot, {}, self.position, self.state, {})
        self.assertEqual('ORIGINAL_TP', action['reason'])
        state, _ = position_decision(self.profile, snapshot, {}, self.position,
            self.state, {'z': 2.6, 'rsi': 76.})
        self.assertTrue(state['extended'])
        state, action = position_decision(self.profile, snapshot, {}, self.position,
            state, {'z': 1., 'rsi': 60.})
        self.assertEqual('ZRSI_REVERSAL', action['reason'])

    def test_impossible_partial_keeps_structure_trailing_and_never_widen(self):
        self.profile['management'].update(breakeven_enabled=False,
            trailing_enabled=True, trailing_mode='STRUCTURE', trailing_structure_lookback=2,
            trailing_step_price_units=.1)
        self.profile['stop_loss'].update(structure_timeframe='M1', structure_buffer_price_units=.1)
        now = self.case.snapshot['server_time']
        history = {'M1': [Bar((now//60-2)*60,4198.,4199.,4197.8,4198.6,100),
                          Bar((now//60-1)*60,4198.6,4199.8,4198.4,4199.5,100)]}
        state, action = position_decision(self.profile, self.case.snapshot, history,
            self.position, self.state, {})
        self.assertEqual('MODIFY_POSITION', action['action'])
        self.assertAlmostEqual(4197.7, action['sl'])
        position = dict(self.position, sl=4198.)
        _, action = position_decision(self.profile, self.case.snapshot, history, position, state, {})
        self.assertIsNone(action)

    def test_valid_partial_is_once_and_definite_rejection_does_not_block_be(self):
        self.position['volume'] = .04
        self.case.service.manage_positions(self.profile)
        queued = self.case.service.history()[0]
        self.assertEqual('PARTIAL_CLOSE', queued['command']['action'])
        command = self.case.service.next_command(self.profile, self.case.snapshot['bridge_session_id'])
        rejected = self.case.broker_result(dict(command, price=self.case.snapshot['bid']), state='REJECTED', broker_verified=False,
            order_send_called=False, retcode=10014, reason='BROKER_REJECTED_TEST',
            position_ticket=700, order_ticket=0, deal_ticket=0, filled_volume=0, fill_price=0)
        self.case.service.record_result(rejected, self.case.snapshot['bridge_session_id'])
        self.case.service.on_snapshot()
        self.case.service.manage_positions(self.profile)
        history = self.case.service.history()
        self.assertEqual(1, sum(r['command']['action'] == 'PARTIAL_CLOSE' for r in history))
        self.assertTrue(any(r['command']['action'] == 'MODIFY_POSITION' for r in history))

    def test_broker_partial_fill_is_not_retried_and_other_protection_continues(self):
        self.position['volume'] = .04
        self.case.service.manage_positions(self.profile)
        command = self.case.service.next_command(self.profile, self.case.snapshot['bridge_session_id'])
        result = self.case.broker_result(dict(command, price=self.case.snapshot['bid']), position_ticket=700, retcode=10010,
            filled_volume=.01, fill_price=4200.)
        self.case.service.record_result(result, self.case.snapshot['bridge_session_id'])
        self.position['volume'] = .03
        self.case.service.on_snapshot()
        self.case.service.manage_positions(self.profile)
        self.assertTrue(self.case.service.position_state(self.key)['partial_confirmed'])
        self.assertEqual(1, sum(r['command']['action'] == 'PARTIAL_CLOSE' for r in self.case.service.history()))
        self.assertTrue(any(r['command']['action'] == 'MODIFY_POSITION' for r in self.case.service.history()))

    def test_shared_partial_volume_validates_percent_step_and_remainder(self):
        self.assertEqual(.02, partial_close_volume(.05, 50, self.case.snapshot))
        for volume, percent, code in ((.01,50,'VOLUME_BELOW_BROKER_MINIMUM'),
                                     (.02,99,'PARTIAL_REMAINDER_BELOW_MINIMUM'),
                                     (.04,100,'PARTIAL_PERCENT_MUST_BE_BELOW_100')):
            with self.subTest(volume=volume, percent=percent):
                # .02 at 99% floors to .01, so use a broker min .02 for the remainder case.
                snapshot = dict(self.case.snapshot)
                if code == 'PARTIAL_REMAINDER_BELOW_MINIMUM':
                    snapshot.update(volume_min=.02)
                    volume = .04
                with self.assertRaisesRegex(TradePlanError,code):
                    partial_close_volume(volume,percent,snapshot)


class RecoveryPermissionRepairTests(unittest.TestCase):
    def setUp(self):
        self.case = broker_fixtures.BrokerExecutionTests(methodName='runTest')
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.temp = tempfile.TemporaryDirectory(prefix='xaupy-rc2-restore-')
        self.addCleanup(self.temp.cleanup)
        self.engine = EngineServer(port=0, state_dir=self.temp.name)
        self.addCleanup(lambda: asyncio.run(self.engine.close()))
        self.snapshot = deepcopy(self.case.snapshot)
        self.snapshot['account_trade_mode'] = 'REAL'  # ONLY a fixture dictionary.
        profile = deepcopy(self.case.profile)
        profile['execution'].update(demo_only=False, allow_real_account=True)
        settings = deepcopy(self.case.settings)
        settings['safety'].update(allow_real_account=True, auto_start_trading=True)
        self.engine.settings_store.save(settings=settings, profile=profile)
        self.engine.active_profile = deepcopy(self.engine.settings_store.profile)
        self.engine.strategy.set_profile(self.engine.active_profile)
        self.engine.execution.bridge = SimpleNamespace(latest_fresh_snapshot=lambda: deepcopy(self.snapshot))
        self.engine.execution.settings = self.engine.settings_store.settings
        self.assertTrue(self.request('execution_mode_set', dict(mode='AUTO',confirmed=True,
            **{k:self.snapshot[k] for k in IDENTITY}))['accepted'])
        self.backup = self.request('backup_create')['backup']['id']

    def request(self, kind, payload=None):
        reply, _ = self.engine._dispatch(Envelope.create(kind, payload))
        self.assertEqual(kind+'_ack', reply.type, reply.to_json())
        return reply.payload

    def preview(self):
        reply = self.request('backup_restore_preview', {'backup_id':self.backup})
        self.assertTrue(reply['ok'], reply)
        return reply['preview']

    def restore(self, preview=None, **kwargs):
        preview = preview or self.preview()
        return self.request('backup_restore', {'backup_id':self.backup, 'confirmed':True,
            'preview_hash':preview['preview_hash'], **kwargs})

    def test_unconfirmed_restore_has_no_mutations(self):
        before = self.engine.settings_store.path.read_bytes()
        result = self.request('backup_restore', {'backup_id':self.backup})
        self.assertFalse(result['ok'])
        self.assertIn('RESTORE_CONFIRMATION_REQUIRED', str(result['errors']))
        self.assertEqual(before, self.engine.settings_store.path.read_bytes())
        self.assertEqual('AUTO', self.engine.execution.policy['mode'])
        self.assertEqual([], self.engine.execution.history())

    def test_revoked_real_is_not_restored_and_auto_requires_new_review(self):
        settings = deepcopy(self.engine.settings_store.settings)
        settings['safety']['allow_real_account'] = False
        result = self.request('settings_set', {'settings':settings})
        self.assertTrue(result['ok'])
        self.assertFalse(result['trading_enabled'], 'ack must not carry pre-change flags')
        preview = self.preview()
        self.assertFalse(preview['after']['settings']['safety']['allow_real_account'])
        self.assertTrue(preview['after']['profile']['execution']['demo_only'])
        result = self.restore(preview)
        self.assertTrue(result['ok'], result)
        self.assertFalse(result['execution_enabled'])
        self.assertFalse(result['trading_enabled'])
        status = self.engine.execution.status()
        self.assertEqual('OFF', status['mode'])
        self.assertFalse(status['permissions']['effective_allow_real'])
        self.assertFalse(self.engine.settings_store.settings['safety']['auto_start_trading'])
        self.assertTrue(self.engine.settings_store.settings['safety']['require_reconciliation'])
        restarted = SettingsStore(self.temp.name)
        self.assertFalse(restarted.settings['safety']['allow_real_account'])
        self.assertFalse(restarted.settings['safety']['auto_start_trading'])

    def test_restore_with_existing_grant_still_stops_and_cancels_unsent(self):
        self.engine.execution.submit(self.case.entry(), self.engine.active_profile)
        result = self.restore()
        self.assertTrue(result['ok'], result)
        self.assertEqual('OFF', self.engine.execution.policy['mode'])
        self.assertFalse(result['trading_enabled'])
        self.assertEqual('CANCELLED', self.engine.execution.history()[0]['state'])
        self.assertFalse(self.engine.settings_store.settings['safety']['auto_start_trading'])

    def test_restore_preserves_ambiguous_evidence_and_never_resends(self):
        self.engine.execution.submit(self.case.entry(), self.engine.active_profile)
        command = self.engine.execution.next_command(self.engine.active_profile, self.snapshot['bridge_session_id'])
        self.assertIsNotNone(command)
        self.engine.execution.disconnected()
        result = self.restore()
        self.assertTrue(result['ok'], result)
        self.assertEqual('UNKNOWN', self.engine.execution.history()[0]['state'])
        self.assertIsNone(self.engine.execution.next_command(self.engine.active_profile, self.snapshot['bridge_session_id']))

    def test_preview_is_bound_to_current_config_and_selected_backup(self):
        preview = self.preview()
        settings = deepcopy(self.engine.settings_store.settings)
        settings['appearance']['font_scale'] = 110
        self.assertTrue(self.request('settings_set', {'settings':settings})['ok'])
        before = self.engine.settings_store.path.read_bytes()
        result = self.restore(preview)
        self.assertFalse(result['ok'])
        self.assertIn('RESTORE_PREVIEW_CHANGED', str(result['errors']))
        self.assertEqual(before, self.engine.settings_store.path.read_bytes())
        self.assertEqual('AUTO', self.engine.execution.policy['mode'])

    def test_backup_changed_after_preview_rejected_without_profile_mutation(self):
        import json
        preview = self.preview()
        path = self.engine.settings_store.backup_dir/self.backup
        backup = json.loads(path.read_text())
        backup['profile']['risk']['fixed_lot'] = .02
        path.write_text(json.dumps(backup), encoding='utf-8')
        before = self.engine.settings_store.path.read_bytes()
        result = self.restore(preview)
        self.assertFalse(result['ok'])
        self.assertEqual(before, self.engine.settings_store.path.read_bytes())

    def test_permission_grant_does_not_reactivate_previous_auto_selection(self):
        settings = deepcopy(self.engine.settings_store.settings)
        settings['safety']['allow_real_account'] = False
        self.assertTrue(self.request('settings_set', {'settings':settings})['ok'])
        settings['safety']['allow_real_account'] = True
        result = self.request('settings_set', {'settings':settings})
        self.assertTrue(result['ok'])
        self.assertFalse(result['trading_enabled'])
        self.assertEqual('OFF', self.engine.execution.policy['mode'])


    def test_changed_account_or_mode_invalidates_restore_review(self):
        preview = self.preview()
        before = self.engine.settings_store.path.read_bytes()
        self.snapshot['account_login'] += 1
        result = self.restore(preview)
        self.assertFalse(result['ok'])
        self.assertIn('RESTORE_PREVIEW_CHANGED', str(result['errors']))
        self.assertEqual(before, self.engine.settings_store.path.read_bytes())
        self.snapshot['account_login'] -= 1
        self.engine.execution.set_mode({'mode':'OFF'}, self.engine.active_profile)
        result = self.restore(preview)
        self.assertFalse(result['ok'])
        self.assertIn('RESTORE_PREVIEW_CHANGED', str(result['errors']))

    def test_restore_write_failure_keeps_old_profile_and_persists_safe_off(self):
        from unittest.mock import patch
        before = self.engine.settings_store.path.read_bytes()
        profile = deepcopy(self.engine.active_profile)
        preview = self.preview()
        with patch('xaupy_engine.settings._atomic_json', side_effect=OSError('isolated-write-failure')):
            result = self.restore(preview)
        self.assertFalse(result['ok'])
        self.assertIn('isolated-write-failure', str(result['errors']))
        self.assertFalse(result['execution_enabled'])
        self.assertEqual('OFF', result['execution']['mode'])
        self.assertEqual(before, self.engine.settings_store.path.read_bytes())
        self.assertEqual(profile, self.engine.active_profile)
        self.assertEqual('OFF', self.engine.execution.meta('policy')['mode'])

    def test_invalid_permission_update_does_not_mutate_policy_or_file(self):
        before = self.engine.settings_store.path.read_bytes()
        settings = deepcopy(self.engine.settings_store.settings)
        settings['safety']['allow_real_account'] = False
        settings['connection']['port'] = 'not-a-port'
        result = self.request('settings_set', {'settings':settings})
        self.assertFalse(result['ok'])
        self.assertEqual('AUTO', self.engine.execution.policy['mode'])
        self.assertEqual(before, self.engine.settings_store.path.read_bytes())


class BrokerCapabilityPreflightTests(unittest.TestCase):
    def setUp(self):
        self.case = broker_fixtures.BrokerExecutionTests(methodName='runTest')
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.case.enable('MANUAL')

    def test_missing_or_malformed_new_ea_capabilities_fail_closed(self):
        caps = deepcopy(self.case.snapshot['execution_capabilities'])
        for broken in (None, {}, dict(caps, trade_allowed=1), dict(caps, schema_version=True)):
            self.case.snapshot['execution_capabilities'] = broken
            status = self.case.service.status()
            self.assertFalse(status['execution_enabled'])
            self.assertIn(status['reason'], ('BRIDGE_UPGRADE_REQUIRED', 'BROKER_CAPABILITIES_INVALID'))
            with self.assertRaises(TradePlanError):
                self.case.service.submit(self.case.entry(), self.case.profile)
        self.assertEqual([], self.case.service.history())

    def test_algo_permission_is_not_confused_with_user_mode(self):
        self.case.snapshot['execution_capabilities']['trade_allowed'] = False
        status = self.case.service.status()
        self.assertEqual('MANUAL', status['mode'])
        self.assertEqual('TRADE_PERMISSION_DISABLED', status['reason'])
        self.assertFalse(status['entry_enabled'])
        self.assertFalse(status['management_enabled'])
        self.case.snapshot['execution_capabilities']['trade_allowed'] = True
        self.assertTrue(self.case.service.status()['entry_enabled'])

    def test_netting_exposure_blocks_entry_but_not_owned_position_management(self):
        self.case.snapshot['execution_capabilities']['netting_symbol_exposed'] = True
        status = self.case.service.status()
        self.assertFalse(status['entry_enabled'])
        self.assertTrue(status['management_enabled'])
        self.assertEqual('NETTING_SYMBOL_ALREADY_EXPOSED', status['entry_reason'])
        with self.assertRaisesRegex(TradePlanError, 'NETTING_SYMBOL_ALREADY_EXPOSED'):
            self.case.service.submit(self.case.entry(), self.case.profile)
        self.assertEqual([], self.case.service.history())

    def test_pending_expiry_support_checked_before_queue_without_silent_gtc_fallback(self):
        self.case.snapshot['execution_capabilities']['specified_expiration'] = False
        with self.assertRaisesRegex(TradePlanError, 'BROKER_EXPIRATION_NOT_SUPPORTED'):
            self.case.service.submit(dict(intent_id=str(uuid4()), confirmed=True, action='PLACE_PENDING',
                side='BUY', order_type='BUY_STOP', price=4202.), self.case.profile)
        self.assertEqual([], self.case.service.history())
        self.assertTrue(self.case.service.submit(self.case.entry(), self.case.profile)['accepted'])

    def test_broker_side_and_order_type_limits_are_independent(self):
        caps = self.case.snapshot['execution_capabilities']
        caps['allow_sell'] = False
        self.assertFalse(self.case.service.status()['allow_sell'])
        self.assertTrue(self.case.service.status()['allow_buy'])
        with self.assertRaisesRegex(TradePlanError, 'SYMBOL_ENTRY_DISABLED'):
            self.case.service.submit(dict(intent_id=str(uuid4()), confirmed=True, action='MARKET_SELL'), self.case.profile)
        caps['market_orders'] = False
        with self.assertRaisesRegex(TradePlanError, 'BROKER_MARKET_ORDERS_UNSUPPORTED'):
            self.case.service.submit(self.case.entry(), self.case.profile)
        caps['stop_orders'] = False
        with self.assertRaisesRegex(TradePlanError, 'BROKER_STOP_ORDERS_UNSUPPORTED'):
            self.case.service.submit(dict(intent_id=str(uuid4()), confirmed=True, action='PLACE_PENDING',
                side='BUY', order_type='BUY_STOP', price=4202.), self.case.profile)
        self.assertEqual([], self.case.service.history())


if __name__ == '__main__':
    unittest.main()
