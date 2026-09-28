from dataclasses import replace
import unittest
from xaupy_engine.indicator_comparison import compare_indicators
from xaupy_engine.strategy_engine import Bar


class IndicatorComparisonTests(unittest.TestCase):
    def test_native_comparison_aligns_closed_bar_and_reports_mismatch(self):
        bars=[Bar(1800000000+i*60,100+i,101+i,99+i,100+i) for i in range(60)]
        last=bars[-1].time
        # Rising closes yield Wilder RSI=100 independently of seed. Z20 is
        # (19 - 9.5) / sqrt((20^2 - 1)/12), population standard deviation.
        expected_z=9.5/((20*20-1)/12)**.5
        probe=dict(timeframe='M1',bar_time=last,RSI7=100,RSI14=100,RSI20=50,Z20=expected_z,EMA20=None)
        result=compare_indicators({'point':.01,'indicator_probes':[probe]},dict(M1=bars+[Bar(last+60,999,1000,998,999)]))
        statuses={row['indicator']:row['status'] for row in result['rows']}
        self.assertEqual({'RSI7':'PASS','RSI14':'PASS','RSI20':'DIFFERENT','Z20':'PASS','EMA20':'WARMUP'},statuses)
        self.assertFalse(compare_indicators({'indicator_probes':[{**probe,'bar_time':last+1}]},dict(M1=bars))['available'])
