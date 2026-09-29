#property strict
#property version   "1.022"
#property description "XAUPY data and execution bridge. Account-bound user control with broker confirmation."

input string InpHost               = "127.0.0.1";
input uint   InpPort               = 39421;
input uint   InpConnectTimeoutMs   = 1500;
input uint   InpSocketTimeoutMs    = 1500;
input uint   InpTimerMs            = 250;
input long   InpMagic              = 991188;
input double InpMaxVolume          = 0.10;
input double InpMaxDailyLossPct    = 2.00;
input int    InpMaxOpenPositions   = 1;

#include "XAUPY_DemoOnce.mqh"
#include "XAUPY_Execution.mqh"
#include "XAUPY_MarketServices.mqh"

int  g_socket = INVALID_HANDLE;
bool g_handshake_ok = false;
long g_sequence = 0;
ulong g_last_connect_attempt_ms = 0;
ulong g_last_history_ms = 0;
ulong g_last_network_error_log_ms = 0;
ulong g_last_handshake_log_ms = 0;
const int HISTORY_BAR_LIMIT = 256;
const int TICK_BATCH_LIMIT = 1000;
string g_tick_stream_id = "";
long g_tick_batch_sequence = 0;
long g_tick_cursor_msc = 0;
int g_tick_cursor_count = 0;

void LogNetworkError(string operation, int error)
{
   ulong now_ms = GetTickCount64();
   if(g_last_network_error_log_ms != 0 && now_ms - g_last_network_error_log_ms < 10000)
      return;
   g_last_network_error_log_ms = now_ms;
   if(error == 4014)
      Print("XAUPY_BRIDGE permission denied (4014): run as an Expert Advisor and allow 127.0.0.1 in MT5 Tools > Options > Expert Advisors. Operation=", operation);
   else
      Print("XAUPY_BRIDGE ", operation, " failed err=", error, "; reconnect requires fresh account data before user-authorized execution.");
}

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

      long type=HistoryDealGetInteger(ticket,DEAL_TYPE);
      if(type!=DEAL_TYPE_BUY && type!=DEAL_TYPE_SELL)
         continue;

      realized += HistoryDealGetDouble(ticket, DEAL_PROFIT);
      realized += HistoryDealGetDouble(ticket, DEAL_COMMISSION);
      realized += HistoryDealGetDouble(ticket, DEAL_SWAP);
      realized += HistoryDealGetDouble(ticket, DEAL_FEE);
   }
   return realized;
}

string JsonPositions(bool all_symbols=false)
{
   string json = "[";
   bool first = true;
   int total = PositionsTotal();

   for(int i=0; i<total; i++)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if(!all_symbols && PositionGetString(POSITION_SYMBOL) != _Symbol)
         continue;
      if((long)PositionGetInteger(POSITION_MAGIC) != InpMagic)
         continue;

      if(!first)
         json += ",";
      first = false;

      int digits = (int)SymbolInfoInteger(PositionGetString(POSITION_SYMBOL), SYMBOL_DIGITS);
      long identifier=PositionGetInteger(POSITION_IDENTIFIER);
      ulong entry_order=0;
      double initial_sl=0,initial_tp=0;
      if(HistorySelectByPosition(identifier))
      {
         for(int j=0;j<HistoryDealsTotal();j++)
         {
            ulong deal=HistoryDealGetTicket(j);
            if(deal && HistoryDealGetInteger(deal,DEAL_ENTRY)==DEAL_ENTRY_IN)
            {
               entry_order=(ulong)HistoryDealGetInteger(deal,DEAL_ORDER);
               if(HistoryOrderSelect(entry_order))
               {
                  initial_sl=HistoryOrderGetDouble(entry_order,ORDER_SL);
                  initial_tp=HistoryOrderGetDouble(entry_order,ORDER_TP);
               }
               break;
            }
         }
      }

      string item = "{";
      item += JsonKey("ticket") + StringFormat("%I64u", ticket) + ",";
      item += JsonKey("position_identifier") + StringFormat("%I64d",identifier) + ",";
      item += JsonKey("entry_order") + StringFormat("%I64u",entry_order) + ",";
      item += JsonKey("initial_sl") + JsonNumber(initial_sl,digits) + ",";
      item += JsonKey("initial_tp") + JsonNumber(initial_tp,digits) + ",";
      item += JsonKey("magic") + StringFormat("%I64d", (long)PositionGetInteger(POSITION_MAGIC)) + ",";
      item += JsonKey("symbol") + JsonString(PositionGetString(POSITION_SYMBOL)) + ",";
      item += JsonKey("side") + JsonString(PositionTypeText(PositionGetInteger(POSITION_TYPE))) + ",";
      item += JsonKey("volume") + JsonNumber(PositionGetDouble(POSITION_VOLUME), 8) + ",";
      item += JsonKey("price_open") + JsonNumber(PositionGetDouble(POSITION_PRICE_OPEN), digits) + ",";
      item += JsonKey("price_current") + JsonNumber(PositionGetDouble(POSITION_PRICE_CURRENT), digits) + ",";
      item += JsonKey("sl") + JsonNumber(PositionGetDouble(POSITION_SL), digits) + ",";
      item += JsonKey("tp") + JsonNumber(PositionGetDouble(POSITION_TP), digits) + ",";
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
      item += JsonKey("volume_initial") + JsonNumber(OrderGetDouble(ORDER_VOLUME_INITIAL), 8) + ",";
      item += JsonKey("volume_current") + JsonNumber(OrderGetDouble(ORDER_VOLUME_CURRENT), 8) + ",";
      item += JsonKey("expiration") + StringFormat("%I64d",OrderGetInteger(ORDER_TIME_EXPIRATION)) + ",";
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

double HistoryPositionEntryPrice(long position_id, string symbol, ulong exit_ticket, double &entry_cost)
{
   entry_cost=0;
   if(!HistorySelectByPosition((ulong)position_id)) return 0;
   double volume=0, average=0, costs=0;
   int total = HistoryDealsTotal();
   for(int i=0; i<total; i++)
   {
      ulong deal_ticket = HistoryDealGetTicket(i);
      if(deal_ticket == 0)
         continue;
      if((long)HistoryDealGetInteger(deal_ticket, DEAL_POSITION_ID) != position_id)
         continue;
      if(HistoryDealGetString(deal_ticket, DEAL_SYMBOL) != symbol)
         continue;
      long entry = HistoryDealGetInteger(deal_ticket, DEAL_ENTRY);
      double lot=HistoryDealGetDouble(deal_ticket,DEAL_VOLUME);
      double fee=HistoryDealGetDouble(deal_ticket,DEAL_COMMISSION)+HistoryDealGetDouble(deal_ticket,DEAL_FEE);
      if(deal_ticket==exit_ticket)
      {
         entry_cost=volume>0 ? costs*MathMin(lot,volume)/volume : 0;
         return volume>0 ? average : 0;
      }
      if(entry==DEAL_ENTRY_IN && lot>0)
      {
         average=(average*volume+HistoryDealGetDouble(deal_ticket,DEAL_PRICE)*lot)/(volume+lot);
         volume+=lot; costs+=fee;
      }
      else if(entry==DEAL_ENTRY_OUT || entry==DEAL_ENTRY_OUT_BY || entry==DEAL_ENTRY_INOUT)
      {
         double closed=MathMin(lot,volume);
         if(volume>0) costs*=1-closed/volume;
         volume-=closed;
         if(entry==DEAL_ENTRY_INOUT && lot>closed)
         {
            volume=lot-closed; average=HistoryDealGetDouble(deal_ticket,DEAL_PRICE);
            costs=fee*volume/lot;
         }
      }
   }
   return 0.0;
}

string JsonDeals(bool all_symbols=false)
{
   static datetime cached_at=0;
   static string cached_symbol="[]", cached_all="[]";
   datetime now = TimeCurrent();
   if(cached_at && now-cached_at<10) return all_symbols ? cached_all : cached_symbol;
   datetime from = now - (datetime)(7 * 24 * 60 * 60);
   if(!HistorySelect(from, now))
      return "[]";

   string json = "[";
   bool first = true;
   int emitted = 0;
   int total = HistoryDealsTotal();
   ulong selected[];
   // Copy tickets before per-position lookups replace MT5's history selection.
   for(int i=total-1;i>=0 && ArraySize(selected)<100;i--)
   {
      ulong ticket=HistoryDealGetTicket(i);
      long entry=HistoryDealGetInteger(ticket,DEAL_ENTRY);
      if(HistoryDealGetInteger(ticket,DEAL_MAGIC)!=InpMagic || (entry!=DEAL_ENTRY_OUT && entry!=DEAL_ENTRY_OUT_BY && entry!=DEAL_ENTRY_INOUT)) continue;
      int n=ArraySize(selected); ArrayResize(selected,n+1); selected[n]=ticket;
   }

   for(int i=0; i<ArraySize(selected) && emitted<50; i++)
   {
      ulong ticket = selected[i];
      if(!HistoryDealSelect(ticket)) continue;
      if(ticket == 0)
         continue;
      if(!all_symbols && HistoryDealGetString(ticket, DEAL_SYMBOL) != _Symbol)
         continue;
      if((long)HistoryDealGetInteger(ticket, DEAL_MAGIC) != InpMagic)
         continue;

      long entry = HistoryDealGetInteger(ticket, DEAL_ENTRY);
      if(entry != DEAL_ENTRY_OUT && entry != DEAL_ENTRY_OUT_BY && entry != DEAL_ENTRY_INOUT)
         continue;

      double profit = HistoryDealGetDouble(ticket, DEAL_PROFIT);
      double commission = HistoryDealGetDouble(ticket, DEAL_COMMISSION)+HistoryDealGetDouble(ticket,DEAL_FEE);
      double swap = HistoryDealGetDouble(ticket, DEAL_SWAP);
      long position_id = HistoryDealGetInteger(ticket, DEAL_POSITION_ID);
      string symbol = HistoryDealGetString(ticket, DEAL_SYMBOL);
      int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
      double entry_cost=0;
      double price_in = HistoryPositionEntryPrice(position_id, symbol, ticket, entry_cost);
      commission+=entry_cost;
      double price_out = HistoryDealGetDouble(ticket, DEAL_PRICE);

      if(!first)
         json += ",";
      first = false;

      string item = "{";
      item += JsonKey("ticket") + StringFormat("%I64u", ticket) + ",";
      item += JsonKey("order_ticket") + StringFormat("%I64u", (ulong)HistoryDealGetInteger(ticket, DEAL_ORDER)) + ",";
      item += JsonKey("magic") + StringFormat("%I64d", (long)HistoryDealGetInteger(ticket, DEAL_MAGIC)) + ",";
      item += JsonKey("symbol") + JsonString(HistoryDealGetString(ticket, DEAL_SYMBOL)) + ",";
      item += JsonKey("side") + JsonString(HistoryDealGetInteger(ticket, DEAL_TYPE)==DEAL_TYPE_SELL ? "BUY" : "SELL") + ",";
      item += JsonKey("entry") + JsonString(DealEntryText(entry)) + ",";
      item += JsonKey("volume") + JsonNumber(HistoryDealGetDouble(ticket, DEAL_VOLUME), 8) + ",";
      item += JsonKey("price_in") + JsonNumber(price_in, digits) + ",";
      item += JsonKey("price_out") + JsonNumber(price_out, digits) + ",";
      item += JsonKey("sl") + JsonNumber(HistoryDealGetDouble(ticket, DEAL_SL), digits) + ",";
      item += JsonKey("tp") + JsonNumber(HistoryDealGetDouble(ticket, DEAL_TP), digits) + ",";
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
   if(all_symbols) { cached_all=json; cached_at=now; } else cached_symbol=json;
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
   if(!g_full_enabled)
      return "USER_STOPPED";

   if(!TerminalInfoInteger(TERMINAL_CONNECTED))
      return "TERMINAL_DISCONNECTED";

   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED))
      return "TERMINAL_TRADE_NOT_ALLOWED";

   if(!MQLInfoInteger(MQL_TRADE_ALLOWED))
      return "MQL_TRADE_NOT_ALLOWED";

   if(!AccountInfoInteger(ACCOUNT_TRADE_ALLOWED) || !AccountInfoInteger(ACCOUNT_TRADE_EXPERT))
      return "ACCOUNT_TRADE_NOT_ALLOWED";

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
   json += JsonKey("execution_locked") + JsonBool(!g_full_enabled) + ",";
   json += JsonKey("execution_ready") + JsonBool(GuardianReason()=="READY") + ",";
   json += JsonKey("reason") + JsonString(GuardianReason()) + ",";
   json += JsonKey("demo_only") + "false,";
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
   json += JsonKey("H4")  + JsonBar(PERIOD_H4) + ",";
   json += JsonKey("D1") + JsonBar(PERIOD_D1);
   json += "}";
   return json;
}

string JsonHistoricalRate(const MqlRates &rate)
{
   string json = "{";
   json += JsonKey("time") + StringFormat("%I64d", (long)rate.time) + ",";
   json += JsonKey("open") + JsonNumber(rate.open, _Digits) + ",";
   json += JsonKey("high") + JsonNumber(rate.high, _Digits) + ",";
   json += JsonKey("low") + JsonNumber(rate.low, _Digits) + ",";
   json += JsonKey("close") + JsonNumber(rate.close, _Digits) + ",";
   json += JsonKey("tick_volume") + StringFormat("%I64d", (long)rate.tick_volume);
   return json + "}";
}

// Latest bars and warm-up arrays are captured from the same CopyRates result.
// Shift 1 excludes the forming candle. MT5's original broker timestamps remain
// unchanged; neither ticks nor missing candles are invented.
string JsonBarsWithHistory(string &history_json)
{
   ENUM_TIMEFRAMES frames[9] = {PERIOD_M1, PERIOD_M3, PERIOD_M5, PERIOD_M15,
                                PERIOD_M30, PERIOD_H1, PERIOD_H2, PERIOD_H4, PERIOD_D1};
   string labels[9] = {"M1", "M3", "M5", "M15", "M30", "H1", "H2", "H4", "D1"};
   string latest_json = "{";
   history_json = "{";
   for(int index = 0; index < 9; index++)
   {
      if(index > 0) { latest_json += ","; history_json += ","; }
      MqlRates rates[];
      ArraySetAsSeries(rates, false);
      int copied = CopyRates(_Symbol, frames[index], 1, HISTORY_BAR_LIMIT, rates);
      latest_json += JsonKey(labels[index]);
      latest_json += copied > 0 ? JsonHistoricalRate(rates[copied - 1]) : "null";
      history_json += JsonKey(labels[index]) + "[";
      for(int i = 0; i < copied; i++)
      {
         if(i > 0) history_json += ",";
         history_json += JsonHistoricalRate(rates[i]);
      }
      history_json += "]";
   }
   history_json += "}";
   return latest_json + "}";
}

string BuildHelloPayload()
{
   string json = "{";
   json += JsonKey("bridge_version") + JsonString("1.022") + ",";
   json += JsonKey("execution_capable") + "true,";
   json += JsonKey("component") + JsonString("mt5-bridge") + ",";
   json += JsonKey("symbol") + JsonString(_Symbol) + ",";
   json += JsonKey("magic") + StringFormat("%I64d", InpMagic) + ",";
   json += JsonKey("account_login") + StringFormat("%I64d",AccountInfoInteger(ACCOUNT_LOGIN)) + ",";
   json += JsonKey("account_server") + JsonString(AccountInfoString(ACCOUNT_SERVER)) + ",";
   json += JsonKey("bridge_session_id") + JsonString(g_bridge_session_id) + ",";
   json += JsonKey("demo_once_capable") + "true,";
   json += JsonKey("demo_once_consumed") + JsonBool(OnceBudgetConsumed()) + ",";
   json += JsonKey("execution_locked") + "true";
   json += "}";
   return json;
}

string JsonExecutionCapabilities()
{
   long mode=SymbolInfoInteger(_Symbol,SYMBOL_TRADE_MODE);
   long orders=SymbolInfoInteger(_Symbol,SYMBOL_ORDER_MODE);
   bool hedging=AccountInfoInteger(ACCOUNT_MARGIN_MODE)==ACCOUNT_MARGIN_MODE_RETAIL_HEDGING;
   bool allowed=TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) && MQLInfoInteger(MQL_TRADE_ALLOWED) &&
                AccountInfoInteger(ACCOUNT_TRADE_ALLOWED) && AccountInfoInteger(ACCOUNT_TRADE_EXPERT);
   string json="{"+JsonKey("schema_version")+"1,";
   json+=JsonKey("trade_allowed")+JsonBool(allowed)+",";
   json+=JsonKey("allow_buy")+JsonBool(mode==SYMBOL_TRADE_MODE_FULL || mode==SYMBOL_TRADE_MODE_LONGONLY)+",";
   json+=JsonKey("allow_sell")+JsonBool(mode==SYMBOL_TRADE_MODE_FULL || mode==SYMBOL_TRADE_MODE_SHORTONLY)+",";
   json+=JsonKey("market_orders")+JsonBool((orders&SYMBOL_ORDER_MARKET)!=0)+",";
   json+=JsonKey("stop_orders")+JsonBool((orders&SYMBOL_ORDER_STOP)!=0)+",";
   json+=JsonKey("limit_orders")+JsonBool((orders&SYMBOL_ORDER_LIMIT)!=0)+",";
   json+=JsonKey("server_sl")+JsonBool((orders&SYMBOL_ORDER_SL)!=0)+",";
   json+=JsonKey("server_tp")+JsonBool((orders&SYMBOL_ORDER_TP)!=0)+",";
   json+=JsonKey("specified_expiration")+JsonBool((SymbolInfoInteger(_Symbol,SYMBOL_EXPIRATION_MODE)&SYMBOL_EXPIRATION_SPECIFIED)!=0)+",";
   json+=JsonKey("netting_symbol_exposed")+JsonBool(!hedging && PositionSelect(_Symbol))+",";
   json+=JsonKey("margin_mode")+JsonString(hedging ? "HEDGING" : "NETTING");
   return json+"}";
}

string BuildSnapshotPayload(bool include_history=false)
{
   MqlTick tick;
   ZeroMemory(tick);
   SymbolInfoTick(_Symbol, tick);

   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   double spread_points = 0.0;
   if(point > 0.0)
      spread_points = (tick.ask - tick.bid) / point;

   string history_json = "";
   string latest_bars = include_history ? JsonBarsWithHistory(history_json) : JsonBars();
   string json = "{";
   json += JsonKey("bridge_version") + JsonString("1.022") + ",";
   json += JsonKey("execution_capable") + "true,";
   json += JsonKey("symbol") + JsonString(_Symbol) + ",";
   json += JsonKey("magic") + StringFormat("%I64d", InpMagic) + ",";
   json += JsonKey("terminal_connected") + JsonBool((bool)TerminalInfoInteger(TERMINAL_CONNECTED)) + ",";
   json += JsonKey("account_trade_mode") + JsonString(AccountTradeModeText()) + ",";
   json += JsonKey("account_login") + StringFormat("%I64d", AccountInfoInteger(ACCOUNT_LOGIN)) + ",";
   json += JsonKey("account_server") + JsonString(AccountInfoString(ACCOUNT_SERVER)) + ",";
   json += JsonKey("bridge_session_id") + JsonString(g_bridge_session_id) + ",";
   json += JsonKey("demo_once_capable") + "true,";
   json += JsonKey("demo_once_consumed") + JsonBool(OnceBudgetConsumed()) + ",";
   json += JsonKey("demo_once_status") + JsonString(g_once_has_result ? g_once_result.status : OnceBudgetConsumed() ? "CONSUMED" : "AVAILABLE") + ",";
   json += JsonKey("demo_once_guard") + DemoOnceGuardJson() + ",";
   json += JsonKey("account_currency") + JsonString(AccountInfoString(ACCOUNT_CURRENCY)) + ",";
   json += JsonKey("leverage") + StringFormat("%I64d", AccountInfoInteger(ACCOUNT_LEVERAGE)) + ",";
   json += JsonKey("balance") + JsonNumber(AccountInfoDouble(ACCOUNT_BALANCE), 2) + ",";
   json += JsonKey("equity") + JsonNumber(AccountInfoDouble(ACCOUNT_EQUITY), 2) + ",";
   json += JsonKey("margin_free") + JsonNumber(AccountInfoDouble(ACCOUNT_MARGIN_FREE), 2) + ",";
   json += JsonKey("bid") + JsonNumber(tick.bid, _Digits) + ",";
   json += JsonKey("ask") + JsonNumber(tick.ask, _Digits) + ",";
   json += JsonKey("tick_time_msc") + StringFormat("%I64d", tick.time_msc) + ",";
   json += JsonKey("spread_points") + JsonNumber(spread_points, 2) + ",";
   json += JsonKey("digits") + IntegerToString(_Digits) + ",";
   json += JsonKey("point") + JsonNumber(point, 10) + ",";
   json += JsonKey("volume_min") + JsonNumber(SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN), 8) + ",";
   json += JsonKey("volume_max") + JsonNumber(SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX), 8) + ",";
   json += JsonKey("volume_step") + JsonNumber(SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP), 8) + ",";
   json += JsonKey("tick_size") + JsonNumber(SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE), 10) + ",";
   json += JsonKey("tick_value") + JsonNumber(SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE), 8) + ",";
   json += JsonKey("tick_value_loss") + JsonNumber(SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE_LOSS), 8) + ",";
   json += JsonKey("stops_level") + IntegerToString((int)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL)) + ",";
   json += JsonKey("freeze_level") + IntegerToString((int)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_FREEZE_LEVEL)) + ",";
   json += JsonKey("positions_count") + IntegerToString(OwnPositionsCount()) + ",";
   json += JsonKey("orders_count") + IntegerToString(OwnOrdersCount()) + ",";
   json += JsonKey("own_daily_realized") + JsonNumber(OwnDailyRealized(), 2) + ",";
   json += JsonKey("positions") + JsonPositions() + ",";
   json += JsonKey("all_positions") + JsonPositions(true) + ",";
   json += JsonKey("orders") + JsonOrders() + ",";
   json += JsonKey("deals") + JsonDeals() + ",";
   json += JsonKey("all_deals") + JsonDeals(true) + ",";
   json += JsonKey("guardian") + JsonGuardian() + ",";
   json += JsonKey("execution_capabilities") + JsonExecutionCapabilities() + ",";
   json += JsonKey("server_time") + StringFormat("%I64d", (long)TimeTradeServer()) + ",";
   json += JsonKey("server_utc_offset_seconds") + StringFormat("%I64d", (long)MathRound((double)(TimeTradeServer()-TimeGMT())/60)*60) + ",";
   json += JsonKey("weekend_session_end") + StringFormat("%I64d",WeekendSessionEnd()) + ",";
   json += JsonKey("symbol_sessions") + JsonSymbolSessions() + ",";
   json += JsonKey("calendar") + g_calendar_json + ",";
   json += JsonKey("broker_ping_ms") + JsonNumber((double)TerminalInfoInteger(TERMINAL_PING_LAST)/1000.0,3) + ",";
   json += JsonKey("terminal_path") + JsonString(TerminalInfoString(TERMINAL_PATH)) + ",";
   json += JsonKey("terminal_data_path") + JsonString(TerminalInfoString(TERMINAL_DATA_PATH)) + ",";
   json += JsonKey("currency_base") + JsonString(SymbolInfoString(_Symbol,SYMBOL_CURRENCY_BASE)) + ",";
   json += JsonKey("currency_profit") + JsonString(SymbolInfoString(_Symbol,SYMBOL_CURRENCY_PROFIT)) + ",";
   json += JsonKey("indicator_probes") + JsonIndicatorProbes() + ",";
   json += JsonKey("bars") + latest_bars;
   if(include_history)
      json += "," + JsonKey("bar_history") + history_json;
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
   g_full_enabled = false;
   if(g_socket != INVALID_HANDLE)
   {
      SocketClose(g_socket);
      g_socket = INVALID_HANDLE;
   }

   g_handshake_ok = false;
   g_last_history_ms = 0;
   g_tick_stream_id = "";
   g_tick_cursor_msc = 0;
   g_tick_cursor_count = 0;
}

string TickBatchPayload()
{
   MqlTick latest;
   bool have_quote = SymbolInfoTick(_Symbol, latest);
   string reason = "";
   bool complete = true;
   if(g_tick_stream_id == "" || !have_quote || g_tick_cursor_msc == 0 ||
      latest.time_msc < g_tick_cursor_msc || latest.time_msc - g_tick_cursor_msc > 5000 ||
      g_tick_cursor_count > TICK_BATCH_LIMIT)
   {
      reason = g_tick_stream_id == "" ? "STREAM_BASELINE" : "CURSOR_GAP";
      g_tick_stream_id = NewRequestId();
      g_tick_batch_sequence = 0;
      g_tick_cursor_msc = have_quote ? latest.time_msc : 0;
      g_tick_cursor_count = 0;
      complete = false;
   }
   MqlTick ticks[];
   int copied = 0;
   int skip = g_tick_cursor_count;
   ulong started = GetTickCount64();
   ResetLastError();
   if(have_quote && g_tick_cursor_msc > 0)
      copied = CopyTicks(_Symbol, ticks, COPY_TICKS_ALL, (ulong)g_tick_cursor_msc,
                         (uint)(TICK_BATCH_LIMIT + skip + 1));
   int copy_error = GetLastError();
   // CopyTicks may synchronize terminal history. Never pretend a delayed or
   // partial request was continuous; bulk candle history runs in a separate process.
   if(!have_quote || copied < skip || copied < 0 || copy_error != 0 ||
      GetTickCount64() - started > 2000 ||
      (skip > 0 && (ticks[0].time_msc != g_tick_cursor_msc || ticks[skip-1].time_msc != g_tick_cursor_msc)))
   {
      complete = false;
      reason = "COPY_TICKS_GAP";
      copied = 0;
      skip = 0;
      g_tick_cursor_msc = 0;
      g_tick_cursor_count = 0;
   }
   int end = (int)MathMin(copied, skip + TICK_BATCH_LIMIT);
   string items = "[";
   for(int i=skip; i<end; i++)
   {
      if(i > skip) items += ",";
      items += "{" + JsonKey("time_msc") + StringFormat("%I64d", ticks[i].time_msc) + ",";
      items += JsonKey("bid") + JsonNumber(ticks[i].bid, _Digits) + ",";
      items += JsonKey("ask") + JsonNumber(ticks[i].ask, _Digits) + ",";
      items += JsonKey("last") + JsonNumber(ticks[i].last, _Digits) + ",";
      items += JsonKey("flags") + IntegerToString((int)ticks[i].flags) + "}";
      if(ticks[i].time_msc == g_tick_cursor_msc)
         g_tick_cursor_count++;
      else
      {
         g_tick_cursor_msc = ticks[i].time_msc;
         g_tick_cursor_count = 1;
      }
   }
   items += "]";
   g_tick_batch_sequence++;
   return "{" + JsonKey("symbol") + JsonString(_Symbol) + "," +
      JsonKey("server_time") + StringFormat("%I64d", (long)TimeTradeServer()) + "," +
      JsonKey("tick_batch") + "{" + JsonKey("stream_id") + JsonString(g_tick_stream_id) + "," +
      JsonKey("sequence") + StringFormat("%I64d", g_tick_batch_sequence) + "," +
      JsonKey("complete") + JsonBool(complete) + "," +
      JsonKey("gap_reason") + JsonString(reason) + "," + JsonKey("ticks") + items + "}}";
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
      LogNetworkError("socket create", GetLastError());
      return false;
   }

   ResetLastError();
   if(!SocketConnect(g_socket, InpHost, InpPort, InpConnectTimeoutMs))
   {
      LogNetworkError("connect", GetLastError());
      CloseSocket();
      return false;
   }

   return true;
}

bool ReadResponseLine(string &response_text)
{
   response_text = "";
   uchar response_bytes[];
   int total = 0;
   const int max_response_bytes = 1024 * 1024;
   ulong started_ms = GetTickCount64();
   while(!IsStopped() && GetTickCount64() - started_ms < InpSocketTimeoutMs)
   {
      if(!SocketIsConnected(g_socket))
      {
         LogNetworkError("read disconnected socket", 5273);
         return false;
      }
      ResetLastError();
      uint available = SocketIsReadable(g_socket);
      int readable_error = GetLastError();
      if(available == 0)
      {
         if(readable_error != 0)
         {
            LogNetworkError("socket readability", readable_error);
            return false;
         }
         Sleep(5);
         continue;
      }
      ulong elapsed_ms = GetTickCount64() - started_ms;
      if(elapsed_ms >= InpSocketTimeoutMs)
         break;
      uint remaining_ms = (uint)(InpSocketTimeoutMs - elapsed_ms);
      uint read_size = (uint)MathMin(available, 16384);
      uchar chunk[];
      int received = SocketRead(g_socket, chunk, read_size, remaining_ms);
      if(received <= 0)
      {
         LogNetworkError("socket read", GetLastError());
         return false;
      }
      int newline_at = -1;
      for(int i = 0; i < received; i++)
      {
         if(chunk[i] == 10) { newline_at = i; break; }
      }
      int append_count = newline_at >= 0 ? newline_at : received;
      if(total + append_count >= max_response_bytes)
      {
         LogNetworkError("oversize response frame", 5273);
         return false;
      }
      ArrayResize(response_bytes, total + append_count);
      if(append_count > 0)
         ArrayCopy(response_bytes, chunk, total, 0, append_count);
      total += append_count;
      if(newline_at >= 0)
      {
         // Decode only the complete frame; UTF-8 characters may cross packets.
         response_text = CharArrayToString(response_bytes, 0, total, CP_UTF8);
         return total > 0;
      }
   }
   LogNetworkError("response frame timeout", 5273);
   return false;
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
   if(send_len > 1024 * 1024)
   {
      Print("XAUPY_BRIDGE snapshot exceeds bounded IPC packet size");
      CloseSocket();
      return false;
   }
   int offset = 0;
   while(offset < send_len)
   {
      int chunk_size = (int)MathMin(16384, send_len - offset);
      uchar chunk[];
      ArrayResize(chunk, chunk_size);
      ArrayCopy(chunk, bytes, 0, offset, chunk_size);
      int sent = SocketSend(g_socket, chunk, (uint)chunk_size);
      if(sent <= 0)
      {
         LogNetworkError("socket send", GetLastError());
         CloseSocket();
         return false;
      }
      offset += sent;
   }

   if(!ReadResponseLine(response_text))
   {
      CloseSocket();
      return false;
   }

   COnceJson reply;
   int reply_payload=-1;
   if(!OnceValidateEnvelope(response_text,request_id,expected_type,reply,reply_payload))
   {
      LogNetworkError("invalid response correlation/type", 5273);
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
   DemoOnceReplayResult();
   ulong now_ms = GetTickCount64();
   if(g_last_handshake_log_ms == 0 || now_ms - g_last_handshake_log_ms >= 10000)
   {
      Print("XAUPY_BRIDGE handshake ready; trading follows the account-bound user mode in the app.");
      g_last_handshake_log_ms = now_ms;
   }
   return true;
}

int OnInit()
{
   MathSrand((int)(GetTickCount() ^ (uint)TimeLocal()));
   if(!DemoOnceParserSelfTest() || !FullParserSelfTest())
   {
      Print("XAUPY_DEMO_ONCE pure JSON self-test FAILED; EA initialization refused.");
      return INIT_FAILED;
   }
   DemoOnceInit();
   FullInit();

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

   Print("XAUPY_BRIDGE initialized. User execution mode is OFF until confirmed by the app.");
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   ReleaseIndicatorProbes();
   EventKillTimer();
   CloseSocket();
   Print("XAUPY_BRIDGE stopped reason=", reason);
}

void OnTimer()
{
   if(!EnsureHandshake())
      return;

   string response;
   DemoOncePoll();
   bool include_history = g_last_history_ms == 0 || GetTickCount64() - g_last_history_ms >= 60000;
   if(!SendRequest("bridge_snapshot",
                   BuildSnapshotPayload(include_history),
                   "bridge_snapshot_ack",
                   response))
   {
      return;
   }
   if(include_history)
      g_last_history_ms = GetTickCount64();
   DemoOnceHandleAck(response);
   FullHandleAck(response);
   // Closed bars precede ticks so Python can replay each event without looking ahead.
   if(!SendRequest("bridge_ticks", TickBatchPayload(), "bridge_ticks_ack", response)) return;
   DemoOnceHandleAck(response);
   FullHandleAck(response);
   FullPoll();
   // Reconnect/restart reconciliation needs this connection's fresh identity snapshot first.
   // A rejected result stays pending and can never prevent the next snapshot/tick update.
   if(g_once_report_pending && SendRequest("bridge_demo_once_result",g_once_report,"bridge_demo_once_result_ack",response))
   {
      if(DemoOnceResultAckAccepted(response)) g_once_report_pending=false;
   }
   RefreshCalendar();
}

void OnTick()
{
   // OnTick can coalesce ticks. The timer uses the ordered CopyTicks database instead.
}
