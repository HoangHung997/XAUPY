#ifndef XAUPY_MARKET_SERVICES_MQH
#define XAUPY_MARKET_SERVICES_MQH

// Read-only terminal services, cached independently of the tick batch cursor.
string g_calendar_json="{\"available\":false,\"reason\":\"NOT_LOADED\",\"events\":[]}";
ulong g_calendar_read_ms=0;
int g_probe_handles[];
string g_probe_keys[];
double ProbeIndicator(ENUM_TIMEFRAMES frame,int period,string kind)
{
   string key=IntegerToString((int)frame)+":"+IntegerToString(period)+":"+kind;
   int handle=INVALID_HANDLE;
   for(int i=0;i<ArraySize(g_probe_keys);i++) if(g_probe_keys[i]==key) {handle=g_probe_handles[i];break;}
   if(handle==INVALID_HANDLE)
   {
      handle=kind=="RSI" ? iRSI(_Symbol,frame,period,PRICE_CLOSE) : kind=="STD" ? iStdDev(_Symbol,frame,period,0,MODE_SMA,PRICE_CLOSE) : iMA(_Symbol,frame,period,0,kind=="EMA"?MODE_EMA:MODE_SMA,PRICE_CLOSE);
      if(handle==INVALID_HANDLE)return EMPTY_VALUE;
      int size=ArraySize(g_probe_keys);ArrayResize(g_probe_keys,size+1);ArrayResize(g_probe_handles,size+1);
      g_probe_keys[size]=key;g_probe_handles[size]=handle;
   }
   double values[];
   if(CopyBuffer(handle,0,1,1,values)!=1 || !MathIsValidNumber(values[0]) || values[0]==EMPTY_VALUE)return EMPTY_VALUE;
   return values[0];
}
string ProbeNumber(double value) { return value==EMPTY_VALUE ? "null" : JsonNumber(value,10); }
string JsonIndicatorProbes()
{
   static ulong previous=0;static string cache="[]";
   ulong now=GetTickCount64();if(previous && now-previous<10000)return cache;previous=now;
   ENUM_TIMEFRAMES frames[9]={PERIOD_M1,PERIOD_M3,PERIOD_M5,PERIOD_M15,PERIOD_M30,PERIOD_H1,PERIOD_H2,PERIOD_H4,PERIOD_D1};
   string names[9]={"M1","M3","M5","M15","M30","H1","H2","H4","D1"};
   cache="[";
   for(int i=0;i<9;i++)
   {
      if(i)cache+=",";
      datetime bar_time=iTime(_Symbol,frames[i],1);
      double mean=ProbeIndicator(frames[i],20,"SMA"),sigma=ProbeIndicator(frames[i],20,"STD");
      double z=(mean==EMPTY_VALUE || sigma==EMPTY_VALUE) ? EMPTY_VALUE : sigma>0 ? (iClose(_Symbol,frames[i],1)-mean)/sigma : 0;
      cache+="{"+JsonKey("timeframe")+JsonString(names[i])+","+JsonKey("bar_time")+StringFormat("%I64d",(long)bar_time)+",";
      cache+=JsonKey("RSI7")+ProbeNumber(ProbeIndicator(frames[i],7,"RSI"))+","+JsonKey("RSI14")+ProbeNumber(ProbeIndicator(frames[i],14,"RSI"))+",";
      cache+=JsonKey("RSI20")+ProbeNumber(ProbeIndicator(frames[i],20,"RSI"))+","+JsonKey("EMA20")+ProbeNumber(ProbeIndicator(frames[i],20,"EMA"))+",";
      cache+=JsonKey("Z20")+ProbeNumber(z)+"}";
   }
   return cache+="]";
}
void ReleaseIndicatorProbes()
{
   for(int i=0;i<ArraySize(g_probe_handles);i++)IndicatorRelease(g_probe_handles[i]);
   ArrayResize(g_probe_handles,0);ArrayResize(g_probe_keys,0);
}

string JsonSymbolSessions()
{
   string json="["; bool first=true;
   for(int day=0;day<7;day++)
      for(uint index=0;index<100;index++)
      {
         datetime start=0,end=0;
         if(!SymbolInfoSessionTrade(_Symbol,(ENUM_DAY_OF_WEEK)day,index,start,end)) break;
         if(!first) json+=","; first=false;
         json+="{"+JsonKey("day")+IntegerToString(day)+","+JsonKey("index")+IntegerToString(index)+",";
         json+=JsonKey("from_seconds")+StringFormat("%I64d",(long)start)+","+JsonKey("to_seconds")+StringFormat("%I64d",(long)end)+"}";
      }
   return json+"]";
}
long WeekendSessionEnd()
{
   datetime now=TimeTradeServer(); MqlDateTime date; TimeToStruct(now,date);
   long today=(long)now-date.hour*3600-date.min*60-date.sec;
   long friday=today+(5-date.day_of_week)*86400,last=0;
   for(uint i=0;i<100;i++)
   {
      datetime start=0,end=0;
      if(!SymbolInfoSessionTrade(_Symbol,FRIDAY,i,start,end)) break;
      long finish=(long)end;
      if(finish<=(long)start) finish+=86400;
      last=MathMax(last,finish);
   }
   return last>0 ? friday+last : 0;
}
void RefreshCalendar()
{
   ulong now_ms=GetTickCount64();
   if(g_calendar_read_ms && now_ms-g_calendar_read_ms<60000) return;
   g_calendar_read_ms=now_ms;
   datetime now=TimeTradeServer();
   string currencies[2]; currencies[0]=SymbolInfoString(_Symbol,SYMBOL_CURRENCY_BASE); currencies[1]=SymbolInfoString(_Symbol,SYMBOL_CURRENCY_PROFIT);
   string events="[",reason=""; bool first=true,available=true;
   for(int currency=0;currency<2;currency++)
   {
      if(currencies[currency]=="" || (currency==1 && currencies[1]==currencies[0])) continue;
      if(currencies[currency]=="XAU" || currencies[currency]=="XAG" || currencies[currency]=="XPT" || currencies[currency]=="XPD" || currencies[currency]=="BTC" || currencies[currency]=="ETH") continue;
      MqlCalendarValue values[]; ResetLastError();
      int count=CalendarValueHistory(values,now-86400,now+7*86400,NULL,currencies[currency]);
      int error=GetLastError();
      if(count<0 || error!=0) { available=false; reason="MT5_CALENDAR_"+IntegerToString(error); continue; }
      for(int i=0;i<count;i++)
      {
         MqlCalendarEvent event;
         if(!CalendarEventById(values[i].event_id,event)) { available=false; reason="EVENT_METADATA_UNAVAILABLE"; continue; }
         if(!first) events+=","; first=false;
         string impact=event.importance==CALENDAR_IMPORTANCE_HIGH ? "HIGH" : event.importance==CALENDAR_IMPORTANCE_MODERATE ? "MEDIUM" : "LOW";
         events+="{"+JsonKey("id")+StringFormat("%I64u",values[i].id)+","+JsonKey("name")+JsonString(event.name)+",";
         events+=JsonKey("time")+StringFormat("%I64d",(long)values[i].time)+","+JsonKey("currency")+JsonString(currencies[currency])+",";
         events+=JsonKey("importance")+JsonString(impact)+","+JsonKey("actual")+(values[i].HasActualValue() ? JsonNumber(values[i].GetActualValue()) : "null")+",";
         events+=JsonKey("forecast")+(values[i].HasForecastValue() ? JsonNumber(values[i].GetForecastValue()) : "null")+"}";
      }
   }
   events+="]";
   g_calendar_json="{"+JsonKey("available")+JsonBool(available)+","+JsonKey("reason")+JsonString(reason)+",";
   g_calendar_json+=JsonKey("source")+JsonString("MT5_CALENDAR")+","+JsonKey("timezone")+JsonString("BROKER")+",";
   g_calendar_json+=JsonKey("as_of")+StringFormat("%I64d",(long)TimeTradeServer())+","+JsonKey("events")+events+"}";
}
#endif
