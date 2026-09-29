#ifndef XAUPY_EXECUTION_RULES_MQH
#define XAUPY_EXECUTION_RULES_MQH

// Pure predicates, shared by the EA and the compiled isolated rules test.
// No account, file, network or trading API is called from this header.
bool FullProtectionRule(bool buy,double reference,double sl,double tp,double minimum,string &reason)
{
   if(!MathIsValidNumber(reference) || !MathIsValidNumber(sl) || !MathIsValidNumber(tp) ||
      !MathIsValidNumber(minimum) || reference<=0 || sl<=0 || tp<0 || minimum<=0 ||
      (buy ? reference-sl : sl-reference)<minimum-1e-9)
      { reason="INVALID_PROTECTION"; return false; }
   if(tp>0 && (buy ? tp-reference : reference-tp)<minimum-1e-9)
      { reason="INVALID_SERVER_TP"; return false; }
   return true;
}
bool FullPendingRiskRule(bool buy,double old_price,double old_sl,double price,double sl,string &reason)
{
   if(!MathIsValidNumber(price) || !MathIsValidNumber(sl) || price<=0 || sl<=0)
      { reason="INVALID_PROTECTION"; return false; }
   double risk=buy ? price-sl : sl-price;
   if(risk<=0) { reason="INVALID_PROTECTION"; return false; }
   if(old_sl>0)
   {
      if((buy && sl<old_sl-1e-9) || (!buy && sl>old_sl+1e-9))
         { reason="NEVER_WIDEN_SL"; return false; }
      double old_risk=buy ? old_price-old_sl : old_sl-old_price;
      if(risk>old_risk+1e-9) { reason="PENDING_RISK_INCREASE"; return false; }
   }
   return true;
}
bool FullPendingDistanceRule(long type,double price,double bid,double ask,double minimum,string &reason)
{
   // ENUM_ORDER_TYPE values: BUY_LIMIT=2, SELL_LIMIT=3, BUY_STOP=4, SELL_STOP=5.
   if(type<2 || type>5) { reason="UNSUPPORTED_PENDING_TYPE"; return false; }
   double distance=type==4 ? price-ask : type==5 ? bid-price : type==2 ? ask-price : price-bid;
   if(!MathIsValidNumber(distance) || !MathIsValidNumber(minimum) || minimum<=0 || distance<minimum-1e-9)
      { reason="PENDING_PRICE_TOO_CLOSE"; return false; }
   return true;
}
bool FullCashRiskRule(double loss,double commission,double remaining,string &reason)
{
   if(!MathIsValidNumber(loss) || !MathIsValidNumber(commission) || !MathIsValidNumber(remaining) ||
      loss<0 || commission<0 || remaining<=0 || loss+commission>remaining+1e-8)
      { reason="RISK_BUDGET_EXCEEDED"; return false; }
   return true;
}
bool FullRulesSelfTest()
{
   string reason="";
   if(!FullProtectionRule(true,100,98,103,.01,reason))return false;
   if(FullProtectionRule(true,100,101,103,.01,reason))return false;
   if(!FullProtectionRule(false,100,102,97,.01,reason))return false;
   if(FullProtectionRule(false,100,102,101,.01,reason))return false;
   if(FullPendingRiskRule(true,100,98,101,98,reason))return false;
   if(!FullPendingRiskRule(true,100,98,101,99,reason))return false;
   if(FullPendingRiskRule(false,100,102,99,102,reason))return false;
   if(!FullPendingRiskRule(false,100,102,99,101,reason))return false;
   if(FullPendingDistanceRule(4,100,100,100.2,.1,reason))return false;
   if(!FullPendingDistanceRule(5,99,100,100.2,.1,reason))return false;
   if(FullCashRiskRule(95,6,100,reason))return false;
   if(!FullCashRiskRule(95,5,100,reason))return false;
   return true;
}
#endif
