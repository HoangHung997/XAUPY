#property strict
#property version   "0.30"
#property description "XAUPY Task 003 MT5 data bridge. Execution is hard-locked."

input string InpHost               = "127.0.0.1";
input uint   InpPort               = 39421;
input uint   InpConnectTimeoutMs   = 1500;
input uint   InpSocketTimeoutMs    = 1500;
input uint   InpTimerMs            = 1000;
input long   InpMagic              = 991188;
input double InpMaxVolume          = 0.10;
input double InpMaxDailyLossPct    = 2.00;
input int    InpMaxOpenPositions   = 1;

const bool TASK003_EXECUTION_LOCKED = true;

int  g_socket = INVALID_HANDLE;
bool g_handshake_ok = false;
long g_sequence = 0;
ulong g_last_connect_attempt_ms = 0;

string JsonEscape(string value)
{
   string s = value;
   StringReplace(s, "\\", "\\\\");
   StringReplace(s, """, "\\"");
   StringReplace(s, "\r", "\\r");
   StringReplace(s, "\n", "\\n");
   StringReplace(s, "\t", "\\t");
   return s;
}

string JsonString(string value)
{
   return """ + JsonEscape(value) + """;
}

string JsonBool(bool value)
{
   return value ? "true" : "false";
}

string JsonNumber(double value, int digits=8)
{
   return DoubleToString(value, digits);
}

string IsoUtcNow()
{
   MqlDateTime dt;
   TimeToStruct(TimeGMT(), dt);
   return StringFormat("%04d-%02d-%02dT%02d:%02d:%02dZ",
                       dt.year, dt.mon, dt.day, dt.hour, dt.min, dt.sec);
}

string Hex8(uint value)
{
   return StringFormat("%08X", value);
}

string Hex4(uint value)
{
   return StringFormat("%04X", value & 0xFFFF);
}

string NewRequestId()
{
   g_sequence++;
   uint a = (uint)(GetTickCount() ^ (uint)TimeLocal() ^ (uint)g_sequence);
   uint b = (uint)MathRand();
   uint c = (uint)MathRand();
   uint d = (uint)MathRand();
   uint e = (uint)MathRand();
   uint f = (uint)MathRand();

   return Hex8(a) + "-" +
          Hex4(b) + "-" +
          Hex4(c) + "-" +
          Hex4(d) + "-" +
          Hex4(e) + Hex8(f);
}

string AccountTradeModeText()
{
   ENUM_ACCOUNT_TRADE_MODE mode = (ENUM_ACCOUNT_TRADE_MODE)AccountInfoInteger(ACCOUNT_TRADE_MODE);
   if(mode == ACCOUNT_TRADE_MODE_DEMO)
      return "DEMO";
   if(mode == ACCOUNT_TRADE_MODE_CONTEST)
      return "CONTEST";
   if(mode == ACCOUNT_TRADE_MODE_REAL)
      return "REAL";
   return "UNKNOWN";
}

int OwnPositionsCount()
{
   int count = 0;
   int total = PositionsTotal();
   for(int i=0; i<total; i++)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol)
         continue;
      if((long)PositionGetInteger(POSITION_MAGIC) != InpMagic)
         continue;
      count++;
   }
   return count;
}

int OwnOrdersCount()
{
   int count = 0;
   int total = OrdersTotal();
   for(int i=0; i<total; i++)
   {
      ulong ticket = OrderGetTicket(i);
      if(ticket == 0)
         continue;
      if(OrderGetString(ORDER_SYMBOL) != _Symbol)
         continue;
      if((long)OrderGetInteger(ORDER_MAGIC) != InpMagic)
         continue;
      count++;
   }
   return count;
}

double AccountDailyRealized()
{
   datetime now = TimeCurrent();
   string date_text = TimeToString(now, TIME_DATE);
   datetime start = StringToTime(date_text);

   if(!HistorySelect(start, now))
      return 0.0;

   double realized = 0.0;
   int total = HistoryDealsTotal();

   for(int i=0; i<total; i++)
   {
      ulong ticket = HistoryDealGetTicket(i);
      if(ticket == 0)
         continue;

      ENUM_DEAL_ENTRY entry = (ENUM_DEAL_ENTRY)HistoryDealGetInteger(ticket, DEAL_ENTRY);
      if(entry != DEAL_ENTRY_OUT && entry != DEAL_ENTRY_OUT_BY)
         continue;

      realized += HistoryDealGetDouble(ticket, DEAL_PROFIT);
      realized += HistoryDealGetDouble(ticket, DEAL_COMMISSION);
      realized += HistoryDealGetDouble(ticket, DEAL_SWAP);
   }

   return realized;
}

string GuardianReason()
{
   if(TASK003_EXECUTION_LOCKED)
      return "TASK003_EXECUTION_LOCKED";

   if(!TerminalInfoInteger(TERMINAL_CONNECTED))
      return "TERMINAL_DISCONNECTED";

   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED))
      return "TERMINAL_TRADE_NOT_ALLOWED";

   if(!MQLInfoInteger(MQL_TRADE_ALLOWED))
      return "MQL_TRADE_NOT_ALLOWED";

   if((ENUM_ACCOUNT_TRADE_MODE)AccountInfoInteger(ACCOUNT_TRADE_MODE) != ACCOUNT_TRADE_MODE_DEMO)
      return "DEMO_ONLY";

   if(OwnPositionsCount() >= InpMaxOpenPositions)
      return "MAX_OPEN_POSITIONS";

   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double loss_limit = MathAbs(balance) * InpMaxDailyLossPct / 100.0;
   double realized = AccountDailyRealized();
   if(realized <= -loss_limit)
      return "DAILY_LOSS_LIMIT";

   return "READY";
}

string JsonGuardian()
{
   bool terminal_connected = (bool)TerminalInfoInteger(TERMINAL_CONNECTED);
   bool terminal_trade_allowed = (bool)TerminalInfoInteger(TERMINAL_TRADE_ALLOWED);
   bool mql_trade_allowed = (bool)MQLInfoInteger(MQL_TRADE_ALLOWED);
   bool demo_account = ((ENUM_ACCOUNT_TRADE_MODE)AccountInfoInteger(ACCOUNT_TRADE_MODE) == ACCOUNT_TRADE_MODE_DEMO);
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double realized = AccountDailyRealized();
   double loss_limit = MathAbs(balance) * InpMaxDailyLossPct / 100.0;

   string json = "{";
   json += ""execution_locked":true,";
   json += ""execution_ready":false,";
   json += ""reason":" + JsonString(GuardianReason()) + ",";
   json += ""demo_only":true,";
   json += ""demo_account":" + JsonBool(demo_account) + ",";
   json += ""terminal_connected":" + JsonBool(terminal_connected) + ",";
   json += ""terminal_trade_allowed":" + JsonBool(terminal_trade_allowed) + ",";
   json += ""mql_trade_allowed":" + JsonBool(mql_trade_allowed) + ",";
   json += ""max_volume":" + JsonNumber(InpMaxVolume, 2) + ",";
   json += ""max_daily_loss_pct":" + JsonNumber(InpMaxDailyLossPct, 2) + ",";
   json += ""daily_realized":" + JsonNumber(realized, 2) + ",";
   json += ""daily_loss_limit":" + JsonNumber(loss_limit, 2) + ",";
   json += ""max_open_positions":" + IntegerToString(InpMaxOpenPositions) + ",";
   json += ""own_positions":" + IntegerToString(OwnPositionsCount()) + ",";
   json += ""own_orders":" + IntegerToString(OwnOrdersCount());
   json += "}";
   return json;
}

string JsonBar(ENUM_TIMEFRAMES timeframe)
{
   MqlRates rates[];
   ArraySetAsSeries(rates, true);

   int copied = CopyRates(_Symbol, timeframe, 1, 1, rates);
   if(copied != 1)
      return "null";

   string json = "{";
   json += ""time":" + IntegerToString((int)rates[0].time) + ",";
   json += ""open":" + JsonNumber(rates[0].open, _Digits) + ",";
   json += ""high":" + JsonNumber(rates[0].high, _Digits) + ",";
   json += ""low":" + JsonNumber(rates[0].low, _Digits) + ",";
   json += ""close":" + JsonNumber(rates[0].close, _Digits) + ",";
   json += ""tick_volume":" + IntegerToString((int)rates[0].tick_volume);
   json += "}";
   return json;
}

string JsonBars()
{
   string json = "{";
   json += ""M1":"  + JsonBar(PERIOD_M1)  + ",";
   json += ""M3":"  + JsonBar(PERIOD_M3)  + ",";
   json += ""M5":"  + JsonBar(PERIOD_M5)  + ",";
   json += ""M15":" + JsonBar(PERIOD_M15) + ",";
   json += ""M30":" + JsonBar(PERIOD_M30) + ",";
   json += ""H1":"  + JsonBar(PERIOD_H1)  + ",";
   json += ""H2":"  + JsonBar(PERIOD_H2)  + ",";
   json += ""H4":"  + JsonBar(PERIOD_H4);
   json += "}";
   return json;
}

string BuildHelloPayload()
{
   string json = "{";
   json += ""bridge_version":"0.3.0-task003",";
   json += ""component":"mt5-bridge",";
   json += ""symbol":" + JsonString(_Symbol) + ",";
   json += ""magic":" + IntegerToString((int)InpMagic) + ",";
   json += ""execution_locked":true";
   json += "}";
   return json;
}

string BuildSnapshotPayload()
{
   MqlTick tick;
   ZeroMemory(tick);
   SymbolInfoTick(_Symbol, tick);

   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   double spread_points = 0.0;
   if(point > 0.0)
      spread_points = (tick.ask - tick.bid) / point;

   string json = "{";
   json += ""bridge_version":"0.3.0-task003",";
   json += ""symbol":" + JsonString(_Symbol) + ",";
   json += ""magic":" + IntegerToString((int)InpMagic) + ",";
   json += ""terminal_connected":" + JsonBool((bool)TerminalInfoInteger(TERMINAL_CONNECTED)) + ",";
   json += ""account_trade_mode":" + JsonString(AccountTradeModeText()) + ",";
   json += ""account_login":" + IntegerToString((int)AccountInfoInteger(ACCOUNT_LOGIN)) + ",";
   json += ""account_currency":" + JsonString(AccountInfoString(ACCOUNT_CURRENCY)) + ",";
   json += ""balance":" + JsonNumber(AccountInfoDouble(ACCOUNT_BALANCE), 2) + ",";
   json += ""equity":" + JsonNumber(AccountInfoDouble(ACCOUNT_EQUITY), 2) + ",";
   json += ""margin_free":" + JsonNumber(AccountInfoDouble(ACCOUNT_MARGIN_FREE), 2) + ",";
   json += ""bid":" + JsonNumber(tick.bid, _Digits) + ",";
   json += ""ask":" + JsonNumber(tick.ask, _Digits) + ",";
   json += ""spread_points":" + JsonNumber(spread_points, 2) + ",";
   json += ""digits":" + IntegerToString(_Digits) + ",";
   json += ""point":" + JsonNumber(point, 10) + ",";
   json += ""volume_min":" + JsonNumber(SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN), 2) + ",";
   json += ""volume_max":" + JsonNumber(SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX), 2) + ",";
   json += ""volume_step":" + JsonNumber(SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP), 2) + ",";
   json += ""tick_size":" + JsonNumber(SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE), 10) + ",";
   json += ""tick_value":" + JsonNumber(SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE), 8) + ",";
   json += ""stops_level":" + IntegerToString((int)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL)) + ",";
   json += ""freeze_level":" + IntegerToString((int)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_FREEZE_LEVEL)) + ",";
   json += ""positions_count":" + IntegerToString(OwnPositionsCount()) + ",";
   json += ""orders_count":" + IntegerToString(OwnOrdersCount()) + ",";
   json += ""guardian":" + JsonGuardian() + ",";
   json += ""bars":" + JsonBars();
   json += "}";
   return json;
}

string BuildEnvelope(string message_type, string request_id, string payload_json)
{
   string json = "{";
   json += ""schema_version":1,";
   json += ""type":" + JsonString(message_type) + ",";
   json += ""request_id":" + JsonString(request_id) + ",";
   json += ""sent_at_utc":" + JsonString(IsoUtcNow()) + ",";
   json += ""payload":" + payload_json;
   json += "}";
   return json;
}

void CloseSocket()
{
   if(g_socket != INVALID_HANDLE)
   {
      SocketClose(g_socket);
      g_socket = INVALID_HANDLE;
   }

   g_handshake_ok = false;
}

bool EnsureConnected()
{
   if(g_socket != INVALID_HANDLE && SocketIsConnected(g_socket))
      return true;

   CloseSocket();

   ulong now_ms = GetTickCount64();
   if(now_ms - g_last_connect_attempt_ms < 1000)
      return false;

   g_last_connect_attempt_ms = now_ms;

   g_socket = SocketCreate(SOCKET_DEFAULT);
   if(g_socket == INVALID_HANDLE)
   {
      Print("XAUPY_BRIDGE socket create failed: ", GetLastError());
      return false;
   }

   ResetLastError();
   if(!SocketConnect(g_socket, InpHost, InpPort, InpConnectTimeoutMs))
   {
      Print("XAUPY_BRIDGE connect failed ", InpHost, ":", InpPort, " err=", GetLastError());
      CloseSocket();
      return false;
   }

   Print("XAUPY_BRIDGE connected ", InpHost, ":", InpPort);
   return true;
}

bool SendRequest(string message_type,
                 string payload_json,
                 string expected_type,
                 string &response_text)
{
   response_text = "";

   if(!EnsureConnected())
      return false;

   string request_id = NewRequestId();
   string request = BuildEnvelope(message_type, request_id, payload_json) + "\n";

   uchar bytes[];
   int byte_count = StringToCharArray(request, bytes, 0, WHOLE_ARRAY, CP_UTF8);
   if(byte_count <= 1)
      return false;

   int send_len = byte_count - 1;
   int sent = SocketSend(g_socket, bytes, (uint)send_len);
   if(sent != send_len)
   {
      Print("XAUPY_BRIDGE socket send failed err=", GetLastError());
      CloseSocket();
      return false;
   }

   uchar recv[];
   ArrayResize(recv, 65536);

   int received = SocketRead(g_socket, recv, 65535, InpSocketTimeoutMs);
   if(received <= 0)
   {
      Print("XAUPY_BRIDGE socket read failed err=", GetLastError());
      CloseSocket();
      return false;
   }

   response_text = CharArrayToString(recv, 0, received, CP_UTF8);

   int newline = StringFind(response_text, "\n");
   if(newline >= 0)
      response_text = StringSubstr(response_text, 0, newline);

   string request_token = ""request_id":"" + request_id + """;
   string type_token = ""type":"" + expected_type + """;

   if(StringFind(response_text, request_token) < 0 ||
      StringFind(response_text, type_token) < 0)
   {
      Print("XAUPY_BRIDGE invalid response: ", response_text);
      CloseSocket();
      return false;
   }

   if(StringFind(response_text, ""execution_enabled":true") >= 0 ||
      StringFind(response_text, ""trading_enabled":true") >= 0)
   {
      Print("XAUPY_BRIDGE safety violation: Engine reported execution enabled.");
      CloseSocket();
      return false;
   }

   return true;
}

bool EnsureHandshake()
{
   if(g_handshake_ok)
      return true;

   string response;
   if(!SendRequest("bridge_hello", BuildHelloPayload(), "bridge_hello_ack", response))
      return false;

   g_handshake_ok = true;
   Print("XAUPY_BRIDGE handshake ready; execution remains locked.");
   return true;
}

int OnInit()
{
   MathSrand((int)(GetTickCount() ^ (uint)TimeLocal()));

   if(InpTimerMs < 250)
   {
      Print("XAUPY_BRIDGE InpTimerMs must be >= 250");
      return INIT_PARAMETERS_INCORRECT;
   }

   if(InpHost != "127.0.0.1" && InpHost != "localhost")
   {
      Print("XAUPY_BRIDGE Task 003 only permits loopback host.");
      return INIT_PARAMETERS_INCORRECT;
   }

   if(!EventSetMillisecondTimer((int)InpTimerMs))
   {
      Print("XAUPY_BRIDGE timer setup failed err=", GetLastError());
      return INIT_FAILED;
   }

   Print("XAUPY_BRIDGE Task 003 initialized. EXECUTION LOCKED.");
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   CloseSocket();
   Print("XAUPY_BRIDGE stopped reason=", reason);
}

void OnTimer()
{
   if(!EnsureHandshake())
      return;

   string response;
   if(!SendRequest("bridge_snapshot",
                   BuildSnapshotPayload(),
                   "bridge_snapshot_ack",
                   response))
   {
      return;
   }
}

void OnTick()
{
   // Task 003 uses timer-based snapshots. No trading logic exists here.
}
