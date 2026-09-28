from datetime import datetime,timezone
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from xaupy_engine.monitoring import MonitoringService,market_sessions


class MonitoringServiceTests(unittest.TestCase):
    def test_london_and_new_york_change_with_their_own_dst_calendar(self):
        winter=market_sessions(datetime(2026,1,5,12,tzinfo=timezone.utc))
        summer=market_sessions(datetime(2026,7,6,12,tzinfo=timezone.utc))
        self.assertEqual('12:00',winter[2]['local_time'])
        self.assertEqual('13:00',summer[2]['local_time'])
        self.assertFalse(winter[3]['active'])
        self.assertTrue(summer[3]['active'])

    def test_weekend_session_countdown_skips_closed_days(self):
        rows=market_sessions(datetime(2026,9,27,12,tzinfo=timezone.utc))
        self.assertTrue(all(not row['active'] for row in rows))
        self.assertTrue(all(row['minutes_to_change']>0 for row in rows))

    def test_resource_reading_reports_real_capacity_or_explicit_unavailability(self):
        with tempfile.TemporaryDirectory() as root:
            service=MonitoringService(Path(root))
            value=service.resources()
            if value['available']:
                self.assertGreater(value['ram_total_bytes'],0)
                self.assertGreaterEqual(value['disk_free_bytes'],0)
                for metric in ('cpu_percent','ram_percent','disk_percent'):
                    self.assertGreaterEqual(value[metric],0)
                    self.assertLessEqual(value[metric],100)
            service._psutil=None
            self.assertEqual({'available':False,'reason':'RESOURCE_PROVIDER_MISSING'},service.resources())


if __name__=='__main__': unittest.main()
