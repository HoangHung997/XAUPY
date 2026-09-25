#property strict
#property version   "1.009"
#property description "XAUPY Task 009 MT5 data/order-book bridge. Broker execution is hard-locked."

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
   string slash = CharToString(92);
   string quote = CharToString(34);
   string cr = CharToString(13);
   string lf = CharToString(10);
   string tab = CharToString(9);

   StringReplace(s, slash, slash + slash);
   StringReplace(s, quote, slash + quote);
   StringReplace(s, cr, slash + "r");
   StringReplace(s, lf, slash + "n");
   StringReplace(s, tab, slash + "t");
   return s;
}

string JsonString(string value)
{
   string quote = CharToString(34);
   return quote + JsonEscape(value) + quote;
}

string JsonKey(string key)
{
   return JsonString(key) + ":";
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


string PositionTypeText(long value)
{
   if(value == POSITION_TYPE_BUY)
      return "BUY";
   if(value == POSITION_TYPE_SELL)
      return "SELL";
   return "UNKNOWN";
}

string OrderTypeText(long value)
{
   if(value == ORDER_TYPE_BUY_LIMIT)       return "BUY LIMIT";
   if(value == ORDER_TYPE_SELL_LIMIT)      return "SELL LIMIT";
   if(value == ORDER_TYPE_BUY_STOP)        return "BUY STOP";
   if(value == ORDER_TYPE_SELL_STOP)       return "SELL STOP";
   if(value == ORDER_TYPE_BUY_STOP_LIMIT)  return "BUY STOP LIMIT";
   if(value == ORDER_TYPE_SELL_STOP_LIMIT) return "SELL STOP LIMIT";
   return IntegerToString((int)value);
}

string OrderStateText(long value)
{
   if(value == ORDER_STATE_STARTED)  return "STARTED";
   if(value == ORDER_STATE_PLACED)   return "PLACED";
   if(value == ORDER_STATE_CANCELED) return "CANCELED";
   if(value == ORDER_STATE_PARTIAL)  return "PARTIAL";
   if(value == ORDER_STATE_FILLED)   return "FILLED";
   if(value == ORDER_STATE_REJECTED) return "REJECTED";
   if(value == ORDER_STATE_EXPIRED)  return "EXPIRED";
   return IntegerToString((int)value);
}

string DealTypeText(long value)
{
   if(value == DEAL_TYPE_BUY)
      return "BUY";
   if(value == DEAL_TYPE_SELL)
      return "SELL";
   return IntegerToString((int)value);
}

string DealEntryText(long value)
{
   if(value == DEAL_ENTRY_IN)     return "IN";
   if(value == DEAL_ENTRY_OUT)    return "OUT";
   if(value == DEAL_ENTRY_OUT_BY) return "OUT_BY";
   if(value == DEAL_ENTRY_INOUT)  return "INOUT";
   return IntegerToString((int)value);
}

string DealReasonText(long value)
{
   if(value == DEAL_REASON_SL)     return "SL";
   if(value == DEAL_REASON_TP)     return "TP";
   if(value == DEAL_REASON_CLIENT) return "MANUAL";
   if(value == DEAL_REASON_EXPERT) return "EXPERT";
   return IntegerToString((int)value);
}

double OwnDailyRealized()
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
      if(HistoryDealGetString(ticket, DEAL_SYMBOL) != _Symbol)
         continue;
      if((long)HistoryDealGetInteger(ticket, DEAL_MAGIC) != InpMagic)
         continue;

      ENUM_DEAL_ENTRY entry = (ENUM_DEAL_ENTRY)HistoryDealGetInteger(ticket, DEAL_ENTRY);
      if(entry != DEAL_ENTRY_OUT && entry != DEAL_ENTRY_OUT_BY && entry != DEAL_ENTRY_INOUT)
         continue;

      realized += HistoryDealGetDouble(ticket, DEAL_PROFIT);
      realized += HistoryDealGetDouble(ticket, DEAL_COMMISSION);
      realized += HistoryDealGetDouble(ticket, DEAL_SWAP);
   }
   return realized;
}

string JsonPositions()
{
   string json = "[";
   bool first = true;
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

      if(!first)
         json += ",";
      first = false;

      string item = "{";
      item += JsonKey("ticket") + StringFormat("%I64u", ticket) + ",";
      item += JsonKey("magic") + StringFormat("%I64d", (long)PositionGetInteger(POSITION_MAGIC)) + ",";
      item += JsonKey("symbol") + JsonString(PositionGetString(POSITION_SYMBOL)) + ",";
      item += JsonKey("side") + JsonString(PositionTypeText(PositionGetInteger(POSITION_TYPE))) + ",";
      item += JsonKey("volume") + JsonNumber(PositionGetDouble(POSITION_VOLUME), 2) + ",";
      item += JsonKey("price_open") + JsonNumber(PositionGetDouble(POSITION_PRICE_OPEN), _Digits) + ",";
      item += JsonKey("price_current") + JsonNumber(PositionGetDouble(POSITION_PRICE_CURRENT), _Digits) + ",";
      item += JsonKey("sl") + JsonNumber(PositionGetDouble(POSITION_SL), _Digits) + ",";
      item += JsonKey("tp") + JsonNumber(PositionGetDouble(POSITION_TP), _Digits) + ",";
      item += JsonKey("profit") + JsonNumber(PositionGetDouble(POSITION_PROFIT), 2) + ",";
      item += JsonKey("swap") + JsonNumber(PositionGetDouble(POSITION_SWAP), 2) + ",";
      item += JsonKey("time") + StringFormat("%I64d", PositionGetInteger(POSITION_TIME)) + ",";
      item += JsonKey("comment") + JsonString(PositionGetString(POSITION_COMMENT));
      item += "}";
      json += item;
   }

   json += "]";
   return json;
}

string JsonOrders()
{
   string json = "[";
   bool first = true;
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

      if(!first)
         json += ",";
      first = false;

      string item = "{";
      item += JsonKey("ticket") + StringFormat("%I64u", ticket) + ",";
      item += JsonKey("magic") + StringFormat("%I64d", (long)OrderGetInteger(ORDER_MAGIC)) + ",";
      item += JsonKey("symbol") + JsonString(OrderGetString(ORDER_SYMBOL)) + ",";
      item += JsonKey("type") + JsonString(OrderTypeText(OrderGetInteger(ORDER_TYPE))) + ",";
      item += JsonKey("volume_initial") + JsonNumber(OrderGetDouble(ORDER_VOLUME_INITIAL), 2) + ",";
      item += JsonKey("volume_current") + JsonNumber(OrderGetDouble(ORDER_VOLUME_CURRENT), 2) + ",";
      item += JsonKey("price_open") + JsonNumber(OrderGetDouble(ORDER_PRICE_OPEN), _Digits) + ",";
      item += JsonKey("price_current") + JsonNumber(OrderGetDouble(ORDER_PRICE_CURRENT), _Digits) + ",";
      item += JsonKey("sl") + JsonNumber(OrderGetDouble(ORDER_SL), _Digits) + ",";
      item += JsonKey("tp") + JsonNumber(OrderGetDouble(ORDER_TP), _Digits) + ",";
      item += JsonKey("state") + JsonString(OrderStateText(OrderGetInteger(ORDER_STATE))) + ",";
      item += JsonKey("time_setup") + StringFormat("%I64d", OrderGetInteger(ORDER_TIME_SETUP)) + ",";
      item += JsonKey("comment") + JsonString(OrderGetString(ORDER_COMMENT));
      item += "}";
      json += item;
   }

   json += "]";
   return json;
}

string JsonDeals()
{
   datetime now = TimeCurrent();
   datetime from = now - (datetime)(7 * 24 * 60 * 60);
   if(!HistorySelect(from, now))
      return "[]";

   string json = "[";
   bool first = true;
   int emitted = 0;
   int total = HistoryDealsTotal();

   for(int i=total-1; i>=0 && emitted<50; i--)
   {
      ulong ticket = HistoryDealGetTicket(i);
      if(ticket == 0)
         continue;
      if(HistoryDealGetString(ticket, DEAL_SYMBOL) != _Symbol)
         continue;
      if((long)HistoryDealGetInteger(ticket, DEAL_MAGIC) != InpMagic)
         continue;

      long entry = HistoryDealGetInteger(ticket, DEAL_ENTRY);
      if(entry != DEAL_ENTRY_OUT && entry != DEAL_ENTRY_OUT_BY && entry != DEAL_ENTRY_INOUT)
         continue;

      double profit = HistoryDealGetDouble(ticket, DEAL_PROFIT);
      double commission = HistoryDealGetDouble(ticket, DEAL_COMMISSION);
      double swap = HistoryDealGetDouble(ticket, DEAL_SWAP);

      if(!first)
         json += ",";
      first = false;

      string item = "{";
      item += JsonKey("ticket") + StringFormat("%I64u", ticket) + ",";
      item += JsonKey("order_ticket") + StringFormat("%I64u", (ulong)HistoryDealGetInteger(ticket, DEAL_ORDER)) + ",";
      item += JsonKey("magic") + StringFormat("%I64d", (long)HistoryDealGetInteger(ticket, DEAL_MAGIC)) + ",";
      item += JsonKey("symbol") + JsonString(HistoryDealGetString(ticket, DEAL_SYMBOL)) + ",";
      item += JsonKey("side") + JsonString(DealTypeText(HistoryDealGetInteger(ticket, DEAL_TYPE))) + ",";
      item += JsonKey("entry") + JsonString(DealEntryText(entry)) + ",";
      item += JsonKey("volume") + JsonNumber(HistoryDealGetDouble(ticket, DEAL_VOLUME), 2) + ",";
      item += JsonKey("price") + JsonNumber(HistoryDealGetDouble(ticket, DEAL_PRICE), _Digits) + ",";
      item += JsonKey("profit") + JsonNumber(profit, 2) + ",";
      item += JsonKey("commission") + JsonNumber(commission, 2) + ",";
      item += JsonKey("swap") + JsonNumber(swap, 2) + ",";
      item += JsonKey("realized_total") + JsonNumber(profit + commission + swap, 2) + ",";
      item += JsonKey("reason") + JsonString(DealReasonText(HistoryDealGetInteger(ticket, DEAL_REASON))) + ",";
      item += JsonKey("time") + StringFormat("%I64d", HistoryDealGetInteger(ticket, DEAL_TIME)) + ",";
      item += JsonKey("comment") + JsonString(HistoryDealGetString(ticket, DEAL_COMMENT));
      item += "}";
      json += item;
      emitted++;
   }

   json += "]";
   return json;
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
   json += JsonKey("execution_locked") + "true,";
   json += JsonKey("execution_ready") + "false,";
   json += JsonKey("reason") + JsonString(GuardianReason()) + ",";
   json += JsonKey("demo_only") + "true,";
   json += JsonKey("demo_account") + JsonBool(demo_account) + ",";
   json += JsonKey("terminal_connected") + JsonBool(terminal_connected) + ",";
   json += JsonKey("terminal_trade_allowed") + JsonBool(terminal_trade_allowed) + ",";
   json += JsonKey("mql_trade_allowed") + JsonBool(mql_trade_allowed) + ",";
   json += JsonKey("max_volume") + JsonNumber(InpMaxVolume, 2) + ",";
   json += JsonKey("max_daily_loss_pct") + JsonNumber(InpMaxDailyLossPct, 2) + ",";
   json += JsonKey("daily_realized") + JsonNumber(realized, 2) + ",";
   json += JsonKey("daily_loss_limit") + JsonNumber(loss_limit, 2) + ",";
   json += JsonKey("max_open_positions") + IntegerToString(InpMaxOpenPositions) + ",";
   json += JsonKey("own_positions") + IntegerToString(OwnPositionsCount()) + ",";
   json += JsonKey("own_orders") + IntegerToString(OwnOrdersCount());
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
   json += JsonKey("time") + StringFormat("%I64d", (long)rates[0].time) + ",";
   json += JsonKey("open") + JsonNumber(rates[0].open, _Digits) + ",";
   json += JsonKey("high") + JsonNumber(rates[0].high, _Digits) + ",";
   json += JsonKey("low") + JsonNumber(rates[0].low, _Digits) + ",";
   json += JsonKey("close") + JsonNumber(rates[0].close, _Digits) + ",";
   json += JsonKey("tick_volume") + StringFormat("%I64d", (long)rates[0].tick_volume);
   json += "}";
   return json;
}

string JsonBars()
{
   string json = "{";
   json += JsonKey("M1")  + JsonBar(PERIOD_M1)  + ",";
   json += JsonKey("M3")  + JsonBar(PERIOD_M3)  + ",";
   json += JsonKey("M5")  + JsonBar(PERIOD_M5)  + ",";
   json += JsonKey("M15") + JsonBar(PERIOD_M15) + ",";
   json += JsonKey("M30") + JsonBar(PERIOD_M30) + ",";
   json += JsonKey("H1")  + JsonBar(PERIOD_H1)  + ",";
   json += JsonKey("H2")  + JsonBar(PERIOD_H2)  + ",";
   json += JsonKey("H4")  + JsonBar(PERIOD_H4);
   json += "}";
   return json;
}

string BuildHelloPayload()
{
   string json = "{";
   json += JsonKey("bridge_version") + JsonString("0.3.0-task003") + ",";
   json += JsonKey("component") + JsonString("mt5-bridge") + ",";
   json += JsonKey("symbol") + JsonString(_Symbol) + ",";
   json += JsonKey("magic") + StringFormat("%I64d", InpMagic) + ",";
   json += JsonKey("execution_locked") + "true";
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
   json += JsonKey("bridge_version") + JsonString("0.3.0-task003") + ",";
   json += JsonKey("symbol") + JsonString(_Symbol) + ",";
   json += JsonKey("magic") + StringFormat("%I64d", InpMagic) + ",";
   json += JsonKey("terminal_connected") + JsonBool((bool)TerminalInfoInteger(TERMINAL_CONNECTED)) + ",";
   json += JsonKey("account_trade_mode") + JsonString(AccountTradeModeText()) + ",";
   json += JsonKey("account_login") + StringFormat("%I64d", AccountInfoInteger(ACCOUNT_LOGIN)) + ",";
   json += JsonKey("account_currency") + JsonString(AccountInfoString(ACCOUNT_CURRENCY)) + ",";
   json += JsonKey("leverage") + StringFormat("%I64d", AccountInfoInteger(ACCOUNT_LEVERAGE)) + ",";
   json += JsonKey("balance") + JsonNumber(AccountInfoDouble(ACCOUNT_BALANCE), 2) + ",";
   json += JsonKey("equity") + JsonNumber(AccountInfoDouble(ACCOUNT_EQUITY), 2) + ",";
   json += JsonKey("margin_free") + JsonNumber(AccountInfoDouble(ACCOUNT_MARGIN_FREE), 2) + ",";
   json += JsonKey("bid") + JsonNumber(tick.bid, _Digits) + ",";
   json += JsonKey("ask") + JsonNumber(tick.ask, _Digits) + ",";
   json += JsonKey("spread_points") + JsonNumber(spread_points, 2) + ",";
   json += JsonKey("digits") + IntegerToString(_Digits) + ",";
   json += JsonKey("point") + JsonNumber(point, 10) + ",";
   json += JsonKey("volume_min") + JsonNumber(SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN), 2) + ",";
   json += JsonKey("volume_max") + JsonNumber(SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX), 2) + ",";
   json += JsonKey("volume_step") + JsonNumber(SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP), 2) + ",";
   json += JsonKey("tick_size") + JsonNumber(SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE), 10) + ",";
   json += JsonKey("tick_value") + JsonNumber(SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE), 8) + ",";
   json += JsonKey("stops_level") + IntegerToString((int)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL)) + ",";
   json += JsonKey("freeze_level") + IntegerToString((int)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_FREEZE_LEVEL)) + ",";
   json += JsonKey("positions_count") + IntegerToString(OwnPositionsCount()) + ",";
   json += JsonKey("orders_count") + IntegerToString(OwnOrdersCount()) + ",";
   json += JsonKey("own_daily_realized") + JsonNumber(OwnDailyRealized(), 2) + ",";
   json += JsonKey("positions") + JsonPositions() + ",";
   json += JsonKey("orders") + JsonOrders() + ",";
   json += JsonKey("deals") + JsonDeals() + ",";
   json += JsonKey("guardian") + JsonGuardian() + ",";
   json += JsonKey("bars") + JsonBars();
   json += "}";
   return json;
}

string BuildEnvelope(string message_type, string request_id, string payload_json)
{
   string json = "{";
   json += JsonKey("schema_version") + "1,";
   json += JsonKey("type") + JsonString(message_type) + ",";
   json += JsonKey("request_id") + JsonString(request_id) + ",";
   json += JsonKey("sent_at_utc") + JsonString(IsoUtcNow()) + ",";
   json += JsonKey("payload") + payload_json;
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

   string request_token = JsonKey("request_id") + JsonString(request_id);
   string type_token = JsonKey("type") + JsonString(expected_type);

   if(StringFind(response_text, request_token) < 0 ||
      StringFind(response_text, type_token) < 0)
   {
      Print("XAUPY_BRIDGE invalid response: ", response_text);
      CloseSocket();
      return false;
   }

   if(StringFind(response_text, JsonKey("execution_enabled") + "true") >= 0 ||
      StringFind(response_text, JsonKey("trading_enabled") + "true") >= 0)
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

   Print("XAUPY_BRIDGE Task 009 initialized. ORDER BOOK ACTIVE; BROKER EXECUTION LOCKED.");
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
   // Task 009 remains timer-based and read-only. No broker trading logic exists here.
}
