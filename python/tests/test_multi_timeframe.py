from copy import deepcopy
import unittest
from xaupy_engine.config_schema import default_profile,normalized_profile,validate_profile
from xaupy_engine.strategy_engine import Bar
from test_intrabar_strategy import START,engine_for,baseline,batch,price_for,close_first_bar


def configured(frames='M3',logic='AND',seed=True):
    engine=engine_for();profile=deepcopy(engine.profile)
    profile['mtf']=dict(pullback_timeframes=frames,trigger_timeframes='',logic=logic)
    engine.set_profile(profile)
    if seed:
        closes=[b.close for b in engine.history['M1']]
        engine.history['M3']=[Bar(START-(len(closes)-i)*180,value,value,value,value) for i,value in enumerate(closes)]
    return engine


def observed_reversal(engine):
    baseline(engine);peak=price_for(engine,2.5001);retreat=price_for(engine,2.2)
    engine.ingest_tick_batch(batch(2,[(10000,peak),(50000,retreat)]))
    close_first_bar(engine,retreat)
    return engine.ingest_tick_batch(batch(3,[(61000,price_for(engine,2.2))]))


class MultiTimeframeTests(unittest.TestCase):
    def test_old_profile_migrates_without_enabling_additional_signals(self):
        profile=default_profile();profile.pop('mtf')
        normalized=normalized_profile(profile)
        self.assertEqual('',normalized['mtf']['pullback_timeframes'])
        self.assertEqual([],validate_profile(profile))
        profile['mtf']=dict(pullback_timeframes='M3,M3',trigger_timeframes='',logic='AND')
        self.assertTrue(validate_profile(profile))

    def test_two_real_timeframes_latch_and_confirm_before_one_primary_signal(self):
        engine=configured();result=observed_reversal(engine)
        self.assertEqual(1,result['signal_sequence'],result)
        self.assertEqual('TRIGGERED_SELL',engine.mtf.engines['M3/M1'].state)
        self.assertTrue(result['multi_timeframe']['confirmations'][0]['passed'])
        self.assertFalse(engine.mtf.permits('SELL',START+61),'Consumed child signal cannot authorize another primary signal')
        sequence=engine.mtf.sequence
        engine.ingest_tick_batch(batch(3,[(61000,price_for(engine,2.2))]))
        self.assertEqual(sequence,engine.mtf.sequence,'Duplicate transport must not create extra auxiliary observations')

    def test_missing_secondary_history_blocks_primary_without_invented_values(self):
        engine=configured(seed=False);result=observed_reversal(engine)
        self.assertEqual(0,result['signal_sequence'])
        self.assertEqual('WAIT_MTF_CONFIRMATION',result['blocked_reason'])

    def test_all_and_any_are_distinct_and_stream_gap_clears_confirmations(self):
        strict=configured('M3,M5','AND');self.assertEqual(0,observed_reversal(strict)['signal_sequence'])
        any_one=configured('M3,M5','OR');self.assertEqual(1,observed_reversal(any_one)['signal_sequence'])
        any_one.ingest_tick_batch(batch(5,[(62000,100)],complete=False))
        self.assertTrue(all(child.last_signal is None for child in any_one.mtf.engines.values()))
        self.assertFalse(any_one.mtf.permits('SELL',START+62))
