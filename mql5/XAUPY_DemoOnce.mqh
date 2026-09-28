#ifndef XAUPY_DEMO_ONCE_MQH
#define XAUPY_DEMO_ONCE_MQH
#include "XAUPY_StrictJson.mqh"

struct DemoOnceCommand
{
   string kind,attempt_id,account_server,symbol,profile_hash,bridge_session_id,side;
   long account_login,magic,max_deviation_points,issued_server_time,expires_server_time,signal_sequence,signal_bar_time;
   double volume,reference_price,sl,tp,max_spread_price_units,max_loss_money;
};
struct DemoOnceResult
{
   DemoOnceCommand command;
   bool order_send_called;
   uint retcode,retcode_external;
   ulong order_ticket,deal_ticket;
   double filled_volume,fill_price,sl,tp;
   string status,reason;
};
struct DemoHistoryPosition { long id,last_exit; double net; bool has_exit; };
struct DemoOnceGuard
{
   bool history_complete,account_trade_allowed,account_expert_allowed;
   long broker_day_start,trades_today,consecutive_losses,last_exit_time;
   double day_start_balance,daily_realized;
   int symbol_positions,symbol_orders;
};

string g_bridge_session_id="";
string g_once_scope="";
string g_once_report="";
string g_once_persisted_report="";
bool g_once_report_pending=false;
bool g_once_consumed=false;
bool g_once_has_result=false;
DemoOnceResult g_once_result;

bool OnceHex(string value,int length)
{
   if(StringLen(value)!=length) return false;
   for(int i=0;i<length;i++) { ushort c=value[i]; if(!((c>=48&&c<=57)||(c>=65&&c<=70)||(c>=97&&c<=102))) return false; }
   return true;
}
bool OnceUuid(string value)
{
   if(StringLen(value)!=36 || value[8]!=45 || value[13]!=45 || value[18]!=45 || value[23]!=45) return false;
   StringReplace(value,"-",""); return OnceHex(value,32);
}
string OnceScope()
{
   string identity=StringFormat("%I64d",AccountInfoInteger(ACCOUNT_LOGIN))+"|"+AccountInfoString(ACCOUNT_SERVER)+"|"+_Symbol;
   uchar bytes[],key[],digest[]; int count=StringToCharArray(identity,bytes,0,WHOLE_ARRAY,CP_UTF8);
   if(count<=1) return ""; ArrayResize(bytes,count-1);
   if(CryptEncode(CRYPT_HASH_SHA256,bytes,key,digest)!=32) return "";
   string hash=""; for(int i=0;i<32;i++) hash+=StringFormat("%02X",digest[i]);
   return "XAUPY.DO."+StringSubstr(hash,0,48);
}
string OnceFile(string suffix) { return "XAUPY\\"+g_once_scope+suffix; }
bool OnceWrite(string path,string json)
{
   // Binary UTF-8 files avoid codepage changes in broker server names.
   uchar bytes[]; int count=StringToCharArray(json,bytes,0,WHOLE_ARRAY,CP_UTF8)-1;
   if(count<=0) return false;
   int handle=FileOpen(path,FILE_WRITE|FILE_BIN);
   if(handle==INVALID_HANDLE) return false;
   uint written=FileWriteArray(handle,bytes,0,count);
   FileFlush(handle); FileClose(handle);
   return written==(uint)count;
}
bool OnceRead(string path,string &json)
{
   int handle=FileOpen(path,FILE_READ|FILE_BIN|FILE_SHARE_READ);
   if(handle==INVALID_HANDLE) return false;
   ulong size=FileSize(handle);
   if(size==0 || size>16384) { FileClose(handle); return false; }
   uchar bytes[]; uint read=FileReadArray(handle,bytes,0,(int)size); FileClose(handle);
   if(read!=(uint)size) return false;
   json=CharArrayToString(bytes,0,(int)size,CP_UTF8); return true;
}
bool OnceBudgetConsumed()
{
   if(g_once_scope=="") return true;
   // The permanent file survives the terminal's four-week global-variable expiry.
   return FileIsExist(OnceFile(".claim")) || FileIsExist(OnceFile(".result")) ||
      (GlobalVariableCheck(g_once_scope) && GlobalVariableGet(g_once_scope)!=0.0);
}
void DemoOnceInit()
{
   g_bridge_session_id=NewRequestId(); // Deliberately never reset by CloseSocket.
   g_bridge_session_id=Hex8((uint)(ChartID()^GetMicrosecondCount()^GetTickCount64()))+StringSubstr(g_bridge_session_id,8);
   StringToLower(g_bridge_session_id);
   g_once_scope=OnceScope(); g_once_consumed=OnceBudgetConsumed();
   string saved="";
   if(OnceRead(OnceFile(".result"),saved) || (!OnceBudgetConsumed() && OnceRead(OnceFile(".rejected"),saved)))
   {
      COnceJson document;
      string status,attempt,server,symbol; long account=0;
      if(document.Parse(saved) && document.nodes[0].type==ONCE_OBJECT &&
         document.String(0,"status",status) && document.String(0,"attempt_id",attempt) && OnceUuid(attempt) &&
         document.String(0,"account_server",server) && server==AccountInfoString(ACCOUNT_SERVER) &&
         document.String(0,"symbol",symbol) && symbol==_Symbol &&
         document.Long(0,"account_login",account) && account==AccountInfoInteger(ACCOUNT_LOGIN))
      {
         g_once_persisted_report=saved; g_once_report=saved; g_once_report_pending=true;
      }
   }
}
void DemoOnceReplayResult()
{
   if(g_once_persisted_report!="") { g_once_report=g_once_persisted_report; g_once_report_pending=true; }
}
bool OnceParseCommand(COnceJson &json,int node,DemoOnceCommand &command)
{
   ZeroMemory(command);
   if(node<0 || json.nodes[node].type!=ONCE_OBJECT || json.Count(node)!=20) return false;
   if(!json.String(node,"kind",command.kind) || command.kind!="DEMO_ONE_SHOT_MARKET" ||
      !json.String(node,"attempt_id",command.attempt_id) || !OnceUuid(command.attempt_id) ||
      !json.Long(node,"account_login",command.account_login) || command.account_login<=0 ||
      !json.String(node,"account_server",command.account_server) || StringLen(command.account_server)==0 || StringLen(command.account_server)>128 ||
      !json.String(node,"symbol",command.symbol) || StringLen(command.symbol)==0 || StringLen(command.symbol)>64 ||
      !json.Long(node,"magic",command.magic) || command.magic<=0 ||
      !json.String(node,"profile_hash",command.profile_hash) || !OnceHex(command.profile_hash,64) ||
      !json.String(node,"bridge_session_id",command.bridge_session_id) || !OnceUuid(command.bridge_session_id) ||
      !json.String(node,"side",command.side) || (command.side!="BUY" && command.side!="SELL") ||
      !json.Double(node,"volume",command.volume) || command.volume<=0 || command.volume>0.01 ||
      !json.Double(node,"reference_price",command.reference_price) || command.reference_price<=0 ||
      !json.Double(node,"sl",command.sl) || command.sl<=0 || !json.Double(node,"tp",command.tp) || command.tp<=0 ||
      !json.Long(node,"max_deviation_points",command.max_deviation_points) || command.max_deviation_points<0 || command.max_deviation_points>1000 ||
      !json.Double(node,"max_spread_price_units",command.max_spread_price_units) || command.max_spread_price_units<=0 ||
      !json.Double(node,"max_loss_money",command.max_loss_money) || command.max_loss_money<=0 ||
      !json.Long(node,"issued_server_time",command.issued_server_time) || command.issued_server_time<=0 ||
      !json.Long(node,"expires_server_time",command.expires_server_time) ||
      command.expires_server_time<=command.issued_server_time || command.expires_server_time-command.issued_server_time>5 ||
      !json.Long(node,"signal_sequence",command.signal_sequence) || command.signal_sequence<=0 ||
      !json.Long(node,"signal_bar_time",command.signal_bar_time) || command.signal_bar_time<=0 ||
      command.signal_bar_time>command.issued_server_time) return false;
   return true;
}
bool OnceValidateEnvelope(string text,string request_id,string expected_type,COnceJson &reply,int &payload)
{
   string id,type; long version=0;
   if(!reply.Parse(text) || reply.nodes[0].type!=ONCE_OBJECT ||
      !reply.String(0,"request_id",id) || id!=request_id || !reply.String(0,"type",type) || type!=expected_type ||
      !reply.Long(0,"schema_version",version) || version!=1) return false;
   payload=reply.Find(0,"payload");
   if(payload<0 || reply.nodes[payload].type!=ONCE_OBJECT) return false;
   bool execution=false,trading=false,capable=false;
   if((reply.Find(payload,"execution_enabled")>=0 && !reply.Bool(payload,"execution_enabled",execution)) ||
      (reply.Find(payload,"trading_enabled")>=0 && !reply.Bool(payload,"trading_enabled",trading))) return false;
   if((execution || trading) && (!reply.Bool(payload,"execution_capable",capable) || !capable)) return false;
   return true;
}
bool OnceTestCommand(string text)
{
   COnceJson json; DemoOnceCommand command;
   return json.Parse(text) && OnceParseCommand(json,0,command);
}
bool DemoOnceResultAckAccepted(string text)
{
   // Request correlation/type/schema have already been checked by SendRequest.
   COnceJson json; bool accepted=false;
   if(!json.Parse(text)) return false;
   int payload=json.Find(0,"payload");
   return payload>=0 && json.nodes[payload].type==ONCE_OBJECT && json.Bool(payload,"accepted",accepted) && accepted;
}
bool DemoOnceParserSelfTest()
{
   // Pure parser/contract fixtures: never call a broker API, network or file function.
   string valid="{\"kind\":\"DEMO_ONE_SHOT_MARKET\",\"attempt_id\":\"12345678-1234-4234-8234-123456789012\",\"account_login\":12345,\"account_server\":\"Demo\\u002dServer\",\"symbol\":\"XAUUSD\",\"magic\":991188,\"profile_hash\":\"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\",\"bridge_session_id\":\"12345678-1234-4234-8234-123456789013\",\"side\":\"BUY\",\"volume\":0.01,\"reference_price\":2000,\"sl\":1999,\"tp\":2002,\"max_deviation_points\":10,\"max_spread_price_units\":0.5,\"max_loss_money\":5,\"issued_server_time\":1700000000,\"expires_server_time\":1700000005,\"signal_sequence\":1,\"signal_bar_time\":1699999980}";
   int checks=0;
   if(!OnceTestCommand(valid)) return false; checks++;
   string bad=valid; StringReplace(bad,"\"volume\":0.01","\"volume\":0.01,\"volume\":0.01");
   if(OnceTestCommand(bad)) return false; checks++;
   bad=valid; StringReplace(bad,"\"volume\":0.01","\"volume\":NaN"); if(OnceTestCommand(bad)) return false; checks++;
   bad=valid; StringReplace(bad,"\"volume\":0.01","\"volume\":\"0.01\""); if(OnceTestCommand(bad)) return false; checks++;
   bad=valid; StringReplace(bad,"\"account_login\":12345","\"account_login\":12345.0"); if(OnceTestCommand(bad)) return false; checks++;
   bad=valid; StringReplace(bad,"\"account_login\":12345","\"account_login\":9223372036854775808"); if(OnceTestCommand(bad)) return false; checks++;
   bad=valid; StringReplace(bad,"\"volume\":0.01","\"volume\":0.02"); if(OnceTestCommand(bad)) return false; checks++;
   bad=valid; StringReplace(bad,"1700000005","1700000006"); if(OnceTestCommand(bad)) return false; checks++;
   if(OnceTestCommand(valid+" garbage")) return false; checks++;
   bad=valid; StringReplace(bad,"\"side\":\"BUY\"","\"side\":true"); if(OnceTestCommand(bad)) return false; checks++;
   bad=valid; StringReplace(bad,"\"volume\":0.01","\"volume\":0.01,\"extra\":1"); if(OnceTestCommand(bad)) return false; checks++;
   COnceJson json; string decoded;
   if(!json.Parse(valid) || !json.String(0,"account_server",decoded) || decoded!="Demo-Server") return false; checks++;
   if(json.Parse("{\"same\":1,\"sa\\u006de\":2}")) return false; checks++;
   if(json.Parse("{\"bad\":\"\\uD800\"}")) return false; checks++;
   string envelope="{\"schema_version\":1,\"request_id\":\"r1\",\"type\":\"bridge_snapshot_ack\",\"payload\":{\"execution_enabled\":false,\"trading_enabled\":false,\"demo_once_command\":"+valid+"}}";
   int payload=-1;
   if(!OnceValidateEnvelope(envelope,"r1","bridge_snapshot_ack",json,payload)) return false; checks++;
   if(OnceValidateEnvelope(envelope,"wrong","bridge_snapshot_ack",json,payload)) return false; checks++;
   if(OnceValidateEnvelope(envelope,"r1","bridge_ticks_ack",json,payload)) return false; checks++;
   bad=envelope; StringReplace(bad,"\"execution_enabled\":false","\"execution_enabled\":true");
   if(OnceValidateEnvelope(bad,"r1","bridge_snapshot_ack",json,payload)) return false; checks++;
   bad=envelope; StringReplace(bad,"\"trading_enabled\":false","\"trading_enabled\":\"false\"");
   if(OnceValidateEnvelope(bad,"r1","bridge_snapshot_ack",json,payload)) return false; checks++;
   if(!DemoOnceResultAckAccepted("{\"payload\":{\"accepted\":true}}")) return false; checks++;
   if(DemoOnceResultAckAccepted("{\"payload\":{\"accepted\":false}}")) return false; checks++;
   if(DemoOnceResultAckAccepted("{\"payload\":{\"accepted\":\"true\"}}")) return false; checks++;
   if(DemoOnceResultAckAccepted("{\"payload\":{}}")) return false; checks++;
   Print("XAUPY_DEMO_ONCE pure JSON self-test PASS: ",checks," checks; no broker/file/network operations.");
   return true;
}
string OnceResultJson(const DemoOnceResult &result)
{
   string json="{";
   json+=JsonKey("attempt_id")+JsonString(result.command.attempt_id)+",";
   json+=JsonKey("bridge_session_id")+JsonString(result.command.bridge_session_id)+",";
   json+=JsonKey("account_login")+StringFormat("%I64d",result.command.account_login)+",";
   json+=JsonKey("account_server")+JsonString(result.command.account_server)+",";
   json+=JsonKey("symbol")+JsonString(result.command.symbol)+",";
   json+=JsonKey("magic")+StringFormat("%I64d",result.command.magic)+",";
   json+=JsonKey("order_send_called")+JsonBool(result.order_send_called)+",";
   json+=JsonKey("retcode")+IntegerToString(result.retcode)+",";
   json+=JsonKey("retcode_external")+IntegerToString(result.retcode_external)+",";
   json+=JsonKey("order_ticket")+StringFormat("%I64u",result.order_ticket)+",";
   json+=JsonKey("deal_ticket")+StringFormat("%I64u",result.deal_ticket)+",";
   json+=JsonKey("filled_volume")+JsonNumber(result.filled_volume,8)+",";
   json+=JsonKey("fill_price")+JsonNumber(result.fill_price,10)+",";
   json+=JsonKey("sl")+JsonNumber(result.sl,10)+","+JsonKey("tp")+JsonNumber(result.tp,10)+",";
   json+=JsonKey("status")+JsonString(result.status)+","+JsonKey("reason")+JsonString(result.reason)+"}";
   return json;
}
void OncePublish(const DemoOnceResult &result,bool persist)
{
   string json=OnceResultJson(result);
   if(persist || !OnceBudgetConsumed())
   {
      // The already flushed claim is never removed, even if result persistence fails.
      // Pre-validation rejections have a separate replay file and do not consume a broker-send budget.
      string suffix=persist ? ".result" : ".rejected";
      if(OnceWrite(OnceFile(suffix+".tmp"),json) && FileMove(OnceFile(suffix+".tmp"),0,OnceFile(suffix),FILE_REWRITE))
         g_once_persisted_report=json;
      else Print("XAUPY_DEMO_ONCE result persistence failed; durable budget remains consumed, never retry.");
   }
   g_once_report=json; g_once_report_pending=true;
}
bool OnceAnyExposure(int &positions,int &orders)
{
   positions=0; orders=0;
   for(int i=0;i<PositionsTotal();i++)
   {
      if(PositionGetTicket(i)==0) return false;
      string symbol; if(!PositionGetString(POSITION_SYMBOL,symbol)) return false;
      if(symbol==_Symbol) positions++;
   }
   for(int i=0;i<OrdersTotal();i++)
   {
      if(OrderGetTicket(i)==0) return false;
      string symbol; if(!OrderGetString(ORDER_SYMBOL,symbol)) return false;
      if(symbol==_Symbol) orders++;
   }
   return true;
}
bool OncePositionStillOpen(long id,bool &is_open)
{
   is_open=false;
   for(int i=0;i<PositionsTotal();i++)
   {
      long identifier=0;
      if(PositionGetTicket(i)==0 || !PositionGetInteger(POSITION_IDENTIFIER,identifier)) return false;
      if(identifier==id) is_open=true;
   }
   return true;
}
bool DemoOnceReadGuard(DemoOnceGuard &guard)
{
   ZeroMemory(guard);
   guard.account_trade_allowed=(bool)AccountInfoInteger(ACCOUNT_TRADE_ALLOWED);
   guard.account_expert_allowed=(bool)AccountInfoInteger(ACCOUNT_TRADE_EXPERT);
   guard.symbol_positions=-1; guard.symbol_orders=-1;
   if(!OnceAnyExposure(guard.symbol_positions,guard.symbol_orders)) return false;
   datetime now=TimeTradeServer();
   if(now<=0) return false;
   MqlDateTime day; if(!TimeToStruct(now,day)) return false;
   day.hour=0; day.min=0; day.sec=0; guard.broker_day_start=(long)StructToTime(day);
   if(!HistorySelect(0,now)) return false;
   DemoHistoryPosition positions[]; ulong today_orders[]; double all_day_change=0;
   int total=HistoryDealsTotal();
   for(int i=0;i<total;i++)
   {
      ulong deal=HistoryDealGetTicket(i);
      if(deal==0) return false;
      long time,type,magic,entry,position_id,order; string symbol;
      double profit,commission,swap,fee;
      if(!HistoryDealGetInteger(deal,DEAL_TIME,time) || !HistoryDealGetInteger(deal,DEAL_TYPE,type) ||
         !HistoryDealGetInteger(deal,DEAL_MAGIC,magic) || !HistoryDealGetInteger(deal,DEAL_ENTRY,entry) ||
         !HistoryDealGetInteger(deal,DEAL_POSITION_ID,position_id) || !HistoryDealGetInteger(deal,DEAL_ORDER,order) ||
         !HistoryDealGetString(deal,DEAL_SYMBOL,symbol) || !HistoryDealGetDouble(deal,DEAL_PROFIT,profit) ||
         !HistoryDealGetDouble(deal,DEAL_COMMISSION,commission) || !HistoryDealGetDouble(deal,DEAL_SWAP,swap) ||
         !HistoryDealGetDouble(deal,DEAL_FEE,fee)) return false;
      double net=profit+commission+swap+fee;
      if(!MathIsValidNumber(net)) return false;
      if(time>=guard.broker_day_start)
      {
         if(type==DEAL_TYPE_CREDIT) return false; // Credit is not balance; do not infer a day baseline.
         all_day_change+=net;
      }
      if(symbol!=_Symbol || magic!=InpMagic || (type!=DEAL_TYPE_BUY && type!=DEAL_TYPE_SELL)) continue;
      if(time>=guard.broker_day_start)
      {
         guard.daily_realized+=net;
         if(entry==DEAL_ENTRY_IN || entry==DEAL_ENTRY_INOUT)
         {
            bool seen=false; for(int k=0;k<ArraySize(today_orders);k++) if(today_orders[k]==(ulong)order) seen=true;
            if(!seen) { int k=ArraySize(today_orders); ArrayResize(today_orders,k+1); today_orders[k]=(ulong)order; guard.trades_today++; }
         }
      }
      int index=-1;
      for(int k=0;k<ArraySize(positions);k++) if(positions[k].id==position_id) { index=k; break; }
      if(index<0) { index=ArraySize(positions); ArrayResize(positions,index+1); ZeroMemory(positions[index]); positions[index].id=position_id; }
      positions[index].net+=net;
      if(entry==DEAL_ENTRY_OUT || entry==DEAL_ENTRY_OUT_BY || entry==DEAL_ENTRY_INOUT)
      {
         positions[index].has_exit=true; positions[index].last_exit=(long)MathMax(positions[index].last_exit,time);
         guard.last_exit_time=(long)MathMax(guard.last_exit_time,time);
      }
   }
   // Closed positions, newest exit first; partial exits of an open position are not a completed loss.
   for(int i=0;i<ArraySize(positions);i++)
      for(int j=i+1;j<ArraySize(positions);j++)
         if(positions[j].last_exit>positions[i].last_exit) { DemoHistoryPosition swap=positions[i]; positions[i]=positions[j]; positions[j]=swap; }
   for(int i=0;i<ArraySize(positions);i++)
   {
      if(!positions[i].has_exit) continue;
      bool is_open=false;
      if(!OncePositionStillOpen(positions[i].id,is_open)) return false;
      if(is_open) continue;
      if(positions[i].net>=0) break;
      guard.consecutive_losses++;
   }
   guard.day_start_balance=AccountInfoDouble(ACCOUNT_BALANCE)-all_day_change;
   guard.history_complete=MathIsValidNumber(guard.day_start_balance) && guard.day_start_balance>0 &&
      TerminalInfoInteger(TERMINAL_CONNECTED) && AccountInfoInteger(ACCOUNT_LOGIN)>0;
   return guard.history_complete;
}
string DemoOnceGuardJson()
{
   DemoOnceGuard guard; DemoOnceReadGuard(guard);
   string json="{"+JsonKey("history_complete")+JsonBool(guard.history_complete)+",";
   json+=JsonKey("broker_day_start")+StringFormat("%I64d",guard.broker_day_start)+",";
   json+=JsonKey("trades_today")+StringFormat("%I64d",guard.trades_today)+",";
   json+=JsonKey("consecutive_losses")+StringFormat("%I64d",guard.consecutive_losses)+",";
   json+=JsonKey("last_exit_time")+StringFormat("%I64d",guard.last_exit_time)+",";
   json+=JsonKey("day_start_balance")+JsonNumber(guard.day_start_balance,8)+",";
   json+=JsonKey("daily_realized")+JsonNumber(guard.daily_realized,8)+",";
   json+=JsonKey("symbol_positions")+IntegerToString(guard.symbol_positions)+",";
   json+=JsonKey("symbol_orders")+IntegerToString(guard.symbol_orders)+",";
   json+=JsonKey("account_trade_allowed")+JsonBool(guard.account_trade_allowed)+",";
   return json+JsonKey("account_expert_allowed")+JsonBool(guard.account_expert_allowed)+"}";
}

bool OnceLiveGuard(const DemoOnceCommand &command,MqlTradeRequest &request,string &reason)
{
   reason="";
   if((ENUM_ACCOUNT_TRADE_MODE)AccountInfoInteger(ACCOUNT_TRADE_MODE)!=ACCOUNT_TRADE_MODE_DEMO) { reason="DEMO_ACCOUNT_REQUIRED"; return false; }
   if(command.account_login!=AccountInfoInteger(ACCOUNT_LOGIN) || command.account_server!=AccountInfoString(ACCOUNT_SERVER) ||
      command.symbol!=_Symbol || command.magic!=InpMagic || command.bridge_session_id!=g_bridge_session_id || OnceScope()!=g_once_scope)
      { reason="IDENTITY_OR_SESSION_MISMATCH"; return false; }
   if(!TerminalInfoInteger(TERMINAL_CONNECTED) || !TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) || !MQLInfoInteger(MQL_TRADE_ALLOWED) ||
      !AccountInfoInteger(ACCOUNT_TRADE_ALLOWED) || !AccountInfoInteger(ACCOUNT_TRADE_EXPERT))
      { reason="TRADING_PERMISSION_NOT_ALREADY_ENABLED"; return false; }
   // History can synchronize with the broker. Read it before taking the final quote/clock.
   DemoOnceGuard guard;
   if(!DemoOnceReadGuard(guard) || !guard.history_complete || guard.symbol_positions!=0 || guard.symbol_orders!=0 ||
      InpMaxDailyLossPct<=0 || guard.daily_realized<=-guard.day_start_balance*InpMaxDailyLossPct/100.0)
      { reason="HISTORY_OR_DAILY_LOSS_GUARD"; return false; }
   long now=(long)TimeTradeServer();
   if(now<command.issued_server_time || now>=command.expires_server_time) { reason="COMMAND_EXPIRED_OR_FUTURE"; return false; }
   MqlTick tick; ZeroMemory(tick);
   if(!SymbolInfoTick(_Symbol,tick) || !MathIsValidNumber(tick.bid) || !MathIsValidNumber(tick.ask) || tick.bid<=0 || tick.ask<tick.bid || tick.time_msc<=0 ||
      now*1000-tick.time_msc>2000 || tick.time_msc-now*1000>1000) { reason="FRESH_QUOTE_REQUIRED"; return false; }
   double point,tick_size,min_volume,max_volume,step; long stops,trade_mode,order_mode,filling,execution;
   if(!SymbolInfoDouble(_Symbol,SYMBOL_POINT,point) || point<=0 ||
      !SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE,tick_size) || tick_size<=0 ||
      !SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN,min_volume) || !SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MAX,max_volume) ||
      !SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP,step) || step<=0 ||
      !SymbolInfoInteger(_Symbol,SYMBOL_TRADE_STOPS_LEVEL,stops) ||
      !SymbolInfoInteger(_Symbol,SYMBOL_TRADE_MODE,trade_mode) || !SymbolInfoInteger(_Symbol,SYMBOL_ORDER_MODE,order_mode) ||
      !SymbolInfoInteger(_Symbol,SYMBOL_FILLING_MODE,filling) || !SymbolInfoInteger(_Symbol,SYMBOL_TRADE_EXEMODE,execution))
      { reason="SYMBOL_METADATA_UNAVAILABLE"; return false; }
   bool buy=command.side=="BUY";
   if(trade_mode==SYMBOL_TRADE_MODE_DISABLED || trade_mode==SYMBOL_TRADE_MODE_CLOSEONLY ||
      (buy && trade_mode==SYMBOL_TRADE_MODE_SHORTONLY) || (!buy && trade_mode==SYMBOL_TRADE_MODE_LONGONLY) ||
      (order_mode&SYMBOL_ORDER_MARKET)==0 || (order_mode&SYMBOL_ORDER_SL)==0 || (order_mode&SYMBOL_ORDER_TP)==0)
      { reason="SYMBOL_MARKET_OR_PROTECTION_NOT_ALLOWED"; return false; }
   if(command.volume>0.01 || command.volume>InpMaxVolume || command.volume>max_volume || command.volume<min_volume ||
      MathAbs(command.volume/step-MathRound(command.volume/step))>1e-7)
      { reason="VOLUME_CAP_OR_BROKER_STEP"; return false; }
   int positions,orders;
   if(!OnceAnyExposure(positions,orders) || positions!=0 || orders!=0 || InpMaxOpenPositions<1)
      { reason="SYMBOL_EXPOSURE_OR_BOOK_UNKNOWN"; return false; }
   double price=buy ? tick.ask : tick.bid;
   if(tick.ask-tick.bid>command.max_spread_price_units+1e-10 ||
      MathAbs(price-command.reference_price)>command.max_deviation_points*point+1e-10)
      { reason="SPREAD_OR_REFERENCE_DEVIATION_CAP"; return false; }
   double sl=NormalizeDouble(MathRound(command.sl/tick_size)*tick_size,_Digits);
   double tp=NormalizeDouble(MathRound(command.tp/tick_size)*tick_size,_Digits);
   if(MathAbs(sl-command.sl)>tick_size*1e-7 || MathAbs(tp-command.tp)>tick_size*1e-7)
      { reason="STOPS_MUST_BE_TICK_ALIGNED"; return false; }
   double close_side=buy ? tick.bid : tick.ask;
   double distance=MathMax((double)stops*point,tick_size);
   if((buy && (sl>=close_side || close_side-sl+1e-10<distance || tp<=close_side || tp-close_side+1e-10<distance)) ||
      (!buy && (sl<=close_side || sl-close_side+1e-10<distance || tp>=close_side || close_side-tp+1e-10<distance)))
      { reason="BROKER_CLOSE_SIDE_STOP_DISTANCE"; return false; }
   ENUM_ORDER_TYPE side=buy ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   double worst_entry=command.reference_price+(buy ? 1 : -1)*command.max_deviation_points*point;
   double planned=0;
   if(worst_entry<=0 || (buy ? tp<=worst_entry : tp>=worst_entry) || !OrderCalcProfit(side,_Symbol,command.volume,worst_entry,sl,planned) ||
      !MathIsValidNumber(planned) || planned>=0 || -planned>command.max_loss_money+1e-8 ||
      guard.daily_realized+planned < -guard.day_start_balance*InpMaxDailyLossPct/100.0-1e-8)
      { reason="PLANNED_LOSS_CAP_OR_CALCULATION_FAILED"; return false; }
   ZeroMemory(request);
   request.action=TRADE_ACTION_DEAL; request.magic=(ulong)InpMagic; request.symbol=_Symbol; request.volume=command.volume;
   request.type=side; request.price=price; request.sl=sl; request.tp=tp; request.deviation=(ulong)command.max_deviation_points;
   request.type_time=ORDER_TIME_GTC;
   if((filling&SYMBOL_FILLING_FOK)!=0) request.type_filling=ORDER_FILLING_FOK;
   else if((filling&SYMBOL_FILLING_IOC)!=0) request.type_filling=ORDER_FILLING_IOC;
   else if(execution==SYMBOL_TRADE_EXECUTION_INSTANT || execution==SYMBOL_TRADE_EXECUTION_REQUEST) request.type_filling=ORDER_FILLING_FOK;
   else { reason="NO_BOUNDED_FILLING_MODE"; return false; }
   string compact=command.attempt_id; StringReplace(compact,"-",""); request.comment="X1:"+StringSubstr(compact,0,28);
   return true;
}

bool OnceClaimBudget(const DemoOnceCommand &command,int &lock_handle,string &reason)
{
   lock_handle=FileOpen(OnceFile(".lock"),FILE_READ|FILE_WRITE|FILE_BIN);
   if(lock_handle==INVALID_HANDLE) { reason="TERMINAL_WIDE_LOCK_BUSY"; return false; }
   if(OnceBudgetConsumed()) { reason="DEMO_ONCE_BUDGET_ALREADY_CONSUMED"; FileClose(lock_handle); lock_handle=INVALID_HANDLE; return false; }
   if(!GlobalVariableCheck(g_once_scope) && GlobalVariableSet(g_once_scope,0.0)==0)
      { reason="BUDGET_INITIALIZATION_FAILED"; FileClose(lock_handle); lock_handle=INVALID_HANDLE; return false; }
   if(!GlobalVariableSetOnCondition(g_once_scope,1.0,0.0))
      { reason="BUDGET_CLAIM_FAILED"; FileClose(lock_handle); lock_handle=INVALID_HANDLE; return false; }
   GlobalVariablesFlush();
   g_once_consumed=true;
   // Never remove/reset either claim after this point, including rejected/unknown outcomes.
   string claim="{"+JsonKey("attempt_id")+JsonString(command.attempt_id)+","+
      JsonKey("bridge_session_id")+JsonString(command.bridge_session_id)+","+
      JsonKey("profile_hash")+JsonString(command.profile_hash)+","+JsonKey("budget_consumed")+"true}";
   if(!OnceWrite(OnceFile(".claim"),claim))
      { reason="DURABLE_CLAIM_WRITE_FAILED"; FileClose(lock_handle); lock_handle=INVALID_HANDLE; return false; }
   string verified;
   if(!OnceRead(OnceFile(".claim"),verified) || verified!=claim)
      { reason="DURABLE_CLAIM_READBACK_FAILED"; FileClose(lock_handle); lock_handle=INVALID_HANDLE; return false; }
   return true;
}
bool OnceVerifyFill(DemoOnceResult &result)
{
   if(!result.order_send_called || result.order_ticket==0) return false;
   if(!HistorySelect((datetime)MathMax(0,result.command.issued_server_time-60),TimeTradeServer())) return false;
   double volume=0,value=0; ulong first_deal=0;
   for(int i=0;i<HistoryDealsTotal();i++)
   {
      ulong deal=HistoryDealGetTicket(i); if(deal==0) return false;
      if((ulong)HistoryDealGetInteger(deal,DEAL_ORDER)!=result.order_ticket) continue;
      if(HistoryDealGetString(deal,DEAL_SYMBOL)!=result.command.symbol || HistoryDealGetInteger(deal,DEAL_MAGIC)!=result.command.magic ||
         HistoryDealGetInteger(deal,DEAL_ENTRY)!=DEAL_ENTRY_IN ||
         HistoryDealGetInteger(deal,DEAL_TYPE)!=(result.command.side=="BUY" ? DEAL_TYPE_BUY : DEAL_TYPE_SELL)) return false;
      double part=HistoryDealGetDouble(deal,DEAL_VOLUME),price=HistoryDealGetDouble(deal,DEAL_PRICE);
      if(part<=0 || price<=0 || !MathIsValidNumber(part) || !MathIsValidNumber(price)) return false;
      volume+=part; value+=part*price; if(first_deal==0) first_deal=deal;
   }
   if(volume<=0 || volume>result.command.volume+1e-8) return false;
   result.deal_ticket=first_deal; result.filled_volume=volume; result.fill_price=value/volume;
   double broker_sl=0,broker_tp=0;
   if(!HistoryOrderSelect(result.order_ticket) || !HistoryOrderGetDouble(result.order_ticket,ORDER_SL,broker_sl) ||
      !HistoryOrderGetDouble(result.order_ticket,ORDER_TP,broker_tp) || broker_sl<=0 || broker_tp<=0)
      { result.reason="DEAL_FOUND_PROTECTION_NOT_YET_VERIFIED"; return false; }
   result.sl=broker_sl; result.tp=broker_tp;
   if(MathAbs(broker_sl-result.command.sl)>1e-8 || MathAbs(broker_tp-result.command.tp)>1e-8)
      { result.status="UNKNOWN"; result.reason="DEAL_FOUND_PROTECTION_MISMATCH"; return false; }
   // If the broker position is still open, verify its actual protection too.
   long identifier=HistoryDealGetInteger(first_deal,DEAL_POSITION_ID);
   for(int i=0;i<PositionsTotal();i++)
   {
      if(PositionGetTicket(i)==0) { result.reason="POSITION_PROTECTION_QUERY_FAILED"; return false; }
      if(PositionGetInteger(POSITION_IDENTIFIER)!=identifier) continue;
      if(PositionGetString(POSITION_SYMBOL)!=result.command.symbol || PositionGetInteger(POSITION_MAGIC)!=result.command.magic ||
         !PositionGetDouble(POSITION_SL,broker_sl) || !PositionGetDouble(POSITION_TP,broker_tp) ||
         MathAbs(broker_sl-result.command.sl)>1e-8 || MathAbs(broker_tp-result.command.tp)>1e-8)
      { result.status="UNKNOWN"; result.reason="OPEN_POSITION_PROTECTION_MISMATCH"; return false; }
      result.sl=broker_sl; result.tp=broker_tp;
   }
   result.status="FILLED";
   double point=SymbolInfoDouble(_Symbol,SYMBOL_POINT);
   result.reason=MathAbs(result.fill_price-result.command.reference_price)>result.command.max_deviation_points*point+1e-8
      ? "BROKER_DEAL_VERIFIED_SLIPPAGE_CAP_EXCEEDED" : "BROKER_DEAL_AND_PROTECTION_VERIFIED";
   return true;
}
void DemoOncePoll()
{
   if(!g_once_has_result || !g_once_result.order_send_called || (g_once_result.status!="PENDING" && g_once_result.status!="UNKNOWN")) return;
   string before=OnceResultJson(g_once_result);
   OnceVerifyFill(g_once_result);
   if(OnceResultJson(g_once_result)!=before) OncePublish(g_once_result,true);
}
void DemoOnceHandleAck(string response)
{
   COnceJson json;
   if(!json.Parse(response)) return;
   int payload=json.Find(0,"payload"); if(payload<0 || json.nodes[payload].type!=ONCE_OBJECT) return;
   int node=json.Find(payload,"demo_once_command"); if(node<0 || json.nodes[node].type==ONCE_NULL) return;
   DemoOnceCommand command;
   if(!OnceParseCommand(json,node,command)) { Print("XAUPY_DEMO_ONCE rejected malformed command; no broker call."); return; }
   if(g_once_has_result && g_once_result.command.attempt_id==command.attempt_id)
      { g_once_report=OnceResultJson(g_once_result); g_once_report_pending=true; return; }
   DemoOnceResult result; ZeroMemory(result); result.command=command; result.sl=command.sl; result.tp=command.tp;
   result.status="REJECTED";
   MqlTradeRequest request;
   if(!OnceLiveGuard(command,request,result.reason)) { OncePublish(result,false); return; }
   MqlTradeCheckResult checked; ZeroMemory(checked);
   if(!OrderCheck(request,checked) || (checked.retcode!=0 && checked.retcode!=TRADE_RETCODE_DONE))
      { result.retcode=checked.retcode; result.reason="ORDER_CHECK_REJECTED: "+checked.comment; OncePublish(result,false); return; }
   int lock_handle=INVALID_HANDLE;
   if(!OnceClaimBudget(command,lock_handle,result.reason)) { OncePublish(result,false); return; }
   result.status="UNKNOWN"; result.reason="DURABLE_CLAIM_SEND_OUTCOME_NOT_RECORDED";
   g_once_result=result; g_once_has_result=true;
   OncePublish(result,true);
   if(g_once_persisted_report!=OnceResultJson(result)) { FileClose(lock_handle); return; }
   // Re-read account, quote, permissions, exposure, TTL and loss immediately before the single send.
   MqlTradeRequest final_request;
   if(!OnceLiveGuard(command,final_request,result.reason))
   {
      result.status="REJECTED"; g_once_result=result; OncePublish(result,true); FileClose(lock_handle); return;
   }
   // A changing quote never causes a retry/recheck loop after the budget is claimed.
   MqlTick immediate; ZeroMemory(immediate);
   int final_positions,final_orders;
   double immediate_point=SymbolInfoDouble(_Symbol,SYMBOL_POINT);
   double immediate_tick_size=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE);
   long immediate_stops=0;
   long immediate_now=(long)TimeTradeServer();
   if((ENUM_ACCOUNT_TRADE_MODE)AccountInfoInteger(ACCOUNT_TRADE_MODE)!=ACCOUNT_TRADE_MODE_DEMO ||
      AccountInfoInteger(ACCOUNT_LOGIN)!=command.account_login || AccountInfoString(ACCOUNT_SERVER)!=command.account_server ||
      !TerminalInfoInteger(TERMINAL_CONNECTED) || !TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) || !MQLInfoInteger(MQL_TRADE_ALLOWED) ||
      !AccountInfoInteger(ACCOUNT_TRADE_ALLOWED) || !AccountInfoInteger(ACCOUNT_TRADE_EXPERT) ||
      !OnceAnyExposure(final_positions,final_orders) || final_positions!=0 || final_orders!=0 ||
      !SymbolInfoTick(_Symbol,immediate) || !MathIsValidNumber(immediate.bid) || !MathIsValidNumber(immediate.ask) ||
      immediate.bid<=0 || immediate.ask<immediate.bid || immediate.time_msc<=0 ||
      (command.side=="BUY" ? immediate.ask : immediate.bid)!=final_request.price ||
      immediate.ask-immediate.bid>command.max_spread_price_units+1e-10 ||
      immediate_point<=0 || immediate_tick_size<=0 || !SymbolInfoInteger(_Symbol,SYMBOL_TRADE_STOPS_LEVEL,immediate_stops) ||
      immediate_now*1000-immediate.time_msc>2000 || immediate.time_msc-immediate_now*1000>1000 ||
      immediate_now<command.issued_server_time || immediate_now>=command.expires_server_time)
   { result.status="REJECTED"; result.reason="FINAL_DEMO_IDENTITY_OR_TTL_CHANGED"; g_once_result=result; OncePublish(result,true); FileClose(lock_handle); return; }
   double immediate_close=command.side=="BUY" ? immediate.bid : immediate.ask;
   double immediate_distance=MathMax((double)immediate_stops*immediate_point,immediate_tick_size);
   if((command.side=="BUY" && (immediate_close-final_request.sl+1e-10<immediate_distance || final_request.tp-immediate_close+1e-10<immediate_distance)) ||
      (command.side=="SELL" && (final_request.sl-immediate_close+1e-10<immediate_distance || immediate_close-final_request.tp+1e-10<immediate_distance)))
   { result.status="REJECTED"; result.reason="FINAL_CLOSE_SIDE_STOP_DISTANCE_CHANGED"; g_once_result=result; OncePublish(result,true); FileClose(lock_handle); return; }
   MqlTradeResult sent; ZeroMemory(sent);
   result.order_send_called=true;
   bool returned=OrderSend(final_request,sent); // Sole broker mutation site. Never retry, even after false/timeout.
   result.retcode=sent.retcode; result.retcode_external=sent.retcode_external; result.order_ticket=sent.order; result.deal_ticket=sent.deal;
   result.status="UNKNOWN"; result.reason="ORDER_SEND_OUTCOME_UNVERIFIED";
   if(returned && (sent.retcode==TRADE_RETCODE_DONE || sent.retcode==TRADE_RETCODE_DONE_PARTIAL || sent.retcode==TRADE_RETCODE_PLACED))
      { result.status="PENDING"; result.reason="BROKER_ACCEPTED_AWAITING_DEAL_EVIDENCE"; }
   else if(sent.retcode!=0 && sent.retcode!=TRADE_RETCODE_TIMEOUT && sent.retcode!=TRADE_RETCODE_CONNECTION && sent.retcode!=TRADE_RETCODE_ERROR)
      { result.status="REJECTED"; result.reason="BROKER_REJECTED: "+sent.comment; }
   if(result.order_ticket==0 && result.deal_ticket!=0 && HistoryDealSelect(result.deal_ticket))
      result.order_ticket=(ulong)HistoryDealGetInteger(result.deal_ticket,DEAL_ORDER);
   OnceVerifyFill(result);
   g_once_result=result; OncePublish(result,true); FileClose(lock_handle);
}

#endif
