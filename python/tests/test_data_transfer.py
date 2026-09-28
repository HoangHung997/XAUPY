import hashlib
import json
from pathlib import Path
import tempfile
import sqlite3
from contextlib import closing
import unittest
import zipfile
from xaupy_engine.data_transfer import DataTransfer
from xaupy_engine.config_schema import default_profile
from xaupy_engine.user_library import UserLibrary
from xaupy_engine.backtest import load_historical_dataset


class DataTransferTests(unittest.TestCase):
    def test_actual_tick_and_bar_results_round_trip_and_reject_inner_tampering(self):
        from copy import deepcopy
        from xaupy_engine.backtest import BacktestEngine, BacktestRepository
        from xaupy_engine.tick_backtest import TickBacktestEngine
        from test_tick_backtest import fixture
        cfg, data, date = fixture()
        cfg['profile']['name'] = 'Nghiên cứu dữ liệu thật'
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            repo = BacktestRepository(root/'bt')
            originals = []
            for engine_type in (BacktestEngine, TickBacktestEngine):
                profile = deepcopy(cfg)
                if engine_type is BacktestEngine:
                    profile['trigger']['confirm_closed_bar'] = True
                engine = engine_type(profile, initial_balance=1000, spread_pips=20, commission_per_lot=7)
                originals.append(repo.save(engine.run(data, from_date=date, to_date=date)))
            exporter = DataTransfer(root/'source', root/'logs', root/'bt', root/'opt')
            self.addCleanup(exporter.close)
            archive = root/'bundle.zip'; exporter.export(archive)
            importer = DataTransfer(root/'target', root/'tlogs', root/'tbt', root/'topt')
            self.addCleanup(importer.close)
            importer.import_archive(archive)
            restored = BacktestRepository(root/'tbt')
            by_hash = {r['result_hash']: restored.get(r['run_id']) for r in restored.history()}
            self.assertEqual(2, len(by_hash))
            for original in originals:
                result = by_hash[original['result_hash']]
                self.assertNotEqual(original['run_id'], result['run_id'])
                self.assertEqual(original['trades'], result['trades'])
                self.assertEqual(original['metrics'], result['metrics'])
            # Even a freshly repacked archive with valid outer hashes must not
            # turn edited P/L into an authenticated research result.
            changed = deepcopy(originals[1]); changed['metrics']['net_profit'] += 123
            (root/'bt'/(changed['run_id']+'.json')).write_text(json.dumps(changed), encoding='utf-8')
            forged = root/'forged.zip'; exporter.export(forged)
            with self.assertRaisesRegex(ValueError, 'Backtest result integrity'):
                importer.import_archive(forged)
            self.assertEqual(2, len(restored.history()))

    def test_open_wal_database_exports_a_consistent_readable_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);state=root/'source'
            db_path=state/'broker-history'/'run'/'broker-history.sqlite'
            db_path.parent.mkdir(parents=True)
            with closing(sqlite3.connect(db_path)) as db:
                db.execute('PRAGMA journal_mode=WAL')
                db.execute('CREATE TABLE deals(ticket INTEGER PRIMARY KEY, volume REAL)')
                db.execute('INSERT INTO deals VALUES(42, .01)');db.commit()
                exporter=DataTransfer(state,root/'logs',root/'bt',root/'opt');self.addCleanup(exporter.close)
                archive=root/'bundle.zip';exporter.export(archive)
                importer=DataTransfer(root/'target',root/'t-logs',root/'t-bt',root/'t-opt');self.addCleanup(importer.close)
                result=importer.import_archive(archive)
                imported=Path(result['import_directory'])/'broker-history'/'run'/'broker-history.sqlite'
                with closing(sqlite3.connect(imported.resolve().as_uri()+'?mode=ro',uri=True)) as snapshot:
                    self.assertEqual(('ok',),snapshot.execute('PRAGMA integrity_check').fetchone())
                    self.assertEqual([(42,.01)],snapshot.execute('SELECT * FROM deals').fetchall())
                self.assertEqual([(42,.01)],db.execute('SELECT * FROM deals').fetchall())

    def test_portable_history_profiles_and_logs_round_trip_without_permissions(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source';target=root/'target';source.mkdir()
            UserLibrary(source).save_profile('saved',default_profile())
            (source/'runtime-v1.json').write_text('DO NOT EXPORT')
            (source/'demo-once-v1.json').write_text('SPENT')
            directory=source/'market-history'/'data';directory.mkdir(parents=True)
            path=directory/'XAUUSD_M1.csv'
            path.write_text('time,open,high,low,close,tick_volume,spread,real_volume\n1800000000,2000,2002,1999,2001,10,20,0\n1800000060,2001,2003,2000,2002,10,20,0\n')
            meta=dict(point=.01,trade_tick_size=.01,trade_tick_value=1,volume_min=.01,volume_max=10,volume_step=.01)
            manifest=dict(symbol='XAUUSD',symbol_metadata=meta,timeframes=dict(M1=dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),rows=2)))
            (directory/'manifest.json').write_text(json.dumps(manifest))
            logs=root/'logs';logs.mkdir();(logs/'journal-v1.jsonl').write_text('{"message":"original"}\n')
            exporter=DataTransfer(source,logs,root/'backtests',root/'optimizer');self.addCleanup(exporter.close)
            archive=root/'bundle.zip';exporter.export(archive)
            importer=DataTransfer(target,root/'target-logs',root/'target-bt',root/'target-opt');self.addCleanup(importer.close)
            result=importer.import_archive(archive)
            library=UserLibrary(target)
            self.assertEqual('saved',library.profile_list()[0]['id'])
            imported=Path(library.history_catalog()[0]['path'])
            self.assertTrue(imported.is_relative_to(target));self.assertEqual(2,len(load_historical_dataset(imported).bars))
            self.assertFalse((target/'runtime-v1.json').exists());self.assertFalse((target/'demo-once-v1.json').exists())
            self.assertFalse((root/'target-logs'/'journal-v1.jsonl').exists())
            self.assertTrue((Path(result['import_directory'])/'logs'/'journal-v1.jsonl').exists())
            second=root/'second.zip';importer.export(second)
            third=DataTransfer(root/'third',root/'third-logs',root/'third-bt',root/'third-opt');self.addCleanup(third.close)
            third.import_archive(second)
            again=UserLibrary(root/'third').history_catalog()
            self.assertEqual(2,len(load_historical_dataset(again[0]['path']).bars))
            self.assertTrue(any((root/'third'/'imports').glob('*/logs/*/journal-v1.jsonl')))
            with self.assertRaisesRegex(ValueError,'already exists'):exporter.export(archive)

    def test_imported_broker_reports_are_queryable_only_for_the_recorded_account(self):
        from xaupy_engine.broker_history import write_report
        from xaupy_engine.broker_history_jobs import BrokerHistoryJobs
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source';path=source/'broker-history'/'run'/'broker-history.sqlite'
            path.parent.mkdir(parents=True)
            identity=dict(account_login=123,account_server='Demo',magic=1)
            write_report(path,identity,[])
            exporter=DataTransfer(source,root/'logs',root/'bt',root/'opt');self.addCleanup(exporter.close)
            archive=root/'bundle.zip';exporter.export(archive)
            importer=DataTransfer(root/'target',root/'tlogs',root/'tbt',root/'topt');self.addCleanup(importer.close)
            importer.import_archive(archive)
            jobs=BrokerHistoryJobs(root/'target')
            report=jobs.query(identity)
            self.assertEqual(0,report['total']);self.assertTrue(report['report_id'].startswith('import-'))
            self.assertEqual(report,jobs.query(identity,report_id=report['report_id']))
            with self.assertRaisesRegex(ValueError,'No history'):jobs.query({**identity,'account_login':456})

    def test_integrity_and_traversal_fail_without_publishing_data(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);target=root/'state';transfer=DataTransfer(target,root/'logs',root/'bt',root/'opt');self.addCleanup(transfer.close)
            for name,sha in [('profiles/../escape.json','x'),('profiles/safe.json','0'*64)]:
                archive=root/'bad.zip';content=b'{}'
                manifest=dict(schema_version=1,kind='XAUPY_DATA_BUNDLE',files=[dict(path=name,size=2,sha256=sha)])
                with zipfile.ZipFile(archive,'w') as z:z.writestr(name,content);z.writestr('bundle-manifest.json',json.dumps(manifest))
                with self.assertRaises(ValueError):transfer.import_archive(archive)
            self.assertEqual([],list(target.glob('imports/*/import-complete.json')))
            self.assertFalse((target/'profiles').exists())
