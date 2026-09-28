import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from xaupy_engine.user_library import UserLibrary
from xaupy_engine.config_schema import default_profile
from xaupy_engine.backtest import load_historical_dataset, BacktestError
from xaupy_engine.trade_plan import entry_guard, TradePlanError


class UserLibraryTests(unittest.TestCase):
    def test_tick_history_catalog_and_profile_library_are_separate(self):
        with tempfile.TemporaryDirectory() as root:
            store=UserLibrary(Path(root));directory=Path(root)/'market-history'/'quotes';directory.mkdir(parents=True)
            path=directory/'ticks-dataset.json';path.write_text('{}')
            (directory/'manifest.json').write_text(json.dumps(dict(symbol='XAUUSD',status='COMPLETE',timeframes={},
                ticks=dict(path=str(path),tick_count=12,first_time_msc=1800000000000,last_time_msc=1800000060000,sha256='test'))))
            store.save_profile('one',default_profile())
            self.assertEqual('TICKS',store.history_catalog()[0]['timeframe'])
            self.assertEqual(1,len(store.profile_list()))
            store.save_startup_profile(default_profile());store.clear_startup_profile()
            self.assertIsNone(store.startup_profile())
    def test_startup_default_is_persisted_without_touching_running_profile(self):
        with tempfile.TemporaryDirectory() as root:
            store=UserLibrary(Path(root));profile=default_profile();profile['pullback']['rsi_period']=9
            saved=store.save_startup_profile(profile)
            self.assertEqual(9,UserLibrary(Path(root)).startup_profile()['pullback']['rsi_period'])
            self.assertFalse((Path(root)/'runtime-v1.json').exists())
            (store.profiles/saved['id']/(saved['revision']+'.json')).write_text('{}')
            with self.assertRaises((ValueError,KeyError)):store.startup_profile()

    def test_revisions_persist_and_never_change_active_permissions(self):
        with tempfile.TemporaryDirectory() as root:
            store=UserLibrary(Path(root)); profile=default_profile()
            a=store.save_profile('one',profile); profile['pullback']['rsi_period']=8
            b=store.save_profile('one',profile)
            self.assertNotEqual(a['revision'],b['revision'])
            self.assertEqual(2,len(store.profile_list()))
            self.assertEqual(8,store.profile_get('one',b['revision'])['pullback']['rsi_period'])
            self.assertFalse((Path(root)/'runtime-v1.json').exists())
            with self.assertRaises(ValueError): store.save_profile('../escape',profile)
            path=store.profiles/'one'/(a['revision']+'.json')
            doc=json.loads(path.read_text()); doc['profile']['pullback']['rsi_period']=15; path.write_text(json.dumps(doc))
            with self.assertRaisesRegex(ValueError,'integrity'): store.profile_get('one',a['revision'])

    def test_calendar_explicit_coverage_timezone_and_symbol_filter(self):
        with tempfile.TemporaryDirectory() as root:
            store=UserLibrary(Path(root))
            doc=dict(coverage_start_utc='2026-09-28T00:00:00Z',coverage_end_utc='2026-09-29T00:00:00Z',events=[
                dict(timestamp_utc='2026-09-28T12:00:00Z',currency='USD',impact='HIGH',title='Test release'),
                dict(timestamp_utc='2026-09-28T12:00:00Z',currency='JPY',impact='HIGH',title='JPY release')])
            store.save_calendar(doc)
            from datetime import datetime
            now=int(datetime.fromisoformat('2026-09-28T12:00:00+00:00').timestamp())+10800
            snapshot=dict(server_time=now,server_utc_offset_seconds=10800,symbol='XAUUSD.a',currency_base='XAU',currency_profit='USD')
            calendar=store.merge_calendar(snapshot)['calendar']
            self.assertTrue(calendar['available']); self.assertEqual(1,len(calendar['events']))
            self.assertEqual(now,calendar['events'][0]['time'])
            self.assertNotIn('calendar',store.merge_calendar({**snapshot,'server_time':now+86400}))
            doc['events'][0]['timestamp_utc']='2026-09-28T12:00:00'
            with self.assertRaisesRegex(ValueError,'timezone'):store.save_calendar(doc)
            self.assertEqual(2,len(UserLibrary(Path(root)).calendar['events']))

    def test_archive_can_load_directly_and_rejects_changed_csv(self):
        with tempfile.TemporaryDirectory() as root:
            store=UserLibrary(Path(root)); directory=Path(root)/'market-history'/'test'; directory.mkdir(parents=True)
            path=directory/'XAUUSD_M1.csv'
            path.write_text('time,open,high,low,close,tick_volume,spread,real_volume\n1800000000,2000,2002,1999,2001,10,20,0\n1800000060,2001,2003,2000,2002,10,20,0\n')
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            meta=dict(point=.01,trade_tick_size=.01,trade_tick_value=1,volume_min=.01,volume_max=10,volume_step=.01)
            manifest=dict(symbol='XAUUSD',symbol_metadata=meta,timeframes=dict(M1=dict(path=str(path),sha256=digest,rows=2)))
            (directory/'manifest.json').write_text(json.dumps(manifest))
            self.assertEqual(1,len(store.history_catalog()))
            data=load_historical_dataset(str(path))
            self.assertEqual(2,len(data.bars)); self.assertEqual('XAUUSD',data.metadata.symbol)
            path.write_text(path.read_text()+'1800000120,2001,2003,2000,2002,10,20,0\n')
            with self.assertRaisesRegex(BacktestError,'unchanged'): load_historical_dataset(str(path))
