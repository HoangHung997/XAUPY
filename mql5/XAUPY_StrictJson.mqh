#ifndef XAUPY_STRICT_JSON_MQH
#define XAUPY_STRICT_JSON_MQH

enum OnceJsonType { ONCE_OBJECT, ONCE_ARRAY, ONCE_STRING, ONCE_NUMBER, ONCE_BOOL, ONCE_NULL };
struct OnceJsonNode { int parent; OnceJsonType type; string key; string value; };

// The trading exception must never derive executable fields from substring matches.
// This bounded JSON reader rejects duplicate decoded keys, trailing input, invalid
// escapes/numbers and excessive nesting. Integer access rejects fractional/coerced values.
class COnceJson
{
private:
   string source;
   int cursor;
   bool failed;
   void Space() { while(cursor<StringLen(source) && (source[cursor]==32 || source[cursor]==9 || source[cursor]==10 || source[cursor]==13)) cursor++; }
   int Hex(ushort c) { if(c>=48 && c<=57) return c-48; if(c>=65 && c<=70) return c-55; if(c>=97 && c<=102) return c-87; return -1; }
   bool Unicode(ushort &value)
   {
      if(cursor+4>StringLen(source)) return false;
      int n=0;
      for(int i=0;i<4;i++) { int digit=Hex(source[cursor++]); if(digit<0) return false; n=n*16+digit; }
      value=(ushort)n; return true;
   }
   bool Quoted(string &value)
   {
      value="";
      if(cursor>=StringLen(source) || source[cursor++]!=34) return false;
      while(cursor<StringLen(source))
      {
         ushort c=source[cursor++];
         if(c==34) return true;
         if(c<32) return false;
         if(c!=92) { value+=ShortToString(c); continue; }
         if(cursor>=StringLen(source)) return false;
         c=source[cursor++];
         if(c==34 || c==92 || c==47) value+=ShortToString(c);
         else if(c==98) value+=ShortToString(8);
         else if(c==102) value+=ShortToString(12);
         else if(c==110) value+=ShortToString(10);
         else if(c==114) value+=ShortToString(13);
         else if(c==116) value+=ShortToString(9);
         else if(c==117)
         {
            ushort unit=0;
            if(!Unicode(unit) || unit==0) return false;
            if(unit>=0xD800 && unit<=0xDBFF)
            {
               if(cursor+2>StringLen(source) || source[cursor++]!=92 || source[cursor++]!=117) return false;
               ushort low=0;
               if(!Unicode(low) || low<0xDC00 || low>0xDFFF) return false;
               value+=ShortToString(unit)+ShortToString(low);
            }
            else { if(unit>=0xDC00 && unit<=0xDFFF) return false; value+=ShortToString(unit); }
         }
         else return false;
      }
      return false;
   }
   bool Number(string &value)
   {
      int start=cursor,n=StringLen(source);
      if(cursor<n && source[cursor]==45) cursor++;
      if(cursor>=n) return false;
      if(source[cursor]==48) cursor++;
      else { if(source[cursor]<49 || source[cursor]>57) return false; while(cursor<n && source[cursor]>=48 && source[cursor]<=57) cursor++; }
      if(cursor<n && source[cursor]==46)
      {
         cursor++; int digit=cursor;
         while(cursor<n && source[cursor]>=48 && source[cursor]<=57) cursor++;
         if(cursor==digit) return false;
      }
      if(cursor<n && (source[cursor]==101 || source[cursor]==69))
      {
         cursor++; if(cursor<n && (source[cursor]==43 || source[cursor]==45)) cursor++;
         int digit=cursor; while(cursor<n && source[cursor]>=48 && source[cursor]<=57) cursor++;
         if(cursor==digit) return false;
      }
      value=StringSubstr(source,start,cursor-start);
      return MathIsValidNumber(StringToDouble(value));
   }
   int Value(int parent,string key,int depth)
   {
      Space();
      if(depth>16 || ArraySize(nodes)>=8192 || cursor>=StringLen(source)) { failed=true; return -1; }
      int index=ArraySize(nodes); ArrayResize(nodes,index+1);
      nodes[index].parent=parent; nodes[index].key=key; nodes[index].value="";
      ushort c=source[cursor];
      if(c==123 || c==91)
      {
         bool object=(c==123); nodes[index].type=object ? ONCE_OBJECT : ONCE_ARRAY;
         ushort close=object ? 125 : 93; cursor++; Space();
         if(cursor<StringLen(source) && source[cursor]==close) { cursor++; return index; }
         while(!failed)
         {
            string child_key="";
            if(object)
            {
               Space(); if(!Quoted(child_key) || Find(index,child_key)>=0) { failed=true; break; }
               Space(); if(cursor>=StringLen(source) || source[cursor++]!=58) { failed=true; break; }
            }
            if(Value(index,child_key,depth+1)<0) break;
            Space(); if(cursor>=StringLen(source)) { failed=true; break; }
            c=source[cursor++]; if(c==close) return index;
            if(c!=44) { failed=true; break; }
         }
      }
      else if(c==34) { nodes[index].type=ONCE_STRING; if(Quoted(nodes[index].value)) return index; }
      else if(c==45 || (c>=48 && c<=57)) { nodes[index].type=ONCE_NUMBER; if(Number(nodes[index].value)) return index; }
      else
      {
         string literal="";
         if(StringSubstr(source,cursor,4)=="true") literal="true";
         else if(StringSubstr(source,cursor,5)=="false") literal="false";
         else if(StringSubstr(source,cursor,4)=="null") literal="null";
         if(literal!="") { nodes[index].type=literal=="null" ? ONCE_NULL : ONCE_BOOL; nodes[index].value=literal; cursor+=StringLen(literal); return index; }
      }
      failed=true; return -1;
   }
public:
   OnceJsonNode nodes[];
   bool Parse(string text)
   {
      source=text; cursor=0; failed=false; ArrayResize(nodes,0);
      if(StringLen(text)>1048576 || Value(-1,"",0)<0) return false;
      Space(); return !failed && cursor==StringLen(source);
   }
   int Find(int parent,string key)
   {
      for(int i=parent+1;i<ArraySize(nodes);i++) if(nodes[i].parent==parent && nodes[i].key==key) return i;
      return -1;
   }
   int Count(int parent) { int n=0; for(int i=parent+1;i<ArraySize(nodes);i++) if(nodes[i].parent==parent) n++; return n; }
   bool String(int parent,string key,string &value)
   {
      int i=Find(parent,key); if(i<0 || nodes[i].type!=ONCE_STRING) return false; value=nodes[i].value; return true;
   }
   bool Bool(int parent,string key,bool &value)
   {
      int i=Find(parent,key); if(i<0 || nodes[i].type!=ONCE_BOOL) return false; value=nodes[i].value=="true"; return true;
   }
   bool Double(int parent,string key,double &value)
   {
      int i=Find(parent,key); if(i<0 || nodes[i].type!=ONCE_NUMBER) return false;
      value=StringToDouble(nodes[i].value); return MathIsValidNumber(value);
   }
   bool Long(int parent,string key,long &value)
   {
      int i=Find(parent,key); if(i<0 || nodes[i].type!=ONCE_NUMBER) return false;
      string raw=nodes[i].value; int start=(StringLen(raw)>0 && raw[0]==45) ? 1 : 0;
      if(StringLen(raw)==start) return false;
      for(int n=start;n<StringLen(raw);n++) if(raw[n]<48 || raw[n]>57) return false;
      value=StringToInteger(raw);
      return StringFormat("%I64d",value)==raw; // includes overflow and non-canonical -0 rejection
   }
};
#endif
