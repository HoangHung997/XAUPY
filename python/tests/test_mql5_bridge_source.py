import pathlib
import re
import unittest
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[2]
SOURCE = ROOT / "mql5" / "XAUPY_Bridge_EA.mq5"


class Mql5BridgeSourceSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = SOURCE.read_text(encoding="utf-8")
        cls.demo = (SOURCE.parent / "XAUPY_DemoOnce.mqh").read_text(encoding="utf-8")
        cls.parser = (SOURCE.parent / "XAUPY_StrictJson.mqh").read_text(encoding="utf-8")
        cls.all_source = "\n".join((cls.text, cls.demo, cls.parser))

    def test_bridge_reports_actual_user_mode(self):
        self.assertIn('if(!g_full_enabled)', self.text)
        self.assertIn("execution_locked", self.text)
        self.assertIn("execution_ready", self.text)
        self.assertIn('return "USER_STOPPED"', self.text)

    def test_legacy_demo_execution_keeps_its_single_bounded_send(self):
        forbidden = (
            "OrderSendAsync(",
            "CTrade ",
            "CTrade\t",
            "#include <Trade/Trade.mqh>",
        )
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, self.all_source)
        self.assertNotIn("OrderSend(", self.text)
        self.assertEqual(len(re.findall(r"\bOrderSend\s*\(", self.all_source)), 1)
        send_path = self.demo.split("void DemoOnceHandleAck(string response)", 1)[1]
        self.assertIn("OrderSend(final_request,sent)", send_path)
        self.assertNotRegex(send_path, r"\b(?:for|while)\s*\(")

    def test_loopback_guard_exists(self):
        self.assertIn('InpHost != "127.0.0.1"', self.text)
        self.assertIn('InpHost != "localhost"', self.text)

    def test_required_timeframes_are_exported(self):
        for timeframe in ("PERIOD_M1","PERIOD_M3","PERIOD_M5","PERIOD_M15","PERIOD_M30","PERIOD_H1","PERIOD_H2","PERIOD_H4"):
            with self.subTest(timeframe=timeframe):
                self.assertIn(timeframe, self.text)

    def test_task009_exports_owned_ticket_level_order_book(self):
        for token in (
            "JsonPositions()",
            "JsonOrders()",
            "JsonDeals()",
            'JsonKey("positions")',
            'JsonKey("orders")',
            'JsonKey("deals")',
            "DEAL_POSITION_ID",
            "HistoryPositionEntryPrice",
            "OwnDailyRealized",
        ):
            with self.subTest(token=token):
                self.assertIn(token, self.text)

    def test_legacy_demo_adapter_cannot_manage_or_close_positions(self):
        for token in ("PositionClose(", "PositionModify(", "OrderDelete(", "TRADE_ACTION_REMOVE", "TRADE_ACTION_SLTP", "TRADE_ACTION_CLOSE_BY", "TRADE_ACTION_PENDING"):
            self.assertNotIn(token, self.all_source)

    def test_general_adapter_claims_before_send_and_does_not_retry_send(self):
        full=(SOURCE.parent/'XAUPY_Execution.mqh').read_text(encoding='utf-8')
        self.assertEqual(1,len(re.findall(r'\bOrderSend\s*\(',full)))
        handler=full.split('void FullHandleAck(string text)',1)[1].split('void FullDiscoverEvidence',1)[0]
        self.assertLess(handler.index('FileFlush(lock)'),handler.index('OrderSend(request,sent)'))
        self.assertLess(handler.index('OrderCheck(request,check)'),handler.index('FileFlush(lock)'))
        self.assertNotRegex(handler,r'\b(?:for|while)\s*\(')
        recovery=full.split('void FullDiscoverEvidence',1)[1]
        self.assertNotIn('OrderSend(',recovery)
        self.assertIn('FullDealAggregate',full)

    def test_one_shot_claim_and_unknown_report_precede_single_broker_send(self):
        send_path = self.demo.split("void DemoOnceHandleAck(string response)", 1)[1]
        steps = ("OnceParseCommand(json,node,command)", "OnceLiveGuard(command,request", "OrderCheck(request,checked)",
                 "OnceClaimBudget(command,lock_handle", 'result.status="UNKNOWN"', "OncePublish(result,true)",
                 "g_once_persisted_report!=OnceResultJson(result)", "OnceLiveGuard(command,final_request",
                 "ACCOUNT_TRADE_MODE_DEMO", "OnceAnyExposure(final_positions,final_orders)", "OrderSend(final_request,sent)")
        offsets = [send_path.index(step) for step in steps]
        self.assertEqual(offsets, sorted(offsets))
        self.assertIn("immediate_now>=command.expires_server_time", send_path)
        self.assertIn("immediate.ask-immediate.bid>command.max_spread_price_units", send_path)
        self.assertIn("FINAL_CLOSE_SIDE_STOP_DISTANCE_CHANGED", send_path)

    def test_budget_is_shared_by_identity_and_not_reset_by_new_attempt_or_restart(self):
        scope = self.demo.split("string OnceScope()", 1)[1].split("string OnceFile", 1)[0]
        for identity in ("ACCOUNT_LOGIN", "ACCOUNT_SERVER", "_Symbol"):
            self.assertIn(identity, scope)
        self.assertNotIn("attempt_id", scope)
        claim = self.demo.split("bool OnceClaimBudget", 1)[1].split("bool OnceVerifyFill", 1)[0]
        self.assertIn("FILE_READ|FILE_WRITE|FILE_BIN", claim)
        self.assertNotIn("FILE_SHARE", claim)
        self.assertLess(claim.index("GlobalVariableSetOnCondition"), claim.index("GlobalVariablesFlush()"))
        self.assertLess(claim.index("GlobalVariablesFlush()"), claim.index('OnceWrite(OnceFile(".claim")'))
        self.assertIn('OnceRead(OnceFile(".claim"),verified)', claim)
        self.assertNotIn("GlobalVariableDel", self.all_source)
        self.assertNotIn("FileDelete", self.all_source)
        reconnect = self.text.split("void CloseSocket()", 1)[1].split("bool EnsureConnected", 1)[0]
        self.assertNotIn("g_bridge_session_id=", reconnect.replace(" ", ""))

    def test_filled_requires_broker_deal_and_actual_protective_stops(self):
        verify = self.demo.split("bool OnceVerifyFill", 1)[1].split("void DemoOncePoll", 1)[0]
        checks = ("HistorySelect(", "DEAL_ORDER", "DEAL_SYMBOL", "DEAL_MAGIC", "DEAL_ENTRY_IN", "DEAL_TYPE",
                  "DEAL_VOLUME", "DEAL_PRICE", "HistoryOrderSelect(", "ORDER_SL", "ORDER_TP", "POSITION_SL", "POSITION_TP")
        for check in checks:
            self.assertLess(verify.index(check), verify.index('result.status="FILLED"'))
        poll = self.demo.split("void DemoOncePoll()", 1)[1].split("void DemoOnceHandleAck", 1)[0]
        self.assertNotIn("OrderSend", poll)
        init = self.demo.split("void DemoOnceInit()", 1)[1].split("void DemoOnceReplayResult", 1)[0]
        self.assertNotIn("OrderSend", init)

    def test_native_parser_selftest_gates_initialization_before_io(self):
        init = self.text.split("int OnInit()", 1)[1].split("void OnDeinit", 1)[0]
        self.assertLess(init.index("DemoOnceParserSelfTest()"), init.index("DemoOnceInit()"))
        self.assertLess(init.index("DemoOnceParserSelfTest()"), init.index("EventSetMillisecondTimer"))
        fixture = self.demo.split("bool DemoOnceParserSelfTest()", 1)[1].split("string OnceResultJson", 1)[0]
        self.assertGreaterEqual(fixture.count("checks++"), 23)
        for mutation in ("OrderSend(", "FileOpen(", "SocketConnect(", "GlobalVariableSet("):
            self.assertNotIn(mutation, fixture)
        self.assertIn("Find(index,child_key)>=0", self.parser)
        self.assertIn("StringFormat(\"%I64d\",value)==raw", self.parser)

    def test_commands_only_execute_after_correlated_structured_ack(self):
        request = self.text.split("bool SendRequest(", 1)[1].split("bool EnsureHandshake()", 1)[0]
        self.assertIn("OnceValidateEnvelope(response_text,request_id,expected_type", request)
        self.assertNotIn("StringFind", request)
        self.assertIn('json.Count(node)!=20', self.demo)
        timer = self.text.split("void OnTimer()", 1)[1].split("void OnTick()", 1)[0]
        self.assertEqual(timer.count("DemoOnceHandleAck(response)"), 2)
        for field in ("account_server", "bridge_session_id", "demo_once_capable", "demo_once_consumed", "demo_once_guard"):
            self.assertIn(f'JsonKey("{field}")', self.text)

    def test_replayed_result_follows_fresh_snapshot_and_only_accepted_ack_clears_pending(self):
        timer = self.text.split("void OnTimer()", 1)[1].split("void OnTick()", 1)[0]
        self.assertLess(timer.index('SendRequest("bridge_snapshot"'), timer.index('SendRequest("bridge_ticks"'))
        self.assertLess(timer.index('SendRequest("bridge_ticks"'), timer.index('SendRequest("bridge_demo_once_result"'))
        self.assertEqual(timer.count("g_once_report_pending=false"), 1)
        self.assertIn("if(DemoOnceResultAckAccepted(response)) g_once_report_pending=false;", timer)
        ack = self.demo.split("bool DemoOnceResultAckAccepted", 1)[1].split("bool DemoOnceParserSelfTest", 1)[0]
        self.assertIn('json.Bool(payload,"accepted",accepted) && accepted', ack)
        self.assertNotIn("OrderSend", ack)

    def test_socket_data_channel_exists(self):
        for token in ("SocketCreate(", "SocketConnect(", "SocketSend(", "SocketRead(", "bridge_snapshot"):
            with self.subTest(token=token):
                self.assertIn(token, self.text)

    def test_snapshot_builder_has_unique_top_level_fields(self):
        # Python rejects duplicate JSON keys. A successful EA compile/hello must
        # not hide a snapshot that is unusable by every data consumer.
        builder = self.text.split("string BuildSnapshotPayload(", 1)[1].split("string BuildEnvelope(", 1)[0]
        fields = re.findall(r'JsonKey\("([^"\\]+)"\)', builder)
        duplicates = {key: count for key, count in Counter(fields).items() if count > 1}
        self.assertGreater(len(fields), 40)
        self.assertFalse(duplicates, f"Duplicate snapshot fields: {duplicates}")
        for required in ("terminal_path", "terminal_data_path", "bars", "bar_history", "indicator_probes"):
            self.assertIn(required, fields)


if __name__ == "__main__":
    unittest.main()
