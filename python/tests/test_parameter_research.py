from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import threading
import unittest
from unittest.mock import patch
from test_tick_backtest import fixture
from xaupy_engine.optimizer import OptimizerEngine, OptimizerError, OptimizationCancelled, prepare_candidate
from xaupy_engine.parameter_research import research_candidates, research_segments, run_research


def dataset15():
    cfg,data,_=fixture()
    ticks=tuple({**t,'time_msc':t['time_msc']+day*86400000,'continuous':False if i==0 else True}
        for day in range(15) for i,t in enumerate(data.ticks))
    data=replace(data,ticks=ticks)
    dates=[datetime.fromtimestamp(t//1000,timezone.utc).date().isoformat() for t in (ticks[0]['time_msc'],ticks[-1]['time_msc'])]
    return cfg,data,dates


class ResearchTests(unittest.TestCase):
    def test_process_workers_preserve_results_and_holdout_selection(self):
        cfg,data,dates=dataset15()
        def run(workers):
            engine=OptimizerEngine(cfg,initial_balance=1000,spread_pips=20,commission_per_lot=7,min_trades=20,max_workers=workers)
            return run_research(engine,data,from_date=dates[0],to_date=dates[1])
        serial=run(1);parallel=run(2)
        self.assertEqual(serial['optimizer_hash'],parallel['optimizer_hash'])
        self.assertEqual(serial['research'],parallel['research'])
        self.assertEqual(2,parallel['workers_used'])

    def test_disabled_indicators_permissions_and_risk_are_preserved(self):
        cfg,_,_=fixture();before=deepcopy(cfg)
        candidates=research_candidates(cfg)
        self.assertLessEqual(len(candidates),10)
        self.assertEqual(before,cfg)
        for c in candidates:
            self.assertFalse(any(k.startswith(('risk.','execution.','sessions.','stop_loss.')) for k in c))
            if not cfg['pullback']['rsi_enabled']:self.assertFalse(any(k.startswith('pullback.rsi') for k in c))

    def test_dates_split_chronologically_and_short_history_rejected(self):
        cfg,data,dates=dataset15();parts=research_segments(data,*dates)
        self.assertLess(parts['train'][1],parts['validation'][0]);self.assertLess(parts['validation'][1],parts['test'][0])
        _,short,day=fixture()
        with self.assertRaisesRegex(OptimizerError,'15'):research_segments(short,day,day)

    def test_real_tick_research_reports_no_qualified_result_and_cancellable(self):
        cfg,data,dates=dataset15()
        engine=OptimizerEngine(cfg,initial_balance=1000,spread_pips=20,commission_per_lot=7,min_trades=20)
        before=deepcopy(cfg);progress=[]
        result=run_research(engine,data,from_date=dates[0],to_date=dates[1],progress=lambda *x:progress.append(x))
        self.assertFalse(result['research']['qualified']);self.assertEqual(before,cfg)
        self.assertEqual('OBSERVED_BID_ASK_NEXT_TICK_V1',result['backtest_model'])
        self.assertEqual(progress[-1][0],progress[-1][1])
        selected=result['research']['selected_index']
        self.assertEqual(selected,result['research']['stages']['test']['index'])
        self.assertEqual(selected,result['research']['stages']['cost_stress']['index'])
        candidate=prepare_candidate(result,cfg,selected)
        self.assertFalse(candidate['qualified']);self.assertEqual(cfg['execution'],candidate['profile']['execution'])
        self.assertTrue(candidate['analysis_context_matches'])
        changed=deepcopy(cfg);changed['risk']['max_trades_per_day']+=1
        changed_candidate=prepare_candidate(result,changed,selected)
        self.assertFalse(changed_candidate['analysis_context_matches']);self.assertFalse(changed_candidate['qualified'])
        self.assertIn('risk.max_trades_per_day',[row['path'] for row in changed_candidate['context_changes']])
        event=threading.Event();event.set()
        with self.assertRaises(OptimizationCancelled):run_research(engine,data,from_date=dates[0],to_date=dates[1],cancel_event=event)

    def test_holdout_results_cannot_change_selected_parameters(self):
        cfg,data,dates=dataset15();engine=OptimizerEngine(cfg,initial_balance=1000,spread_pips=20,commission_per_lot=7,min_trades=1)
        selected=[]
        for test_profit in (-1000,1000):
            def evaluate(index,parameters,dataset,start,end):
                test=start==research_segments(data,*dates)['test'][0]
                return dict(index=index,parameters=parameters,eligible=True,score=index,
                    metrics=dict(total_trades=25,net_profit=test_profit if test else index+1,max_drawdown_usd=1,max_drawdown_pct=1),result_hash='fixture')
            with patch.object(engine,'_evaluate_candidate',side_effect=evaluate):
                result=run_research(engine,data,from_date=dates[0],to_date=dates[1])
            selected.append(result['research']['selected_index'])
        self.assertEqual(selected[0],selected[1])
