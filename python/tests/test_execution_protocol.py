import asyncio
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from uuid import uuid4

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from xaupy_engine.server import EngineServer
from xaupy_engine.strategy_engine import HISTORY_TIMEFRAME_SECONDS
from test_demo_once import NOW
from test_strategy_protocol import exchange


class GeneralExecutionProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.server=EngineServer(port=0,state_dir=self.temp.name)
        profile=deepcopy(self.server.active_profile)
        profile['stop_loss'].update(mode='FIXED',fixed_price_units=3.)
        profile['take_profit'].update(mode='FIXED',fixed_price_units=6.)
        profile['risk'].update(sizing_mode='FIXED_LOT',fixed_lot=.01)
        self.server.active_profile=profile
        self.server.strategy.set_profile(profile)
        await self.server.start()
        self.writers=[]
        self.ea=await self.connect()
        self.desktop=await self.connect()
        self.session=str(uuid4())
        self.snapshot=dict(execution_capabilities=dict(schema_version=1,trade_allowed=True,allow_buy=True,allow_sell=True,market_orders=True,stop_orders=True,limit_orders=True,server_sl=True,server_tp=True,specified_expiration=True,netting_symbol_exposed=False,margin_mode='HEDGING'),bridge_version='1.022',execution_capable=True,demo_once_capable=True,bridge_session_id=self.session,
            account_login=100,account_server='Test-Demo',symbol='XAUUSD',magic=991188,account_trade_mode='DEMO',terminal_connected=True,
            server_time=NOW,tick_time_msc=NOW*1000,bid=4200.,ask=4200.2,balance=10000.,point=.01,tick_size=.01,tick_value=1.,
            volume_min=.01,volume_max=100.,volume_step=.01,stops_level=10,freeze_level=0,positions=[],orders=[],deals=[],
            guardian={'execution_locked':True,'execution_ready':False,'reason':'USER_STOPPED','max_volume':.1},
            demo_once_guard=dict(history_complete=True,broker_day_start=NOW//86400*86400,trades_today=0,consecutive_losses=0,last_exit_time=0,day_start_balance=10000.,daily_realized=0.),
            bars={tf:dict(time=(NOW//span-1)*span,open=4200.,high=4201.,low=4199.,close=4200.,tick_volume=1) for tf,span in HISTORY_TIMEFRAME_SECONDS.items()})
        await exchange(*self.ea,'bridge_hello',self.hello())
        await exchange(*self.ea,'bridge_snapshot',self.snapshot)

    def hello(self):
        return dict(component='mt5-bridge',bridge_version='1.022',symbol='XAUUSD',execution_capable=True,demo_once_capable=True,bridge_session_id=self.session)

    async def connect(self):
        connection=await asyncio.open_connection('127.0.0.1',self.server.bound_port)
        self.writers.append(connection[1])
        return connection

    async def asyncTearDown(self):
        for writer in self.writers: writer.close()
        await asyncio.gather(*(w.wait_closed() for w in self.writers),return_exceptions=True)
        await self.server.close()
        self.temp.cleanup()

    async def activate(self):
        identity={k:self.snapshot[k] for k in ('account_login','account_server','symbol','magic')}
        reply=await exchange(*self.desktop,'execution_mode_set',dict(mode='MANUAL',confirmed=True,**identity))
        self.assertTrue(reply.payload['accepted'],reply.payload)

    async def test_real_command_only_leaves_owner_and_result_requires_broker_evidence(self):
        await self.activate()
        action=dict(intent_id=str(uuid4()),confirmed=True,action='MARKET_BUY')
        queued=await exchange(*self.desktop,'execution_action',action)
        self.assertTrue(queued.payload['accepted'])
        self.assertFalse(queued.payload['broker_request_sent'])
        duplicate=await exchange(*self.desktop,'execution_action',action)
        self.assertEqual(action['intent_id'],duplicate.payload['intent_id'])
        forged=await exchange(*self.desktop,'bridge_snapshot',self.snapshot)
        self.assertEqual('error',forged.type)
        ack=await exchange(*self.ea,'bridge_snapshot',self.snapshot)
        command=ack.payload['execution_command']
        self.assertEqual(action['intent_id'],command['intent_id'])
        self.assertIsNone((await exchange(*self.ea,'bridge_snapshot',self.snapshot)).payload['execution_command'])
        evidence={k:command[k] for k in ('intent_id','account_login','account_server','symbol','magic','bridge_session_id')}
        evidence.update(state='CONFIRMED',broker_verified=False,order_send_called=True,retcode=10009,order_ticket=10,deal_ticket=11,position_ticket=12,
                        filled_volume=.01,fill_price=4200.2,sl=command['sl'],tp=command['tp'])
        rejected=await exchange(*self.ea,'bridge_execution_result',evidence)
        self.assertFalse(rejected.payload['accepted'])
        evidence['broker_verified']=True
        accepted=await exchange(*self.ea,'bridge_execution_result',evidence)
        self.assertTrue(accepted.payload['accepted'],accepted.payload)
        heartbeat=await exchange(*self.desktop,'heartbeat')
        self.assertEqual('CONFIRMED',heartbeat.payload['execution']['recent'][0]['state'])

    async def test_general_execution_session_does_not_require_legacy_one_shot_capability(self):
        # Establish a wholly new owning session without the unrelated legacy flag.
        self.ea[1].close(); await self.ea[1].wait_closed()
        for _ in range(100):
            if self.server._demo_bridge_writer is None: break
            await asyncio.sleep(.01)
        self.assertIsNone(self.server._demo_bridge_writer)
        self.session=str(uuid4()); self.snapshot['bridge_session_id']=self.session
        self.ea=await self.connect()
        hello=self.hello();hello.pop('demo_once_capable')
        reply=await exchange(*self.ea,'bridge_hello',hello)
        self.assertEqual('bridge_hello_ack',reply.type)
        await exchange(*self.ea,'bridge_snapshot',self.snapshot)
        await self.activate()
        action=dict(intent_id=str(uuid4()),confirmed=True,action='MARKET_BUY')
        self.assertTrue((await exchange(*self.desktop,'execution_action',action)).payload['accepted'])
        reply=await exchange(*self.ea,'bridge_snapshot',self.snapshot)
        self.assertEqual(action['intent_id'],reply.payload['execution_command']['intent_id'])
        forged=await exchange(*self.desktop,'bridge_snapshot',self.snapshot)
        self.assertEqual('error',forged.type)

    async def test_old_one_shot_and_continuous_modes_cannot_dispatch_concurrently(self):
        await self.activate()
        reply=await exchange(*self.desktop,'demo_once_arm',{'confirmed':True})
        self.assertFalse(reply.payload['accepted'])
        self.assertEqual('GENERAL_EXECUTION_ACTIVE',reply.payload['demo_once']['code'])
        self.assertIsNone((await exchange(*self.ea,'bridge_snapshot',self.snapshot)).payload['demo_once_command'])

    async def test_owner_disconnect_preserves_unknown_and_reconnect_never_resends(self):
        await self.activate()
        await exchange(*self.desktop,'execution_action',dict(intent_id=str(uuid4()),confirmed=True,action='MARKET_BUY'))
        command=(await exchange(*self.ea,'bridge_snapshot',self.snapshot)).payload['execution_command']
        self.ea[1].close(); await self.ea[1].wait_closed()
        await asyncio.sleep(.02)
        report=await exchange(*self.desktop,'execution_status')
        self.assertEqual('UNKNOWN',report.payload['recent'][0]['state'])
        self.session=str(uuid4()); self.snapshot['bridge_session_id']=self.session
        self.ea=await self.connect()
        await exchange(*self.ea,'bridge_hello',self.hello())
        reply=await exchange(*self.ea,'bridge_snapshot',self.snapshot)
        self.assertIsNone(reply.payload['execution_command'])
        self.assertNotEqual(self.session,command['bridge_session_id'])


if __name__=='__main__': unittest.main()
