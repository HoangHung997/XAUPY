from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from xaupy_engine.config_schema import default_profile
from xaupy_engine.position_management import position_decision
from xaupy_engine.strategy_engine import Bar
from test_demo_once import NOW


class PositionManagementTests(unittest.TestCase):
    def setUp(self):
        self.profile=default_profile()
        self.profile['management'].update(breakeven_enabled=False,trailing_enabled=False,sl_tighten_mode='OFF')
        self.snapshot=dict(bid=4203.,ask=4203.2,server_time=NOW,point=.01,tick_size=.01,stops_level=10,freeze_level=10)
        self.position=dict(side='BUY',price_open=4200.,sl=4197.,tp=4220.,volume=.04)
        self.state=dict(initial_risk=3.,original_tp=4206.,entry_z=-2.,entry_rsi=30.)

    def decision(self,metrics=None,**kw):
        return position_decision(self.profile,self.snapshot,kw.pop('history',{}),self.position,self.state,metrics or {},**kw)

    def test_breakeven_waits_for_rr_and_never_widens_existing_stop(self):
        self.profile['management']['breakeven_enabled']=True
        self.snapshot['bid']=4202.9
        self.assertIsNone(self.decision()[1])
        self.snapshot['bid']=4203.
        self.assertEqual(4200.1,self.decision()[1]['sl'])
        self.position['sl']=4201.
        self.assertIsNone(self.decision()[1])

    def test_partial_is_one_intent_per_position_not_once_per_tick(self):
        self.profile['management']['partial_close_enabled']=True
        self.assertEqual('PARTIAL_CLOSE',self.decision()[1]['action'])
        self.state['partial_intent']='already-dispatched'
        self.assertIsNone(self.decision()[1])

    def test_dynamic_latches_peak_and_exits_on_reversal_inside_same_candle(self):
        self.profile['take_profit']['mode']='ZRSI_DYNAMIC'
        self.snapshot.update(bid=4205.8,ask=4206.)
        state,action=self.decision({'z':2.6,'rsi':76.})
        self.assertTrue(state['extended'])
        self.assertIsNone(action)
        self.assertNotIn('extended',self.state)
        self.state=state
        state,action=self.decision({'z':2.0,'rsi':71.})
        self.assertEqual('ZRSI_REVERSAL',action['reason'])
        self.assertEqual(2.6,state['peak_z'])

    def test_dynamic_extension_needs_enabled_indicator_values_and_respects_timeout(self):
        self.profile['take_profit']['mode']='ZRSI_DYNAMIC'
        self.snapshot.update(bid=4206.,ask=4206.2)
        self.assertEqual('ORIGINAL_TP',self.decision({'z':2.})[1]['reason'])
        self.state.update(extended=True,extension_time=NOW-901,peak_z=2.,peak_rsi=72.)
        self.assertEqual('EXTENSION_TIMEOUT',self.decision({'z':2.,'rsi':72.})[1]['reason'])

    def test_sell_stop_has_correct_ask_side_freeze_and_rounding(self):
        self.position.update(side='SELL',price_open=4206.,sl=4209.)
        self.profile['management'].update(breakeven_enabled=True,breakeven_offset_price_units=.103)
        self.snapshot.update(bid=4202.8,ask=4203.)
        self.assertEqual(4205.9,self.decision()[1]['sl'])
        self.snapshot['freeze_level']=400
        self.assertIsNone(self.decision()[1])

    def test_trailing_uses_only_closed_bars_and_manual_mode_requires_manual_choice(self):
        self.profile['management'].update(trailing_enabled=True,trailing_structure_lookback=2)
        self.profile['stop_loss'].update(structure_timeframe='M1',structure_buffer_price_units=.1)
        history={'M1':[Bar(NOW-120,4200.,4201.,4199.,4200.,1),Bar(NOW-60,4200.,4202.,4200.,4201.,1),Bar(NOW,4200.,4250.,4150.,4200.,1)]}
        self.assertEqual(4198.9,self.decision(history=history)[1]['sl'])
        self.assertIsNone(self.decision(history=history,automatic=False)[1])
        self.state['manual_trailing']=True
        self.assertEqual(4198.9,self.decision(history=history,automatic=False)[1]['sl'])

    def test_weekend_cutoff_uses_terminal_session_end(self):
        self.profile['sessions'].update(weekend_close_enabled=True,weekend_close_minutes_before=30)
        self.snapshot['weekend_session_end']=NOW+1700
        self.assertEqual('WEEKEND_CLOSE',self.decision()[1]['reason'])


if __name__=='__main__': unittest.main()
