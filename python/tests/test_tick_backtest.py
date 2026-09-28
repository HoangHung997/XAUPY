from copy import deepcopy
from datetime import datetime,timezone
import json
from pathlib import Path
import tempfile
import unittest
from xaupy_engine.backtest import HistoricalDataset,DatasetMetadata,load_historical_dataset,BacktestError
from xaupy_engine.tick_backtest import tick_dataset,TickBacktestEngine
from xaupy_engine.strategy_engine import Bar
from test_intrabar_strategy import START,engine_for,price_for,close_first_bar


def fixture():
    strategy=engine_for()
    cfg=deepcopy(strategy.profile)
    cfg['stop_loss'].update(mode='FIXED',fixed_price_units=3)
    cfg['take_profit'].update(mode='FIXED',fixed_price_units=6)
    cfg['risk'].update(fixed_lot=.01,sizing_mode='FIXED_LOT')
    cfg['sessions'].update(session1_enabled=False,session2_enabled=False,weekend_close_enabled=False,
        **{day:True for day in ('monday','tuesday','wednesday','thursday','friday','saturday','sunday')})
    peak=price_for(strategy,2.5001);retreat=price_for(strategy,2.2)
    history=list(strategy.history['M1'])
    close_first_bar(strategy,retreat);current=price_for(strategy,2.2)
    history.append(Bar(START,100,max(100,peak),min(100,retreat),retreat,100))
    ticks=[dict(time_msc=START*1000+offset,bid=bid,ask=bid+.2) for offset,bid in
        [(1000,100),(10000,peak),(50000,retreat),(61000,current),(62000,current),(63000,current-8)]]
    metadata=DatasetMetadata('XAUUSD',.01,.01,1,.01,100,.01,0,0,0)
    base=HistoricalDataset(Path('fixture.json'),'fixture',metadata,tuple(history))
    return cfg,tick_dataset(base,dict(ticks=ticks)),datetime.fromtimestamp(START,timezone.utc).date().isoformat()


class TickReplayTests(unittest.TestCase):
    def test_compact_tick_storage_preserves_quotes_views_and_replay_hash(self):
        from xaupy_engine.tick_tape import TickTape
        from dataclasses import replace
        cfg,data,date=fixture();tape=TickTape()
        for tick in data.ticks:tape.append(tick)
        tape.seal()
        self.assertEqual(list(data.ticks),list(tape))
        first=data.ticks[0]['time_msc'];second=data.ticks[1]['time_msc']
        self.assertEqual([data.ticks[0]],list(tape.between(first,second)))
        engine=TickBacktestEngine(cfg,initial_balance=1000,spread_pips=0,commission_per_lot=7)
        self.assertEqual(engine.run(data,from_date=date,to_date=date)['result_hash'],
            engine.run(replace(data,ticks=tape),from_date=date,to_date=date)['result_hash'])
        with self.assertRaisesRegex(ValueError,'immutable'):tape.append(data.ticks[0])

    def test_optimizer_uses_real_ticks_for_intrabar_candidate(self):
        from xaupy_engine.optimizer import OptimizerEngine,ParameterRange
        cfg,data,date=fixture()
        engine=OptimizerEngine(cfg,initial_balance=1000,spread_pips=20,commission_per_lot=7,min_trades=1,max_workers=1)
        result=engine.run_sweep(data,from_date=date,to_date=date,parameter_ranges=(ParameterRange('risk.fixed_lot','float',(.01,)),))
        self.assertEqual('OBSERVED_BID_ASK_NEXT_TICK_V1',result['backtest_model'])
        self.assertEqual(1,result['candidates'][0]['metrics']['total_trades'])

    def test_prepared_candidate_patches_current_profile_and_rejects_tampering(self):
        from xaupy_engine.optimizer import OptimizerEngine,ParameterRange,prepare_candidate,OptimizerError
        cfg,data,date=fixture();current=deepcopy(cfg);current['profile']['name']='Current user profile'
        engine=OptimizerEngine(cfg,initial_balance=1000,spread_pips=20,commission_per_lot=7,min_trades=1,max_workers=1)
        result=engine.run_sweep(data,from_date=date,to_date=date,parameter_ranges=(ParameterRange('risk.fixed_lot','float',(.01,)),))
        prepared=prepare_candidate(result,current,0)
        self.assertEqual(current,prepared['expected_profile'])
        self.assertEqual('Current user profile',prepared['profile']['profile']['name'])
        self.assertEqual(current['execution'],prepared['profile']['execution'])
        self.assertEqual(current['risk']['max_lot'],prepared['profile']['risk']['max_lot'])
        self.assertTrue(prepared['baseline_changed'])
        result['candidates'][0]['parameters']['risk.fixed_lot']=10
        with self.assertRaisesRegex(OptimizerError,'integrity'):prepare_candidate(result,current,0)
    def test_real_intrabar_peak_opens_on_next_quote_and_has_net_pl(self):
        cfg,data,date=fixture()
        engine=TickBacktestEngine(cfg,initial_balance=1000,spread_pips=999,commission_per_lot=7)
        result=engine.run(data,from_date=date,to_date=date)
        self.assertEqual('OBSERVED_BID_ASK_NEXT_TICK_V1',result['model'])
        self.assertEqual(1,result['metrics']['total_trades'],result['skipped_signals'])
        trade=result['trades'][0]
        self.assertEqual(START+62,trade['entry_time'])
        self.assertEqual('TP',trade['exit_reason'])
        self.assertAlmostEqual(.07,trade['commission'])
        self.assertAlmostEqual(trade['gross_pl']-.07,trade['net_pl'],places=5)
        self.assertAlmostEqual(1000+trade['net_pl'],result['metrics']['final_balance'])
        self.assertEqual(result['metrics']['final_balance'],result['equity_curve'][-1]['equity'])
        self.assertFalse(result['broker_execution_requested'])
        self.assertEqual(result['result_hash'],engine.run(data,from_date=date,to_date=date)['result_hash'])

    def test_last_signal_cannot_fill_without_a_later_quote(self):
        cfg,data,date=fixture()
        limited=tick_dataset(data,{'ticks':list(data.ticks[:4])})
        result=TickBacktestEngine(cfg,initial_balance=1000,spread_pips=0,commission_per_lot=7).run(limited,from_date=date,to_date=date)
        self.assertEqual(0,result['metrics']['total_trades'])
        self.assertEqual(1,result['skipped_signals']['UNEXECUTED_INTENT_AT_END'])

    def test_gap_invalidates_signal_delivery(self):
        cfg,data,date=fixture();ticks=deepcopy(list(data.ticks));ticks[4]['continuous']=False
        limited=tick_dataset(data,{'ticks':ticks})
        result=TickBacktestEngine(cfg,initial_balance=1000,spread_pips=0,commission_per_lot=7).run(limited,from_date=date,to_date=date)
        self.assertEqual(0,result['metrics']['total_trades'])
        self.assertEqual(1,result['skipped_signals']['ENTRY_TICK_GAP_OR_EXPIRED'])

    def test_future_closed_bar_not_visible_early(self):
        cfg,data,date=fixture()
        from dataclasses import replace
        changed=replace(data,bars=(*data.bars,Bar(START+120,10000,10001,9999,10000)))
        engine=TickBacktestEngine(cfg,initial_balance=1000,spread_pips=0,commission_per_lot=7)
        self.assertEqual(engine.run(data,from_date=date,to_date=date)['trades'],engine.run(changed,from_date=date,to_date=date)['trades'])

    def test_tick_dataset_file_is_validated_by_app_loader(self):
        cfg,data,date=fixture()
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'ticks.json'
            doc=dict(schema_version=1,timeframe='M1',input_model='REAL_TICKS',**data.metadata.public(),bars=[vars(b) for b in data.bars],ticks=list(data.ticks))
            path.write_text(json.dumps(doc));read=load_historical_dataset(path)
            self.assertEqual(6,read.inspect_payload()['tick_count'])
            doc['ticks'][2]['ask']=0;path.write_text(json.dumps(doc))
            with self.assertRaises(BacktestError):load_historical_dataset(path)
