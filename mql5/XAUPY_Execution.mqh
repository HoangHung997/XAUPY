#ifndef XAUPY_EXECUTION_MQH
#define XAUPY_EXECUTION_MQH

// Versioned general execution. Each request is claimed on disk before OrderSend.
// The consumed one-shot ledger is independent and is never reset by this code.
struct FullCommand
{
   string intent_id,bridge_session_id,account_server,symbol,account_trade_mode,profile_hash;
   string action,side,order_type,comment;
   long account_login,magic,ticket,position_identifier,issued_server_time,expires_server_time,expiration,max_deviation_points,max_positions;
   double volume,price,sl,tp,original_tp,initial_risk,max_loss_money,max_spread_price_units,max_volume,max_daily_loss_pct;
   bool allow_real_account,never_widen_sl,require_server_sl;
};
struct FullResult
{
   FullCommand command;
   string state,reason;
   bool order_send_called,broker_verified;
   uint retcode;
   ulong order_ticket,deal_ticket,position_ticket;
   double filled_volume,fill_price,sl,tp;
};
bool g_full_enabled=false;
FullResult g_full_results[];
string FullRoot() { return "XAUPY\\execution\\"+OnceScope()+"."; }
string FullPath(string id,string suffix) { return FullRoot()+id+suffix; }
bool FullParse(COnceJson &json,int node,FullCommand &c)
{
   ZeroMemory(c);
   if(node<0 || json.nodes[node].type!=ONCE_OBJECT) return false;
   if(!json.String(node,"intent_id",c.intent_id) || !OnceUuid(c.intent_id) ||
      !json.String(node,"bridge_session_id",c.bridge_session_id) || !OnceUuid(c.bridge_session_id) ||
      !json.String(node,"account_server",c.account_server) || !json.String(node,"symbol",c.symbol) ||
      !json.String(node,"account_trade_mode",c.account_trade_mode) ||
      !json.String(node,"profile_hash",c.profile_hash) || !OnceHex(c.profile_hash,64) ||
      !json.Long(node,"account_login",c.account_login) || c.account_login<=0 ||
      !json.Long(node,"magic",c.magic) || c.magic<=0 ||
      !json.String(node,"action",c.action) || !json.Long(node,"issued_server_time",c.issued_server_time) ||
      !json.Long(node,"expires_server_time",c.expires_server_time) ||
      c.expires_server_time<=c.issued_server_time || c.expires_server_time-c.issued_server_time>5 ||
      !json.Bool(node,"allow_real_account",c.allow_real_account) ||
      !json.Bool(node,"never_widen_sl",c.never_widen_sl) || !c.never_widen_sl ||
      !json.Bool(node,"require_server_sl",c.require_server_sl) || !c.require_server_sl ||
      !json.Long(node,"max_positions",c.max_positions) || c.max_positions<1 ||
      !json.Double(node,"max_volume",c.max_volume) || c.max_volume<=0 ||
      !json.Double(node,"max_daily_loss_pct",c.max_daily_loss_pct) || c.max_daily_loss_pct<=0 ||
      !json.Long(node,"max_deviation_points",c.max_deviation_points) || c.max_deviation_points<0 ||
      !json.String(node,"comment",c.comment) || StringLen(c.comment)>31) return false;
   if(c.action=="ENTRY")
   {
      if(!json.String(node,"side",c.side) || (c.side!="BUY" && c.side!="SELL") ||
         !json.String(node,"order_type",c.order_type) ||
         !json.Double(node,"volume",c.volume) || c.volume<=0 ||
         !json.Double(node,"price",c.price) || c.price<=0 ||
         !json.Double(node,"sl",c.sl) || c.sl<=0 || !json.Double(node,"tp",c.tp) || c.tp<0 ||
         !json.Double(node,"original_tp",c.original_tp) || c.original_tp<=0 ||
         !json.Double(node,"initial_risk",c.initial_risk) || c.initial_risk<=0 ||
         !json.Double(node,"max_loss_money",c.max_loss_money) || c.max_loss_money<=0 ||
         !json.Double(node,"max_spread_price_units",c.max_spread_price_units) || c.max_spread_price_units<0 ||
         !json.Long(node,"expiration",c.expiration)) return false;
      if(c.order_type!=c.side && c.order_type!=c.side+"_STOP" && c.order_type!=c.side+"_LIMIT") return false;
   }
   else
   {
      if(c.action!="CLOSE_POSITION" && c.action!="PARTIAL_CLOSE" && c.action!="MODIFY_POSITION" && c.action!="MODIFY_PENDING" && c.action!="CANCEL_PENDING") return false;
      if(!json.Long(node,"ticket",c.ticket) || c.ticket<=0) return false;
      if(c.action!="MODIFY_PENDING" && c.action!="CANCEL_PENDING" && (!json.Long(node,"position_identifier",c.position_identifier) || c.position_identifier<=0)) return false;
      if((c.action=="PARTIAL_CLOSE" || c.action=="CLOSE_POSITION") && (!json.Double(node,"volume",c.volume) || c.volume<=0)) return false;
      if(c.action=="MODIFY_POSITION" || c.action=="MODIFY_PENDING")
      {
         if(!json.Double(node,"sl",c.sl) || c.sl<=0 || !json.Double(node,"tp",c.tp) || c.tp<0) return false;
         if(c.action=="MODIFY_PENDING" && (!json.Double(node,"price",c.price) || c.price<=0 || !json.Long(node,"expiration",c.expiration))) return false;
      }
   }
   return true;
}
string FullCommandJson(FullCommand &c)
{
   string s="{"+JsonKey("intent_id")+JsonString(c.intent_id)+","+JsonKey("bridge_session_id")+JsonString(c.bridge_session_id)+",";
   s+=JsonKey("account_login")+StringFormat("%I64d",c.account_login)+","+JsonKey("account_server")+JsonString(c.account_server)+",";
   s+=JsonKey("symbol")+JsonString(c.symbol)+","+JsonKey("magic")+StringFormat("%I64d",c.magic)+",";
   s+=JsonKey("profile_hash")+JsonString(c.profile_hash)+","+JsonKey("account_trade_mode")+JsonString(c.account_trade_mode)+",";
   s+=JsonKey("action")+JsonString(c.action)+","+JsonKey("side")+JsonString(c.side)+","+JsonKey("order_type")+JsonString(c.order_type)+",";
   s+=JsonKey("comment")+JsonString(c.comment)+","+JsonKey("ticket")+StringFormat("%I64d",c.ticket)+",";
   s+=JsonKey("position_identifier")+StringFormat("%I64d",c.position_identifier)+",";
   s+=JsonKey("volume")+JsonNumber(c.volume)+","+JsonKey("price")+JsonNumber(c.price,10)+","+JsonKey("sl")+JsonNumber(c.sl,10)+","+JsonKey("tp")+JsonNumber(c.tp,10)+",";
   s+=JsonKey("original_tp")+JsonNumber(c.original_tp,10)+","+JsonKey("initial_risk")+JsonNumber(c.initial_risk,10)+",";
   s+=JsonKey("max_loss_money")+JsonNumber(c.max_loss_money)+","+JsonKey("max_spread_price_units")+JsonNumber(c.max_spread_price_units)+",";
   s+=JsonKey("max_volume")+JsonNumber(c.max_volume)+","+JsonKey("max_daily_loss_pct")+JsonNumber(c.max_daily_loss_pct)+",";
   s+=JsonKey("issued_server_time")+StringFormat("%I64d",c.issued_server_time)+","+JsonKey("expires_server_time")+StringFormat("%I64d",c.expires_server_time)+",";
   s+=JsonKey("expiration")+StringFormat("%I64d",c.expiration)+","+JsonKey("max_positions")+StringFormat("%I64d",c.max_positions)+",";
   s+=JsonKey("max_deviation_points")+StringFormat("%I64d",c.max_deviation_points)+","+JsonKey("allow_real_account")+JsonBool(c.allow_real_account)+",";
   return s+JsonKey("never_widen_sl")+JsonBool(c.never_widen_sl)+","+JsonKey("require_server_sl")+JsonBool(c.require_server_sl)+"}";
}
bool FullParserFixture(string text)
{
   COnceJson json; FullCommand command;
   return json.Parse(text) && FullParse(json,0,command);
}
bool FullParserSelfTest()
{
   // Pure local fixtures. No account, file, network or OrderSend calls.
   FullCommand command; ZeroMemory(command);
   command.intent_id="12345678-1234-4234-8234-123456789012";
   command.bridge_session_id="12345678-1234-4234-8234-123456789013";
   command.account_login=12345; command.account_server="Fixture"; command.account_trade_mode="DEMO";
   command.symbol="XAUUSD"; command.magic=991188; command.comment="test";
   command.profile_hash="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
   command.action="ENTRY"; command.side="BUY"; command.order_type="BUY";
   command.volume=.001; command.price=2000; command.sl=1999; command.tp=2002; command.original_tp=2002;
   command.initial_risk=1; command.max_loss_money=5; command.max_spread_price_units=.5;
   command.max_volume=.01; command.max_positions=1; command.max_daily_loss_pct=3;
   command.issued_server_time=1700000000; command.expires_server_time=1700000005;
   command.never_widen_sl=true; command.require_server_sl=true;
   string valid=FullCommandJson(command),bad; int checks=0;
   if(!FullParserFixture(valid))return false; checks++;
   bad=valid; StringReplace(bad,"1700000005","1700000006"); if(FullParserFixture(bad))return false; checks++;
   bad=valid; StringReplace(bad,"\"volume\":0.00100000","\"volume\":\"0.001\""); if(bad==valid || FullParserFixture(bad))return false; checks++;
   bad=valid; StringReplace(bad,"\"account_login\":12345","\"account_login\":12345.5"); if(FullParserFixture(bad))return false; checks++;
   bad=valid; StringReplace(bad,"\"never_widen_sl\":true","\"never_widen_sl\":false"); if(FullParserFixture(bad))return false; checks++;
   bad=valid; StringReplace(bad,"\"intent_id\":","\"intent_id\":null,\"intent_id\":"); if(FullParserFixture(bad))return false; checks++;
   command.action="MODIFY_POSITION"; command.ticket=123; command.position_identifier=124;
   if(!FullParserFixture(FullCommandJson(command)))return false; checks++;
   command.position_identifier=0;
   if(FullParserFixture(FullCommandJson(command)))return false; checks++;
   command.action="CANCEL_PENDING";
   if(!FullParserFixture(FullCommandJson(command)))return false; checks++;
   command.action="UNSUPPORTED";
   if(FullParserFixture(FullCommandJson(command)))return false; checks++;
   Print("XAUPY_EXECUTION pure parser self-test PASS ",checks," checks");
   return true;
}
string FullResultJson(FullResult &r)
{
   string s="{"+JsonKey("intent_id")+JsonString(r.command.intent_id)+","+JsonKey("bridge_session_id")+JsonString(r.command.bridge_session_id)+",";
   s+=JsonKey("account_login")+StringFormat("%I64d",r.command.account_login)+","+JsonKey("account_server")+JsonString(r.command.account_server)+",";
   s+=JsonKey("symbol")+JsonString(r.command.symbol)+","+JsonKey("magic")+StringFormat("%I64d",r.command.magic)+",";
   s+=JsonKey("state")+JsonString(r.state)+","+JsonKey("reason")+JsonString(r.reason)+",";
   s+=JsonKey("order_send_called")+JsonBool(r.order_send_called)+","+JsonKey("broker_verified")+JsonBool(r.broker_verified)+",";
   s+=JsonKey("retcode")+IntegerToString(r.retcode)+","+JsonKey("order_ticket")+StringFormat("%I64u",r.order_ticket)+",";
   s+=JsonKey("deal_ticket")+StringFormat("%I64u",r.deal_ticket)+","+JsonKey("position_ticket")+StringFormat("%I64u",r.position_ticket)+",";
   s+=JsonKey("filled_volume")+JsonNumber(r.filled_volume)+","+JsonKey("fill_price")+JsonNumber(r.fill_price,10)+",";
   return s+JsonKey("sl")+JsonNumber(r.sl,10)+","+JsonKey("tp")+JsonNumber(r.tp,10)+"}";
}
string FullComment(FullCommand &c)
{
   string id=c.intent_id; StringReplace(id,"-","");
   return StringSubstr(c.comment,0,12)+"|X"+StringSubstr(id,0,16);
}
bool FullIdentity(FullCommand &c,bool require_session=true)
{
   return c.account_login==AccountInfoInteger(ACCOUNT_LOGIN) && c.account_server==AccountInfoString(ACCOUNT_SERVER) &&
      c.symbol==_Symbol && c.magic==InpMagic && (!require_session || c.bridge_session_id==g_bridge_session_id);
}
bool FullGrid(double value,double step) { return step>0 && MathAbs(value/step-MathRound(value/step))<1e-6; }
bool FullPrepare(FullCommand &c,MqlTradeRequest &request,string &reason)
{
   ZeroMemory(request); reason="";
   if(!FullIdentity(c) || !g_full_enabled) { reason="IDENTITY_OR_USER_MODE"; return false; }
   bool real=AccountInfoInteger(ACCOUNT_TRADE_MODE)==ACCOUNT_TRADE_MODE_REAL;
   if((real && (!c.allow_real_account || c.account_trade_mode!="REAL")) || (!real && c.account_trade_mode!=AccountTradeModeText()))
      { reason="ACCOUNT_PERMISSION_MISMATCH"; return false; }
   if(!TerminalInfoInteger(TERMINAL_CONNECTED) || !TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) || !MQLInfoInteger(MQL_TRADE_ALLOWED) ||
      !AccountInfoInteger(ACCOUNT_TRADE_ALLOWED) || !AccountInfoInteger(ACCOUNT_TRADE_EXPERT))
      { reason="BROKER_TRADING_PERMISSION"; return false; }
   long now=(long)TimeTradeServer();
   if(now<c.issued_server_time || now>=c.expires_server_time) { reason="COMMAND_EXPIRED"; return false; }
   MqlTick quote={};
   if(!SymbolInfoTick(_Symbol,quote) || quote.bid<=0 || quote.ask<quote.bid || now*1000-quote.time_msc>2000 || quote.time_msc-now*1000>1000)
      { reason="FRESH_QUOTE_REQUIRED"; return false; }
   double point=SymbolInfoDouble(_Symbol,SYMBOL_POINT),tick=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE);
   double minimum=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN),maximum=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MAX),step=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP);
   if(point<=0 || tick<=0 || minimum<=0 || maximum<minimum || step<=0) { reason="SYMBOL_METADATA"; return false; }
   double gap=(double)SymbolInfoInteger(_Symbol,SYMBOL_TRADE_STOPS_LEVEL)*point;
   double freeze=(double)SymbolInfoInteger(_Symbol,SYMBOL_TRADE_FREEZE_LEVEL)*point;
   request.symbol=_Symbol; request.magic=InpMagic; request.deviation=(ulong)c.max_deviation_points; request.comment=FullComment(c);
   long filling=SymbolInfoInteger(_Symbol,SYMBOL_FILLING_MODE),execution=SymbolInfoInteger(_Symbol,SYMBOL_TRADE_EXEMODE);
   request.type_filling=(filling&SYMBOL_FILLING_FOK)!=0 ? ORDER_FILLING_FOK : (filling&SYMBOL_FILLING_IOC)!=0 ? ORDER_FILLING_IOC : ORDER_FILLING_RETURN;
   if(c.action=="ENTRY")
   {
      bool buy=c.side=="BUY",pending=c.order_type!=c.side;
      long trade_mode=SymbolInfoInteger(_Symbol,SYMBOL_TRADE_MODE);
      if(trade_mode==SYMBOL_TRADE_MODE_DISABLED || trade_mode==SYMBOL_TRADE_MODE_CLOSEONLY ||
         (buy && trade_mode==SYMBOL_TRADE_MODE_SHORTONLY) || (!buy && trade_mode==SYMBOL_TRADE_MODE_LONGONLY))
         { reason="SYMBOL_ENTRY_DISABLED"; return false; }
      DemoOnceGuard guard;
      if(!DemoOnceReadGuard(guard) || !guard.history_complete || guard.daily_realized<=-guard.day_start_balance*MathMin(InpMaxDailyLossPct,c.max_daily_loss_pct)/100)
         { reason="HISTORY_OR_DAILY_LOSS"; return false; }
      if(OwnPositionsCount()+OwnOrdersCount()>=MathMin((long)InpMaxOpenPositions,c.max_positions)) { reason="MAX_POSITIONS"; return false; }
      // Netting must never merge this strategy into a position owned by another EA.
      if(AccountInfoInteger(ACCOUNT_MARGIN_MODE)!=ACCOUNT_MARGIN_MODE_RETAIL_HEDGING && PositionSelect(_Symbol))
         { reason="NETTING_SYMBOL_ALREADY_EXPOSED"; return false; }
      if(c.volume<minimum || c.volume>MathMin(maximum,MathMin(InpMaxVolume,c.max_volume)) || !FullGrid(c.volume,step))
         { reason="VOLUME_LIMIT_OR_STEP"; return false; }
      if(quote.ask-quote.bid>c.max_spread_price_units+1e-10) { reason="SPREAD_LIMIT"; return false; }
      request.action=pending ? TRADE_ACTION_PENDING : TRADE_ACTION_DEAL;
      request.type=buy ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
      if(c.order_type=="BUY_STOP") request.type=ORDER_TYPE_BUY_STOP;
      if(c.order_type=="SELL_STOP") request.type=ORDER_TYPE_SELL_STOP;
      if(c.order_type=="BUY_LIMIT") request.type=ORDER_TYPE_BUY_LIMIT;
      if(c.order_type=="SELL_LIMIT") request.type=ORDER_TYPE_SELL_LIMIT;
      request.price=pending ? c.price : buy ? quote.ask : quote.bid;
      request.volume=c.volume; request.sl=c.sl; request.tp=c.tp;
      if(pending)
      {
         request.type_filling=ORDER_FILLING_RETURN;
         if(c.expiration<=now || (SymbolInfoInteger(_Symbol,SYMBOL_EXPIRATION_MODE)&SYMBOL_EXPIRATION_SPECIFIED)==0)
            { reason="BROKER_EXPIRATION_NOT_SUPPORTED"; return false; }
         request.type_time=ORDER_TIME_SPECIFIED; request.expiration=(datetime)c.expiration;
      }
      else if(MathAbs(request.price-c.price)>c.max_deviation_points*point+tick/2) { reason="PRICE_DEVIATION"; return false; }
      double reference=pending ? c.price : buy ? quote.bid : quote.ask;
      if(!FullGrid(c.sl,tick) || (c.tp && !FullGrid(c.tp,tick)) || (pending && !FullGrid(c.price,tick)) ||
         (buy ? reference-c.sl : c.sl-reference)<MathMax(gap,tick)-1e-10 ||
         (c.tp && (buy ? c.tp-reference : reference-c.tp)<MathMax(gap,tick)-1e-10)) { reason="INVALID_PROTECTION"; return false; }
      double loss=0,worst=request.price+(buy ? 1 : -1)*c.max_deviation_points*point;
      if(!OrderCalcProfit(buy ? ORDER_TYPE_BUY : ORDER_TYPE_SELL,_Symbol,c.volume,worst,c.sl,loss) || loss>=0 || -loss>c.max_loss_money+1e-8)
         { reason="RISK_BUDGET_EXCEEDED"; return false; }
   }
   else if(c.action=="CANCEL_PENDING" || c.action=="MODIFY_PENDING")
   {
      if(!OrderSelect((ulong)c.ticket) || OrderGetString(ORDER_SYMBOL)!=_Symbol || OrderGetInteger(ORDER_MAGIC)!=InpMagic)
         { reason="OWNED_ORDER_NOT_FOUND"; return false; }
      request.order=(ulong)c.ticket;
      request.action=c.action=="CANCEL_PENDING" ? TRADE_ACTION_REMOVE : TRADE_ACTION_MODIFY;
      if(c.action=="MODIFY_PENDING")
      {
         request.price=c.price; request.sl=c.sl; request.tp=c.tp; request.stoplimit=OrderGetDouble(ORDER_PRICE_STOPLIMIT);
         request.type_time=(ENUM_ORDER_TYPE_TIME)OrderGetInteger(ORDER_TYPE_TIME); request.expiration=(datetime)c.expiration;
         double old=OrderGetDouble(ORDER_SL); long type=OrderGetInteger(ORDER_TYPE);
         bool buy=type==ORDER_TYPE_BUY_STOP || type==ORDER_TYPE_BUY_LIMIT || type==ORDER_TYPE_BUY_STOP_LIMIT;
         if(old>0 && (buy ? c.sl<old-tick/2 : c.sl>old+tick/2)) { reason="NEVER_WIDEN_SL"; return false; }
         if(!FullGrid(c.price,tick) || !FullGrid(c.sl,tick) || (c.tp && !FullGrid(c.tp,tick))) { reason="INVALID_PRICE_GRID"; return false; }
      }
   }
   else
   {
      if(!PositionSelectByTicket((ulong)c.ticket) || PositionGetString(POSITION_SYMBOL)!=_Symbol || PositionGetInteger(POSITION_MAGIC)!=InpMagic || PositionGetInteger(POSITION_IDENTIFIER)!=c.position_identifier)
         { reason="OWNED_POSITION_NOT_FOUND"; return false; }
      request.position=(ulong)c.ticket;
      bool buy=PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY;
      if(c.action=="MODIFY_POSITION")
      {
         double old=PositionGetDouble(POSITION_SL),reference=buy ? quote.bid : quote.ask;
         if((old>0 && (buy ? c.sl<old-tick/2 : c.sl>old+tick/2)) || !FullGrid(c.sl,tick) || (c.tp && !FullGrid(c.tp,tick)) ||
            (buy ? reference-c.sl : c.sl-reference)<MathMax(MathMax(gap,freeze),tick)-1e-10)
            { reason="STOP_WIDEN_OR_FREEZE"; return false; }
         request.action=TRADE_ACTION_SLTP; request.sl=c.sl; request.tp=c.tp;
      }
      else
      {
         double current=PositionGetDouble(POSITION_VOLUME);
         request.volume=c.action=="CLOSE_POSITION" ? current : c.volume;
         if(request.volume<minimum || request.volume>current+1e-9 || !FullGrid(request.volume,step) ||
            (c.action=="PARTIAL_CLOSE" && current-request.volume<minimum-1e-9)) { reason="PARTIAL_VOLUME_OR_REMAINDER"; return false; }
         request.action=TRADE_ACTION_DEAL; request.type=buy ? ORDER_TYPE_SELL : ORDER_TYPE_BUY; request.price=buy ? quote.bid : quote.ask;
      }
   }
   if(request.action==TRADE_ACTION_DEAL && request.type_filling==ORDER_FILLING_RETURN && execution==SYMBOL_TRADE_EXECUTION_MARKET)
      { reason="BROKER_FILLING_MODE_UNSUPPORTED"; return false; }
   return true;
}
bool FullDealAggregate(FullResult &r)
{
   FullCommand c=r.command;
   if(r.order_ticket==0 || !HistorySelect((datetime)MathMax(0,c.issued_server_time-60),TimeTradeServer()+60)) return false;
   double volume=0,weighted=0; long position_id=0; ulong first_deal=0;
   for(int i=0;i<HistoryDealsTotal();i++)
   {
      ulong ticket=HistoryDealGetTicket(i);
      if(!ticket || HistoryDealGetInteger(ticket,DEAL_ORDER)!=(long)r.order_ticket) continue;
      long entry=HistoryDealGetInteger(ticket,DEAL_ENTRY),pid=HistoryDealGetInteger(ticket,DEAL_POSITION_ID);
      if(HistoryDealGetInteger(ticket,DEAL_MAGIC)!=c.magic || HistoryDealGetString(ticket,DEAL_SYMBOL)!=c.symbol ||
         (c.action=="ENTRY" ? entry!=DEAL_ENTRY_IN : (entry!=DEAL_ENTRY_OUT && entry!=DEAL_ENTRY_OUT_BY)) ||
         (c.action=="ENTRY" && HistoryDealGetInteger(ticket,DEAL_TYPE)!=(c.side=="BUY" ? DEAL_TYPE_BUY : DEAL_TYPE_SELL)) ||
         (position_id!=0 && pid!=position_id) || (c.action!="ENTRY" && pid!=c.position_identifier)) return false;
      if(!first_deal) first_deal=ticket;
      position_id=pid;
      double amount=HistoryDealGetDouble(ticket,DEAL_VOLUME);
      volume+=amount; weighted+=amount*HistoryDealGetDouble(ticket,DEAL_PRICE);
   }
   if(volume<=0 || (c.volume>0 && volume>c.volume+1e-9) || !HistoryOrderSelect(r.order_ticket)) return false;
   long state=HistoryOrderGetInteger(r.order_ticket,ORDER_STATE);
   if(state!=ORDER_STATE_FILLED && state!=ORDER_STATE_PARTIAL && state!=ORDER_STATE_CANCELED) return false;
   if(OrderSelect(r.order_ticket)) return false; // Wait for the request's final aggregate.
   r.deal_ticket=first_deal; r.filled_volume=volume; r.fill_price=weighted/volume;
   if(c.action=="ENTRY")
   {
      double tick=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE);
      r.sl=HistoryOrderGetDouble(r.order_ticket,ORDER_SL); r.tp=HistoryOrderGetDouble(r.order_ticket,ORDER_TP);
      if(MathAbs(r.sl-c.sl)>tick/2+1e-10 || MathAbs(r.tp-c.tp)>tick/2+1e-10) return false;
      for(int i=0;i<PositionsTotal();i++)
      {
         ulong ticket=PositionGetTicket(i);
         if(ticket && PositionGetInteger(POSITION_IDENTIFIER)==position_id)
         {
            if(PositionGetInteger(POSITION_MAGIC)!=c.magic || PositionGetString(POSITION_SYMBOL)!=c.symbol ||
               MathAbs(PositionGetDouble(POSITION_SL)-c.sl)>tick/2+1e-10 || MathAbs(PositionGetDouble(POSITION_TP)-c.tp)>tick/2+1e-10) return false;
            r.position_ticket=ticket; break;
         }
      }
   }
   else r.position_ticket=(ulong)c.ticket;
   return true;
}
bool FullVerify(FullResult &r)
{
   if(!r.order_send_called || !FullIdentity(r.command,false)) return false;
   FullCommand c=r.command; double tick=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE);
   bool matched=false;
   if(c.action=="MODIFY_POSITION")
   {
      matched=PositionSelectByTicket((ulong)c.ticket) && PositionGetInteger(POSITION_MAGIC)==c.magic &&
         PositionGetString(POSITION_SYMBOL)==c.symbol && MathAbs(PositionGetDouble(POSITION_SL)-c.sl)<tick/2+1e-10 && MathAbs(PositionGetDouble(POSITION_TP)-c.tp)<tick/2+1e-10;
      r.position_ticket=(ulong)c.ticket;
   }
   else if(c.action=="CANCEL_PENDING")
      matched=HistoryOrderSelect((ulong)c.ticket) && HistoryOrderGetInteger((ulong)c.ticket,ORDER_STATE)==ORDER_STATE_CANCELED && HistoryOrderGetInteger((ulong)c.ticket,ORDER_MAGIC)==c.magic;
   else if(c.action=="MODIFY_PENDING" || (c.action=="ENTRY" && c.order_type!=c.side))
   {
      ulong order=c.action=="MODIFY_PENDING" ? (ulong)c.ticket : r.order_ticket;
      matched=order>0 && OrderSelect(order) && OrderGetInteger(ORDER_MAGIC)==c.magic && OrderGetString(ORDER_SYMBOL)==c.symbol &&
         MathAbs(OrderGetDouble(ORDER_SL)-c.sl)<tick/2+1e-10 && MathAbs(OrderGetDouble(ORDER_TP)-c.tp)<tick/2+1e-10 && MathAbs(OrderGetDouble(ORDER_PRICE_OPEN)-c.price)<tick/2+1e-10;
      if(matched) r.order_ticket=order;
      if(!matched && c.action=="ENTRY" && order>0 && HistoryOrderSelect(order))
         matched=HistoryOrderGetInteger(order,ORDER_MAGIC)==c.magic && HistoryOrderGetString(order,ORDER_SYMBOL)==c.symbol &&
            HistoryOrderGetInteger(order,ORDER_STATE)==ORDER_STATE_FILLED && MathAbs(HistoryOrderGetDouble(order,ORDER_SL)-c.sl)<tick/2+1e-10 && MathAbs(HistoryOrderGetDouble(order,ORDER_TP)-c.tp)<tick/2+1e-10;
   }
   else matched=FullDealAggregate(r);
   if(matched) { r.state="CONFIRMED"; r.reason=(r.filled_volume>0 && c.volume>0 && r.filled_volume<c.volume-1e-9) ? "BROKER_PARTIAL_FILL_VERIFIED" : "BROKER_STATE_VERIFIED"; r.broker_verified=true; return true; }
   return false;
}
bool FullStoreResult(FullResult &r)
{
   string text=FullResultJson(r);
   if(!OnceWrite(FullPath(r.command.intent_id,".result"),text) || !OnceWrite(FullPath(r.command.intent_id,".pending"),text))
   {
      Print("XAUPY execution result persistence failed; intent stays claimed: ",r.command.intent_id);
      return false;
   }
   string verified;
   return OnceRead(FullPath(r.command.intent_id,".result"),verified) && verified==text;
}
void FullHandleAck(string text)
{
   COnceJson json;
   if(!json.Parse(text)) return;
   int payload=json.Find(0,"payload"); bool enabled=false;
   g_full_enabled=json.Bool(payload,"execution_enabled",enabled) && enabled;
   int node=json.Find(payload,"execution_command");
   if(node<0 || json.nodes[node].type==ONCE_NULL) return;
   FullResult result; ZeroMemory(result); result.state="REJECTED";
   if(!FullParse(json,node,result.command)) { Print("XAUPY invalid execution command"); return; }
   FullCommand c=result.command; string path=FullPath(c.intent_id,".claim");
   // A durable claim, even incomplete, means never send this ID again.
   if(FileIsExist(path))
   {
      string saved;
      if(OnceRead(FullPath(c.intent_id,".result"),saved)) OnceWrite(FullPath(c.intent_id,".pending"),saved);
      return;
   }
   if(FileIsExist(FullPath(c.intent_id,".result")))
   {
      string cached;
      if(OnceRead(FullPath(c.intent_id,".result"),cached)) OnceWrite(FullPath(c.intent_id,".pending"),cached);
      return;
   }
   MqlTradeRequest request={};
   if(!FullPrepare(c,request,result.reason)) { FullStoreResult(result); return; }
   MqlTradeCheckResult check={};
   if(!OrderCheck(request,check) || (check.retcode!=0 && check.retcode!=TRADE_RETCODE_DONE))
   { result.retcode=check.retcode; result.reason="ORDER_CHECK: "+check.comment; FullStoreResult(result); return; }
   FolderCreate("XAUPY"); FolderCreate("XAUPY\\execution");
   string serialized=FullCommandJson(c);
   if(!OnceWrite(FullPath(c.intent_id,".command"),serialized)) { result.reason="COMMAND_PERSIST_FAILED"; FullStoreResult(result); return; }
   string verified_command;
   if(!OnceRead(FullPath(c.intent_id,".command"),verified_command) || verified_command!=serialized) return;
   int lock=FileOpen(path,FILE_READ|FILE_WRITE|FILE_BIN);
   if(lock==INVALID_HANDLE) return;
   if(FileSize(lock)>0) { FileClose(lock); return; }
   uchar mark[]={1};
   if(FileWriteArray(lock,mark)!=1) { FileClose(lock); return; }
   FileFlush(lock);
   // Recheck identity, price and expiry immediately before the sole send.
   if(!FullPrepare(c,request,result.reason)) { FullStoreResult(result); FileClose(lock); return; }
   result.order_send_called=true; result.state="UNKNOWN"; result.reason="AWAITING_BROKER_EVIDENCE";
   if(!FullStoreResult(result)) { FileClose(lock); return; }
   MqlTradeResult sent={}; bool ok=OrderSend(request,sent);
   result.retcode=sent.retcode; result.order_ticket=sent.order; result.deal_ticket=sent.deal;
   if(result.order_ticket==0 && result.deal_ticket>0 && HistoryDealSelect(result.deal_ticket)) result.order_ticket=(ulong)HistoryDealGetInteger(result.deal_ticket,DEAL_ORDER);
   if(!ok || (sent.retcode!=TRADE_RETCODE_DONE && sent.retcode!=TRADE_RETCODE_DONE_PARTIAL && sent.retcode!=TRADE_RETCODE_PLACED && sent.retcode!=TRADE_RETCODE_NO_CHANGES))
   {
      if(sent.retcode!=0 && sent.retcode!=TRADE_RETCODE_TIMEOUT && sent.retcode!=TRADE_RETCODE_CONNECTION && sent.retcode!=TRADE_RETCODE_ERROR)
      { result.state="REJECTED"; result.reason="BROKER_REJECTED: "+sent.comment; }
   }
   FullVerify(result); FullStoreResult(result); FileClose(lock);
   int count=ArraySize(g_full_results); ArrayResize(g_full_results,count+1); g_full_results[count]=result;
}
void FullDiscoverEvidence(FullResult &r)
{
   if(!FullIdentity(r.command,false) || !r.order_send_called || r.state!="UNKNOWN") return;
   string comment=FullComment(r.command);
   if(r.order_ticket==0)
   {
      ulong match=0; int count=0;
      for(int i=0;i<OrdersTotal();i++)
      {
         ulong ticket=OrderGetTicket(i);
         if(ticket && OrderGetInteger(ORDER_MAGIC)==r.command.magic && OrderGetString(ORDER_SYMBOL)==r.command.symbol && OrderGetString(ORDER_COMMENT)==comment)
         { match=ticket; count++; }
      }
      if(HistorySelect((datetime)MathMax(0,r.command.issued_server_time-60),TimeTradeServer()+60))
      {
         for(int i=0;i<HistoryOrdersTotal();i++)
         {
            ulong ticket=HistoryOrderGetTicket(i);
            if(ticket && HistoryOrderGetInteger(ticket,ORDER_MAGIC)==r.command.magic && HistoryOrderGetString(ticket,ORDER_SYMBOL)==r.command.symbol && HistoryOrderGetString(ticket,ORDER_COMMENT)==comment)
            { if(match!=ticket) { match=ticket; count++; } }
         }
      }
      if(count==1) r.order_ticket=match;
   }
   if(r.order_ticket>0 && r.deal_ticket==0 && HistorySelect((datetime)MathMax(0,r.command.issued_server_time-60),TimeTradeServer()+60))
   {
      ulong match=0; int count=0;
      for(int i=0;i<HistoryDealsTotal();i++)
      {
         ulong ticket=HistoryDealGetTicket(i);
         if(ticket && HistoryDealGetInteger(ticket,DEAL_ORDER)==(long)r.order_ticket && HistoryDealGetInteger(ticket,DEAL_MAGIC)==r.command.magic)
         { match=ticket; count++; }
      }
      // Multiple split deals need explicit aggregate reconciliation; never
      // pretend a randomly selected deal represents the whole request.
      if(count==1) r.deal_ticket=match;
   }
}
void FullInit()
{
   FolderCreate("XAUPY"); FolderCreate("XAUPY\\execution");
   string name; long find=FileFindFirst(FullRoot()+"*.command",name);
   if(find==INVALID_HANDLE) return;
   do
   {
      string text; COnceJson json; FullResult result; ZeroMemory(result);
      if(!OnceRead("XAUPY\\execution\\"+name,text) || !json.Parse(text) || !FullParse(json,0,result.command)) continue;
      if(!FullIdentity(result.command,false) || !FileIsExist(FullPath(result.command.intent_id,".claim"))) continue;
      result.state="UNKNOWN"; result.reason="RESTART_RECONCILIATION"; result.order_send_called=true;
      string saved; COnceJson previous;
      if(OnceRead(FullPath(result.command.intent_id,".result"),saved) && previous.Parse(saved))
      {
         string state; if(previous.String(0,"state",state) && (state=="CONFIRMED" || state=="REJECTED")) continue;
         long order=0,deal=0,retcode=0;
         previous.Long(0,"order_ticket",order); previous.Long(0,"deal_ticket",deal); previous.Long(0,"retcode",retcode);
         result.order_ticket=(ulong)order; result.deal_ticket=(ulong)deal; result.retcode=(uint)retcode;
      }
      FullDiscoverEvidence(result);
      if(FullVerify(result) && result.retcode==0) result.retcode=TRADE_RETCODE_DONE;
      FullStoreResult(result);
      int count=ArraySize(g_full_results); ArrayResize(g_full_results,count+1); g_full_results[count]=result;
   } while(FileFindNext(find,name));
   FileFindClose(find);
}
void FullPoll()
{
   static ulong last_poll=0;
   if(last_poll && GetTickCount64()-last_poll<1000) return;
   last_poll=GetTickCount64();
   for(int i=0;i<ArraySize(g_full_results);i++)
      if(g_full_results[i].state=="UNKNOWN")
      {
         FullDiscoverEvidence(g_full_results[i]);
         if(FullVerify(g_full_results[i]))
         {
            if(g_full_results[i].retcode==0) g_full_results[i].retcode=TRADE_RETCODE_DONE;
            FullStoreResult(g_full_results[i]);
         }
      }
   for(int i=ArraySize(g_full_results)-1;i>=0;i--)
      if(g_full_results[i].state!="UNKNOWN") ArrayRemove(g_full_results,i,1);
   string name; long find=FileFindFirst(FullRoot()+"*.pending",name);
   if(find==INVALID_HANDLE) return;
   // One result per timer keeps tick transport responsive after a reconnect.
   string path="XAUPY\\execution\\"+name, text, response;
   FileFindClose(find);
   if(OnceRead(path,text) && SendRequest("bridge_execution_result",text,"bridge_execution_result_ack",response))
   {
      COnceJson ack; bool accepted=false;
      if(ack.Parse(response) && ack.Bool(ack.Find(0,"payload"),"accepted",accepted) && accepted) FileDelete(path);
   }
}

#endif
