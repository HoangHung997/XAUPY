"""Read-only acceptance of an OFF-mode release connected to its actual MT5 EA.

Uses hello/heartbeat/diagnostics and already-imported history only. It cannot
change a profile, account permission, mode, ledger or broker order.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from demo_once import Client

TIMEFRAMES = {'M1','M3','M5','M15','M30','H1','H2','H4','D1'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,required=True)
    parser.add_argument('--login',type=int,required=True)
    parser.add_argument('--server',required=True)
    parser.add_argument('--magic',type=int,required=True)
    parser.add_argument('--symbol',default='XAUUSD')
    parser.add_argument('--seconds',type=int,default=10)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    if not 1<=args.port<=65535 or not 1<=args.seconds<=60:
        parser.error('Invalid port/duration')
    client = Client(args.port)
    try:
        samples=[]
        for i in range(args.seconds+1):
            sample=client.request('heartbeat')
            if sample['execution']['mode']!='OFF':
                raise RuntimeError('Acceptance requires user-stopped execution')
            samples.append(sample)
            if i<args.seconds: time.sleep(1)
        diagnostics=client.request('diagnostics_get')['diagnostics']
        history=client.request('broker_history_query',{'page':0,'limit':100,'symbol':args.symbol})
    finally:
        client.close()
    last=samples[-1]; monitoring=last['monitoring']; broker=diagnostics['broker_metadata']
    indicators=diagnostics['indicator_comparison']['rows']
    expected=dict(account_login=args.login,account_server=args.server,magic=args.magic,symbol=args.symbol)
    # A disconnect/re-attach can legitimately expose a null quote. Record a
    # failed check and preserve evidence instead of crashing the acceptance.
    ticks=[s['overview'].get('tick_time_msc') or 0 for s in samples]
    history_data=history.get('history',{})
    checks={
        'expected_demo_identity':all(broker.get(k)==v for k,v in expected.items()) and broker.get('account_trade_mode')=='DEMO',
        'execution_off_without_intents':all(s['execution']['mode']=='OFF' and not s['execution']['counts'] for s in samples),
        'every_snapshot_fresh':all(s['bridge'].get('terminal_connected') and s['bridge'].get('connected') and s['bridge'].get('age_ms',99999)<5000 for s in samples),
        'snapshots_advance':last['bridge']['snapshots_total']>samples[0]['bridge']['snapshots_total'],
        'ticks_advance_without_regression':ticks[-1]>ticks[0]>0 and all(b>=a for a,b in zip(ticks,ticks[1:])),
        'tick_batches_advance':last['tick_transport']['received_ticks']>samples[0]['tick_transport']['received_ticks'],
        'nine_chart_histories':TIMEFRAMES<=last['overview'].get('bar_history',{}).keys() and all(len(last['overview']['bar_history'][tf])>50 for tf in TIMEFRAMES),
        'forming_candle_projection':TIMEFRAMES<=last['overview'].get('forming_bars',{}).keys(),
        'nine_scanner_timeframes':{r['timeframe'] for r in monitoring['scanner']}==TIMEFRAMES,
        'native_indicator_agreement':len(indicators)==45 and all(r['status']=='PASS' for r in indicators),
        'calendar_from_mt5':monitoring['calendar'].get('available') is True and monitoring['calendar'].get('source')=='MT5_CALENDAR',
        'broker_sessions_received':bool(monitoring['symbol_sessions']),
        'four_market_clocks':len(monitoring['sessions'])==4 and all(s['available'] for s in monitoring['sessions']),
        'measured_resources':monitoring['resources']['available'] and monitoring['resources']['process_rss_bytes']>0,
        'broker_ping_measured':monitoring.get('broker_ping_ms',0)>0,
        'native_logs_read':monitoring['native_logs']['available'] and len(monitoring['native_logs']['source_files'])==2,
        'broker_day_statistics':monitoring['kpi']['history_complete'] and monitoring['kpi']['profit_today'] is not None,
        'imported_history_matches_identity':history.get('ok') is True and all(history_data.get('metadata',{}).get(k)==expected[k] for k in ('account_login','account_server','magic')),
    }
    result=dict(passed=all(checks.values()),checks=checks,observed_utc=datetime.now(timezone.utc).isoformat(),
        scope='Live EA/Python data services; native Desktop controls and broker actions require separate acceptance',
        read_only=True,requests=['hello','heartbeat','diagnostics_get','broker_history_query'],
        engine_version=last['engine_version'],indicator_statuses=dict(Counter(r['status'] for r in indicators)),
        first=samples[0],last=last,diagnostics=diagnostics,broker_history=history)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(passed=result['passed'],checks=checks,output=str(args.output))))
    return 0 if result['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
