import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from xaupy_engine.tick_collect import collect_quotes,parse_range
from xaupy_engine.backtest import load_historical_dataset,BacktestError
from test_tick_backtest import fixture


class TickCollectionTests(unittest.TestCase):
    def test_hour_boundary_and_equal_millisecond_quotes_are_preserved_once(self):
        start,end=parse_range('2026-09-25','2026-09-25')
        rows=[dict(time_msc=(start+3599)*1000,bid=2000,ask=2000.2),
              dict(time_msc=(start+3600)*1000,bid=2001,ask=2001.2),
              dict(time_msc=(start+3600)*1000,bid=2002,ask=2002.2)]
        class Provider:
            COPY_TICKS_ALL=0
            @staticmethod
            def copy_ticks_range(symbol,lower,upper,flags):
                return [r for r in rows if lower.timestamp()*1000<=r['time_msc']<=upper.timestamp()*1000]
        output=io.BytesIO();progress=[]
        report=collect_quotes(Provider,'XAUUSD',start,end,output,progress.append)
        actual=[json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(3,report['tick_count']);self.assertEqual([2000,2001,2002],[t['bid'] for t in actual])
        self.assertEqual([False,True,True],[t['continuous'] for t in actual])
        self.assertEqual(24,len(progress));self.assertEqual(hashlib.sha256(output.getvalue()).hexdigest(),report['sha256'])

    def test_invalid_quote_breaks_continuity_without_fabricating_prices(self):
        start,end=parse_range('2026-09-25','2026-09-25')
        class Provider:
            COPY_TICKS_ALL=0
            @staticmethod
            def copy_ticks_range(symbol,lower,upper,flags):
                return [dict(time_msc=start*1000+i,bid=price,ask=2001) for i,price in enumerate((2000,0,2000))]
        output=io.BytesIO();report=collect_quotes(Provider,'XAUUSD',start,end,output,lambda _:None)
        self.assertEqual(1,report['invalid_quotes']);self.assertEqual(2,report['tick_count'])
        self.assertFalse(json.loads(output.getvalue().splitlines()[-1])['continuous'])

    def test_tick_sidecar_hash_and_path_are_checked(self):
        _,data,_=fixture()
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'data.json';sidecar=Path(root)/'ticks.jsonl'
            content=''.join(json.dumps(t)+'\n' for t in data.ticks).encode();sidecar.write_bytes(content)
            doc=dict(schema_version=1,timeframe='M1',input_model='REAL_TICKS',**data.metadata.public(),
                bars=[vars(b) for b in data.bars],ticks_file='ticks.jsonl',ticks_sha256=hashlib.sha256(content).hexdigest())
            path.write_text(json.dumps(doc));self.assertEqual(6,len(load_historical_dataset(path).ticks))
            sidecar.write_bytes(content+b'\n')
            with self.assertRaisesRegex(BacktestError,'integrity'):load_historical_dataset(path)
            doc['ticks_file']='../escape.jsonl';path.write_text(json.dumps(doc))
            with self.assertRaisesRegex(BacktestError,'adjacent'):load_historical_dataset(path)
