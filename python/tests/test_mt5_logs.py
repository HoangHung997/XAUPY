from pathlib import Path
import tempfile
import unittest
from xaupy_engine.mt5_logs import Mt5LogReader
from xaupy_engine.journal import StructuredJournal


class NativeLogTests(unittest.TestCase):
    def test_utf16_partial_lines_restart_and_truncation(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);folder=root/'terminal'/'MQL5'/'Logs';folder.mkdir(parents=True)
            path=folder/'20260928.log';state=root/'state';state.mkdir()
            journal=StructuredJournal(root/'journal');reader=Mt5LogReader(state,journal)
            first='AA\t0\t12:00\tBridge started\r\n'
            path.write_bytes(b'\xff\xfe'+first.encode('utf-16-le')+'partial'.encode('utf-16-le'))
            reader.read_once(root/'terminal');self.assertEqual(1,journal.event_count)
            with path.open('ab') as stream:stream.write(' finished\r\n'.encode('utf-16-le'))
            reader.read_once(root/'terminal');self.assertEqual(2,journal.event_count)
            reader.close();reader=Mt5LogReader(state,journal)
            reader.read_once(root/'terminal');self.assertEqual(2,journal.event_count)
            path.write_bytes(b'\xff\xfe'+'BB\t1\t12:01\tFailure\r\n'.encode('utf-16-le'))
            reader.read_once(root/'terminal')
            self.assertEqual(3,journal.event_count)
            events=journal.query(date_scope='ALL',limit=10)['events']
            self.assertEqual('ERROR',events[0]['level']);self.assertEqual('MT5_EXPERTS',events[0]['tag'])
            self.assertIn('native_raw_line',events[0]['details'])
            with path.open('ab') as stream:stream.write('BB\t0\t12:02\tRecovered\r\n'.encode('utf-16-le'))
            reader.read_once(root/'terminal');reader.close();self.assertEqual(4,journal.event_count)
