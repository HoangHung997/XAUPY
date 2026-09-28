import tempfile
from pathlib import Path
import unittest
from xaupy_engine.broker_history import reconstruct, write_report, query_report


def deal(ticket, entry, volume, price, commission=0, profit=0, side=0, magic=1, position=100):
    return dict(ticket=ticket,entry=entry,volume=volume,price=price,commission=commission,profit=profit,
        type=side,magic=magic,position_id=position,symbol='XAUUSD',time=1000+ticket,order=1000+ticket)


class BrokerHistoryTests(unittest.TestCase):
    def test_partial_exit_allocates_entry_fees_without_double_count(self):
        rows=reconstruct([deal(1,0,1,2000,-4),deal(2,1,.25,2010,-1,2.5,1),deal(3,1,.75,2020,-3,15,1)],1)
        self.assertEqual([2000,2000],[r['price_in'] for r in rows])
        self.assertEqual([-2,-6],[r['commission'] for r in rows])
        self.assertEqual(9.5,sum(r['realized_total'] for r in rows))
        self.assertEqual(['BUY','BUY'],[r['side'] for r in rows])

    def test_reversal_costs_split_and_new_side_recovers(self):
        rows=reconstruct([deal(1,0,1,2000,-2),deal(2,2,2,2010,-4,10,1),deal(3,1,1,2005,-2,5,0)],1)
        self.assertEqual(['BUY','SELL'],[r['side'] for r in rows])
        self.assertEqual([2000,2010],[r['price_in'] for r in rows])
        self.assertEqual(7,sum(r['realized_total'] for r in rows))

    def test_missing_entry_never_fabricates_price(self):
        row=reconstruct([deal(3,1,1,2005,-2,5,0)],1)[0]
        self.assertIsNone(row['price_in']); self.assertFalse(row['entry_complete'])

    def test_close_reason_and_broker_time_are_preserved(self):
        exit_deal = {**deal(3,1,1,2005,-2,5,0), 'reason':4, 'time':1790574477}
        row = reconstruct([exit_deal],1)[0]
        self.assertEqual(('SL',4,1790574477),(row['reason'],row['reason_code'],row['time']))
        unknown = reconstruct([{**exit_deal,'reason':99}],1)[0]
        self.assertEqual('UNKNOWN (99)',unknown['reason'])

    def test_account_identity_paging_and_all_symbols(self):
        identity=dict(account_login=123,account_server='Demo',magic=1)
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'history.sqlite'
            deals=[deal(1,0,1,2000),deal(2,1,.5,2010,profit=5,side=1),deal(3,1,.5,2010,profit=5,side=1)]
            write_report(path,identity,deals)
            first=query_report(path,identity,limit=1)
            second=query_report(path,identity,limit=1,page=1)
            self.assertTrue(first['has_more']); self.assertFalse(second['has_more'])
            self.assertNotEqual(first['rows'][0]['ticket'],second['rows'][0]['ticket'])
            self.assertEqual(0,query_report(path,identity,symbol='EURUSD')['total'])
            with self.assertRaisesRegex(ValueError,'IDENTITY'): query_report(path,{**identity,'account_login':456})
            with self.assertRaises(ValueError): query_report(path,identity,page=-1)
