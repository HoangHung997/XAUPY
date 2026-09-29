"""First-release pure planning and execution lifecycle tests; never use MT5."""
from copy import deepcopy
from pathlib import Path
import subprocess
import shutil
import tempfile
import unittest
from uuid import uuid4
import test_broker_execution as fixtures
from xaupy_engine.broker_execution import IDENTITY
from xaupy_engine.strategy_engine import Bar
from xaupy_engine.trade_plan import TradePlanError, plan_entry, pending_cancellation_reason
from xaupy_engine.position_management import position_decision


class ReleaseWorkflowTests(fixtures.BrokerExecutionTests):
    def stop_signal(self, side='BUY', timeframe='M1', *, intrabar=False):
        self.profile['entry']['mode']='STOP_CONFIRM'
        self.profile['timeframes']['trigger']=timeframe
        span={'M1':60,'M5':300}[timeframe]
        now=self.snapshot['server_time']
        time=now//span*span-(0 if intrabar else span)
        candle=Bar(time,4200,4203,4197,4201,2)
        self.strategy.history={timeframe:[candle]}
        signal=dict(side=side,bar_time=time,sequence=1,trigger_bar=vars(candle))
        if intrabar:signal['tick_time_msc']=now*1000
        return signal

    def test_stop_confirm_is_anchored_to_signal_high_not_current_quote(self):
        signal=self.stop_signal()
        plan=plan_entry(self.profile,self.snapshot,self.strategy.history,'BUY',signal=signal)
        self.assertAlmostEqual(4203.3,plan['price'])
        self.assertEqual(signal['bar_time'],plan['signal_bar_time'])
        self.assertEqual('BUY_STOP',plan['order_type'])

    def test_sell_stop_uses_signal_low_without_double_spread(self):
        signal=self.stop_signal('SELL')
        plan=plan_entry(self.profile,self.snapshot,self.strategy.history,'SELL',signal=signal)
        self.assertAlmostEqual(4196.9,plan['price'])
        self.assertGreater(plan['sl'],plan['price'])

    def test_intrabar_signal_extreme_is_frozen_not_replaced_by_future_high(self):
        signal=self.stop_signal(intrabar=True)
        self.strategy.history['M1']=[Bar(signal['bar_time'],4200,4900,4000,4201,900)]
        plan=plan_entry(self.profile,self.snapshot,self.strategy.history,'BUY',signal=signal)
        self.assertAlmostEqual(4203.3,plan['price'])

    def test_stop_signal_timeframe_age_not_hardcoded_m1(self):
        signal=self.stop_signal(timeframe='M5')
        self.profile['entry']['pending_expiration_minutes']=30
        self.profile['entry']['max_signal_age_bars']=2
        plan=plan_entry(self.profile,self.snapshot,self.strategy.history,'BUY',signal=signal)
        self.assertEqual(signal['bar_time']+300+600,plan['expiration'])

    def test_missing_signal_bar_rejected_instead_of_inventing_pending(self):
        self.profile['entry']['mode']='STOP_CONFIRM'
        with self.assertRaisesRegex(TradePlanError,'STOP_CONFIRM_SIGNAL_BAR_REQUIRED'):
            plan_entry(self.profile,self.snapshot,{},'BUY')

    def test_dormant_percent_cannot_override_fixed_lot(self):
        self.profile['risk'].update(sizing_mode='FIXED_LOT',risk_percent=.01,fixed_lot=.1)
        plan=plan_entry(self.profile,self.snapshot,{},'BUY')
        self.assertEqual(.1,plan['volume'])

    def test_explicit_stop_outside_config_is_rejected_not_silently_clamped(self):
        for points in (1,100000):
            with self.subTest(points=points),self.assertRaisesRegex(TradePlanError,'EXPLICIT_SL_OUTSIDE_LIMITS'):
                plan_entry(self.profile,self.snapshot,{},'BUY',{'sl_points':points})

    def test_pending_cancels_for_opposite_direction(self):
        self.profile['entry']['cancel_on_direction_change']=True
        self.assertEqual('PENDING_DIRECTION_CHANGED',pending_cancellation_reason(self.profile,self.snapshot,{'direction':'SELL'},'BUY'))
        self.assertIsNone(pending_cancellation_reason(self.profile,self.snapshot,{'direction':'BOTH'},'BUY'))
        self.profile['entry']['cancel_on_direction_change']=False
        self.assertIsNone(pending_cancellation_reason(self.profile,self.snapshot,{'direction':'SELL'},'BUY'))

    def test_be_is_not_suppressed_by_a_larger_inactive_trailing_step(self):
        self.profile['management'].update(breakeven_enabled=True,breakeven_trigger_rr=0,trailing_enabled=False,trailing_step_price_units=10)
        position=dict(side='BUY',price_open=4198.,sl=4198.,tp=4206.)
        _,decision=position_decision(self.profile,self.snapshot,{},position,{'initial_risk':3}, {})
        self.assertIsNotNone(decision)
        self.assertAlmostEqual(4198.1,decision['sl'])

    def test_queue_reserves_cash_risk_not_only_position_count(self):
        self.profile['risk'].update(max_open_positions=4,max_lot=1,fixed_lot=.5)
        self.snapshot['guardian']['max_volume']=1
        self.enable()
        self.service.submit(self.entry(),self.profile)
        with self.assertRaisesRegex(TradePlanError,'RISK_BUDGET_EXCEEDED'):
            self.service.submit(self.entry(),self.profile)
        self.assertEqual(1,len(self.service.history()))

    def test_changed_confirmation_identity_rejected_without_queue(self):
        self.enable()
        identity={k:self.snapshot[k] for k in IDENTITY};identity['account_login']+=1
        with self.assertRaisesRegex(TradePlanError,'CONFIRMED_ACCOUNT_MISMATCH'):
            self.service.submit(self.entry(confirmed_identity=identity),self.profile)
        self.assertEqual([],self.service.history())

    def test_pending_price_only_move_cannot_increase_stop_distance(self):
        self.enable()
        self.snapshot['orders']=[dict(ticket=700,magic=991188,symbol='XAUUSD',type='BUY_STOP',volume_current=.01,
            price_open=4202.,sl=4199.,tp=4208.,expiration=self.snapshot['server_time']+600)]
        with self.assertRaisesRegex(TradePlanError,'PENDING_RISK_INCREASE'):
            self.service.submit(dict(intent_id=str(uuid4()),action='MODIFY_PENDING',ticket=700,price=4203.,confirmed=True),self.profile)

    def test_pending_result_requires_actual_order_and_protection(self):
        self.enable()
        self.service.submit(dict(intent_id=str(uuid4()),action='PLACE_PENDING',side='BUY',order_type='BUY_STOP',price=4203.,confirmed=True),self.profile)
        command=self.service.next_command(self.profile,self.snapshot['bridge_session_id'])
        good=self.broker_result(command,filled_volume=0,fill_price=0,deal_ticket=0,position_ticket=0)
        with self.assertRaisesRegex(TradePlanError,'ORDER_EVIDENCE_REQUIRED'):
            self.service.record_result({**good,'order_ticket':0},self.snapshot['bridge_session_id'])
        with self.assertRaisesRegex(TradePlanError,'PROTECTION_EVIDENCE_MISMATCH'):
            self.service.record_result({**good,'sl':command['sl']+1},self.snapshot['bridge_session_id'])
        self.assertTrue(self.service.record_result(good,self.snapshot['bridge_session_id'])['accepted'])

    def test_close_result_cannot_claim_success_for_a_different_ticket(self):
        self.enable()
        self.snapshot['positions']=[dict(ticket=700,magic=991188,symbol='XAUUSD',side='BUY',volume=.02,price_open=4198.,sl=4195.,tp=4206.)]
        self.service.submit(dict(intent_id=str(uuid4()),action='CLOSE_POSITION',ticket=700,confirmed=True),self.profile)
        command=self.service.next_command(self.profile,self.snapshot['bridge_session_id'])
        result={**{k:command[k] for k in (*IDENTITY,'intent_id','bridge_session_id')},'state':'CONFIRMED',
                'order_send_called':True,'broker_verified':True,'retcode':10009,'position_ticket':999,
                'order_ticket':501,'deal_ticket':502,'filled_volume':.02,'fill_price':4200.,'sl':4195.,'tp':4206.}
        with self.assertRaisesRegex(TradePlanError,'POSITION_EVIDENCE_MISMATCH'):
            self.service.record_result(result,self.snapshot['bridge_session_id'])
        result['position_ticket']=700
        self.assertTrue(self.service.record_result(result,self.snapshot['bridge_session_id'])['accepted'])

    def test_history_pages_are_stable_when_new_actions_arrive(self):
        # Isolated local-management records exercise the real SQLite ledger only.
        for i in range(7):
            self.service._queue(str(uuid4()),str(i),{'action':'MANAGEMENT_ENABLED','ticket':i})
        page=self.service.query_history({'limit':3})
        original=[x['id'] for x in self.service.history()]
        self.service._queue(str(uuid4()),'new',{'action':'MANAGEMENT_ENABLED','ticket':99})
        next_page=self.service.query_history({'limit':3,'offset':3,'snapshot_time':page['snapshot_time']})
        self.assertEqual(original[:6],[x['id'] for x in page['items']+next_page['items']])
        self.assertEqual(7,next_page['total'])
        self.assertTrue(next_page['has_more'])
        exact=self.service.query_history({'intent_id':original[-1]})
        self.assertEqual([original[-1]],[x['id'] for x in exact['items']])

    def test_history_rejects_invalid_cursor_and_limits(self):
        for payload in ({'limit':0},{'limit':501},{'offset':-1},{'snapshot_time':float('nan')},{'intent_id':'not-an-id'}):
            with self.subTest(payload=payload),self.assertRaises((TradePlanError,ValueError)):
                self.service.query_history(payload)


# Fixtures do not count as additional release test cases.
for _name in fixtures.BrokerExecutionTests.__dict__:
    if _name.startswith('test_'):
        setattr(ReleaseWorkflowTests,_name,None)


class CompiledEaRuleTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('g++'),'Pure MQL predicates compiled in the Linux CI job; MetaEditor compiles EA on Windows')
    def test_actual_mql_rules_compile_and_pass_isolated_predicates(self):
        root=Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory(prefix='xaupy-ea-rules-') as tmp:
            source=Path(tmp)/'rules.cpp';binary=Path(tmp)/'rules'
            source.write_text('''#include <string>\n#include <cmath>\n#include <algorithm>\nusing string=std::string;
#define MathIsValidNumber std::isfinite
#define MathMax std::max
#define MathMin std::min
#include "XAUPY_ExecutionRules.mqh"
int main(){
 if(!FullRulesSelfTest())return 1;
 for(int i=1;i<10000;i++){
   double shift=i*.01;string reason;
   if(FullPendingRiskRule(true,100,98,100+shift,98,reason))return 2;
   if(!FullPendingRiskRule(true,100,98,100+shift,98+shift,reason))return 3;
   if(FullCashRiskRule(100,shift,100,reason))return 4;
 }
 return 0;
}
''')
            subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror','-I',str(root/'mql5'),str(source),'-o',str(binary)],check=True,capture_output=True,timeout=20)
            subprocess.run([str(binary)],check=True,timeout=5)

if __name__=='__main__':unittest.main()
